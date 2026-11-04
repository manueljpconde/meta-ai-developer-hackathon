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
    "expense": ("description", "amount"),
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
    "expense": "expense",
}

DEAL_KINDS = tuple(k for k in REQUIRED if k not in ("new_deal", "expense"))

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


_EXACT_WORD = re.compile(r"\b(?:exact|exactly|exata|exato|exatamente)\b")
_NOT_EXACT = re.compile(r"\b(?:not|nao|nunca|never)\s+(?:\w+\s+)?(?:exact|exactly|exata|exato|exatamente)\b"
                        r"|\b(?:inexact|inexata|inexato)\b")


def _truthy(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "sim", "y", "s")
    return bool(value)


def says_exact_date(text, iso):
    """True when the agent's own words make this date exact: the word
    "exact" / "exata", or a full day, month and year equal to the date."""
    if not text:
        return False
    plain = _plain(text).replace("'", "")
    if _EXACT_WORD.search(plain) and not _NOT_EXACT.search(plain):
        return True
    for match in re.finditer(r"\b([0-9]{1,2})[/.\-]([0-9]{1,2})[/.\-]([0-9]{4})\b", plain):
        if _exact(int(match.group(3)), int(match.group(2)), int(match.group(1)))[0] == iso:
            return True
    for names in (PT_MONTH_NAMES, EN_MONTH_NAMES):
        for index, name in enumerate(names):
            patterns = (
                r"\b([0-9]{1,2})(?:st|nd|rd|th|o|\u00ba)?\s*(?:de\s+|of\s+)?%s\s*(?:de\s+|,\s*)?(20[0-9]{2})\b" % name,
                r"\b%s\s+(?:the\s+)?([0-9]{1,2})(?:st|nd|rd|th)?\s*,?\s*(?:de\s+)?(20[0-9]{2})\b" % name,
            )
            for pattern in patterns:
                for found in re.finditer(pattern, plain):
                    if _exact(int(found.group(2)), index + 1, int(found.group(1)))[0] == iso:
                        return True
    return False


# The words that say which field a correction is about.
CORRECTION_WORDS = (
    (r"\b(?:share|percent|percentage|percentagem|cento|parte)\b|%", ("share", "percentage")),
    (r"\b(?:commission|comissao)\b", ("commission",)),
    (r"\b(?:amount|valor|quantia)\b", ("amount",)),
    (r"\b(?:euro|euros|eur)\b|\u20ac", ("commission", "amount")),
    (r"\b(?:date|data|escritura|cpcv)\b|\b(?:%s)\b" % "|".join(PT_MONTH_NAMES + EN_MONTH_NAMES),
     ("escritura_date", "date")),
    (r"\b(?:stage|estado|fase|potencial|potential|provavel|likely|probable|confirmado|confirmed)\b", ("stage",)),
)


def fields_named(text, kind):
    """The required fields of this kind that the words of a correction name."""
    plain = _plain(text or "")
    named = []
    for pattern, keys in CORRECTION_WORDS:
        if re.search(pattern, plain):
            named.extend(key for key in keys if key in REQUIRED.get(kind, ()) and key not in named)
    return named


def forget_fields(ex, fields):
    """Drop fields the agent corrected without giving a usable value, so
    the old value is never read back and the field is asked again."""
    for field in fields:
        ex.pop(field, None)
        if field in ("escritura_date", "date"):
            ex.pop("escritura_estimada", None)


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
    if kind == "new_deal":
        # Answers to a new deal's questions can come back under an update's field names.
        extracted = dict(extracted)
        for source, target in (("percentage", "share"), ("date", "escritura_date")):
            if extracted.get(target) in (None, "") and extracted.get(source) not in (None, ""):
                extracted[target] = extracted.pop(source)
    supplied = set()
    flagged = _truthy(extracted.get("escritura_estimada"))
    for key in ("name", "deal", "agency", "description"):
        if extracted.get(key) not in (None, ""):
            cleaned = _clean_text(extracted[key])
            if cleaned:
                ex[key] = cleaned
                supplied.add(key)
    cents_given = extracted.get("agency_commission_cents")
    if (isinstance(cents_given, int) and not isinstance(cents_given, bool)
            and cents_given > 0 and extracted.get("commission") in (None, "")):
        ex["commission"] = cents_given
        supplied.add("commission")
    for key in ("commission", "amount"):
        cents = parse_money(extracted.get(key))
        if cents is not None:
            ex[key] = cents
            supplied.add(key)
    for key, raw in (("share", extracted.get("share", extracted.get("share_rate"))),
                     ("percentage", extracted.get("percentage"))):
        rate = parse_rate(raw)
        if rate is not None and says_negative_number(said):
            rate = None  # "minus 40" said and 40 extracted is still a negative share
        if rate is not None:
            ex[key] = rate
            supplied.add(key)
        elif raw not in (None, ""):
            ex.pop(key, None)  # a stated but unusable share is asked again, never kept
    if kind == "expense":
        if ex.get("description"):
            ex["description"] = ex["description"][0].upper() + ex["description"][1:]
        day = extracted.get("day")
        if isinstance(day, int) and not isinstance(day, bool) and extracted.get("date") in (None, ""):
            iso = "%s-%02d" % (today_iso()[:7], day)
            if parse_date(iso)[0] == iso:
                ex["date"] = iso
                supplied.add("date")
    if extracted.get("status") in ("paid", "planned"):
        ex["status"] = extracted["status"]
        supplied.add("status")
    stage = parse_stage(extracted.get("stage"))
    if stage:
        ex["stage"] = stage
        supplied.add("stage")
    for key in ("escritura_date", "date", "cpcv_date"):
        if extracted.get(key) in (None, ""):
            continue
        iso, estimated = parse_date(extracted[key])
        if iso is None:
            continue
        if estimated and key in ("date", "cpcv_date") and kind != "escritura_date":
            continue  # a CPCV or a receipt needs the exact day
        ex[key] = iso
        supplied.add(key)
        if key == "escritura_date" or (key == "date" and kind == "escritura_date"):
            # What the agent says beats extraction's flag: a date said as exact
            # or in full (day, month and year) is exact. Only a month alone is
            # estimated.
            keep_flag = flagged and not (not estimated and says_exact_date(said, iso))
            ex["escritura_estimada"] = 1 if (estimated or keep_flag) else 0
    apply_aliases(conv)
    return supplied


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
    return re.sub(r"[\s.,!?;:]+$", "", text.strip().lower())


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
    if kind == "expense":
        return _resolve_expense(conv, deals, missing, lang)
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


def today_iso():
    from app import web
    return web.nl_today()


def _resolve_expense(conv, deals, missing, lang):
    """An expense: its deal is optional, its date defaults to today, paid unless said planned."""
    ex = conv["extracted"]
    if ex.get("deal"):
        found = match_deals(ex["deal"], deals)
        if len(found) == 1:
            conv["deal_id"] = found[0]["id"]
            ex["deal"] = found[0]["name"]
        else:
            spoken = ex.pop("deal")
            conv["deal_id"] = None
            if deals:
                question = i18n.text(lang, "voice_which_deal") % ", ".join(d["name"] for d in (found or deals)[:5])
                if not found:
                    question = i18n.text(lang, "voice_not_found") % spoken + " " + question
                return Outcome("ask", question)
    if missing:
        return Outcome("ask", question_for_missing(missing, lang))
    ex.setdefault("date", today_iso())
    ex.setdefault("status", "paid")
    when = i18n.text(lang, "voice_today") if ex["date"] == today_iso() else format_date(ex["date"], False, lang)
    line = "%s, %s, %s" % (ex["description"], format_euros(ex["amount"], lang), when)
    if conv.get("deal_id"):
        line += ", " + i18n.text(lang, "voice_expense_deal") % ex["deal"]
    if ex["status"] == "planned":
        line += ", " + i18n.text(lang, "voice_expense_planned")
    return Outcome("confirm", line + ". " + i18n.text(lang, "voice_confirm_q"))


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
