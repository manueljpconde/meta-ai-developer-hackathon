"""WSGI application for the first Agentimo screens.

Standard library only. Every figure comes from ``engine.calc``; the
only work here is parsing input text. All HTML output is escaped,
every POST carries a CSRF token tied to a session cookie, SQL uses
parameters only, and responses carry the security headers.
"""

import html
import json
import os
import re
import secrets
import threading
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qsl, quote, unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import auth, i18n, mail, store, voice_audio
from engine.calc import agent_share, calc_month, month_expenses

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


NL_CURRENT_MONTH_ENV = "APP_NL_CURRENT_MONTH"
NL_TODAY_ENV = "APP_NL_TODAY"

# The signed-in agent of the request being served, for the one page element
# that depends on the agent's data (the voice panel's settings check).
_REQUEST = threading.local()



def nl_current_month():
    """Current month from the Lisbon server date, with test override."""
    forced = os.environ.get(NL_CURRENT_MONTH_ENV, "")
    if forced and valid_month(forced):
        return forced
    try:
        today = datetime.now(ZoneInfo("Europe/Lisbon")).date()
    except ZoneInfoNotFoundError:
        today = datetime.now().date()
    return today.strftime("%Y-%m")


def nl_today():
    """Today's date (YYYY-MM-DD) from the Lisbon server date, with test overrides."""
    forced = os.environ.get(NL_TODAY_ENV, "")
    if forced and valid_date(forced):
        return forced
    month = os.environ.get(NL_CURRENT_MONTH_ENV, "")
    if month and valid_month(month):
        return month + "-01"
    try:
        today = datetime.now(ZoneInfo("Europe/Lisbon")).date()
    except ZoneInfoNotFoundError:
        today = datetime.now().date()
    return today.isoformat()


def add_months(year_month, delta):
    """Shift a ``YYYY-MM`` month by delta months."""
    year, month = int(year_month[:4]), int(year_month[5:7])
    index = (year * 12 + (month - 1)) + delta
    return "%04d-%02d" % (index // 12, index % 12 + 1)






def valid_month(text):
    return bool(re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", text or ""))

def valid_date(text):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text or ""):
        return False
    try:
        datetime.strptime(text, "%Y-%m" + "-%d")
        return True
    except ValueError:
        return False

def forecast_month_from_date(escritura_date):
    if escritura_date and len(escritura_date) >= 7:
        return escritura_date[:7]
    return escritura_date or ""

def format_date(date_str, lang):
    if not date_str:
        return ""
    try:
        y, m, d = date_str.split("-")
        idx = int(m) - 1
        if lang == "pt-PT":
            return f"{int(d):02d} de {PT_MONTHS[idx]} de {y}"
        return f"{EN_MONTHS[idx]} {int(d)}, {y}"
    except Exception:
        return date_str

def derive_month(escritura_date):
    if escritura_date and len(escritura_date) >= 7:
        return escritura_date[:7]
    return escritura_date

def date_selects(lang, prefix, value):
    y, m, d = "", "", ""
    if value and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        y, m, d = value.split("-")
    # day 1..31
    day_opts = '<option value=""></option>' + "".join(f'<option value="{i:02d}"{ " selected" if f"{i:02d}"==d else ""}>{i}</option>' for i in range(1,32))
    month_names = PT_MONTHS if lang=="pt-PT" else EN_MONTHS
    month_opts = '<option value=""></option>' + "".join(f'<option value="{i:02d}"{ " selected" if f"{i:02d}"==m else ""}>{month_names[i-1]}</option>' for i in range(1,13))
    year_opts = '<option value=""></option>' + "".join(f'<option value="{yr}"{ " selected" if str(yr)==y else ""}>{yr}</option>' for yr in range(2020, 2035))
    day_label = "dia" if lang == "pt-PT" else "day"
    month_label = "m\u00eas" if lang == "pt-PT" else "month"
    year_label = "ano" if lang == "pt-PT" else "year"
    return (
        f'<select name="{prefix}_day" aria-label="{day_label}">{day_opts}</select>'
        f'<select name="{prefix}_month" aria-label="{month_label}">{month_opts}</select>'
        f'<select name="{prefix}_year" aria-label="{year_label}">{year_opts}</select>'
    )



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


def expense_rule(tenant_id):
    """month -> (expense cents, estimated) by item 6's rule, for one tenant."""
    settings = store.get_settings(DB_PATH, tenant_id=tenant_id)
    estimate = settings["expenses_cents"] if settings else 0
    totals = store.expense_totals(DB_PATH, tenant_id)
    current = nl_today()[:7]

    def rule(month):
        recorded, planned = totals.get(month, (0, 0))
        return month_expenses(month, current, estimate, recorded, planned)
    return rule


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
    if token:
        sess = auth.get_valid_session(DB_PATH, token)
        if sess is not None:
            return {"id": sess["id"], "csrf": sess["csrf_token"],
                    "email": sess["email"], "tenant_id": sess["tenant_id"],
                    "authenticated": True}, []
    # Unauthenticated: CSRF-only session via ephemeral token
    if token in SESSIONS:
        rec = SESSIONS[token]
        if rec.get("authenticated"):
            # Stale authenticated entry, ignore
            pass
        else:
            return rec, []
    token = secrets.token_urlsafe(16)
    csrf = secrets.token_urlsafe(32)
    record = {"id": token, "csrf": csrf, "authenticated": False}
    SESSIONS[token] = record
    cookie = "session=%s; HttpOnly; Path=/; SameSite=Lax" % token
    return record, [cookie]


# ── Session gate: default-deny public list ──────────────────────
# Every route needs a signed-in agent except these.
PUBLIC_ROUTES = {"/signin", "/auth/verify", "/language"}
PUBLIC_PREFIXES = ("/static/",)

def is_public_path(path):
    if path in PUBLIC_ROUTES:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False

# Enumerate all app routes for the enumeration test.
# The test imports this and proves every non-public one redirects.
APP_ROUTES = [
    ("/", "GET"),
    ("/signin", "GET"), ("/signin", "POST"),
    ("/auth/verify", "GET"),
    ("/signout", "POST"),
    ("/account/delete", "GET"), ("/account/delete", "POST"),
    ("/static/style.css", "GET"), ("/static/voice.js", "GET"),
    ("/settings", "GET"), ("/settings", "POST"),
    ("/deals/new", "GET"),
    ("/deals/review", "POST"),
    ("/deals/confirm", "POST"),
    ("/deals/edit", "GET"), ("/deals/update", "POST"),
    ("/deals/delete", "GET"), ("/deals/delete", "POST"),
    ("/voice/transcribe", "POST"),
    ("/voice/extract", "POST"), ("/voice/confirm", "POST"), ("/voice/cancel", "POST"),
    ("/expenses", "GET"), ("/expenses/add", "POST"),
    ("/expenses/edit", "GET"), ("/expenses/update", "POST"), ("/expenses/delete", "POST"),
    ("/language", "POST"),
]


def language_for(environ):
    jar = parse_cookies(environ)
    saved = jar.get("lang", "")
    if saved in i18n.SUPPORTED:
        return saved
    return i18n.detect_language(environ.get("HTTP_ACCEPT_LANGUAGE", ""))


def lang_switch(lang, csrf):
    """Compact PT | EN switch: two tiny buttons in one form, usable in a header."""
    def button(code, label):
        cls = ' class="active"' if code == lang else ""
        return '<button type="submit" name="lang" value="%s"%s>%s</button>' % (code, cls, label)
    return (
        '<form method="post" action="/language" class="lang lang--compact">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '%s | %s'
        "</form>"
        % (esc(csrf), button("pt-PT", "PT"), button("en-GB", "EN"))
    )

lang_form = lang_switch


def nav(lang, current=""):
    """The header navigation, marking the current page when known."""
    links = []
    for href, key in (("/", "nav_home"), ("/deals/new", "nav_new"),
                      ("/expenses", "nav_expenses"), ("/settings", "nav_settings")):
        mark = ' aria-current="page"' if href == current else ""
        links.append('<a href="%s" data-i18n="%s"%s>%s</a>'
                     % (href, key, mark, esc(i18n.text(lang, key))))
    return "<nav>" + " ".join(links) + "</nav>"


def page(lang, csrf, title, body, current="", signed_in=False):
    def signout_form():
        return ('<form method="post" action="/signout" class="signout-form">'
                '<input type="hidden" name="csrf_token" value="%s">'
                '<button type="submit" data-i18n="signout_label">%s</button>'
                '</form>' % (esc(csrf), esc(i18n.text(lang, "signout_label"))))
    mic = '<svg class="mic-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="28" height="28" fill="currentColor" focusable="false"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z"/></svg>'
    voice_btn_header = (
        '<button id="voiceFalarHeader" type="button" class="voice-falar-header">'
        '<span aria-hidden="true">%s</span> <span data-i18n="voice_falar">%s</span></button>'
        % (mic, esc(i18n.text(lang, "voice_falar"))))
    voice_btn_fixed = (
        '<button id="voiceFalar" type="button" class="voice-falar-fixed" aria-label="%s">'
        '<span aria-hidden="true">%s</span></button>'
        % (esc(i18n.text(lang, "voice_falar")), mic))
    voice_panel = ""
    voice_js = ""
    if signed_in:
        tenant_id = getattr(_REQUEST, "tenant_id", None)
        needs_settings = tenant_id is not None and store.get_settings(DB_PATH, tenant_id=tenant_id) is None
        voice_panel = (
            '<div id="voiceBackdrop" class="voice-backdrop" hidden></div>'
            '<div id="voicePanel" class="voice-panel" role="dialog" hidden aria-label="%s"'
            ' data-network-error="%s" data-mic-blocked="%s" data-tap-answer="%s"'
            ' data-too-long="%s" data-server-refused="%s" data-thinking="%s" data-diag-line="%s"'
            ' data-needs-settings="%s">'
            '<div class="voice-panel__inner">'
            '<div id="voiceTranscript" class="voice-transcript"></div>'
            '<div id="voiceWorking" class="voice-working" role="status" aria-live="polite"></div>'
            '<div id="voiceQuestion" class="voice-question"></div>'
            '<div id="voiceReadback" class="voice-readback"></div>'
            '<div id="voiceDiag" class="voice-diag"></div>'
            '<p id="voiceSettingsFirst" class="voice-settings-first" hidden>%s <a href="/settings">%s</a></p>'
            '<form id="voiceTextForm" method="post" action="/voice/extract">'
            '<input type="hidden" name="csrf_token" value="%s">'
            '<input type="hidden" name="conversation_id" id="voiceConvId" value="">'
            '<input type="text" name="text" id="voiceTextInput" autocomplete="off" placeholder="%s" aria-label="%s">'
            '<button type="submit" data-i18n="voice_send">%s</button></form>'
            '<div class="voice-actions">'
            '<button type="button" id="voiceConfirmBtn" class="btn-primary" hidden data-i18n="btn_confirm">%s</button>'
            '<button type="button" id="voiceCancelBtn" class="btn-secondary" data-i18n="voice_cancel_btn">%s</button></div>'
            '</div></div>'
            % (esc(i18n.text(lang, "voice_panel_label")),
               esc(i18n.text(lang, "voice_network_error")),
               esc(i18n.text(lang, "voice_mic_blocked")),
               esc(i18n.text(lang, "voice_tap_answer")),
               esc(i18n.text(lang, "voice_too_long")),
               esc(i18n.text(lang, "voice_server_refused")),
               esc(i18n.text(lang, "voice_thinking")),
               esc(i18n.text(lang, "voice_diag_line")),
               "1" if needs_settings else "0",
               esc(i18n.text(lang, "voice_settings_first")),
               esc(i18n.text(lang, "voice_settings_link")),
               esc(csrf),
               esc(i18n.text(lang, "voice_placeholder")),
               esc(i18n.text(lang, "voice_placeholder")),
               esc(i18n.text(lang, "voice_send")),
               esc(i18n.text(lang, "btn_confirm")),
               esc(i18n.text(lang, "voice_cancel_btn"))))
        voice_js = '<script src="/static/voice.js" defer></script>'
    if signed_in:
        header = ('<div class="brand">Agentimo</div>%s<div class="header-tools">%s%s</div>%s'
                  % (nav(lang, current), lang_switch(lang, csrf), signout_form(), voice_btn_header))
        body = body + voice_panel + voice_btn_fixed + voice_js
    else:
        header = '<div class="brand">Agentimo</div>%s' % lang_switch(lang, csrf)
    return (
        "<!DOCTYPE html>"
        '<html lang="%s"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,'
        ' initial-scale=1">'
        "<title>%s</title>"
        '<link rel="stylesheet" href="/static/style.css">'
        "</head><body>"
        "<header>%s</header><main>%s</main></body></html>"
        % (
            esc(lang), esc(title), header, body,
        )
    )


def error_span(message):
    if not message:
        return ""
    return '<span class="error">%s</span>' % esc(message)

def signin_page(lang, csrf, email="", error=""):
    return (
        '<div class="signin">'
        '<h1 data-i18n="signin_heading">%s</h1>'
        '<p data-i18n="signin_prompt">%s</p>'
        '<form method="post" action="/signin">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '<div><label for="signin-email" data-i18n="signin_label">%s</label>'
        '<input id="signin-email" name="email" type="email" value="%s">%s</div>'
        '<button type="submit" data-i18n="signin_button">%s</button>'
        '</form></div>'
        % (esc(i18n.text(lang, "signin_heading")),
           esc(i18n.text(lang, "signin_prompt")),
           esc(csrf),
           esc(i18n.text(lang, "signin_label")), esc(email),
           error_span(error), esc(i18n.text(lang, "signin_button")))
    )

def check_email_page(lang, email):
    return (
        '<h1 data-i18n="check_email_title">%s</h1>'
        '<p>%s</p>'
        % (esc(i18n.text(lang, "check_email_title")),
           esc(i18n.text(lang, "check_email_body").replace("{email}", email)))
    )

def delete_form(lang, csrf, error):
    return (
        '<h1 data-i18n="delete_title">%s</h1>'
        '<form method="post" action="/account/delete">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '<div><label for="delete-email" data-i18n="delete_label">%s</label>'
        '<input id="delete-email" name="email" type="email" value="">%s</div>'
        '<button type="submit" data-i18n="delete_button">%s</button>'
        '</form>'
        % (esc(i18n.text(lang, "delete_title")), esc(csrf),
           esc(i18n.text(lang, "delete_label")), error_span(error),
           esc(i18n.text(lang, "delete_button")))
    )

def delete_deal_confirm(lang, csrf, deal_id):
    return (
        '<h1 data-i18n="delete_deal_title">%s</h1>'
        '<p data-i18n="delete_deal_confirm">%s</p>'
        '<form method="post" action="/deals/delete?id=%d">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '<button type="submit" data-i18n="delete_deal_button">%s</button>'
        '</form>'
        '<p><a href="/deals/edit?id=%d" data-i18n="delete_deal_cancel">%s</a></p>'
        % (esc(i18n.text(lang, "delete_deal_title")),
           esc(i18n.text(lang, "delete_deal_confirm")),
           deal_id, esc(csrf), esc(i18n.text(lang, "delete_deal_button")),
           deal_id, esc(i18n.text(lang, "delete_deal_cancel")))
    )

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

    def expenses_field():
        zero = values.get("expenses", "").strip() in ("0", "0,00", "0.00", "0,0", "0.0")
        warning = ('<p class="notice" data-i18n="set_expenses_zero">%s</p>'
                   % esc(i18n.text(lang, "set_expenses_zero")) if zero else "")
        return field("expenses", "set_expenses").replace(
            "</div>", '<small class="field-help" data-i18n="set_expenses_help">%s</small>%s</div>'
            % (esc(i18n.text(lang, "set_expenses_help")), warning), 1)
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
            field("ss", "set_ss"), expenses_field(),
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
    esc_val = values.get("escritura_date", "")
    cpcv_val = values.get("cpcv_date", "")
    return (
        '<h1 data-i18n="deal_title">%s</h1>'
        '<form method="post" action="/deals/review" class="two-col">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '<input type="hidden" name="form_locale" value="%s">'
        '<div><label for="deal-name" data-i18n="f_name">%s</label>'
        '<input id="deal-name" name="name" value="%s">%s</div>'
        '<div><label for="deal-commission" data-i18n="f_commission">%s</label>'
        '<input id="deal-commission" name="commission" value="%s">%s</div>'
        '<div><label for="deal-share" data-i18n="f_share">%s</label>'
        '<input id="deal-share" name="share" value="%s">%s</div>'
        '<fieldset><legend data-i18n="f_escritura">%s</legend>%s%s</fieldset>'
        '<fieldset><legend data-i18n="f_cpcv">%s</legend>%s%s</fieldset>'
        '<fieldset><legend data-i18n="f_stage">%s</legend>%s%s</fieldset>'
        '<div><label data-i18n="f_estimada"><input type="checkbox" name="escritura_estimada" value="1"%s> %s</label></div>'
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
            esc(i18n.text(lang, "f_escritura")), date_selects(lang, "escritura_date", esc_val),
            error_span(errors.get("escritura_date", "")),
            esc(i18n.text(lang, "f_cpcv")), date_selects(lang, "cpcv_date", cpcv_val),
            error_span(errors.get("cpcv_date", "")),
            esc(i18n.text(lang, "f_stage")), "".join(stages),
            error_span(errors.get("stage", "")),
            ' checked' if values.get("escritura_estimada") else '', esc(i18n.text(lang, "f_estimada")),
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
        for name in ("name", "commission", "share", "escritura_date", "cpcv_date", "stage", "status",
                     "agency", "form_locale", "escritura_estimada")
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
            esc(format_date(fields.get("escritura_date", "2026-11-15"), lang) + " · " + format_month(forecast_month_from_date(fields.get("escritura_date", "2026-11-15")), lang)),
            esc(i18n.text(lang, "st_" + fields.get("stage", "potencial"))
                if fields.get("stage") in STAGES else ""),
            figures_list(lang, share_cents, result),
            esc(csrf), hidden, shown, esc(key),
            esc(i18n.text(lang, "btn_confirm")),
        )
    )


def forecast_section(lang, month, deals, expenses_cents, estimated=False):
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
    def _deal_row(deal):
        cpcv = esc(format_date(deal.get("cpcv_date",""), lang)) if deal.get("cpcv_date") else ""
        ed = esc(format_date(deal.get("escritura_date",""), lang))
        if deal.get("escritura_estimada"):
            ed = ed + " " + esc(i18n.text(lang, "voice_estimada"))
        escritura = ed
        return '<tr class="deal-row"><td><a href="/deals/edit?id=%d">%s</a></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (deal["id"], esc(deal["name"]), esc(i18n.text(lang, "st_" + deal["stage"])), esc(format_amount(deal["part_base"], lang)), escritura, cpcv)
    rows = "".join(_deal_row(d) for d in deals)
    def _card(deal):
        cpcv = esc(format_date(deal.get("cpcv_date",""), lang)) if deal.get("cpcv_date") else ""
        ed = esc(format_date(deal.get("escritura_date",""), lang))
        if deal.get("escritura_estimada"):
            ed = ed + " " + esc(i18n.text(lang, "voice_estimada"))
        escritura = ed
        return ('<article class="deal-card">'
                '<a href="/deals/edit?id=%d">%s</a>'
                '<span class="deal-card__label" data-i18n="card_name">%s</span><span>%s</span>'
                '<span class="deal-card__label" data-i18n="card_stage">%s</span><span>%s</span>'
                '<span class="deal-card__label" data-i18n="card_amount">%s</span><span>%s</span>'
                '<span class="deal-card__label" data-i18n="card_escritura">%s</span><span>%s</span>'
                '<span class="deal-card__label" data-i18n="card_cpcv">%s</span><span>%s</span>'
                '</article>') % (
                    deal["id"], esc(deal["name"]),
                    esc(i18n.text(lang, "card_name")), esc(deal["name"]),
                    esc(i18n.text(lang, "card_stage")), esc(i18n.text(lang, "st_" + deal["stage"])),
                    esc(i18n.text(lang, "card_amount")), esc(format_amount(deal["part_base"], lang)),
                    esc(i18n.text(lang, "card_escritura")), escritura,
                    esc(i18n.text(lang, "card_cpcv")), cpcv,
                )
    cards = "".join(_card(d) for d in deals)
    cards_html = '<div class="deal-cards">%s</div>' % cards
    breakdown = result["protected_breakdown"]
    expense_key = "m_expenses_est" if estimated else "m_expenses"
    return (
        "<section><h2>%s</h2>"
        "<dl>"
        '<dt data-i18n="m_commission">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_bank">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_set_aside">%s</dt><dd>%s</dd>'
        '<dd class="money-breakdown">%s %s \u00b7 %s %s \u00b7 %s %s</dd>'
        '<dt data-i18n="%s">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_really">%s</dt><dd>%s</dd>'
        "</dl>"
        '<h3 data-i18n="m_deals">%s</h3><table class="deal-table"><thead><tr><th data-i18n="th_name">%s</th><th data-i18n="th_stage">%s</th><th data-i18n="th_amount">%s</th><th data-i18n="th_escritura">%s</th><th data-i18n="th_cpcv">%s</th></tr></thead><tbody>%s</tbody></table>%s</section>'
        % (
            esc(format_month(month, lang)),
            esc(i18n.text(lang, "m_commission")),
            esc(format_amount(result["commission"], lang)),
            esc(i18n.text(lang, "m_bank")),
            esc(format_amount(result["bank_inflow"], lang)),
            esc(i18n.text(lang, "m_set_aside")),
            esc(format_amount(result["protected_money"], lang)),
            esc(i18n.text(lang, "b_iva")),
            esc(format_amount(breakdown["iva"], lang)),
            esc(i18n.text(lang, "b_irs")),
            esc(format_amount(breakdown["irs_reserve"], lang)),
            esc(i18n.text(lang, "b_ss")),
            esc(format_amount(breakdown["ss_reserve"], lang)),
            expense_key, esc(i18n.text(lang, expense_key)),
            esc(format_amount(expenses_cents, lang)),
            esc(i18n.text(lang, "m_really")),
            esc(format_amount(result["really_available"], lang)),
            esc(i18n.text(lang, "m_deals")),
            esc(i18n.text(lang, "th_name")), esc(i18n.text(lang, "th_stage")), esc(i18n.text(lang, "th_amount")), esc(i18n.text(lang, "th_escritura")), esc(i18n.text(lang, "th_cpcv")),
            rows, cards_html,
        )
    )


def _month_really_and_set_aside(deals, expenses_cents):
    """(really yours, money to set aside) of one month's deals, as its card shows them."""
    result = month_figures(deals, expenses_cents)
    return result["really_available"], result["protected_money"]


def forecast_strip_figures(active_deals, expenses_for, today):
    """The three figures of the forecast strip, from the same engine.calc results the cards use.

    The window is the month of ``today`` and the next two. A total is the sum of
    the matching card lines. The estimated share of a total is what the deals with
    an estimated escritura date contribute to it, each taken from engine.calc on
    its own (bank inflow less the money to set aside; expenses belong to no deal).
    ``expenses_for(month)`` gives each month's expense cents.
    """
    start = today[:7]
    window = [add_months(start, i) for i in range(3)]
    in_window = [d for d in active_deals if derive_month(d.get("escritura_date", "")) in window]
    if not in_window:
        return None

    def totals(deals):
        really = aside = 0
        for month in window:
            r, a = _month_really_and_set_aside(
                [d for d in deals if derive_month(d.get("escritura_date", "")) == month], expenses_for(month))
            really += r
            aside += a
        return really, aside

    really, aside = totals(in_window)
    est_really = est_aside = 0
    for deal in in_window:
        if deal.get("escritura_estimada"):
            one = month_figures([deal], 0)
            est_really += one["bank_inflow"] - one["protected_money"]
            est_aside += one["protected_money"]
    future = sorted((d for d in active_deals if d.get("escritura_date", "") >= today),
                    key=lambda d: (d["escritura_date"], d["id"]))
    nxt = None
    if future:
        deal = future[0]
        nxt = {"date": deal["escritura_date"], "estimated": bool(deal.get("escritura_estimada")),
               "amount": month_figures([deal], 0)["bank_inflow"]}
    return {"really": really, "really_estimated": est_really,
            "aside": aside, "aside_estimated": est_aside, "next": nxt}


def forecast_strip(lang, active_deals, expenses_for):
    """The strip above the month cards: three figures, or one line when nothing falls in the window."""
    figures = forecast_strip_figures(active_deals, expenses_for, nl_today())
    if figures is None:
        return '<p class="forecast-strip forecast-strip--empty" data-i18n="strip_none">%s</p>' % esc(i18n.text(lang, "strip_none"))

    def estimated_note(cents):
        if not cents:
            return ""
        shown = format_amount(cents, lang)
        if cents % 100 == 0:
            shown = shown.replace(",00 \u20ac", " \u20ac") if lang == "pt-PT" else shown[:-3]
        return '<small class="strip-note">%s</small>' % esc(i18n.text(lang, "strip_estimated") % shown)

    def item(key, value, note, css):
        return ('<div class="strip-item %s"><span class="strip-label" data-i18n="%s">%s</span>'
                '<strong class="strip-value">%s</strong>%s</div>'
                % (css, key, esc(i18n.text(lang, key)), esc(value), note))

    nxt = figures["next"]
    if nxt is None:
        next_value, next_note = "\u2014", ""
    else:
        date = esc(format_date(nxt["date"], lang))
        if nxt["estimated"]:
            date += " " + esc(i18n.text(lang, "voice_estimada"))
        next_value, next_note = format_amount(nxt["amount"], lang), '<small class="strip-note">%s</small>' % date
    return ('<div class="forecast-strip">%s%s%s</div>' % (
        item("strip_yours", format_amount(figures["really"], lang), estimated_note(figures["really_estimated"]), "strip-yours"),
        item("strip_next", next_value, next_note, "strip-next"),
        item("strip_aside", format_amount(figures["aside"], lang), estimated_note(figures["aside_estimated"]), "strip-aside")))


DASH_LIMIT = 12


def short_month(year_month, lang):
    names = PT_MONTHS if lang == "pt-PT" else EN_MONTHS
    return "%s %s" % (names[int(year_month[5:7]) - 1][:3], year_month[:4])


def dashboard_window(query):
    """(offset in months, step) from the query string; anything invalid gives the default."""
    try:
        step = int(query.get("step", "1"))
    except ValueError:
        step = 1
    if step not in (1, 2):
        step = 1
    try:
        offset = int(query.get("w", "0"))
    except ValueError:
        offset = 0
    return max(-DASH_LIMIT, min(DASH_LIMIT, offset)), step


def dashboard_months(current, offset):
    """(the 3 Recebido months, the 3 Previsto months) of the window shifted by offset."""
    start = add_months(current, offset)
    return [add_months(start, i) for i in (-3, -2, -1)], [add_months(start, i) for i in (0, 1, 2)]


def dashboard_month(month, deals, rule):
    """One dashboard row from engine.calc: each stage before expenses, the month's expenses once."""
    in_month = [d for d in deals if derive_month(d.get("escritura_date", "")) == month]
    expenses, estimated = rule(month)
    total = month_figures(in_month, expenses)
    stages = {code: month_figures([d for d in in_month if d["stage"] == code], 0)["really_available"]
              for code in STAGES}
    return {"month": month, "bank": total["bank_inflow"], "aside": total["protected_money"],
            "expenses": expenses, "estimated": estimated, "really": total["really_available"],
            "stages": stages,
            "estimated_dates": sum(1 for d in in_month if d.get("escritura_estimada"))}


def _width(value, top):
    """A bar width class in twentieths of the largest bar."""
    if top <= 0 or value <= 0:
        return "w0"
    return "w%d" % max(1, min(20, round(value * 20 / top)))


def dashboard(lang, deals, rule, offset, step):
    """Headline, timeline controls, Recebido and Previsto, all from the same engine.calc rows."""
    past, future = dashboard_months(nl_today()[:7], offset)
    received = [dashboard_month(m, deals, rule) for m in past]
    expected = [dashboard_month(m, deals, rule) for m in future]
    top = max([r["bank"] for r in received]
              + [sum(max(v, 0) for v in r["stages"].values()) for r in expected] + [0])
    money = lambda cents: esc(format_amount(cents, lang))
    label = (i18n.text(lang, "dash_next3") if offset == 0
             else "%s – %s" % (short_month(future[0], lang), short_month(future[-1], lang)))
    headline = esc(i18n.text(lang, "dash_headline")) % {
        "label": esc(label),
        "really": "<b>%s</b>" % money(sum(r["really"] for r in expected)),
        "confirmed": '<span class="dash-confirmed">%s</span>' % money(
            sum(r["stages"]["confirmado"] for r in expected)),
    }

    def link(target, key, text, css):
        if target is None:
            return '<span class="%s" aria-disabled="true" title="%s">%s</span>' % (
                css + " dash-off", esc(i18n.text(lang, key)), text)
        return '<a class="%s" href="/?w=%d&amp;step=%d" title="%s" aria-label="%s">%s</a>' % (
            css, target, step, esc(i18n.text(lang, key)), esc(i18n.text(lang, key)), text)

    prev_target = max(-DASH_LIMIT, offset - step) if offset > -DASH_LIMIT else None
    next_target = min(DASH_LIMIT, offset + step) if offset < DASH_LIMIT else None
    steps = "".join(
        '<a href="/?w=%d&amp;step=%d" data-i18n="%s"%s>%s</a>' % (
            offset, n, key, ' aria-current="true"' if n == step else "", esc(i18n.text(lang, key)))
        for n, key in ((1, "dash_step1"), (2, "dash_step2")))
    controls = (
        '<nav class="dash-controls">%s<strong class="dash-range">%s – %s</strong>%s'
        '<span class="dash-steps">%s</span><a class="dash-today" href="/" data-i18n="dash_today">%s</a></nav>'
        % (link(prev_target, "dash_prev", "◀", "dash-arrow"),
           esc(short_month(past[0], lang)), esc(short_month(future[-1], lang)),
           link(next_target, "dash_next", "▶", "dash-arrow"),
           steps, esc(i18n.text(lang, "dash_today"))))

    def exp_label(row):
        return esc(i18n.text(lang, "dash_exp_est" if row["estimated"] else "dash_exp"))

    def received_row(row):
        line = esc(i18n.text(lang, "dash_line_past")) % {
            "exp_label": exp_label(row), "exp": money(row["expenses"]), "really": money(row["really"])}
        return ('<div class="dash-row"><span class="dash-month">%s</span>'
                '<span class="dash-bar"><span class="dash-seg dash-seg--confirmado %s"></span></span>'
                '<b class="dash-amount">%s</b><small class="dash-line">%s</small></div>'
                % (esc(short_month(row["month"], lang)), _width(row["bank"], top), money(row["bank"]), line))

    def expected_row(row):
        segments = "".join('<span class="dash-seg dash-seg--%s %s"></span>' % (code, _width(row["stages"][code], top))
                           for code in ("confirmado", "provavel", "potencial"))
        line = esc(i18n.text(lang, "dash_line_future")) % {
            "bank": money(row["bank"]), "aside": money(row["aside"]),
            "exp_label": exp_label(row), "exp": money(row["expenses"])}
        if row["estimated_dates"]:
            line += ' <em>%s</em>' % esc(i18n.text(lang, "dash_estimated_n") % row["estimated_dates"])
        return ('<div class="dash-row"><span class="dash-month">%s</span><span class="dash-bar">%s</span>'
                '<b class="dash-amount">%s</b><small class="dash-line">%s</small></div>'
                % (esc(short_month(row["month"], lang)), segments, money(row["really"]), line))

    legend = "".join('<span><i class="dash-seg--%s"></i>%s</span>' % (code, esc(i18n.text(lang, "st_" + code)))
                     for code in ("confirmado", "provavel", "potencial"))
    return (
        '<div class="dashboard"><p class="dash-headline">%s</p>%s<div class="dash-blocks">'
        '<section class="dash-card dash-received"><h2 data-i18n="dash_received">%s</h2>%s</section>'
        '<section class="dash-card dash-expected"><h2 data-i18n="dash_expected">%s</h2>%s'
        '<p class="dash-legend">%s</p></section></div></div>'
        % (headline, controls, esc(i18n.text(lang, "dash_received")), "".join(map(received_row, received)),
           esc(i18n.text(lang, "dash_expected")), "".join(map(expected_row, expected)), legend))


def validate_expense(lang, fields, deal_ids):
    """(errors, parsed) for the expense form; amounts by the form's locale, any valid date."""
    errors, parsed = {}, {}
    locale = fields.get("form_locale", lang)
    if locale not in i18n.SUPPORTED:
        locale = lang
    description = fields.get("description", "").strip()
    if not description:
        errors["description"] = i18n.text(lang, "err_description")
    parsed["description"] = description[:200]
    try:
        amount = parse_amount(fields.get("amount", ""), locale)
        if amount <= 0:
            errors["amount"] = i18n.text(lang, "err_positive")
        parsed["amount_cents"] = amount
    except ValueError:
        errors["amount"] = i18n.text(lang, "err_amount")
    date = fields.get("expense_date", "")
    if not date:
        y, m, d = (fields.get("expense_date_" + part, "").strip() for part in ("year", "month", "day"))
        date = "%s-%s-%s" % (y, m, d) if y and m and d else ""
    if not valid_date(date):
        errors["expense_date"] = i18n.text(lang, "err_date")
    parsed["expense_date"] = date
    status = fields.get("status", "")
    if status not in store.EXPENSE_STATUSES:
        status = "paid"
    parsed["status"] = status
    raw_deal = fields.get("deal_id", "").strip()
    parsed["deal_id"] = None
    if raw_deal:
        try:
            deal_id = int(raw_deal)
        except ValueError:
            deal_id = None
        if deal_id not in deal_ids:
            errors["deal_id"] = i18n.text(lang, "err_amount")
        parsed["deal_id"] = deal_id
    return errors, parsed


def expense_form(lang, csrf, action, values, errors, deals, submit_key):
    def text_field(name, key):
        return ('<div><label for="exp-%s" data-i18n="%s">%s</label><input id="exp-%s" name="%s" value="%s">%s</div>'
                % (name, key, esc(i18n.text(lang, key)), name, name, esc(values.get(name, "")),
                   error_span(errors.get(name, ""))))
    status = values.get("status", "paid")
    statuses = "".join('<label><input type="radio" name="status" value="%s"%s>%s</label>' % (
        code, " checked" if status == code else "", esc(i18n.text(lang, key)))
        for code, key in (("paid", "exp_paid"), ("planned", "exp_planned")))
    chosen = str(values.get("deal_id") or "")
    options = '<option value="">%s</option>' % esc(i18n.text(lang, "exp_no_deal")) + "".join(
        '<option value="%d"%s>%s</option>' % (d["id"], " selected" if str(d["id"]) == chosen else "", esc(d["name"]))
        for d in deals)
    return (
        '<form method="post" action="%s" class="two-col">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '<input type="hidden" name="form_locale" value="%s">'
        '%s%s'
        '<fieldset><legend data-i18n="exp_date">%s</legend>%s%s</fieldset>'
        '<fieldset><legend data-i18n="exp_status">%s</legend>%s</fieldset>'
        '<div><label for="exp-deal" data-i18n="exp_deal">%s</label><select id="exp-deal" name="deal_id">%s</select>%s</div>'
        '<button type="submit" data-i18n="%s">%s</button></form>'
        % (action, esc(csrf), esc(lang),
           text_field("description", "exp_description"), text_field("amount", "exp_amount"),
           esc(i18n.text(lang, "exp_date")), date_selects(lang, "expense_date", values.get("expense_date", "")),
           error_span(errors.get("expense_date", "")),
           esc(i18n.text(lang, "exp_status")), statuses,
           esc(i18n.text(lang, "exp_deal")), options, error_span(errors.get("deal_id", "")),
           submit_key, esc(i18n.text(lang, submit_key))))


def expense_items(lang, items, deals):
    names = {d["id"]: d["name"] for d in deals}
    rows = "".join(
        '<li class="expense-item"><a href="/expenses/edit?id=%d">%s</a> · %s · <b>%s</b> · %s%s</li>'
        % (e["id"], esc(e["description"]), esc(format_date(e["expense_date"], lang)),
           esc(format_amount(e["amount_cents"], lang)),
           esc(i18n.text(lang, "exp_paid" if e["status"] == "paid" else "exp_planned")),
           (" · " + esc(names[e["deal_id"]])) if e["deal_id"] in names else "")
        for e in items)
    return '<ul class="expense-list">%s</ul>' % rows


def expenses_page(lang, csrf, month, items, deals, values, errors):
    current = nl_today()[:7]
    month_nav = (
        '<nav class="dash-controls">'
        '<a class="dash-arrow" href="/expenses?month=%s" title="%s" aria-label="%s">◀</a>'
        '<strong class="dash-range">%s</strong>'
        '<a class="dash-arrow" href="/expenses?month=%s" title="%s" aria-label="%s">▶</a>'
        '<a class="dash-today" href="/expenses" data-i18n="exp_today">%s</a></nav>'
        % (add_months(month, -1), esc(i18n.text(lang, "exp_prev")), esc(i18n.text(lang, "exp_prev")),
           esc(format_month(month, lang)),
           add_months(month, 1), esc(i18n.text(lang, "exp_next")), esc(i18n.text(lang, "exp_next")),
           esc(i18n.text(lang, "exp_today"))))
    if items:
        listing = expense_items(lang, items, deals) + '<p class="expense-total"><span data-i18n="exp_total">%s</span>: <b>%s</b></p>' % (
            esc(i18n.text(lang, "exp_total")), esc(format_amount(sum(e["amount_cents"] for e in items), lang)))
    else:
        listing = '<p data-i18n="exp_none">%s</p>' % esc(i18n.text(lang, "exp_none"))
    if "expense_date" not in values:
        values = dict(values, expense_date=nl_today() if month == current else month + "-01")
    return (
        '<h1 data-i18n="exp_title">%s</h1>%s<section class="dash-card">%s</section>'
        '<h2 data-i18n="exp_add">%s</h2>%s'
        % (esc(i18n.text(lang, "exp_title")), month_nav, listing, esc(i18n.text(lang, "exp_add")),
           expense_form(lang, csrf, "/expenses/add", values, errors, deals, "exp_add")))


def expense_edit_page(lang, csrf, expense_id, values, errors, deals):
    return (
        '<h1 data-i18n="exp_edit">%s</h1>%s'
        '<form method="post" action="/expenses/delete?id=%d"><input type="hidden" name="csrf_token" value="%s">'
        '<button type="submit" class="btn-secondary" data-i18n="exp_delete">%s</button></form>'
        % (esc(i18n.text(lang, "exp_edit")),
           expense_form(lang, csrf, "/expenses/update?id=%d" % expense_id, values, errors, deals, "exp_save"),
           expense_id, esc(csrf), esc(i18n.text(lang, "exp_delete"))))


def deal_expenses_section(lang, items):
    body = expense_items(lang, items, []) if items else '<p data-i18n="exp_deal_none">%s</p>' % esc(
        i18n.text(lang, "exp_deal_none"))
    return '<section class="dash-card deal-expenses"><h2 data-i18n="exp_deal_title">%s</h2>%s</section>' % (
        esc(i18n.text(lang, "exp_deal_title")), body)


def edit_form_html(lang, csrf, deal_id, values, errors):
    stages_html = "".join(
        '<label><input type="radio" name="stage" value="%s"%s>%s</label>'
        % (code, ' checked' if values.get("stage", "") == code else '', esc(i18n.text(lang, "st_" + code)))
        for code in STAGES
    )
    esc_val = values.get("escritura_date", "")
    cpcv_val = values.get("cpcv_date", "")
    status = values.get("status", "active")
    status_opts = '<label><input type="radio" name="status" value="active"%s>%s</label><label><input type="radio" name="status" value="fallen"%s>%s</label>' % (
        ' checked' if status != 'fallen' else '', esc(i18n.text(lang, "st_active")),
        ' checked' if status == 'fallen' else '', esc(i18n.text(lang, "st_fallen")),
    )
    return (
        '<h1 data-i18n="deal_edit_title">%s</h1>'
        '<form method="post" action="/deals/update?id=%d" class="two-col">'
        '<input type="hidden" name="csrf_token" value="%s">'
        '<input type="hidden" name="form_locale" value="%s">'
        '<div><label for="deal-name" data-i18n="f_name">%s</label>'
        '<input id="deal-name" name="name" value="%s">%s</div>'
        '<div><label for="deal-commission" data-i18n="f_commission">%s</label>'
        '<input id="deal-commission" name="commission" value="%s">%s</div>'
        '<div><label for="deal-share" data-i18n="f_share">%s</label>'
        '<input id="deal-share" name="share" value="%s">%s</div>'
        '<fieldset><legend data-i18n="f_escritura">%s</legend>%s%s</fieldset>'
        '<fieldset><legend data-i18n="f_cpcv">%s</legend>%s%s</fieldset>'
        '<fieldset><legend data-i18n="f_status">%s</legend>%s%s</fieldset>'
        '<fieldset><legend data-i18n="f_stage">%s</legend>%s%s</fieldset>'
        '<div><label data-i18n="f_estimada"><input type="checkbox" name="escritura_estimada" value="1"%s> %s</label></div>'
        '<div><label for="deal-agency" data-i18n="f_agency">%s</label>'
        '<input id="deal-agency" name="agency" value="%s">%s</div>'
        '<button type="submit" data-i18n="btn_confirm">%s</button>'
        "</form>"
        '<p><a href="/deals/delete?id=%d" data-i18n="delete_deal_button">%s</a></p>'
        % (
            esc(i18n.text(lang, "deal_edit_title")), deal_id, esc(csrf), esc(lang),
            esc(i18n.text(lang, "f_name")), esc(values.get("name", "")), error_span(errors.get("name", "")),
            esc(i18n.text(lang, "f_commission")), esc(values.get("commission", "")), error_span(errors.get("commission", "")),
            esc(i18n.text(lang, "f_share")), esc(values.get("share", "")), error_span(errors.get("share", "")),
            esc(i18n.text(lang, "f_escritura")), date_selects(lang, "escritura_date", esc_val), error_span(errors.get("escritura_date", "")),
            esc(i18n.text(lang, "f_cpcv")), date_selects(lang, "cpcv_date", cpcv_val), error_span(errors.get("cpcv_date", "")),
            esc(i18n.text(lang, "f_status")), status_opts, error_span(errors.get("status", "")),
            esc(i18n.text(lang, "f_stage")), stages_html, error_span(errors.get("stage", "")),
            ' checked' if values.get("escritura_estimada") else '', esc(i18n.text(lang, "f_estimada")),
            esc(i18n.text(lang, "f_agency")), esc(values.get("agency", "")), error_span(errors.get("agency", "")),
            esc(i18n.text(lang, "btn_confirm")),
            deal_id, esc(i18n.text(lang, "delete_deal_button")),
        )
    )


def implausible_flags(lang, parsed):
    """Return errors/warnings for implausible values; callers decide refusal vs confirmation."""
    out = {}
    share_raw = parsed.get("share_rate", "")
    # share entered as "4" when 40 % likely -> value 0.04
    try:
        from decimal import Decimal as _D
        if share_raw and _D(share_raw) == _D("0.04"):
            out["share"] = i18n.text(lang, "err_confirm_share")
    except Exception:
        pass
    comm = parsed.get("commission_cents", None)
    if comm is not None and 0 < comm < 10000:
        out["commission"] = i18n.text(lang, "err_small_commission")
    return out

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
    raw_comm = commission_text.strip()
    if not raw_comm:
        errors["commission"] = i18n.text(lang, "err_commission")
    elif raw_comm.startswith("-"):
        errors["commission"] = i18n.text(lang, "err_negative")
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
    # escritura_date: build from selects or accept full date; month accepted as legacy alias
    esc = fields.get("escritura_date", "")
    if not esc:
        y = fields.get("escritura_date_year", "").strip()
        m = fields.get("escritura_date_month", "").strip()
        d = fields.get("escritura_date_day", "").strip()
        if y or m or d:
            esc = f"{y}-{m}-{d}" if y and m and d else ""
        elif fields.get("month", "").strip() and valid_month(fields.get("month", "").strip()):
            esc = fields.get("month", "").strip() + "-01"
    if not valid_date(esc):
        errors["escritura_date"] = i18n.text(lang, "err_month")
    else:
        parsed["escritura_date"] = esc
        parsed["month"] = forecast_month_from_date(esc)
    # cpcv_date: optional
    cpcv = fields.get("cpcv_date", "")
    if not cpcv:
        y = fields.get("cpcv_date_year", "").strip()
        m = fields.get("cpcv_date_month", "").strip()
        d = fields.get("cpcv_date_day", "").strip()
        if y and m and d:
            cpcv = f"{y}-{m}-{d}"
        elif y or m or d:
            # partial -> invalid
            cpcv = f"{y}-{m}-{d}"
    if cpcv:
        if not valid_date(cpcv):
            errors["cpcv_date"] = i18n.text(lang, "err_month")
        else:
            parsed["cpcv_date"] = cpcv
            parsed["stage"] = "confirmado"
            if fields.get("stage", "") and fields.get("stage", "") not in STAGES:
                pass
            else:
                parsed["stage"] = "confirmado"
    # stage: if cpcv set, already confirmed; otherwise check
    if "stage" not in parsed:
        if fields.get("stage", "") not in STAGES:
            errors["stage"] = i18n.text(lang, "err_stage")
        else:
            parsed["stage"] = fields.get("stage", "")
    # status: fallen or active
    status = fields.get("status", "active").strip() or "active"
    if status not in ("active", "fallen"):
        status = "active"
    parsed["status"] = status
    # cpcv defaults
    if "cpcv_date" not in parsed:
        parsed["cpcv_date"] = cpcv if cpcv and valid_date(cpcv) else None
        if not parsed["cpcv_date"]:
            # also check raw cpcv field if valid date passed directly
            raw_c = fields.get("cpcv_date", "").strip()
            if raw_c and valid_date(raw_c):
                parsed["cpcv_date"] = raw_c
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
    raw_exp = expenses_text.strip()
    if not raw_exp:
        errors["expenses"] = i18n.text(lang, "err_amount")
    elif raw_exp.startswith("-"):
        errors["expenses"] = i18n.text(lang, "err_negative")
    else:
        try:
            expenses = parse_amount(expenses_text, form_locale)
            if expenses < 0:
                errors["expenses"] = i18n.text(lang, "err_negative")
            else:
                parsed["expenses"] = expenses
        except ValueError:
            errors["expenses"] = i18n.text(lang, "err_amount")
    return errors, parsed


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_FILES = {
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
    "/static/voice.js": ("voice.js", "text/javascript; charset=utf-8"),
}
VOICE_PATHS = ("/voice/transcribe", "/voice/extract", "/voice/confirm", "/voice/cancel")
MAX_AUDIO_BODY_BYTES = 16000 * 2 * 61 + 4096


def application(environ, start_response):
    session, new_cookies = session_for(environ)
    _REQUEST.tenant_id = session.get("tenant_id") if session.get("authenticated") else None
    lang = language_for(environ)
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/") or "/"

    # ── Session gate: default deny, public list only
    if not is_public_path(path):
        if not session.get("authenticated"):
            def _redirect(location, cookies=()):
                data = b""
                headers = [("Location", location), ("Content-Type", "text/html; charset=utf-8"),
                           ("Content-Length", "0")]
                for cookie in cookies:
                    headers.append(("Set-Cookie", cookie))
                for cookie in new_cookies:
                    headers.append(("Set-Cookie", cookie))
                start_response("303 See Other", headers)
                return [data]
            return _redirect("/signin")

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
               esc(i18n.text(lang, "refused_msg"))), signed_in=bool(session.get("authenticated")),
        )
        return respond("403 Forbidden", body)

    def too_large():
        body = page(
            lang, session["csrf"],
            i18n.text(lang, "refused_title"),
            '<h1 data-i18n="refused_title">%s</h1>'
            '<p data-i18n="refused_msg">%s</p>'
            % (esc(i18n.text(lang, "refused_title")),
               esc(i18n.text(lang, "refused_msg"))), signed_in=bool(session.get("authenticated")),
        )
        return respond("413 Content Too Large", body)

    def bad_request():
        body = page(
            lang, session["csrf"],
            i18n.text(lang, "refused_title"),
            '<h1 data-i18n="refused_title">%s</h1>'
            '<p data-i18n="refused_msg">%s</p>'
            % (esc(i18n.text(lang, "refused_title")),
               esc(i18n.text(lang, "refused_msg"))), signed_in=bool(session.get("authenticated")),
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

    def json_reply(status, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Cache-Control", "no-store"),
            ("Content-Security-Policy", "default-src 'self'"),
            ("X-Content-Type-Options", "nosniff"),
            ("Content-Length", str(len(payload))),
        ]
        for cookie in new_cookies:
            headers.append(("Set-Cookie", cookie))
        start_response(status, headers)
        return [payload]

    def voice_route(route):
        """Voice endpoints: JSON for the page script, a page without it."""
        from app import voice_handlers as vh
        query = read_query(environ)
        as_json = query.get("format") == "json"
        raw = None
        if route == "/voice/transcribe":
            try:
                length = int(str(environ.get("CONTENT_LENGTH", "0") or 0).strip())
            except (TypeError, ValueError):
                length = 0
            fields = dict(query)
            if length < 0 or length > MAX_AUDIO_BODY_BYTES:
                if csrf_ok(fields):
                    # The body is not read: the app must not read an
                    # over-limit body to measure it. The diagnostic keeps
                    # the reported sample rate and an estimated duration,
                    # with peak null (the panel shows a dash).
                    refusal = {"state": "error", "lang": lang,
                               "conversation_id": query.get("conversation_id", ""),
                               "transcript": "",
                               "message": i18n.text(lang, "voice_wav_error"),
                               "diagnostic": {
                                   "sample_rate": voice_audio.clean_rate(query.get("sample_rate")),
                                   "duration_seconds": round(max(length - 44, 0) / 32000.0, 2),
                                   "peak": None}}
                    if as_json:
                        return json_reply("200 OK", refusal)
                    return respond("200 OK", page(
                        lang, session["csrf"], i18n.text(lang, "voice_falar"),
                        vh.html_body(refusal, session["csrf"]), signed_in=True))
                return too_large()
            raw = environ.get("wsgi.input").read(length) if length > 0 else b""
        else:
            fields = read_post_form()
            if not isinstance(fields, dict):
                return fields
            as_json = as_json or fields.get("format") == "json"
        if not csrf_ok(fields):
            if as_json:
                return json_reply("403 Forbidden", {
                    "state": "error", "lang": lang, "conversation_id": "",
                    "transcript": "", "message": i18n.text(lang, "refused_msg")})
            return forbidden()
        env = vh.make_env(DB_PATH, session, lang)
        if route == "/voice/transcribe":
            data = vh.handle_audio(env, fields, raw)
        elif route == "/voice/extract":
            data = vh.handle_text(env, fields)
        elif route == "/voice/confirm":
            data = vh.handle_confirm(env, fields)
        else:
            data = vh.handle_cancel(env, fields)
        if as_json:
            return json_reply("200 OK", data)
        if data["state"] == "saved":
            return redirect("/")
        return respond("200 OK", page(
            data["lang"], session["csrf"], i18n.text(data["lang"], "voice_falar"),
            vh.html_body(data, session["csrf"]), signed_in=True))

    # ── Auth routes (before session gate: signin/verify are public) ──
    if path == "/signin" and method == "GET":
        body = page(lang, session["csrf"], i18n.text(lang, "signin_title"),
                    signin_page(lang, session["csrf"], "", ""), "/signin")
        return respond("200 OK", body)
    if path == "/signin" and method == "POST":
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if not csrf_ok(fields):
            body = page(lang, session["csrf"], i18n.text(lang, "check_email_title"),
                        '<h1 data-i18n="refused_title">%s</h1><p class="error">%s</p><p><a href="/signin">%s</a></p>'
                        % (esc(i18n.text(lang, "refused_title")), esc(i18n.text(lang, "err_csrf")),
                           esc(i18n.text(lang, "signin_title"))))
            return respond("200 OK", body)
        email = fields.get("email", "").strip()
        if not auth.validate_email(email):
            body = page(lang, session["csrf"], i18n.text(lang, "check_email_title"),
                        '<h1 data-i18n="check_email_title">%s</h1>'
                        '<p class="error">%s</p>'
                        '<p><a href="/signin">%s</a></p>'
                        % (esc(i18n.text(lang, "check_email_title")), esc(i18n.text(lang, "err_email")),
                           esc(i18n.text(lang, "signin_title"))))
            return respond("200 OK", body)
        ip = environ.get("REMOTE_ADDR", "") or environ.get("HTTP_X_FORWARDED_FOR", "")
        ok, result = auth.request_link(DB_PATH, email, ip, lang=lang)
        if not ok:
            msg = i18n.text(lang, result) if result in i18n.STRINGS[lang] else i18n.text(lang, "signin_rate")
            body = page(lang, session["csrf"], i18n.text(lang, "check_email_title"),
                        '<h1 data-i18n="check_email_title">%s</h1><p class="error">%s</p><p><a href="/signin">%s</a></p>'
                        % (esc(i18n.text(lang, "check_email_title")), esc(msg),
                           esc(i18n.text(lang, "signin_title"))))
            return respond("200 OK", body)
        token = result
        base_url = os.environ.get("APP_BASE_URL", "http://localhost:8000")
        mail.send_signin_link(email, token, lang, base_url)
        body = page(lang, session["csrf"], i18n.text(lang, "check_email_title"),
                    check_email_page(lang, esc(email)) + signin_page(lang, session["csrf"], email, ""), "/signin")
        return respond("200 OK", body)
    if path == "/auth/verify" and method == "GET":
        query = read_query(environ)
        token = query.get("token", "")
        if not token:
            body = page(lang, session["csrf"], i18n.text(lang, "signin_title"),
                        '<p class="error" data-i18n="auth_invalid">%s</p>' % esc(i18n.text(lang, "auth_invalid")), "/signin")
            return respond("200 OK", body)
        link = auth.verify_link(DB_PATH, token)
        if link is None:
            body = page(lang, session["csrf"], i18n.text(lang, "signin_title"),
                        '<p class="error" data-i18n="auth_invalid">%s</p>' % esc(i18n.text(lang, "auth_invalid")), "/signin")
            return respond("200 OK", body)
        sess = auth.create_session_for_link(DB_PATH, link)
        cookie = "session=%s; HttpOnly; Path=/; SameSite=Lax; Max-Age=%d" % (sess["id"], auth.SESSION_EXPIRY_SECONDS)
        base_url = os.environ.get("APP_BASE_URL", "http://localhost:8000")
        if base_url.startswith("https://"):
            cookie += "; Secure"
        return respond("303 See Other", "", [("Location", "/"), ("Set-Cookie", cookie)])
    if path == "/signout" and method == "POST":
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if not csrf_ok(fields):
            return forbidden()
        if session.get("authenticated"):
            store.delete_session(DB_PATH, session["id"])
        clear = "session=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax"
        return respond("303 See Other", "", [("Location", "/signin"), ("Set-Cookie", clear)])
    if path == "/account/delete" and method == "GET":
        if not session.get("authenticated"):
            return redirect("/signin")
        body = page(lang, session["csrf"], i18n.text(lang, "delete_title"),
                    delete_form(lang, session["csrf"], ""), "/account/delete", signed_in=True)
        return respond("200 OK", body)
    if path == "/account/delete" and method == "POST":
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if not csrf_ok(fields):
            return forbidden()
        if not session.get("authenticated"):
            return redirect("/signin")
        typed = fields.get("email", "").strip().lower()
        actual = session.get("email", "").strip().lower()
        if typed != actual:
            body = page(lang, session["csrf"], i18n.text(lang, "delete_title"),
                        delete_form(lang, session["csrf"], i18n.text(lang, "delete_mismatch")), "/account/delete", signed_in=True)
            return respond("200 OK", body)
        store.delete_tenant(DB_PATH, session["tenant_id"])
        clear = "session=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax"
        body = page(lang, session["csrf"], i18n.text(lang, "delete_done"),
                    '<p data-i18n="delete_done">%s</p>' % esc(i18n.text(lang, "delete_done")), signed_in=True)
        return respond("200 OK", body, [("Set-Cookie", clear)])

    if path in STATIC_FILES:
        filename, content_type = STATIC_FILES[path]
        try:
            with open(os.path.join(STATIC_DIR, filename), "rb") as handle:
                data = handle.read()
        except OSError:
            start_response("404 Not Found", [("Content-Length", "0")])
            return [b""]
        headers = [
            ("Content-Type", content_type),
            ("Content-Security-Policy", "default-src 'self'"),
            ("X-Content-Type-Options", "nosniff"),
            ("Content-Length", str(len(data))),
        ]
        start_response("200 OK", headers)
        return [data]

    if path == "/" and method == "GET":
        query = read_query(environ)
        only = query.get("month", "")
        rule = expense_rule(session["tenant_id"])
        offset, step = dashboard_window(query)
        if only and valid_month(only):
            months = [only]
        else:
            months = store.months_with_deals(DB_PATH, tenant_id=session["tenant_id"])
        if not months:
            body = page(
                lang, session["csrf"], i18n.text(lang, "home_title"),
                '<h1 data-i18n="home_title">%s</h1>%s'
                '<p data-i18n="home_empty">%s</p>'
                '<p><a href="/deals/new" data-i18n="home_new">%s</a></p>'
                % (esc(i18n.text(lang, "home_title")),
                   dashboard(lang, [], rule, offset, step),
                   esc(i18n.text(lang, "home_empty")),
                   esc(i18n.text(lang, "home_new"))),
                "/", signed_in=True,
            )
            return respond("200 OK", body)
        # Use active deals for forecast (exclude fallen) — never include fallen even if helper raises
        active_deals = store.list_active_deals(DB_PATH, tenant_id=session["tenant_id"])
        active_months = sorted(set(derive_month(d.get("escritura_date", "")) for d in active_deals if d.get("escritura_date")))
        from collections import defaultdict as _dd
        by_month = _dd(list)
        for d in active_deals:
            m = derive_month(d.get("escritura_date", ""))
            by_month[m].append(d)
        if active_months:
            sections = "".join(
                forecast_section(lang, m, by_month.get(m, []), *rule(m))
                for m in sorted(active_months)
            )
        else:
            sections = ""
        fallen_html = ""
        fallen = store.list_fallen_deals(DB_PATH, session["tenant_id"])
        if fallen:
            items_f = "".join('<li><a href="/deals/edit?id=%d">%s</a> \u00b7 %s</li>' % (d["id"], esc(d["name"]), esc(i18n.text(lang, "st_fallen"))) for d in fallen)
            fallen_html = '<details><summary data-i18n="fallen_title">%s (%d)</summary><ul>%s</ul></details>' % (esc(i18n.text(lang, "fallen_title")), len(fallen), items_f)
        body = page(lang, session["csrf"], i18n.text(lang, "home_title"),
                    '<h1 data-i18n="home_title">%s</h1>%s%s<div class="forecast-grid">%s</div>%s'
                    % (esc(i18n.text(lang, "home_title")),
                       dashboard(lang, active_deals, rule, offset, step),
                       forecast_strip(lang, active_deals, lambda m: rule(m)[0]), sections, fallen_html),
                    "/", signed_in=True)
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
        settings = store.get_settings(DB_PATH, tenant_id=session["tenant_id"])
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
                    settings_form(lang, session["csrf"], values, {}),
                    "/settings", signed_in=True)
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
                        settings_form(lang, session["csrf"], values, errors),
                        "/settings", signed_in=True)
            return respond("200 OK", body)
        store.save_settings(DB_PATH, {
            "share_rate": parsed["share"],
            "iva_rate": parsed["iva"],
            "retencao_rate": parsed["retencao"],
            "irs_rate": parsed["irs"],
            "ss_rate": parsed["ss"],
            "expenses_cents": parsed["expenses"],
        }, tenant_id=session["tenant_id"])
        return redirect("/settings")

    if path == "/expenses" and method == "GET":
        query = read_query(environ)
        month = query.get("month", "")
        if not valid_month(month):
            month = nl_today()[:7]
        deals = store.list_deals(DB_PATH, tenant_id=session["tenant_id"])
        body = page(lang, session["csrf"], i18n.text(lang, "exp_title"),
                    expenses_page(lang, session["csrf"], month,
                                  store.list_expenses(DB_PATH, session["tenant_id"], month=month), deals, {}, {}),
                    "/expenses", signed_in=True)
        return respond("200 OK", body)

    if path in ("/expenses/add", "/expenses/update", "/expenses/delete") and method == "POST":
        expense = None
        if path != "/expenses/add":
            try:
                expense_id = int(read_query(environ).get("id", ""))
            except (TypeError, ValueError):
                expense_id = None
            expense = store.get_expense(DB_PATH, session["tenant_id"], expense_id) if expense_id else None
            if expense is None:
                return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if not csrf_ok(fields):
            return forbidden()
        if path == "/expenses/delete":
            store.delete_expense(DB_PATH, session["tenant_id"], expense["id"])
            return redirect("/expenses?month=" + expense["expense_date"][:7])
        deals = store.list_deals(DB_PATH, tenant_id=session["tenant_id"])
        errors, parsed = validate_expense(lang, fields, {d["id"] for d in deals})
        if not errors:
            try:
                if expense is None:
                    store.insert_expense(DB_PATH, session["tenant_id"], parsed)
                elif not store.update_expense(DB_PATH, session["tenant_id"], expense["id"], parsed):
                    return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
            except ValueError:
                errors["deal_id"] = i18n.text(lang, "err_amount")
        if not errors:
            return redirect("/expenses?month=" + parsed["expense_date"][:7])
        values = {name: fields.get(name, "") for name in ("description", "amount", "status", "deal_id")}
        values["expense_date"] = parsed["expense_date"]
        if expense is None:
            month = parsed["expense_date"][:7] if valid_date(parsed["expense_date"]) else nl_today()[:7]
            content = expenses_page(lang, session["csrf"], month,
                                    store.list_expenses(DB_PATH, session["tenant_id"], month=month),
                                    deals, values, errors)
        else:
            content = expense_edit_page(lang, session["csrf"], expense["id"], values, errors, deals)
        return respond("200 OK", page(lang, session["csrf"], i18n.text(lang, "exp_title"), content,
                                      "/expenses", signed_in=True))

    if path == "/expenses/edit" and method == "GET":
        try:
            expense_id = int(read_query(environ).get("id", ""))
        except (TypeError, ValueError):
            expense_id = None
        expense = store.get_expense(DB_PATH, session["tenant_id"], expense_id) if expense_id else None
        if expense is None:
            return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
        values = {"description": expense["description"],
                  "amount": format_edit_amount(expense["amount_cents"], lang),
                  "expense_date": expense["expense_date"], "status": expense["status"],
                  "deal_id": expense["deal_id"]}
        deals = store.list_deals(DB_PATH, tenant_id=session["tenant_id"])
        return respond("200 OK", page(lang, session["csrf"], i18n.text(lang, "exp_edit"),
                                      expense_edit_page(lang, session["csrf"], expense["id"], values, {}, deals),
                                      "/expenses", signed_in=True))

    if path == "/deals/new" and method == "GET":
        settings = store.get_settings(DB_PATH, tenant_id=session["tenant_id"])
        body = page(lang, session["csrf"], i18n.text(lang, "deal_title"),
                    deal_form(lang, session["csrf"], {}, {}, settings),
                    "/deals/new", signed_in=True)
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
        settings = store.get_settings(DB_PATH, tenant_id=session["tenant_id"])
        errors, parsed = validate_deal(lang, fields, form_locale)
        if settings is None:
            errors["commission"] = i18n.text(lang, "err_settings")
        # implausible-input handling: refuse unless explicitly confirmed
        if not errors:
            flags = implausible_flags(lang, parsed)
            if flags:
                # allow if confirmation field present
                for k in list(flags):
                    if fields.get("confirm_"+k) == "1":
                        del flags[k]
                if flags:
                    errors.update(flags)
        if errors:
            values = {name: fields.get(name, "") for name in
                      ("name", "commission", "share", "stage",
                       "agency")}
            body = page(
                lang, session["csrf"], i18n.text(lang, "deal_title"),
                '<p class="notice">%s</p>%s'
                % (esc(i18n.text(lang, "err_settings"))
                   if settings is None else "",
                   deal_form(lang, session["csrf"], values, errors,
                             settings)), signed_in=True)
            return respond("200 OK", body)
        share_cents = agent_share(parsed["commission_cents"],
                                  parsed["share_rate"])
        result = single_figures(share_cents, settings,
                                expense_rule(session["tenant_id"])(parsed["month"])[0])
        key = secrets.token_urlsafe(16)
        shown = {
            "name": parsed["name"],
            "commission": fields.get("commission", ""),
            "share": fields.get("share", ""),
            "escritura_date": parsed.get("escritura_date", ""),
            "cpcv_date": parsed.get("cpcv_date", "") or "",
            "month": parsed["month"],
            "stage": parsed["stage"],
            "status": parsed.get("status", "active"),
            "agency": parsed["agency"],
            "escritura_estimada": "1" if fields.get("escritura_estimada") else "",
            "form_locale": form_locale,
        }
        body = page(lang, session["csrf"], i18n.text(lang, "rev_title"),
                    review_page(lang, session["csrf"], shown, share_cents,
                                result, False, key), signed_in=True)
        return respond("200 OK", body)

    if path == "/deals/confirm" and method == "POST":
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if "shown_share" in fields and "idempotency_key" in fields:
            for name in ("name", "commission", "share", "escritura_date", "cpcv_date", "stage", "status",
                         "agency", "form_locale", "escritura_estimada"):
                fields[name] = unquote(fields.get(name, ""))
        if not csrf_ok(fields):
            return forbidden()
        form_locale = fields.get("form_locale", lang)
        if form_locale not in i18n.SUPPORTED:
            form_locale = lang
        settings = store.get_settings(DB_PATH, tenant_id=session["tenant_id"])
        errors, parsed = validate_deal(lang, fields, form_locale)
        if settings is None:
            errors["commission"] = i18n.text(lang, "err_settings")
        if errors:
            values = {name: fields.get(name, "") for name in
                      ("name", "commission", "share", "stage",
                       "agency")}
            body = page(
                lang, session["csrf"], i18n.text(lang, "deal_title"),
                deal_form(lang, session["csrf"], values, errors, settings), signed_in=True)
            return respond("200 OK", body)
        share_cents = agent_share(parsed["commission_cents"],
                                  parsed["share_rate"])
        result = single_figures(share_cents, settings,
                                expense_rule(session["tenant_id"])(parsed["month"])[0])
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
                "escritura_date": parsed.get("escritura_date", ""),
                "cpcv_date": parsed.get("cpcv_date","") or "",
                "month": parsed["month"],
                "stage": parsed["stage"],
                "status": parsed.get("status","active"),
                "agency": parsed["agency"],
                "escritura_estimada": "1" if fields.get("escritura_estimada") else "",
                "form_locale": form_locale,
            }
            body = page(
                lang, session["csrf"], i18n.text(lang, "rev_title"),
                review_page(lang, session["csrf"], shown_fields, share_cents,
                            result, True, secrets.token_urlsafe(16)), signed_in=True)
            return respond("200 OK", body)
        store.insert_deal(DB_PATH, {
            "name": parsed["name"],
            "agency": parsed["agency"],
            "escritura_date": parsed.get("escritura_date", ""),
            "month": parsed["month"],
            "stage": parsed["stage"],
            "status": parsed.get("status","active"),
            "cpcv_date": parsed.get("cpcv_date"),
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
            "escritura_estimada": 1 if fields.get("escritura_estimada") else 0,
        }, tenant_id=session["tenant_id"])
        return redirect("/?month=" + parsed["month"])

    if path == "/deals/edit" and method == "GET":
        query = read_query(environ)
        raw_id = query.get("id", "")
        try:
            did = int(raw_id)
        except (TypeError, ValueError):
            return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
        deal = store.get_deal(DB_PATH, did, session["tenant_id"])
        if deal is None:
            return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
        settings = store.get_settings(DB_PATH, tenant_id=session["tenant_id"])
        values = {
            "name": deal["name"],
            "commission": format_edit_amount(deal["agency_commission_cents"], lang),
            "share": format_edit_percent(deal["share_rate_used"], lang),
            "escritura_date": deal.get("escritura_date", ""),
            "cpcv_date": deal.get("cpcv_date") or "",
            "status": deal.get("status","active"),
            "stage": deal["stage"],
            "agency": deal["agency"],
            "escritura_estimada": deal.get("escritura_estimada") or 0,
        }
        if fields := {}:  # keep linter happy, not used
            pass
        body = page(lang, session["csrf"], i18n.text(lang, "deal_edit_title"),
                    edit_form_html(lang, session["csrf"], did, values, {})
                    + deal_expenses_section(lang, store.list_expenses(DB_PATH, session["tenant_id"], deal_id=did)),
                    "/deals/edit", signed_in=True)
        return respond("200 OK", body)

    if path == "/deals/update" and method == "POST":
        query = read_query(environ)
        raw_id = query.get("id", "")
        try:
            did = int(raw_id)
        except (TypeError, ValueError):
            return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
        deal = store.get_deal(DB_PATH, did, session["tenant_id"])
        if deal is None:
            return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if not csrf_ok(fields):
            return forbidden()
        form_locale = fields.get("form_locale", lang)
        if form_locale not in i18n.SUPPORTED:
            form_locale = lang
        settings = store.get_settings(DB_PATH, tenant_id=session["tenant_id"])
        errors, parsed = validate_deal(lang, fields, form_locale)
        if settings is None:
            errors["commission"] = i18n.text(lang, "err_settings")
        if errors:
            values = {name: fields.get(name, "") for name in ("name", "commission", "share", "stage", "agency")}
            body = page(lang, session["csrf"], i18n.text(lang, "deal_edit_title"),
                        edit_form_html(lang, session["csrf"], did, values, errors),
                        "/deals/edit", signed_in=True)
            return respond("200 OK", body)
        share_cents = agent_share(parsed["commission_cents"], parsed["share_rate"])
        store.update_deal(DB_PATH, did, session["tenant_id"], {
            "name": parsed["name"],
            "agency": parsed["agency"],
            "escritura_date": parsed.get("escritura_date", ""),
            "month": parsed["month"],
            "stage": parsed["stage"],
            "status": parsed.get("status","active"),
            "cpcv_date": parsed.get("cpcv_date"),
            "agency_commission_cents": parsed["commission_cents"],
            "share_rate": fields.get("share", ""),
            "part_base": share_cents,
            "share_rate_used": parsed["share_rate"],
            "iva_rate": settings["iva_rate"],
            "retencao_rate": settings["retencao_rate"],
            "irs_rate": settings["irs_rate"],
            "ss_rate": settings["ss_rate"],
            "expenses_cents": settings["expenses_cents"],
            "escritura_estimada": 1 if fields.get("escritura_estimada") else 0,
        })
        return redirect("/?month=" + parsed["month"])

    # ── Delete deal with confirmation step (tenant-scoped)
    if path == "/deals/delete" and method == "GET":
        query = read_query(environ)
        raw_id = query.get("id", "")
        try:
            did = int(raw_id)
        except (TypeError, ValueError):
            return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
        deal = store.get_deal(DB_PATH, did, session["tenant_id"])
        if deal is None:
            return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
        body = page(lang, session["csrf"], i18n.text(lang, "delete_deal_title"),
                    delete_deal_confirm(lang, session["csrf"], did), "/deals/delete", signed_in=True)
        return respond("200 OK", body)
    if path == "/deals/delete" and method == "POST":
        query = read_query(environ)
        raw_id = query.get("id", "")
        try:
            did = int(raw_id)
        except (TypeError, ValueError):
            return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
        deal = store.get_deal(DB_PATH, did, session["tenant_id"])
        if deal is None:
            return respond("404 Not Found", page(lang, session["csrf"], "Not found", "<p>Not found</p>", signed_in=True))
        fields = read_post_form()
        if not isinstance(fields, dict):
            return fields
        if not csrf_ok(fields):
            return forbidden()
        store.delete_deal(DB_PATH, did, session["tenant_id"])
        return redirect("/")

    if method == "POST" and path in VOICE_PATHS:
        return voice_route(path)

    start_response("404 Not Found", [("Content-Length", str(len(b"Not found"))),
                                     ("Content-Security-Policy",
                                      "default-src 'self'"),
                                     ("X-Content-Type-Options", "nosniff")])
    return [b"Not found"]