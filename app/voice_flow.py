"""Voice conversation logic: field normalisation, deterministic missing
fields, deal matching, questions and the one-line read-back.

Everything here is plain app code. The model only supplies stated facts
(strings); which fields are still missing, which deal is meant and every
euro (through ``engine.calc``) are worked out here, never by the model.

Conversations live in memory, keyed by an unguessable id and tied to the
tenant that started them.
"""
import re
import secrets
import time
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app import i18n
from engine.calc import agent_share

CONVERSATIONS = {}
MAX_QUESTIONS = 6
CONVERSATION_TTL = 2 * 60 * 60

REQUIRED = {
    "new_deal": ("name", "commission", "share", "escritura_date", "stage"),
    "cpcv_signed": ("deal", "date"),
    "escritura_date": ("deal", "date"),
    "fell_through": ("deal",),
    "commission_received": ("deal", "amount", "date"),
    "change_stage": ("deal", "stage"),
    "change_commission": ("deal", "commission"),
    "change_percentage": ("deal", "percentage"),
    "reopen": ("deal",),
}

KIND_MAP = {
    "new_deal": "new_deal",
    "create_deal": "new_deal",
    "cpcv_signed": "cpcv_signed",
    "escritura_date": "escritura_date",
    "fell_through": "fell_through",
    "commission_received": "commission_received",
    "change_stage": "change_stage",
    "change_commission": "change_commission",
    "change_percentage": "change_percentage",
    "reopen": "reopen",
}

DEAL_KINDS = tuple(k for k in REQUIRED if k != "new_deal")

STAGE_WORDS = {
    "potencial": "potencial", "potential": "potencial",
    "provavel": "provavel", "likely": "provavel", "probable": "provavel",
    "confirmado": "confirmado", "confirmed": "confirmado",
}

PT_MONTH_NAMES = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho",
                  "julho", "agosto", "setembro", "outubro", "novembro",
                  "dezembro")
EN_MONTH_NAMES = ("january", "february", "march", "april", "may", "june",
                  "july", "august", "september", "october", "november",
                  "december")

STOPWORDS = {"em", "de", "do", "da", "no", "na", "in", "the", "a", "o", "at"}


# Words that may surround a share without changing its meaning. Any other
# word (for example "minus", "negative", "menos") makes the share unusable.
SHARE_FILLER = frozenset((
    "a", "an", "o", "os", "as", "the", "of", "de", "do", "da", "is", "e", "it", "to", "at", "about",
    "around", "cerca", "uns", "share", "my", "mine", "percentage", "percent", "per", "cent", "por",
    "cento", "percentagem", "partilha", "fica", "make", "set", "i", "take", "get", "keep", "quero",
    "para", "com", "ser", "with", "be", "me", "please", "favor", "now", "agora", "commission",
    "comissao", "change", "mudar", "alterar", "sim", "yes", "eur", "euro", "euros", "rate"))


def _plain(text):
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


# ── Field normalisation ──────────────────────────────────────────

_NEGATIVE_BEFORE = re.compile(
    r"\b(?:minus|negative|negativo|negativa|menos|loss\s+of|perda\s+de)\b[\s:,]*"
    r"(?:(?:a|an|of|de|um|uma)\s+)?[0-9a-z]")
_NEGATIVE_AFTER = re.compile(
    r"[0-9a-z]\s*(?:%|per\s*cent|percent|por\s*cento)?(?:\s+(?:is|e|fica))?\s*"
    r"(?:negative|negativo|negativa|below\s+zero|abaixo\s+de\s+zero)\b")
_NEGATIVE_MARK = re.compile(r"(?:^|[\s(])[-\u2212\u2013\u2014][0-9]|[0-9]%?[-\u2212\u2013\u2014]\s*$")


def says_negative_number(text):
    """True when what the agent said or typed puts a minus on a number:
    "minus 40", "negative 40", "menos 40", "40 negativo", "-40"."""
    if text is None:
        return False
    plain = _plain(text).replace("pelo menos", " ").replace("at least", " ").replace("no minimo", " ")
    return bool(_NEGATIVE_BEFORE.search(plain) or _NEGATIVE_AFTER.search(plain)
                or _NEGATIVE_MARK.search(plain))


def parse_money(value):
    """Euros in any common spelling to integer cents, or None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            amount = Decimal(str(value))
        else:
            text = _plain(value)
            text = re.sub(r"(euros?|eur|€)", "", text)
            text = re.sub(r"\s+", "", text)
            if not re.fullmatch(r"[0-9][0-9.,]*", text):
                return None
            if "," in text and "." in text:
                if text.rfind(",") > text.rfind("."):
                    text = text.replace(".", "").replace(",", ".")
                else:
                    text = text.replace(",", "")
            elif "," in text:
                if re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+", text):
                    text = text.replace(",", "")
                else:
                    text = text.replace(",", ".")
            elif "." in text and re.fullmatch(r"[0-9]{1,3}(\.[0-9]{3})+", text):
                text = text.replace(".", "")
            amount = Decimal(text)
        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None
    return cents if cents > 0 else None


def parse_rate(value):
    """A share as an exact decimal rate string ("40 %" -> "0.4"), or None."""
    if value is None or isinstance(value, bool):
        return None
    text = _plain(value)
    match = re.search(
        r"([0-9]+(?:[.,][0-9]+)?)\s*(%|por\s*cento|per\s*cent|percent)?", text)
    if not match:
        return None
    digits, marker = match.groups()
    # Anything around the number must be plain filler. A sign, a dash of any
    # kind, brackets, a second number or a word such as "minus", "menos" or
    # "negative" means the value is not a plain share: it is refused and the
    # field is asked again, never read as positive.
    around = text[:match.start()] + " " + text[match.end():]
    if re.search(r"[^a-z\s.,:;!?'\"]", around):
        return None
    if any(word not in SHARE_FILLER for word in re.findall(r"[a-z]+", around)):
        return None
    try:
        number = Decimal(digits.replace(",", "."))
    except InvalidOperation:
        return None
    # A number marked as a percentage is always one: "1%" is 1 %, not 100 %.
    # Unmarked, 1 or more is a percentage and below 1 is already a rate.
    if marker or number >= 1:
        number = number / 100
    if number <= 0 or number > 1:
        return None
    return format(number.normalize(), "f")


def percent_text(rate):
    return format((Decimal(rate) * 100).normalize(), "f")


def parse_stage(value):
    if value is None:
        return None
    return STAGE_WORDS.get(_plain(value).strip())


def current_year_month():
    from app import web
    month = web.nl_current_month()
    return int(month[:4]), int(month[5:7])


def parse_date(value):
    """Return (iso_date, estimated) or (None, False).

    An exact date stays exact. A month alone ("em março", "2026-03")
    becomes the 15th of that month, marked as estimated; a month name
    without a year means its next occurrence.
    """
    if value is None or isinstance(value, bool):
        return None, False
    text = str(value).strip()
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None, False
        return text, False
    if re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", text):
        return text + "-15", True
    plain = _plain(text)
    year, month_now = current_year_month()
    numeric = re.fullmatch(r"([0-9]{1,2})[/.\-]([0-9]{1,2})[/.\-]([0-9]{4})", plain)
    if numeric:
        return _exact(int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1)))
    for names in (PT_MONTH_NAMES, EN_MONTH_NAMES):
        for index, name in enumerate(names):
            if not re.search(r"\b%s\b" % name, plain):
                continue
            explicit = re.search(r"\b(20[0-9]{2})\b", plain)
            rest = re.sub(r"\b20[0-9]{2}\b", " ", plain)
            day = (re.search(r"\b([0-9]{1,2})(?:st|nd|rd|th|o|\u00ba)?\s*(?:de\s+|of\s+)?%s\b" % name, rest)
                   or re.search(r"\b%s\s+(?:the\s+)?([0-9]{1,2})(?:st|nd|rd|th)?\b" % name, rest))
            if day:
                # An exact day stays exact. Without a year it is the next occurrence.
                if explicit:
                    use_year = int(explicit.group(1))
                else:
                    use_year = year + (1 if index + 1 < month_now else 0)
                return _exact(use_year, index + 1, int(day.group(1)))
            if explicit:
                use_year = int(explicit.group(1))
            else:
                use_year = year + (1 if index + 1 < month_now else 0)
            return "%04d-%02d-15" % (use_year, index + 1), True
    return None, False


def _exact(year, month, day):
    try:
        datetime(year, month, day)
    except ValueError:
        return None, False
    return "%04d-%02d-%02d" % (year, month, day), False


def _clean_text(value):
    text = str(value).strip()
    return text[:200] if text else None


def merge_extraction(conv, extracted, said=None):
    """Fold one extraction into the conversation, normalised.

    Only stated facts replace what is there; an unusable value is
    ignored so the field simply stays missing. ``said`` is what the agent
    actually said or typed: when it puts a minus on a number, a share given
    in this turn is refused whatever the extraction returned, and asked again.
    """
    ex = conv["extracted"]
    kind = conv.get("kind")
    for key in ("name", "deal", "agency"):
        if extracted.get(key) not in (None, ""):
            cleaned = _clean_text(extracted[key])
            if cleaned:
                ex[key] = cleaned
    cents_given = extracted.get("agency_commission_cents")
    if (isinstance(cents_given, int) and not isinstance(cents_given, bool)
            and cents_given > 0 and extracted.get("commission") in (None, "")):
        ex["commission"] = cents_given
    for key in ("commission", "amount"):
        cents = parse_money(extracted.get(key))
        if cents is not None:
            ex[key] = cents
    for key, raw in (("share", extracted.get("share", extracted.get("share_rate"))),
                     ("percentage", extracted.get("percentage"))):
        rate = parse_rate(raw)
        if rate is not None and says_negative_number(said):
            rate = None  # "minus 40" said and 40 extracted is still a negative share
        if rate is not None:
            ex[key] = rate
        elif raw not in (None, ""):
            ex.pop(key, None)  # a stated but unusable share is asked again, never kept
    stage = parse_stage(extracted.get("stage"))
    if stage:
        ex["stage"] = stage
    flagged = bool(extracted.get("escritura_estimada"))
    for key in ("escritura_date", "date", "cpcv_date"):
        if extracted.get(key) in (None, ""):
            continue
        iso, estimated = parse_date(extracted[key])
        if iso is None:
            continue
        if estimated and key in ("date", "cpcv_date") and kind != "escritura_date":
            continue  # a CPCV or a receipt needs the exact day
        ex[key] = iso
        if key == "escritura_date" or (key == "date" and kind == "escritura_date"):
            ex["escritura_estimada"] = 1 if (estimated or flagged) else 0
    apply_aliases(conv)


def apply_aliases(conv):
    """Fill a required field from the field the model may have used."""
    ex = conv["extracted"]
    kind = conv.get("kind")
    aliases = {
        "escritura_date": (("date", "escritura_date"),),
        "cpcv_signed": (("date", "cpcv_date"),),
        "commission_received": (("amount", "commission"),),
        "change_commission": (("commission", "amount"),),
        "change_percentage": (("percentage", "share"),),
    }
    for target, source in aliases.get(kind, ()):
        if ex.get(target) is None and ex.get(source) is not None:
            ex[target] = ex[source]
    if kind in DEAL_KINDS and ex.get("deal") is None and ex.get("name"):
        ex["deal"] = ex["name"]
    if kind == "new_deal" and ex.get("name") is None and ex.get("deal"):
        ex["name"] = ex["deal"]


def fill_bare_number(conv, text, asked):
    """A bare number answers the one numeric field that was asked for.

    ``asked`` is what was missing before this turn. "40 %" is a share,
    "10 000 €" an amount; a number with no sign answers only when
    exactly one numeric field was asked, and only if the model's own
    extraction left that field empty.
    """
    kind = conv.get("kind")
    ex = conv["extracted"]
    stripped = text.strip()
    if not re.fullmatch(r"[0-9][0-9.,\s\u00a0]*\s*(%|€|euros?)?", stripped, re.IGNORECASE):
        return
    numeric = [f for f in asked if f in ("commission", "amount", "share", "percentage")]
    if stripped.endswith("%"):
        candidates = [f for f in numeric if f in ("share", "percentage")]
    elif re.search(r"€|euro", stripped, re.IGNORECASE):
        candidates = [f for f in numeric if f in ("commission", "amount")]
    else:
        candidates = numeric
    if len(candidates) != 1 or candidates[0] not in missing_for(kind, ex):
        return
    field = candidates[0]
    if field in ("share", "percentage"):
        value = parse_rate(stripped)
    else:
        value = parse_money(stripped)
    if value is not None:
        ex[field] = value
    apply_aliases(conv)


def missing_for(kind, extracted):
    """Required fields still missing for this kind of update. App code only."""
    missing = []
    for field in REQUIRED.get(kind, ()):
        value = extracted.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


# ── Spoken words ─────────────────────────────────────────────────

def _word(text):
    return re.sub(r"[\s.!]+$", "", text.strip().lower())


def is_cancel(text):
    return _word(text) in ("cancelar", "cancel")


def is_yes(text):
    return _word(text) in ("sim", "yes", "s", "y")


def is_no(text):
    return _word(text) in ("não", "nao", "no")


def is_short_answer(text):
    """A bare yes/no, number or percentage keeps the conversation's language."""
    stripped = text.strip()
    if is_yes(stripped) or is_no(stripped):
        return True
    return not re.search(r"[A-Za-zÀ-ÿ]", stripped)


def lang_from_model(code, fallback):
    if code == "pt":
        return "pt-PT"
    if code == "en":
        return "en-GB"
    return fallback


# ── Conversations ────────────────────────────────────────────────

def purge_old(now=None):
    now = now or time.time()
    for cid in [c for c, v in CONVERSATIONS.items() if now - v["created"] > CONVERSATION_TTL]:
        CONVERSATIONS.pop(cid, None)


def start_conversation(session_id, tenant_id, lang="pt-PT"):
    purge_old()
    cid = secrets.token_urlsafe(16)
    conv = {
        "id": cid,
        "tenant_id": tenant_id,
        "session_id": session_id,
        "lang": lang,
        "state": "collecting",
        "kind": None,
        "extracted": {},
        "deal_id": None,
        "transcript": [],
        "questions_asked": 0,
        "readback": "",
        "share_cents": None,
        "created": time.time(),
    }
    CONVERSATIONS[cid] = conv
    return conv


def get_conversation(cid, tenant_id=None):
    conv = CONVERSATIONS.get(cid) if cid else None
    if conv is not None and tenant_id is not None and conv["tenant_id"] != tenant_id:
        return None
    return conv


def drop_conversation(cid):
    CONVERSATIONS.pop(cid, None)


# ── Deal matching ────────────────────────────────────────────────

def _tokens(text):
    return [t for t in re.findall(r"[a-z0-9]+", _plain(text)) if t not in STOPWORDS]


def match_deals(query, deals):
    """The agent's own deals that the spoken name can mean."""
    wanted = _plain(query).strip()
    exact = [d for d in deals if _plain(d["name"]).strip() == wanted]
    if len(exact) == 1:
        return exact
    q_tokens = set(_tokens(query))
    found = []
    for deal in deals:
        d_tokens = set(_tokens(deal["name"]))
        if q_tokens and d_tokens and (q_tokens <= d_tokens or d_tokens <= q_tokens):
            found.append(deal)
    return found


# ── Formatting ───────────────────────────────────────────────────

def format_euros(cents, lang):
    whole, rest = divmod(abs(cents), 100)
    sign = "-" if cents < 0 else ""
    if lang == "pt-PT":
        grouped = "{:,}".format(whole).replace(",", "\u00a0")
        body = grouped if rest == 0 else "%s,%02d" % (grouped, rest)
        return "%s%s €" % (sign, body)
    grouped = "{:,}".format(whole)
    body = grouped if rest == 0 else "%s.%02d" % (grouped, rest)
    return "%s€%s" % (sign, body)


def format_share(rate, lang):
    text = percent_text(rate)
    if lang == "pt-PT":
        return text.replace(".", ",") + " %"
    return text + "%"


def format_date(iso, estimated, lang):
    """Read-back date: "15 dez", or "meados de março (estimada)"."""
    try:
        year, month, day = (int(p) for p in iso.split("-"))
    except ValueError:
        return iso
    this_year = current_year_month()[0]
    if estimated:
        text = i18n.text(lang, "date_mid") % i18n.text(lang, "month_%d" % month)
        if year != this_year:
            text += " %d" % year
        return text + " " + i18n.text(lang, "voice_estimada")
    short = i18n.text(lang, "mon_%d" % month)
    text = "%d %s" % (day, short) if lang == "pt-PT" else "%s %d" % (short, day)
    if year != this_year:
        text += " %d" % year
    return text


def question_for_missing(missing, lang):
    """One short question for every missing field."""
    if list(missing) == ["escritura_date"]:
        return i18n.text(lang, "vq_escritura_only")
    parts = [i18n.text(lang, "vf_" + field) for field in missing]
    return i18n.text(lang, "vq_one") % i18n.text(lang, "vq_and").join(parts)


def understood_line(conv, lang):
    """What was understood so far, for the screen when a conversation stops."""
    ex = conv["extracted"]
    bits = []
    for key in ("name", "deal"):
        if ex.get(key):
            bits.append(ex[key])
            break
    for key in ("commission", "amount"):
        if ex.get(key):
            bits.append(format_euros(ex[key], lang))
            break
    for key in ("share", "percentage"):
        if ex.get(key):
            bits.append(format_share(ex[key], lang))
            break
    for key in ("escritura_date", "date"):
        if ex.get(key):
            bits.append(format_date(ex[key], ex.get("escritura_estimada"), lang))
            break
    if ex.get("stage"):
        bits.append(i18n.text(lang, "st_" + ex["stage"]))
    return ", ".join(bits)


# ── Resolution: one question or one read-back ────────────────────

class Outcome:
    """What the conversation does next: ask, confirm or stop."""

    def __init__(self, action, text="", mine_cents=None):
        self.action = action
        self.text = text
        self.mine_cents = mine_cents


def resolve(conv, deals, fallen, lang):
    """Decide the next step from the conversation's fields."""
    kind = conv["kind"]
    ex = conv["extracted"]
    missing = missing_for(kind, ex)
    pool = fallen if kind == "reopen" else deals
    if kind in DEAL_KINDS and "deal" not in missing:
        found = match_deals(ex["deal"], pool)
        if len(found) == 1:
            conv["deal_id"] = found[0]["id"]
            ex["deal"] = found[0]["name"]
        else:
            spoken = ex.pop("deal")
            conv["deal_id"] = None
            if not pool:
                return Outcome("stop", i18n.text(lang, "voice_no_deals"))
            names = ", ".join(d["name"] for d in (found or pool)[:5])
            question = i18n.text(lang, "voice_which_deal") % names
            if not found:
                question = i18n.text(lang, "voice_not_found") % spoken + " " + question
            return Outcome("ask", question)
    if missing:
        return Outcome("ask", question_for_missing(missing, lang))
    deal = None
    if kind in DEAL_KINDS:
        deal = next((d for d in pool if d["id"] == conv["deal_id"]), None)
    line, mine = readback(conv, deal, lang)
    return Outcome("confirm", line, mine)


def readback(conv, deal, lang):
    """The one-line read-back and the agent's share in cents (engine.calc)."""
    kind = conv["kind"]
    ex = conv["extracted"]
    mine = None
    values = {}
    if kind == "new_deal":
        mine = agent_share(ex["commission"], ex["share"])
        values = {
            "name": ex["name"],
            "commission": format_euros(ex["commission"], lang),
            "share": format_share(ex["share"], lang),
            "mine": format_euros(mine, lang),
            "date": format_date(ex["escritura_date"], ex.get("escritura_estimada"), lang),
        }
    else:
        values["deal"] = ex["deal"]
        if kind == "cpcv_signed":
            values["date"] = format_date(ex["date"], False, lang)
        elif kind == "escritura_date":
            values["date"] = format_date(ex["date"], ex.get("escritura_estimada"), lang)
        elif kind == "commission_received":
            values["amount"] = format_euros(ex["amount"], lang)
            values["date"] = format_date(ex["date"], False, lang)
        elif kind == "change_stage":
            values["stage"] = i18n.text(lang, "st_" + ex["stage"])
        elif kind == "change_commission":
            mine = agent_share(ex["commission"], deal["share_rate_used"]) if deal else 0
            values["commission"] = format_euros(ex["commission"], lang)
            values["mine"] = format_euros(mine, lang)
        elif kind == "change_percentage":
            mine = agent_share(deal["agency_commission_cents"], ex["percentage"]) if deal else 0
            values["share"] = format_share(ex["percentage"], lang)
            values["mine"] = format_euros(mine, lang)
    line = i18n.text(lang, "rb_" + kind) % values
    return line + " " + i18n.text(lang, "voice_confirm_q"), mine
