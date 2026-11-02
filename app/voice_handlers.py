"""Voice endpoints: one conversation, turn by turn.

Every handler returns a plain dict the page script reads:

    state            ask | confirm | saved | cancelled | ended | error
    question         the one question (state ask)
    readback         the one-line read-back (state confirm)
    message          a short message in the conversation's language
    transcript       everything heard so far
    understood       what was understood so far (cancelled / ended)
    conversation_id  to send back with the next turn
    lang             pt-PT or en-GB, the language to speak and show

``app.web`` turns the dict into JSON (``format=json``) or into a plain
page for a browser without the script. Nothing is saved before a
spoken or tapped yes; money comes from ``engine.calc`` only.
"""
import html as htmlmod
from types import SimpleNamespace

from app import i18n
from app import store
from app import voice as voice_mod
from app import voice_flow as vf
from engine.calc import agent_share


def esc(value):
    return htmlmod.escape(str(value), quote=True)


def make_env(db_path, session, lang):
    return SimpleNamespace(db=db_path, tenant=session["tenant_id"],
                           session_id=session["id"], lang=lang)


def _t(lang, key):
    return i18n.text(lang, key)


def _payload(conv, state, lang, **extra):
    live = conv is not None and state in ("ask", "confirm", "error")
    data = {
        "state": state,
        "conversation_id": conv["id"] if live else "",
        "lang": lang,
        "transcript": "\n".join(conv["transcript"]) if conv else "",
    }
    data.update(extra)
    return data


def _client(attr, factory):
    client = getattr(voice_mod, attr, None)
    return client if client is not None else factory()


def _remember(env, text):
    try:
        store.save_voice_transcript(env.db, env.tenant, text)
    except Exception:
        pass


# ── Ending a conversation ────────────────────────────────────────

def _end(conv, state, lang, message):
    data = _payload(conv, state, lang, message=message,
                    understood=vf.understood_line(conv, lang))
    vf.drop_conversation(conv["id"])
    return data


def _cancel(conv, env):
    if conv is None:
        return _payload(None, "cancelled", env.lang,
                        message=_t(env.lang, "voice_cancelled"), understood="")
    return _end(conv, "cancelled", conv["lang"], _t(conv["lang"], "voice_cancelled"))


def _ask(conv, text):
    """Ask one question, or stop when six have been asked already."""
    lang = conv["lang"]
    if conv["questions_asked"] >= vf.MAX_QUESTIONS:
        return _end(conv, "ended", lang, _t(lang, "voice_too_many_questions"))
    conv["questions_asked"] += 1
    conv["state"] = "collecting"
    return _payload(conv, "ask", lang, question=text)


# ── Saving ───────────────────────────────────────────────────────

DEAL_COLUMNS = (
    "name", "agency", "escritura_date", "month", "stage", "status",
    "cpcv_date", "agency_commission_cents", "share_rate", "part_base",
    "share_rate_used", "iva_rate", "retencao_rate", "irs_rate",
    "ss_rate", "expenses_cents", "escritura_estimada",
)


def _changes_for(kind, ex, deal):
    if kind == "cpcv_signed":
        return {"cpcv_date": ex["date"], "stage": "confirmado"}
    if kind == "escritura_date":
        return {"escritura_date": ex["date"], "month": ex["date"][:7],
                "escritura_estimada": 1 if ex.get("escritura_estimada") else 0}
    if kind == "fell_through":
        return {"status": "fallen"}
    if kind == "reopen":
        return {"status": "active"}
    if kind == "change_stage":
        return {"stage": ex["stage"]}
    if kind == "change_commission":
        return {"agency_commission_cents": ex["commission"],
                "part_base": agent_share(ex["commission"], deal["share_rate_used"])}
    if kind == "change_percentage":
        return {"share_rate": vf.percent_text(ex["percentage"]),
                "share_rate_used": ex["percentage"],
                "part_base": agent_share(deal["agency_commission_cents"], ex["percentage"])}
    raise ValueError(kind)


def _save(env, conv):
    """Write the confirmed update and return the payload."""
    lang = conv["lang"]
    kind = conv["kind"]
    ex = conv["extracted"]
    key = "voice-" + conv["id"]
    failed = _payload(conv, "error", lang, message=_t(lang, "voice_save_failed"))
    try:
        if kind == "new_deal":
            settings = store.get_settings(env.db, tenant_id=env.tenant)
            if settings is None:
                return _payload(conv, "error", lang, message=_t(lang, "voice_no_settings"))
            date = ex["escritura_date"]
            store.insert_deal(env.db, {
                "name": ex["name"], "agency": ex.get("agency", ""),
                "escritura_date": date, "month": date[:7],
                "stage": ex["stage"], "status": "active",
                "cpcv_date": ex.get("cpcv_date"),
                "agency_commission_cents": ex["commission"],
                "share_rate": vf.percent_text(ex["share"]),
                "part_base": agent_share(ex["commission"], ex["share"]),
                "share_rate_used": ex["share"],
                "iva_rate": settings["iva_rate"],
                "retencao_rate": settings["retencao_rate"],
                "irs_rate": settings["irs_rate"],
                "ss_rate": settings["ss_rate"],
                "expenses_cents": settings["expenses_cents"],
                "idempotency_key": key, "tenant_id": env.tenant,
                "escritura_estimada": 1 if ex.get("escritura_estimada") else 0,
            }, tenant_id=env.tenant)
        else:
            deal = store.get_deal(env.db, conv["deal_id"], env.tenant)
            if deal is None:
                return failed
            if kind == "commission_received":
                store.insert_receipt(env.db, env.tenant, deal["id"], ex["amount"], ex["date"], key)
            else:
                fields = {col: deal[col] for col in DEAL_COLUMNS}
                fields.update(_changes_for(kind, ex, deal))
                if not store.update_deal(env.db, deal["id"], env.tenant, fields):
                    return failed
    except Exception:
        return failed
    data = _payload(conv, "saved", lang, message="")
    vf.drop_conversation(conv["id"])
    return data


# ── One turn of text ─────────────────────────────────────────────

def _extract(text):
    extracted = _client("EXTRACTION_CLIENT", voice_mod.ExtractionClient).extract(text)
    if not isinstance(extracted, dict):
        raise voice_mod.ModelError("extraction is not an object")
    return extracted


def _advance(env, conv, text):
    lang = conv["lang"]
    _remember(env, text)
    conv["transcript"].append(text)
    if vf.is_cancel(text):
        return _cancel(conv, env)
    if conv["state"] == "confirm":
        if vf.is_yes(text):
            return _save(env, conv)
        if vf.is_no(text):
            return _ask(conv, _t(lang, "voice_what_to_fix"))
    try:
        extracted = _extract(text)
    except voice_mod.ModelError:
        return _payload(conv, "error", lang, message=_t(lang, "voice_model_error"))
    if extracted.get("intent") == "question":
        qlang = vf.lang_from_model(extracted.get("language"), lang)
        return _end(conv, "ended", qlang, _t(qlang, "voice_question_fallback"))
    if not vf.is_short_answer(text):
        conv["lang"] = lang = vf.lang_from_model(extracted.get("language"), lang)
    kind = conv["kind"] or vf.KIND_MAP.get(extracted.get("kind"))
    if kind is None:
        return _payload(conv, "error", lang, message=_t(lang, "voice_model_error"))
    conv["kind"] = kind
    asked = vf.missing_for(kind, conv["extracted"])
    vf.merge_extraction(conv, extracted)
    vf.fill_bare_number(conv, text, asked)
    deals = store.list_deals(env.db, tenant_id=env.tenant)
    active = [d for d in deals if d.get("status") != "fallen"]
    fallen = [d for d in deals if d.get("status") == "fallen"]
    outcome = vf.resolve(conv, active, fallen, lang)
    if outcome.action == "ask":
        return _ask(conv, outcome.text)
    if outcome.action == "stop":
        return _end(conv, "ended", lang, outcome.text)
    conv["state"] = "confirm"
    conv["readback"] = outcome.text
    conv["share_cents"] = outcome.mine_cents
    return _payload(conv, "confirm", lang, readback=outcome.text)


def handle_text(env, fields):
    text = fields.get("text", "").strip()[:500]
    cid = fields.get("conversation_id", "")
    conv = vf.get_conversation(cid, env.tenant) if cid else None
    lang = conv["lang"] if conv else env.lang
    if not text:
        return _payload(conv, "error", lang, message=_t(lang, "voice_empty"))
    if conv is None:
        if not store.check_voice_limit(env.db, env.tenant):
            return _payload(None, "ended", lang, message=_t(lang, "voice_limit_reached"))
        conv = vf.start_conversation(env.session_id, env.tenant, lang)
    return _advance(env, conv, text)


def handle_audio(env, query, wav):
    """A raw WAV body: checked, transcribed, then handled as typed text."""
    cid = query.get("conversation_id", "")
    conv = vf.get_conversation(cid, env.tenant) if cid else None
    lang = conv["lang"] if conv else env.lang
    if conv is None and store.voice_limit_reached(env.db, env.tenant):
        return _payload(None, "ended", lang, message=_t(lang, "voice_limit_reached"))
    ok, _reason = voice_mod.validate_wav(wav)
    if not ok:
        return _payload(conv, "error", lang, message=_t(lang, "voice_wav_error"))
    try:
        transcript, _raw = _client("TRANSCRIBE_CLIENT", voice_mod.TranscriptionClient).transcribe(wav)
    except Exception:
        return _payload(conv, "error", lang, message=_t(lang, "voice_model_error"))
    transcript = (transcript or "").strip()
    if not transcript:
        return _payload(conv, "error", lang, message=_t(lang, "voice_empty"))
    return handle_text(env, {"text": transcript, "conversation_id": cid})


def handle_confirm(env, fields):
    cid = fields.get("conversation_id", "")
    conv = vf.get_conversation(cid, env.tenant) if cid else None
    if conv is None or conv["state"] != "confirm":
        return _payload(conv, "error", env.lang, message=_t(env.lang, "voice_no_conversation"))
    return _save(env, conv)


def handle_cancel(env, fields):
    cid = fields.get("conversation_id", "")
    conv = vf.get_conversation(cid, env.tenant) if cid else None
    return _cancel(conv, env)


# ── Plain page, for a browser without the script ─────────────────

def html_body(data, csrf):
    lang = data["lang"]
    parts = []
    if data.get("transcript"):
        parts.append('<p class="transcript">%s</p>' % esc(data["transcript"]))
    for key, css in (("question", "voice-question"), ("readback", "voice-readback"),
                     ("message", "voice-message"), ("understood", "voice-understood")):
        if data.get(key):
            parts.append('<p class="%s">%s</p>' % (css, esc(data[key])))
    cid = data.get("conversation_id", "")
    hidden = ('<input type="hidden" name="csrf_token" value="%s">'
              '<input type="hidden" name="conversation_id" value="%s">' % (esc(csrf), esc(cid)))
    if data["state"] == "confirm":
        parts.append('<form method="post" action="/voice/confirm">%s'
                     '<button type="submit" data-i18n="btn_confirm">%s</button></form>'
                     % (hidden, esc(_t(lang, "btn_confirm"))))
    if cid:
        parts.append('<form method="post" action="/voice/cancel">%s'
                     '<button type="submit" data-i18n="voice_cancel_btn">%s</button></form>'
                     % (hidden, esc(_t(lang, "voice_cancel_btn"))))
        parts.append('<form method="post" action="/voice/extract">%s'
                     '<input type="text" name="text" placeholder="%s">'
                     '<button type="submit" data-i18n="voice_send">%s</button></form>'
                     % (hidden, esc(_t(lang, "voice_placeholder")), esc(_t(lang, "voice_send"))))
    return '<div class="voice-result" data-conversation-id="%s">%s</div>' % (esc(cid), "".join(parts))
