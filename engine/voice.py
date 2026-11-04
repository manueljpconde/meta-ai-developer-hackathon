"""Voice conversation logic: deterministic missing-field resolution, estimation, matching."""

PT_MONTHS_VOICE = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
EN_MONTHS_VOICE = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

REQUIRED_FIELDS = {
    "new_deal": ("name", "agency_commission_cents", "share_rate", "escritura_date", "stage"),
    "cpcv_signed": ("deal", "date"),
    "escritura_date": ("deal", "date"),
    "fell_through": ("deal",),
    "commission_received": ("deal", "amount", "date"),
    "change_stage": ("deal", "stage"),
    "change_commission": ("deal", "commission"),
    "change_percentage": ("deal", "percentage"),
    "reopen": ("deal",),
}

# PT month name to number
PT_MONTH_NUM = {m: i + 1 for i, m in enumerate(PT_MONTHS_VOICE)}
EN_MONTH_NUM = {m.lower(): i + 1 for i, m in enumerate(EN_MONTHS_VOICE)}


def parse_month_only(text, year=2026):
    """If text is month-only like 'março' or 'March', return YYYY-MM-15 with estimated flag."""
    t = text.strip().lower()
    for i, name in enumerate(PT_MONTHS_VOICE):
        if t == name or t == name.lower():
            return "%04d-%02d-15" % (year, i + 1), True
    for i, name in enumerate(EN_MONTHS_VOICE):
        if t.lower() == name.lower():
            return "%04d-%02d-15" % (year, i + 1), True
    return None, False


def missing_fields(kind, extracted):
    """Return list of required fields still missing for kind, deterministically."""
    req = REQUIRED_FIELDS.get(kind, ())
    missing = []
    for f in req:
        v = extracted.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(f)
    return missing


def format_estimated_month(date_str, lang):
    """For read-back: 'meados de março' / 'mid-March' for estimated dates."""
    if not date_str:
        return ""
    try:
        y, m, d = date_str.split("-")
        idx = int(m) - 1
        if lang == "pt-PT":
            return "meados de %s" % PT_MONTHS_VOICE[idx]
        return "mid-%s" % EN_MONTHS_VOICE[idx]
    except Exception:
        return date_str


def match_deal(query, deals):
    """Match deal name against agent's own deals. Returns (single_match_or_None, candidates)."""
    if not query or not deals:
        return None, []
    q = query.strip().lower()
    exact = [d for d in deals if d.get("name", "").strip().lower() == q]
    if len(exact) == 1:
        return exact[0], []
    # substring
    subs = [d for d in deals if q in d.get("name", "").strip().lower()]
    if len(subs) == 1:
        return subs[0], []
    if len(subs) > 1:
        return None, subs
    if len(exact) > 1:
        return None, exact
    return None, deals[:3] if deals else []


def deal_names_list(candidates, lang="pt-PT"):
    return ", ".join(d.get("name", "") for d in candidates)
