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
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qsl, quote, unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import auth, i18n, mail, store
from engine.calc import agent_share, calc_month

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
                      ("/settings", "nav_settings")):
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
    voice_btn_header = (
        '<button id="voiceFalarHeader" type="button" class="voice-falar-header">'
        '<span aria-hidden="true">\U0001F399</span> <span data-i18n="voice_falar">%s</span></button>'
        % esc(i18n.text(lang, "voice_falar")))
    voice_btn_fixed = (
        '<button id="voiceFalar" type="button" class="voice-falar-fixed" aria-label="%s">'
        '<span aria-hidden="true">\U0001F399</span></button>'
        % esc(i18n.text(lang, "voice_falar")))
    voice_panel = ""
    voice_js = ""
    if signed_in:
        voice_panel = (
            '<div id="voicePanel" class="voice-panel" role="dialog" hidden aria-label="%s"'
            ' data-network-error="%s" data-mic-blocked="%s" data-tap-answer="%s">'
            '<div class="voice-panel__inner">'
            '<div id="voiceTranscript" class="voice-transcript"></div>'
            '<div id="voiceQuestion" class="voice-question"></div>'
            '<div id="voiceReadback" class="voice-readback"></div>'
            '<div class="voice-actions">'
            '<button type="button" id="voiceConfirmBtn" hidden data-i18n="btn_confirm">%s</button>'
            '<button type="button" id="voiceCancelBtn" data-i18n="voice_cancel_btn">%s</button></div>'
            '<form id="voiceTextForm" method="post" action="/voice/extract">'
            '<input type="hidden" name="csrf_token" value="%s">'
            '<input type="hidden" name="conversation_id" id="voiceConvId" value="">'
            '<input type="text" name="text" id="voiceTextInput" autocomplete="off" placeholder="%s" aria-label="%s">'
            '<button type="submit" data-i18n="voice_send">%s</button></form>'
            '</div></div>'
            % (esc(i18n.text(lang, "voice_panel_label")),
               esc(i18n.text(lang, "voice_network_error")),
               esc(i18n.text(lang, "voice_mic_blocked")),
               esc(i18n.text(lang, "voice_tap_answer")),
               esc(i18n.text(lang, "btn_confirm")),
               esc(i18n.text(lang, "voice_cancel_btn")),
               esc(csrf),
               esc(i18n.text(lang, "voice_placeholder")),
               esc(i18n.text(lang, "voice_placeholder")),
               esc(i18n.text(lang, "voice_send"))))
        voice_js = '<script src="/static/voice.js" defer></script>'
    if signed_in:
        header = '<div class="brand">Agentimo</div>%s%s%s%s' % (nav(lang, current), lang_switch(lang, csrf), signout_form(), voice_btn_header)
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
            esc(format_date(fields.get("escritura_date", "2026-11-15"), lang) + " · " + format_month(forecast_month_from_date(fields.get("escritura_date", "2026-11-15")), lang)),
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
    return (
        "<section><h2>%s</h2>"
        "<dl>"
        '<dt data-i18n="m_commission">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_bank">%s</dt><dd>%s</dd>'
        '<dt data-i18n="m_protected">%s</dt><dd>%s (%s %s; %s %s; %s %s)</dd>'
        '<dt data-i18n="m_really">%s</dt><dd>%s</dd>'
        "</dl>"
        '<h3 data-i18n="m_deals">%s</h3><table class="deal-table"><thead><tr><th data-i18n="th_name">%s</th><th data-i18n="th_stage">%s</th><th data-i18n="th_amount">%s</th><th data-i18n="th_escritura">%s</th><th data-i18n="th_cpcv">%s</th></tr></thead><tbody>%s</tbody></table>%s</section>'
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
            esc(i18n.text(lang, "m_deals")),
            esc(i18n.text(lang, "th_name")), esc(i18n.text(lang, "th_stage")), esc(i18n.text(lang, "th_amount")), esc(i18n.text(lang, "th_escritura")), esc(i18n.text(lang, "th_cpcv")),
            rows, cards_html,
        )
    )


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
                    refusal = {"state": "error", "lang": lang,
                               "conversation_id": query.get("conversation_id", ""),
                               "transcript": "",
                               "message": i18n.text(lang, "voice_wav_error")}
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
        settings = store.get_settings(DB_PATH, tenant_id=session["tenant_id"])
        expenses = settings["expenses_cents"] if settings else 0
        if only and valid_month(only):
            months = [only]
        else:
            months = store.months_with_deals(DB_PATH, tenant_id=session["tenant_id"])
        if not months:
            body = page(
                lang, session["csrf"], i18n.text(lang, "home_title"),
                '<h1 data-i18n="home_title">%s</h1>'
                '<p data-i18n="home_empty">%s</p>'
                '<p><a href="/deals/new" data-i18n="home_new">%s</a></p>'
                % (esc(i18n.text(lang, "home_title")),
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
                forecast_section(lang, m, by_month.get(m, []), expenses)
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
                    '<h1 data-i18n="home_title">%s</h1><div class="forecast-grid">%s</div>%s'
                    % (esc(i18n.text(lang, "home_title")), sections, fallen_html),
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
                                settings["expenses_cents"])
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
                         "agency", "form_locale"):
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
                "escritura_date": parsed.get("escritura_date", ""),
                "cpcv_date": parsed.get("cpcv_date","") or "",
                "month": parsed["month"],
                "stage": parsed["stage"],
                "status": parsed.get("status","active"),
                "agency": parsed["agency"],
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
        }
        if fields := {}:  # keep linter happy, not used
            pass
        body = page(lang, session["csrf"], i18n.text(lang, "deal_edit_title"),
                    edit_form_html(lang, session["csrf"], did, values, {}),
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