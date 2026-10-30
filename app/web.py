"""WSGI application for the first Agentimo screens.

Standard library only. Every figure comes from ``engine.calc``; the
only work here is parsing input text. All HTML output is escaped,
every POST carries a CSRF token tied to a session cookie, SQL uses
parameters only, and responses carry the security headers.
"""

import html
import os
import re
import secrets
from decimal import Decimal
from urllib.parse import parse_qsl, quote, unquote

from app import i18n, store
from engine.calc import agent_share, calc_month
from engine.model_client import MetaMoveClient, ModelError
from engine.move import move_payment
from engine.nl_move import plan_nl_move

DB_PATH = os.environ.get("APP_DB_PATH", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "agentimo.db"))

STAGES = ("potencial", "provavel", "confirmado")

MAX_TEXT_CHARS = 200

SESSIONS = {}

PT_MONTHS = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
EN_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def esc(value):
    return html.escape(str(value), quote=True)


MAX_BODY_BYTES = 65536


class BodyTooLarge(Exception):
    """A request body over the limit, refused before being read."""


class BadBodyEncoding(Exception):
    """A request body that is not valid UTF-8."""


def parse_amount(text, locale):
    """Parse an amount to integer cents, by the form's locale.

    Digits plus, optionally, the locale's decimal separator with at
    most two decimals. Anything else (spaces inside, thousands
    separators, symbols, the other locale's separator) is refused.
    """
    cleaned = text.strip()
    if locale == "pt-PT":
        if not re.fullmatch(r"[0-9]+(,[0-9]{1,2})?", cleaned):
            raise ValueError("invalid amount")
        number = Decimal(cleaned.replace(",", "."))
    else:
        if not re.fullmatch(r"[0-9]+(\.[0-9]{1,2})?", cleaned):
            raise ValueError("invalid amount")
        number = Decimal(cleaned)
    return int(number * 100)


def parse_percent(text, locale):
    """Parse a percentage to an exact Decimal, by the form's locale."""
    cleaned = text.strip()
    if locale == "pt-PT":
        if not re.fullmatch(r"[0-9]+(,[0-9]{1,2})?", cleaned):
            raise ValueError("invalid percentage")
        return Decimal(cleaned.replace(",", "."))
    if not re.fullmatch(r"[0-9]+(\.[0-9]{1,2})?", cleaned):
        raise ValueError("invalid percentage")
    return Decimal(cleaned)


def rate_string(percent):
    """Store a percentage as an exact decimal rate string."""
    return str(percent / 100)


def group_integer(value, lang):
    grouped = "%d" % value
    if lang == "pt-PT":
        return "{:,}".format(value).replace(",", " ")
    return "{:,}".format(value)


def format_amount(cents, lang):
    sign = "-" if cents < 0 else ""
    whole, rest = divmod(abs(cents), 100)
    if lang == "pt-PT":
        return "%s%s,%02d €" % (sign, group_integer(whole, lang), rest)
    return "%s€%s.%02d" % (sign, group_integer(whole, lang), rest)


def format_edit_amount(cents, lang):
    whole, rest = divmod(cents, 100)
    if rest == 0:
        return str(whole)
    text = "%d.%02d" % (whole, rest)
    if lang == "pt-PT":
        return text.replace(".", ",")
    return text


def format_edit_percent(rate, lang):
    percent = Decimal(rate) * 100
    text = format(percent.normalize(), "f")
    if lang == "pt-PT":
        return text.replace(".", ",")
    return text


def format_month(year_month, lang):
    year, month = year_month.split("-")
    index = int(month) - 1
    if lang == "pt-PT":
        return "%s de %s" % (PT_MONTHS[index], year)
    return "%s %s" % (EN_MONTHS[index], year)


NL_SENTENCE_MAX_CHARS = 500

NL_CURRENT_MONTH_ENV = "APP_NL_CURRENT_MONTH"


def nl_client():
    """Build the live interpretation client for one request."""
    return MetaMoveClient()


def nl_current_month():
    """Current month for NL move scenarios, from the environment."""
    return os.environ.get(NL_CURRENT_MONTH_ENV, MOVE_EXAMPLE_CURRENT)


def valid_month(text):
    return bool(re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", text or ""))


def month_figures(deals, expenses_cents):
    """The four amounts for already-rounded parts, via engine.calc."""
    parts = [
        {
            "part_base": deal["part_base"],
            "iva_rate": deal["iva_rate"],
            "retencao_rate": deal["retencao_rate"],
            "irs_rate": deal["irs_rate"],
            "ss_rate": deal["ss_rate"],
        }
        for deal in deals
    ]
    return calc_month(parts, expenses=expenses_cents)


def single_figures(part_base, settings, expenses_cents):
    return month_figures(
        [
            {
                "part_base": part_base,
                "iva_rate": settings["iva_rate"],
                "retencao_rate": settings["retencao_rate"],
                "irs_rate": settings["irs_rate"],
                "ss_rate": settings["ss_rate"],
            }
        ],
        expenses_cents,
    )


def read_form(environ):
    """Read form fields, refusing oversized or non-UTF-8 bodies.

    A body over ``MAX_BODY_BYTES`` raises ``BodyTooLarge`` before
    anything is read; a body that is not valid UTF-8 raises
    ``BadBodyEncoding``. Values are kept exactly as submitted.
    """
    try:
        length = int(str(environ.get("CONTENT_LENGTH", "0") or 0).strip())
    except (TypeError, ValueError):
        length = 0
    if length < 0:
        length = 0
    if length > MAX_BODY_BYTES:
        raise BodyTooLarge()
    raw = environ.get("wsgi.input").read(length) if length > 0 else b""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise BadBodyEncoding()
    fields = {}
    for key, value in parse_qsl(text, keep_blank_values=True):
        if key not in fields:
            fields[key] = value
    return fields


def read_query(environ):
    fields = {}
    for key, value in parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True):
        if key not in fields:
            fields[key] = value
    return fields


def parse_cookies(environ):
    jar = {}
    header = environ.get("HTTP_COOKIE", "")
    for chunk in header.split(";"):
        if "=" in chunk:
            name, value = chunk.split("=", 1)
            jar[name.strip()] = value.strip()
    return jar


def session_for(environ):
    jar = parse_cookies(environ)
    token = jar.get("session", "")
    if token in SESSIONS:
        return SESSIONS[token], []
    token = secrets.token_urlsafe(16)
    csrf = secrets.token_urlsafe(32)
    record = {"id": token, "csrf": csrf}
    SESSIONS[token] = record
    cookie = "session=%s; HttpOnly; Path=/; SameSite=Strict" % token
    return record, [cookie]


def language_for(environ):
    jar = parse_cookies(environ)
    saved = jar.get("lang", "")
    if saved in i18n.SUPPORTED:
        return saved
    return i18n.detect_language(environ.get("HTTP_ACCEPT_LANGUAGE", ""))


def lang_form(lang, csrf):
    options = []
    for code, label in (("pt-PT", "Português"), ("en-GB", "English")):
        selected = ' selected' if code == lang else ''
        options.append(
            '<option value="%s"%s>%s</option>' % (code, selected, label)
        )
    return (
        '<form method="post" action="/language" class="lang">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '<label for="lang" data-i18n="lang_label">%s</label>'
        '<select id="lang" name="lang">%s</select>'
        '<button type="submit" data-i18n="lang_change">%s</button>'
        "</form>"
        % (esc(csrf), esc(i18n.text(lang, "lang_label")),
           "".join(options), esc(i18n.text(lang, "lang_change")))
    )


def page(lang, csrf, title, body):
    return (
        "<!DOCTYPE html>"
        '<html lang="%s"><head><meta charset="utf-8">'
        "<title>%s</title>"
        '<link rel="stylesheet" href="/static/style.css">'
        "</head><body>"
        "<header><nav>"
        '<a href="/" data-i18n="nav_home">%s</a> '
        '<a href="/deals/new" data-i18n="nav_new">%s</a> '
        '<a href="/settings" data-i18n="nav_settings">%s</a>'
        "</nav>%s</header><main>%s</main></body></html>"
        % (
            esc(lang), esc(title),
            esc(i18n.text(lang, "nav_home")),
            esc(i18n.text(lang, "nav_new")),
            esc(i18n.text(lang, "nav_settings")),
            lang_form(lang, csrf), body,
        )
    )


def error_span(message):
    if not message:
        return ""
    return '<span class="error">%s</span>' % esc(message)


def hidden_value(value):
    """Encode a value for a hidden input, keeping the round-trip exact.

    Percent-encoding keeps markup out of the review page source while
    decoding on confirm gives back exactly the submitted text.
    """
    return quote(str(value), safe="")


def settings_form(lang, csrf, values, errors):
    def field(name, key):
        return (
            '<div><label for="set-%s" data-i18n="%s">%s</label>'
            '<input id="set-%s" name="%s" value="%s">%s</div>'
            % (name, key, esc(i18n.text(lang, key)),
               name, name, esc(values.get(name, "")),
               error_span(errors.get(name, "")))
        )
    return (
        '<h1 data-i18n="set_title">%s</h1>'
        '<form method="post" action="/settings">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '<input type="hidden" name="form_locale" value="%s">'
        "%s%s%s%s%s%s"
        '<button type="submit" data-i18n="set_save">%s</button>'
        "</form>"
        % (
            esc(i18n.text(lang, "set_title")), esc(csrf), esc(lang),
            field("share", "set_share"), field("iva", "set_iva"),
            field("retencao", "set_retencao"), field("irs", "set_irs"),
            field("ss", "set_ss"), field("expenses", "set_expenses"),
            esc(i18n.text(lang, "set_save")),
        )
    )


def deal_form(lang, csrf, values, errors, settings):
    share_default = values.get("share", "")
    if not share_default and settings is not None:
        share_default = format_edit_percent(settings["share_rate"], lang)
    stages = []
    for code in STAGES:
        checked = ' checked' if values.get("stage", "") == code else ''
        stages.append(
            '<label><input type="radio" name="stage" value="%s"%s>%s</label>'
            % (code, checked, esc(i18n.text(lang, "st_" + code)))
        )
    return (
        '<h1 data-i18n="deal_title">%s</h1>'
        '<form method="post" action="/deals/review">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '<input type="hidden" name="form_locale" value="%s">'
        '<div><label for="deal-name" data-i18n="f_name">%s</label>'
        '<input id="deal-name" name="name" value="%s">%s</div>'
        '<div><label for="deal-commission" data-i18n="f_commission">%s</label>'
        '<input id="deal-commission" name="commission" value="%s">%s</div>'
        '<div><label for="deal-share" data-i18n="f_share">%s</label>'
        '<input id="deal-share" name="share" value="%s">%s</div>'
        '<div><label for="deal-month" data-i18n="f_month">%s</label>'
        '<input id="deal-month" type="month" name="month" value="%s">%s</div>'
        '<fieldset><legend data-i18n="f_stage">%s</legend>%s%s</fieldset>'
        '<div><label for="deal-agency" data-i18n="f_agency">%s</label>'
        '<input id="deal-agency" name="agency" value="%s">%s</div>'
        '<button type="submit" data-i18n="btn_review">%s</button>'
        "</form>"
        % (
            esc(i18n.text(lang, "deal_title")), esc(csrf), esc(lang),
            esc(i18n.text(lang, "f_name")), esc(values.get("name", "")),
            error_span(errors.get("name", "")),
            esc(i18n.text(lang, "f_commission")),
            esc(values.get("commission", "")),
            error_span(errors.get("commission", "")),
            esc(i18n.text(lang, "f_share")), esc(share_default),
            error_span(errors.get("share", "")),
            esc(i18n.text(lang, "f_month")), esc(values.get("month", "")),
            error_span(errors.get("month", "")),
            esc(i18n.text(lang, "f_stage")), "".join(stages),
            error_span(errors.get("stage", "")),
            esc(i18n.text(lang, "f_agency")), esc(values.get("agency", "")),
            error_span(errors.get("agency", "")),
            esc(i18n.text(lang, "btn_review")),
        )
    )


def figures_list(lang, share_cents, result):
    breakdown = result["protected_breakdown"]
    return (
        "<dl>"
        '<dt data-i18n="m_share">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_commission">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_bank">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_protected">%s</dt><dd>%s</dd>'
        "<dd>%s %s; %s %s; %s %s</dd>"
        '<dt data-i18n="m_really">%s</dt><dd>%s</dd>'
        "</dl>"
        % (
            esc(i18n.text(lang, "m_share")),
            esc(format_amount(share_cents, lang)),
            esc(i18n.text(lang, "m_commission")),
            esc(format_amount(result["commission"], lang)),
            esc(i18n.text(lang, "m_bank")),
            esc(format_amount(result["bank_inflow"], lang)),
            esc(i18n.text(lang, "m_protected")),
            esc(format_amount(result["protected_money"], lang)),
            esc(i18n.text(lang, "b_iva")),
            esc(format_amount(breakdown["iva"], lang)),
            esc(i18n.text(lang, "b_irs")),
            esc(format_amount(breakdown["irs_reserve"], lang)),
            esc(i18n.text(lang, "b_ss")),
            esc(format_amount(breakdown["ss_reserve"], lang)),
            esc(i18n.text(lang, "m_really")),
            esc(format_amount(result["really_available"], lang)),
        )
    )


def review_page(lang, csrf, fields, share_cents, result, stale, key):
    notice = ""
    if stale:
        notice = '<p class="notice" role="alert">%s</p>' % esc(
            i18n.text(lang, "stale_msg"))
    hidden = "".join(
        '<input type="hidden" name="%s" value="%s">'
        % (name, hidden_value(fields.get(name, "")))
        for name in ("name", "commission", "share", "month", "stage",
                     "agency", "form_locale")
    )
    shown = "".join(
        '<input type="hidden" name="shown_%s" value="%d">'
        % (name, value)
        for name, value in (
            ("share", share_cents),
            ("bank", result["bank_inflow"]),
            ("protected", result["protected_money"]),
            ("really", result["really_available"]),
        )
    )
    return (
        '<h1 data-i18n="rev_title">%s</h1>%s'
        "<p>%s · %s · %s</p>"
        "%s"
        '<form method="post" action="/deals/confirm">'
        '<input type="hidden" name="csrf_token" value="%s">'
        "%s%s"
        '<input type="hidden" name="idempotency_key" value="%s">'
        '<button type="submit" data-i18n="btn_confirm">%s</button>'
        "</form>"
        % (
            esc(i18n.text(lang, "rev_title")), notice,
            esc(fields.get("name", "")),
            esc(format_month(fields.get("month", "2026-01"), lang)),
            esc(i18n.text(lang, "st_" + fields.get("stage", "potencial"))
                if fields.get("stage") in STAGES else ""),
            figures_list(lang, share_cents, result),
            esc(csrf), hidden, shown, esc(key),
            esc(i18n.text(lang, "btn_confirm")),
        )
    )


def forecast_section(lang, month, deals, expenses_cents):
    result = month_figures(
        [
            {
                "part_base": deal["part_base"],
                "iva_rate": deal["iva_rate"],
                "retencao_rate": deal["retencao_rate"],
                "irs_rate": deal["irs_rate"],
                "ss_rate": deal["ss_rate"],
            }
            for deal in deals
        ],
        expenses_cents,
    )
    items = "".join(
        "<li>%s · %s · %s</li>"
        % (esc(deal["name"]),
           esc(i18n.text(lang, "st_" + deal["stage"])),
           esc(format_amount(deal["part_base"], lang)))
        for deal in deals
    )
    breakdown = result["protected_breakdown"]
    return (
        "<section><h2>%s</h2>"
        "<dl>"
        '<dt data-i18n="m_commission">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_bank">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_protected">%s</dt><dd>%s (%s %s; %s %s; %s %s)</dd>'
        '<dt data-i18n="m_really">%s</dt><dd>%s</dd>'
        "</dl>"
        '<h3 data-i18n="m_deals">%s</h3><ul>%s</ul></section>'
        % (
            esc(format_month(month, lang)),
            esc(i18n.text(lang, "m_commission")),
            esc(format_amount(result["commission"], lang)),
            esc(i18n.text(lang, "m_bank")),
            esc(format_amount(result["bank_inflow"], lang)),
            esc(i18n.text(lang, "m_protected")),
            esc(format_amount(result["protected_money"], lang)),
            esc(i18n.text(lang, "b_iva")),
            esc(format_amount(breakdown["iva"], lang)),
            esc(i18n.text(lang, "b_irs")),
            esc(format_amount(breakdown["irs_reserve"], lang)),
            esc(i18n.text(lang, "b_ss")),
            esc(format_amount(breakdown["ss_reserve"], lang)),
            esc(i18n.text(lang, "m_really")),
            esc(format_amount(result["really_available"], lang)),
            esc(i18n.text(lang, "m_deals")), items,
        )
    )


def nl_sentence_form(lang, csrf, sentence=""):
    """The one-sentence form starting a move scenario."""
    return (
        '<form method="post" action="/scenarios/move">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '<div><label for="nl-sentence" data-i18n="nl_label">%s</label>'
        '<input id="nl-sentence" name="sentence" value="%s" maxlength="%d">'
        '<p>%s</p></div>'
        '<button type="submit" data-i18n="nl_submit">%s</button>'
        "</form>"
        % (
            esc(csrf),
            esc(i18n.text(lang, "nl_label")),
            esc(sentence),
            NL_SENTENCE_MAX_CHARS,
            esc(i18n.text(lang, "nl_hint")),
            esc(i18n.text(lang, "nl_submit")),
        )
    )


def nl_month_lines(lang, month, figures_result):
    """One month with its four figures, for the NL before/after view."""
    breakdown = figures_result["protected_breakdown"]
    return (
        "<h2>%s</h2>"
        "<dl>"
        '<dt data-i18n="m_commission">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_bank">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_protected">%s</dt><dd>%s (%s %s; %s %s; %s %s)</dd>'
        '<dt data-i18n="m_really">%s</dt><dd>%s</dd>'
        "</dl>"
        % (
            esc(format_month(month, lang)),
            esc(i18n.text(lang, "m_commission")),
            esc(format_amount(figures_result["commission"], lang)),
            esc(i18n.text(lang, "m_bank")),
            esc(format_amount(figures_result["bank_inflow"], lang)),
            esc(i18n.text(lang, "m_protected")),
            esc(format_amount(figures_result["protected_money"], lang)),
            esc(i18n.text(lang, "b_iva")),
            esc(format_amount(breakdown["iva"], lang)),
            esc(i18n.text(lang, "b_irs")),
            esc(format_amount(breakdown["irs_reserve"], lang)),
            esc(i18n.text(lang, "b_ss")),
            esc(format_amount(breakdown["ss_reserve"], lang)),
            esc(i18n.text(lang, "m_really")),
            esc(format_amount(figures_result["really_available"], lang)),
        )
    )


def nl_move_result_page(lang, sentence, outcome):
    """Render one NL move outcome: before/after, question or error."""
    status = outcome.get("status")
    if status == "moved":
        moved = outcome["moved"]
        sections = "".join(
            "<section>%s</section>"
            % nl_month_lines(lang, month, outcome["after"][month])
            for month in sorted(outcome["after"])
        )
        before = "".join(
            "<section>%s</section>"
            % nl_month_lines(lang, month, outcome["before"][month])
            for month in sorted(outcome["before"])
        )
        return (
            "<p>%s</p>"
            "<h2>%s</h2>%s"
            "<h2>%s</h2>%s"
            % (
                esc("%s · %s → %s" % (
                    moved["deal"],
                    format_month(moved["from_month"], lang),
                    format_month(moved["target_month"], lang),
                )),
                esc(i18n.text(lang, "nl_before")),
                before,
                esc(i18n.text(lang, "nl_after")),
                sections,
            )
        )
    if status == "question":
        return '<p class="notice" role="alert">%s</p>' % esc(
            outcome["question"])
    return '<p class="notice" role="alert">%s</p>' % esc(
        outcome.get("message", i18n.text(lang, "refused_msg")))


def nl_records_from_deals(deals):
    """Read stored deals as unpaid expected payment records.

    Stored deals have no payment reference or received flag: each one
    is one unpaid ``part-1`` payment, and the month comes from the
    stored deal itself.
    """
    records = []
    for deal in deals:
        records.append({
            "deal": deal["name"],
            "payment": "part-1",
            "month": deal["month"],
            "part_base": deal["part_base"],
            "received": False,
            "iva_rate": deal["iva_rate"],
            "retencao_rate": deal["retencao_rate"],
            "irs_rate": deal["irs_rate"],
            "ss_rate": deal["ss_rate"],
        })
    return records


def _unused_interpret(sentence):
    """Interpret stub that must never run: empty sentences ask first."""
    raise AssertionError("the model must not be called for this sentence")


def validate_nl_sentence(sentence):
    """Refuse an empty or overlong move sentence before any model call."""
    if sentence is None or not sentence.strip():
        return "empty"
    if len(sentence) > NL_SENTENCE_MAX_CHARS:
        return "too_long"
    return ""


MOVE_EXAMPLE_CURRENT = "2026-11"
MOVE_EXAMPLE_MONTH = "2026-11"
MOVE_EXAMPLE_TARGET = "2026-12"
MOVE_EXAMPLE_EXPENSES = 35000


def move_example_result():
    """One example move, shown with its before and after forecast."""
    records = [
        {
            "deal": "T2 Campo de Ourique",
            "payment": "part-1",
            "month": MOVE_EXAMPLE_MONTH,
            "part_base": 500000,
            "received": False,
            "iva_rate": "0.23",
            "retencao_rate": "0.25",
            "irs_rate": "0.30",
            "ss_rate": "0.10",
        },
    ]
    move = {
        "deal": "T2 Campo de Ourique",
        "payment": "part-1",
        "target_month": MOVE_EXAMPLE_TARGET,
    }
    return move_payment(records, move, MOVE_EXAMPLE_CURRENT,
                        expenses_cents=MOVE_EXAMPLE_EXPENSES)


def move_example_page(lang):
    """Render the example move with its before and after forecast.

    The before forecast holds the payment in November 2026; the after
    forecast is the engine's own recalculation with the payment moved
    to December 2026. Both figures come from the engine; nothing here
    is saved.
    """
    outcome = move_example_result()
    moved = outcome["moved"]
    before = calc_month(
        [{
            "part_base": 500000,
            "iva_rate": "0.23",
            "retencao_rate": "0.25",
            "irs_rate": "0.30",
            "ss_rate": "0.10",
        }],
        expenses=MOVE_EXAMPLE_EXPENSES,
    )
    after = outcome["forecast"][MOVE_EXAMPLE_TARGET]
    section = (
        "<section><h2>%s</h2>"
        "<dl>"
        '<dt data-i18n="m_commission">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_bank">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_protected">%s</dt><dd>%s (%s %s; %s %s; %s %s)</dd>'
        '<dt data-i18n="m_really">%s</dt><dd>%s</dd>'
        "</dl></section>"
    )

    def figures(month, figures_result, breakdown):
        return section % (
            esc(format_month(month, lang)),
            esc(i18n.text(lang, "m_commission")),
            esc(format_amount(figures_result["commission"], lang)),
            esc(i18n.text(lang, "m_bank")),
            esc(format_amount(figures_result["bank_inflow"], lang)),
            esc(i18n.text(lang, "m_protected")),
            esc(format_amount(figures_result["protected_money"], lang)),
            esc(i18n.text(lang, "b_iva")),
            esc(format_amount(breakdown["iva"], lang)),
            esc(i18n.text(lang, "b_irs")),
            esc(format_amount(breakdown["irs_reserve"], lang)),
            esc(i18n.text(lang, "b_ss")),
            esc(format_amount(breakdown["ss_reserve"], lang)),
            esc(i18n.text(lang, "m_really")),
            esc(format_amount(figures_result["really_available"], lang)),
        )

    return (
        "<h1>%s</h1>"
        "<p>%s</p>"
        "%s%s"
        % (
            esc(i18n.text(lang, "move_title")),
            esc("%s · %s → %s" % (
                moved["deal"],
                format_month(moved["from_month"], lang),
                format_month(moved["target_month"], lang),
            )),
            figures(MOVE_EXAMPLE_MONTH, before,
                    before["protected_breakdown"]),
            figures(MOVE_EXAMPLE_TARGET, after,
                    after["protected_breakdown"]),
        )
    )


def validate_deal(lang, fields, form_locale):
    errors = {}
    parsed = {}
    name = fields.get("name", "").strip()
    if not name:
        errors["name"] = i18n.text(lang, "err_name")
    elif len(name) > MAX_TEXT_CHARS:
        errors["name"] = i18n.text(lang, "err_too_long")
    else:
        parsed["name"] = fields.get("name", "").strip()
    commission_text = fields.get("commission", "")
    if not commission_text.strip():
        errors["commission"] = i18n.text(lang, "err_commission")
    else:
        try:
            commission = parse_amount(commission_text, form_locale)
            if commission <= 0:
                errors["commission"] = i18n.text(lang, "err_positive")
            else:
                parsed["commission_cents"] = commission
        except ValueError:
            errors["commission"] = i18n.text(lang, "err_amount")
    share_text = fields.get("share", "")
    if not share_text.strip():
        errors["share"] = i18n.text(lang, "err_percent")
    else:
        try:
            percent = parse_percent(share_text, form_locale)
            if percent < 0 or percent > 100:
                errors["share"] = i18n.text(lang, "err_percent")
            else:
                parsed["share_rate"] = rate_string(percent)
        except ValueError:
            errors["share"] = i18n.text(lang, "err_amount")
    if not valid_month(fields.get("month", "")):
        errors["month"] = i18n.text(lang, "err_month")
    else:
        parsed["month"] = fields.get("month", "")
    if fields.get("stage", "") not in STAGES:
        errors["stage"] = i18n.text(lang, "err_stage")
    else:
        parsed["stage"] = fields.get("stage", "")
    parsed["agency"] = fields.get("agency", "").strip()
    if len(parsed["agency"]) > MAX_TEXT_CHARS:
        errors["agency"] = i18n.text(lang, "err_too_long")
    return errors, parsed


def validate_settings(lang, fields, form_locale):
    errors = {}
    parsed = {}
    for name in ("share", "iva", "retencao", "irs", "ss"):
        text = fields.get(name, "")
        if not text.strip():
            errors[name] = i18n.text(lang, "err_percent")
            continue
        try:
            percent = parse_percent(text, form_locale)
        except ValueError:
            errors[name] = i18n.text(lang, "err_amount")
            continue
        if percent < 0 or percent > 100:
            errors[name] = i18n.text(lang, "err_percent")
            continue
        parsed[name] = rate_string(percent)
    expenses_text = fields.get("expenses", "")
    if not expenses_text.strip():
        errors["expenses"] = i18n.text(lang, "err_amount")
    else:
        try:
            expenses = parse_amount(expenses_text, form_locale)
            if expenses < 0:
                errors["expenses"] = i18n.text(lang, "err_amount")
            else:
                parsed["expenses"] = expenses
        except ValueError:
            errors["expenses"] = i18n.text(lang, "err_amount")
    return errors, parsed


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def application(environ, start_response):
    session, new_cookies = session_for(environ)
    lang = language_for(environ)
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/") or "/"

    def respond(status, body, extra=None):
        data = body.encode("utf-8")
        headers = [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Security-Policy", "default-src 'self'"),
            ("X-Content-Type-Options", "nosniff"),
            ("Content-Length", str(len(data))),
        ]
        for cookie in new_cookies:
            headers.append(("Set-Cookie", cookie))
        for header in extra or []:
            headers.append(header)
        start_response(status, headers)
        return [data]

    def redirect(location, cookies=()):
        headers = [("Location", location)]
        for cookie in cookies:
            headers.append(("Set-Cookie", cookie))
        return respond("303 See Other", "", headers)

    def forbidden():
        body = page(
            lang, session["csrf"],
            i18n.text(lang, "refused_title"),
            '<h1 data-i18n="refused_title">%s</h1>'
            '<p data-i18n="refused_msg">%s</p>'
            % (esc(i18n.text(lang, "refused_title")),
               esc(i18n.text(lang, "refused_msg"))),
        )
        return respond("403 Forbidden", body)

    def too_large():
        body = page(
            lang, session["csrf"],
            i18n.text(lang, "refused_title"),
            '<h1 data-i18n="refused_title">%s</h1>'
            '<p data-i18n="refused_msg">%s</p>'
            % (esc(i18n.text(lang, "refused_title")),
               esc(i18n.text(lang, "refused_msg"))),
        )
        return respond("413 Content Too Large", body)

    def bad_request():
        body = page(
            lang, session["csrf"],
            i18n.text(lang, "refused_title"),
            '<h1 data-i18n="refused_title">%s</h1>'
            '<p data-i18n="refused_msg">%s</p>'
            % (esc(i18n.text(lang, "refused_title")),
               esc(i18n.text(lang, "refused_msg"))),
        )
        return respond("400 Bad Request", body)

    def read_post_form():
        try:
            return read_form(environ)
        except BodyTooLarge:
            return too_large()
        except BadBodyEncoding:
            return bad_request()

    def csrf_ok(fields):
        return fields.get("csrf_token", "") == session["csrf"]

    if path == "/static/style.css":
        try:
            with open(os.path.join(STATIC_DIR, "style.css"), "rb") as handle:
                data = handle.read()
        except OSError:
            start_response("404 Not Found", [("Content-Length", "0")])
            return [b""]
        headers = [
            ("Content-Type", "text/css; charset=utf-8"),
            ("Content-Security-Policy", "default-src 'self'"),
            ("X-Content-Type-Options", "nosniff"),
            ("Content-Length", str(len(data))),
        ]
        start_response("200 OK", headers)
        return [data]

    if path == "/" and method == "GET":
        query = read_query(environ)
        only = query.get("month", "")
        settings = store.get_settings(DB_PATH)
        expenses = settings["expenses_cents"] if settings else 0
        if only and valid_month(only):
            months = [only]
        else:
            months = store.months_with_deals(DB_PATH)
        if not months:
            body = page(
                lang, session["csrf"], i18n.text(lang, "home_title"),
                '<h1 data-i18n="home_title">%s</h1>'
                '<p data-i18n="home_empty">%s</p>'
                '<p><a href="/deals/new" data-i18n="home_new">%s</a></p>'
                % (esc(i18n.text(lang, "home_title")),
                   esc(i18n.text(lang, "home_empty")),
                   esc(i18n.text(lang, "home_new"))),
            )
            return respond("200 OK", body)
        sections = "".join(
            forecast_section(lang, month, store.list_deals(DB_PATH, month),
                             expenses)
            for month in months
        )
        body = page(lang, session["csrf"], i18n.text(lang, "home_title"),
                    '<h1 data-i18n="home_title">%s</h1>%s'
                    % (esc(i18n.text(lang, "home_title")), sections))
        return respond("200 OK", body)

    if path == "/scenarios/move" and method == "GET":
        body = page(lang, session["csrf"], i18n.text(lang, "move_title"),
                    nl_sentence_form(lang, session["csrf"])
                    + move_example_page(lang))
        return respond("200 OK", body)

    if path == "/scenarios/move" and method == "POST":
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if not csrf_ok(fields):
            return forbidden()
        sentence = fields.get("sentence", "")
        problem = validate_nl_sentence(sentence)
        if problem == "empty":
            outcome = plan_nl_move(
                sentence, [], nl_current_month(), _unused_interpret)
        elif problem == "too_long":
            outcome = {
                "status": "question",
                "question": i18n.text(lang, "err_too_long"),
            }
        else:
            settings = store.get_settings(DB_PATH)
            expenses = settings["expenses_cents"] if settings else 0
            deals = store.list_deals(DB_PATH)
            records = nl_records_from_deals(deals)
            try:
                client = nl_client()
            except ModelError as exc:
                outcome = {"status": "error", "message": str(exc)}
            else:
                outcome = plan_nl_move(
                    sentence, records, nl_current_month(),
                    client.interpret_move, expenses_cents=expenses)
        content = (nl_sentence_form(lang, session["csrf"], sentence)
                   + nl_move_result_page(lang, sentence, outcome)
                   + move_example_page(lang))
        body = page(lang, session["csrf"], i18n.text(lang, "move_title"),
                    content)
        return respond("200 OK", body)

    if path == "/language" and method == "POST":
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if not csrf_ok(fields):
            return forbidden()
        chosen = fields.get("lang", "")
        if chosen not in i18n.SUPPORTED:
            chosen = "pt-PT"
        cookie = "lang=%s; Path=/; SameSite=Strict" % chosen
        return redirect("/", [cookie])

    if path == "/settings" and method == "GET":
        settings = store.get_settings(DB_PATH)
        values = {}
        if settings is not None:
            values = {
                "share": format_edit_percent(settings["share_rate"], lang),
                "iva": format_edit_percent(settings["iva_rate"], lang),
                "retencao": format_edit_percent(settings["retencao_rate"],
                                                lang),
                "irs": format_edit_percent(settings["irs_rate"], lang),
                "ss": format_edit_percent(settings["ss_rate"], lang),
                "expenses": format_edit_amount(settings["expenses_cents"],
                                               lang),
            }
        body = page(lang, session["csrf"], i18n.text(lang, "set_title"),
                    settings_form(lang, session["csrf"], values, {}))
        return respond("200 OK", body)

    if path == "/settings" and method == "POST":
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if not csrf_ok(fields):
            return forbidden()
        form_locale = fields.get("form_locale", lang)
        if form_locale not in i18n.SUPPORTED:
            form_locale = lang
        errors, parsed = validate_settings(lang, fields, form_locale)
        if errors:
            values = {name: fields.get(name, "") for name in
                      ("share", "iva", "retencao", "irs", "ss", "expenses")}
            body = page(lang, session["csrf"],
                        i18n.text(lang, "set_title"),
                        settings_form(lang, session["csrf"], values, errors))
            return respond("200 OK", body)
        store.save_settings(DB_PATH, {
            "share_rate": parsed["share"],
            "iva_rate": parsed["iva"],
            "retencao_rate": parsed["retencao"],
            "irs_rate": parsed["irs"],
            "ss_rate": parsed["ss"],
            "expenses_cents": parsed["expenses"],
        })
        return redirect("/settings")

    if path == "/deals/new" and method == "GET":
        settings = store.get_settings(DB_PATH)
        body = page(lang, session["csrf"], i18n.text(lang, "deal_title"),
                    deal_form(lang, session["csrf"], {}, {}, settings))
        return respond("200 OK", body)

    if path == "/deals/review" and method == "POST":
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if not csrf_ok(fields):
            return forbidden()
        form_locale = fields.get("form_locale", lang)
        if form_locale not in i18n.SUPPORTED:
            form_locale = lang
        settings = store.get_settings(DB_PATH)
        errors, parsed = validate_deal(lang, fields, form_locale)
        if settings is None:
            errors["commission"] = i18n.text(lang, "err_settings")
        if errors:
            values = {name: fields.get(name, "") for name in
                      ("name", "commission", "share", "month", "stage",
                       "agency")}
            body = page(
                lang, session["csrf"], i18n.text(lang, "deal_title"),
                '<p class="notice">%s</p>%s'
                % (esc(i18n.text(lang, "err_settings"))
                   if settings is None else "",
                   deal_form(lang, session["csrf"], values, errors,
                             settings)))
            return respond("200 OK", body)
        share_cents = agent_share(parsed["commission_cents"],
                                  parsed["share_rate"])
        result = single_figures(share_cents, settings,
                                settings["expenses_cents"])
        key = secrets.token_urlsafe(16)
        shown = {
            "name": parsed["name"],
            "commission": fields.get("commission", ""),
            "share": fields.get("share", ""),
            "month": parsed["month"],
            "stage": parsed["stage"],
            "agency": parsed["agency"],
            "form_locale": form_locale,
        }
        body = page(lang, session["csrf"], i18n.text(lang, "rev_title"),
                    review_page(lang, session["csrf"], shown, share_cents,
                                result, False, key))
        return respond("200 OK", body)

    if path == "/deals/confirm" and method == "POST":
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if "shown_share" in fields and "idempotency_key" in fields:
            for name in ("name", "commission", "share", "month", "stage",
                         "agency", "form_locale"):
                fields[name] = unquote(fields.get(name, ""))
        if not csrf_ok(fields):
            return forbidden()
        form_locale = fields.get("form_locale", lang)
        if form_locale not in i18n.SUPPORTED:
            form_locale = lang
        settings = store.get_settings(DB_PATH)
        errors, parsed = validate_deal(lang, fields, form_locale)
        if settings is None:
            errors["commission"] = i18n.text(lang, "err_settings")
        if errors:
            values = {name: fields.get(name, "") for name in
                      ("name", "commission", "share", "month", "stage",
                       "agency")}
            body = page(
                lang, session["csrf"], i18n.text(lang, "deal_title"),
                deal_form(lang, session["csrf"], values, errors, settings))
            return respond("200 OK", body)
        share_cents = agent_share(parsed["commission_cents"],
                                  parsed["share_rate"])
        result = single_figures(share_cents, settings,
                                settings["expenses_cents"])
        try:
            shown = {
                "share": int(fields.get("shown_share", "-1")),
                "bank": int(fields.get("shown_bank", "-1")),
                "protected": int(fields.get("shown_protected", "-1")),
                "really": int(fields.get("shown_really", "-1")),
            }
        except ValueError:
            shown = {}
        current = {
            "share": share_cents,
            "bank": result["bank_inflow"],
            "protected": result["protected_money"],
            "really": result["really_available"],
        }
        if shown != current:
            shown_fields = {
                "name": parsed["name"],
                "commission": fields.get("commission", ""),
                "share": fields.get("share", ""),
                "month": parsed["month"],
                "stage": parsed["stage"],
                "agency": parsed["agency"],
                "form_locale": form_locale,
            }
            body = page(
                lang, session["csrf"], i18n.text(lang, "rev_title"),
                review_page(lang, session["csrf"], shown_fields, share_cents,
                            result, True, secrets.token_urlsafe(16)))
            return respond("200 OK", body)
        store.insert_deal(DB_PATH, {
            "name": parsed["name"],
            "agency": parsed["agency"],
            "month": parsed["month"],
            "stage": parsed["stage"],
            "agency_commission_cents": parsed["commission_cents"],
            "share_rate": fields.get("share", ""),
            "part_base": share_cents,
            "share_rate_used": parsed["share_rate"],
            "iva_rate": settings["iva_rate"],
            "retencao_rate": settings["retencao_rate"],
            "irs_rate": settings["irs_rate"],
            "ss_rate": settings["ss_rate"],
            "expenses_cents": settings["expenses_cents"],
            "idempotency_key": fields.get("idempotency_key", ""),
        })
        return redirect("/?month=" + parsed["month"])

    start_response("404 Not Found", [("Content-Length", str(len(b"Not found"))),
                                     ("Content-Security-Policy",
                                      "default-src 'self'"),
                                     ("X-Content-Type-Options", "nosniff")])
    return [b"Not found"]
