"""In-memory voice conversation store for one user session (cookie-backed).

Simpler than DB-backed state: keep per-browser conversation in a server dict keyed by session id.
Tests drive it via helpers; production uses same.

Conversation dict: {
  state: 'collecting'|'confirm'|'ended',
  kind, extracted, missing, language, transcript, questions_asked, deal_match
}
"""
import time
import secrets
import re

from app import store

CONVERSATIONS = {}

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

# map extraction kind to REQUIRED key (normalize aliases)
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

PT_MONTHS = ("janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro")
EN_MONTHS = ("January","February","March","April","May","June","July","August","September","October","November","December")

def missing_for(kind, extracted):
    req = REQUIRED.get(kind, ())
    miss = []
    for f in req:
        v = extracted.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            miss.append(f)
    # escritura_date special: if new_deal and no date
    return miss

def is_cancel(text):
    t = text.strip().lower()
    return t in ("cancelar", "cancel", "cancelar.", "cancel.")

def is_yes(text):
    t = text.strip().lower()
    return t in ("sim", "yes", "sim.", "yes.", "s", "y")

def is_no(text):
    t = text.strip().lower()
    return t in ("não", "nao", "no", "não.", "nao.", "no.")

def question_for_missing(missing, lang):
    # One short question for all missing
    if lang == "pt-PT":
        labels = {"name": "o nome", "commission": "a comissão", "share": "a tua percentagem", "escritura_date": "a data da escritura", "stage": "a fase", "deal": "o negócio", "date": "a data", "amount": "o valor", "percentage": "a percentagem"}
        parts = [labels.get(m, m) for m in missing]
        if "escritura_date" in missing and len(missing) == 1:
            return "Qual é a data da escritura, mesmo aproximada?"
        return "Qual é " + " e ".join(parts) + "?"
    else:
        labels = {"name": "the name", "commission": "the commission", "share": "your share", "escritura_date": "the escritura date", "stage": "the stage", "deal": "the deal", "date": "the date", "amount": "the amount", "percentage": "the percentage"}
        parts = [labels.get(m, m) for m in missing]
        if "escritura_date" in missing and len(missing) == 1:
            return "When is the escritura, even roughly?"
        return "What is " + " and ".join(parts) + "?"

def confirm_line(extracted, kind, share_cents, lang):
    # One-line read-back
    name = extracted.get("name") or extracted.get("deal") or ""
    comm = extracted.get("commission") or extracted.get("agency_commission_cents") or ""
    share = extracted.get("share") or extracted.get("share_rate") or ""
    date = extracted.get("escritura_date") or extracted.get("date") or ""
    # format share for display
    if lang == "pt-PT":
        # show date as dd mon
        date_disp = date
        try:
            y,m,d = date.split("-")
            date_disp = "%s %s" % (d, PT_MONTHS[int(m)-1][:3])
        except Exception:
            pass
        share_disp = "%s €" % (share_cents/100) if share_cents else str(share)
        return "%s, %s, %s, escritura %s. Confirmas?" % (name, comm, share_disp, date_disp)
    else:
        return "%s, %s, %s, escritura %s. Do you confirm?" % (name, comm, share, date)

def start_conversation(session_id, tenant_id, lang="pt-PT"):
    cid = secrets.token_urlsafe(12)
    conv = {
        "id": cid,
        "tenant_id": tenant_id,
        "session_id": session_id,
        "lang": lang,
        "state": "collecting",
        "kind": None,
        "extracted": {},
        "missing": [],
        "transcript": [],
        "questions_asked": 0,
        "confirm_ready": False,
        "share_cents": None,
    }
    CONVERSATIONS[cid] = conv
    return conv

def get_conversation(cid):
    return CONVERSATIONS.get(cid)

def parse_month_only_to_date(text, lang):
    t = text.strip().lower()
    # month-only -> 15th estimated
    for i, n in enumerate(PT_MONTHS):
        if t == n:
            return "2026-%02d-15" % (i+1), True
    for i, n in enumerate(EN_MONTHS):
        if t.lower() == n.lower():
            return "2026-%02d-15" % (i+1), True
    # phrase like "ainda não está marcada, mas deve ser em março"
    for i, n in enumerate(PT_MONTHS):
        if n in t:
            return "2026-%02d-15" % (i+1), True
    return None, False
