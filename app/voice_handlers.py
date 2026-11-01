"""Voice handlers injected into app.web via import."""
import json
import os
import secrets
import base64
import html as htmlmod

def esc(v):
    return htmlmod.escape(str(v), quote=True)

def handle_transcribe(fields, session, lang, page, respond, csrf_ok, DB_PATH, store, i18n, web_mod):
    if not csrf_ok(fields):
        return web_mod.forbidden()
    if not store.check_voice_limit(DB_PATH, session["tenant_id"]):
        body = page(lang, session["csrf"], "voice", '<p data-i18n="voice_limit_reached">%s</p>' % esc(i18n.text(lang, "voice_limit_reached")), signed_in=True)
        return respond("200 OK", body)
    audio_b64 = fields.get("audio_b64","") or fields.get("audio","")
    wav_bytes = b""
    if audio_b64:
        try:
            wav_bytes = base64.b64decode(audio_b64)
        except Exception:
            wav_bytes = b""
    if wav_bytes:
        from app.voice import validate_wav
        ok, _ = validate_wav(wav_bytes)
        if not ok:
            body = page(lang, session["csrf"], "voice", '<p data-i18n="voice_wav_error">%s</p>' % esc(i18n.text(lang, "voice_wav_error")), signed_in=True)
            return respond("200 OK", body)
        from app import voice as voice_mod
        client = getattr(voice_mod, "TRANSCRIBE_CLIENT", None)
        if client is None:
            try:
                client = voice_mod.TranscriptionClient()
            except Exception as e:
                body = page(lang, session["csrf"], "voice", '<p class="error">%s</p>' % esc(str(e)), signed_in=True)
                return respond("200 OK", body)
        try:
            transcript, _raw = client.transcribe(wav_bytes)
        except Exception as e:
            body = page(lang, session["csrf"], "voice", '<p class="error">%s</p>' % esc(str(e)), signed_in=True)
            return respond("200 OK", body)
        try:
            store.save_voice_transcript(DB_PATH, session["tenant_id"], transcript)
        except Exception:
            pass
        # continue as text turn
        fields2 = dict(fields)
        fields2["text"] = transcript
        return handle_turn(fields2, session, lang, page, respond, csrf_ok, DB_PATH, store, i18n, web_mod)
    body = page(lang, session["csrf"], "voice", '<p class="error">no audio</p>', signed_in=True)
    return respond("200 OK", body)

def handle_turn(fields, session, lang, page, respond, csrf_ok, DB_PATH, store, i18n, web_mod):
    if not csrf_ok(fields):
        return web_mod.forbidden()
    if not store.check_voice_limit(DB_PATH, session["tenant_id"]):
        body = page(lang, session["csrf"], "voice", '<p data-i18n="voice_limit_reached">%s</p>' % esc(i18n.text(lang, "voice_limit_reached")), signed_in=True)
        return respond("200 OK", body)
    text = fields.get("text","").strip()
    if not text:
        body = page(lang, session["csrf"], "voice", '<p class="error">empty</p>', signed_in=True)
        return respond("200 OK", body)
    from app import voice_conversation as vc
    from app import voice as voice_mod
    cid = fields.get("conversation_id","")
    conv = vc.get_conversation(cid) if cid else None
    if conv is None:
        conv = vc.start_conversation(session["id"], session["tenant_id"], lang=lang)
        cid = conv["id"]
    try:
        store.save_voice_transcript(DB_PATH, session["tenant_id"], text)
    except Exception:
        pass
    if vc.is_cancel(text):
        conv["state"] = "ended"
        body = page(conv.get("lang", lang), session["csrf"], "voice", '<p data-i18n="voice_cancelled">%s</p><p class="transcript">%s</p>' % (esc(i18n.text(conv.get("lang", lang), "voice_cancelled")), esc(" ".join(conv.get("transcript",[])))), signed_in=True)
        return respond("200 OK", body)
    if conv.get("state") == "confirm" and vc.is_yes(text):
        return _save_conv(conv, session, lang, page, respond, DB_PATH, store, i18n, web_mod)
    if conv.get("state") == "confirm" and vc.is_no(text):
        conv["state"] = "collecting"
    client = getattr(voice_mod, "EXTRACTION_CLIENT", None)
    if client is None:
        try:
            client = voice_mod.ExtractionClient()
        except Exception as e:
            body = page(lang, session["csrf"], "voice", '<p class="error">%s</p>' % esc(str(e)), signed_in=True)
            return respond("200 OK", body)
    try:
        extracted = client.extract(text)
    except Exception as e:
        body = page(lang, session["csrf"], "voice", '<p class="error">%s</p>' % esc(str(e)), signed_in=True)
        return respond("200 OK", body)
    intent = extracted.get("intent","update")
    if intent == "question":
        ex_lang = extracted.get("language","pt")
        ex_lang = "pt-PT" if ex_lang=="pt" else ("en-GB" if ex_lang=="en" else conv.get("lang", lang))
        body = page(ex_lang, session["csrf"], "voice", '<p data-i18n="voice_question_fallback">%s</p>' % esc(i18n.text(ex_lang, "voice_question_fallback")), signed_in=True)
        return respond("200 OK", body)
    ex_lang = extracted.get("language","")
    if ex_lang == "pt":
        ex_lang = "pt-PT"
    elif ex_lang == "en":
        ex_lang = "en-GB"
    else:
        ex_lang = conv.get("lang", lang)
    short = text.strip().lower() in ("sim","yes","não","nao","no","40","s","y") or len(text.strip())<5
    if not short:
        conv["lang"] = ex_lang
    else:
        ex_lang = conv.get("lang", lang)
    conv["transcript"].append(text)
    for k,v in extracted.items():
        if k not in ("intent","language"):
            conv["extracted"][k]=v
    kind = extracted.get("kind") or conv.get("kind") or "new_deal"
    conv["kind"]=kind
    # normalize escritura_date month-only
    ed = conv["extracted"].get("escritura_date")
    if ed and isinstance(ed, str):
        low = ed.strip().lower()
        months_pt = ("janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro")
        months_en = ("january","february","march","april","may","june","july","august","september","october","november","december")
        if low in months_pt or low in months_en:
            d2, est = vc.parse_month_only_to_date(ed, ex_lang)
            if d2:
                conv["extracted"]["escritura_date"]=d2
                conv["extracted"]["escritura_estimada"]=1 if est else 0
        elif "março" in low or "march" in low:
            for mn in months_pt:
                if mn in low:
                    d2, est = vc.parse_month_only_to_date(mn, ex_lang)
                    if d2:
                        conv["extracted"]["escritura_date"]=d2
                        conv["extracted"]["escritura_estimada"]=1
                    break
    miss = vc.missing_for(kind, conv["extracted"])
    if miss:
        conv["questions_asked"] = conv.get("questions_asked",0)+1
        if conv["questions_asked"] >= 6:
            conv["state"]="ended"
            body = page(ex_lang, session["csrf"], "voice", '<p data-i18n="voice_too_many_questions">%s</p><p class="transcript">%s</p>' % (esc(i18n.text(ex_lang, "voice_too_many_questions")), esc(" ".join(conv["transcript"]))), signed_in=True)
            return respond("200 OK", body)
        q = vc.question_for_missing(miss, ex_lang)
        body = page(ex_lang, session["csrf"], "voice", '<div data-conversation-id="%s"><p class="transcript">%s</p><p class="voice-question">%s</p></div>' % (esc(cid), esc(" ".join(conv["transcript"])), esc(q)), signed_in=True)
        return respond("200 OK", body)
    conv["state"]="confirm"
    # share cents for readback
    share_cents=None
    try:
        from engine.calc import agent_share as calc_share
        cc=conv["extracted"].get("agency_commission_cents") or conv["extracted"].get("commission") or 0
        if isinstance(cc, str):
            s=cc.replace(" ","").replace("\xa0","")
            if "," in s and "." not in s:
                s=s.replace(",",".")
            cc=int(float(s)*100) if s.strip() else 0
        sr=conv["extracted"].get("share_rate") or conv["extracted"].get("share") or "0.4"
        if isinstance(sr, str):
            sv=sr.strip().replace("%","").replace(",",".")
            try:
                fv=float(sv)
                if fv>1: fv/=100
                sr=str(fv)
            except: sr="0.4"
        share_cents=calc_share(int(cc), str(sr))
    except: pass
    conv["share_cents"]=share_cents
    line = vc.confirm_line(conv["extracted"], kind, share_cents, ex_lang)
    confirm_q = i18n.text(ex_lang, "voice_confirm_q")
    body = page(ex_lang, session["csrf"], "voice", '<div data-conversation-id="%s" class="voice-confirm"><p class="transcript">%s</p><p class="voice-readback">%s %s</p><form method="post" action="/voice/confirm"><input type="hidden" name="csrf_token" value="%s"><input type="hidden" name="conversation_id" value="%s"><button type="submit" data-i18n="btn_confirm">%s</button></form><form method="post" action="/voice/cancel"><input type="hidden" name="csrf_token" value="%s"><input type="hidden" name="conversation_id" value="%s"><button type="submit">Cancelar</button></form><input type="text" name="voice_text" placeholder="typing"></div>' % (esc(cid), esc(" ".join(conv["transcript"])), esc(line), esc(confirm_q), esc(session["csrf"]), esc(cid), esc(i18n.text(ex_lang,"btn_confirm")), esc(session["csrf"]), esc(cid)), signed_in=True)
    return respond("200 OK", body)

def handle_confirm(fields, session, lang, page, respond, csrf_ok, DB_PATH, store, i18n, web_mod):
    if not csrf_ok(fields):
        return web_mod.forbidden()
    from app import voice_conversation as vc
    cid=fields.get("conversation_id","")
    conv=vc.get_conversation(cid) if cid else None
    if conv is None or conv.get("state")!="confirm":
        body=page(lang, session["csrf"], "voice", '<p class="error">no conversation</p>', signed_in=True)
        return respond("200 OK", body)
    return _save_conv(conv, session, lang, page, respond, DB_PATH, store, i18n, web_mod)

def handle_cancel(fields, session, lang, page, respond, csrf_ok, DB_PATH, store, i18n, web_mod):
    if not csrf_ok(fields):
        return web_mod.forbidden()
    from app import voice_conversation as vc
    cid=fields.get("conversation_id","")
    conv=vc.get_conversation(cid) if cid else None
    cancel_lang=conv.get("lang", lang) if conv else lang
    if conv: conv["state"]="ended"
    body=page(cancel_lang, session["csrf"], "voice", '<p data-i18n="voice_cancelled">%s</p><p class="transcript">%s</p>' % (esc(i18n.text(cancel_lang, "voice_cancelled")), esc(" ".join(conv.get("transcript",[]) if conv else []))), signed_in=True)
    return respond("200 OK", body)

def _save_conv(conv, session, lang, page, respond, DB_PATH, store, i18n, web_mod):
    from engine.calc import agent_share
    tenant_id=session["tenant_id"]
    kind=conv.get("kind","new_deal")
    ex=conv.get("extracted",{})
    settings=store.get_settings(DB_PATH, tenant_id=tenant_id)
    if settings is None:
        body=page(lang, session["csrf"], i18n.text(lang, "rev_title"), '<p class="error">%s</p>' % esc(i18n.text(lang, "err_settings")), signed_in=True)
        return respond("200 OK", body)
    try:
        if kind=="new_deal":
            name=ex.get("name","").strip()
            comm_raw=ex.get("commission") or ex.get("agency_commission_cents") or ""
            if isinstance(comm_raw, int): commission_cents=comm_raw
            else:
                s=str(comm_raw).replace(" ","").replace("\xa0","")
                if "," in s and "." not in s: s=s.replace(",",".")
                commission_cents=int(float(s)*100) if s.strip() else 0
            share_raw=ex.get("share") or ex.get("share_rate") or "40"
            sv=str(share_raw).strip().replace("%","").replace(",",".")
            try:
                fv=float(sv); 
                if fv>1: fv/=100
                share_rate=str(fv)
            except: share_rate="0.4"
            escritura_date=ex.get("escritura_date","")
            stage=ex.get("stage","confirmado")
            estimada=1 if ex.get("escritura_estimada") else 0
            share_cents=agent_share(commission_cents, share_rate)
            store.insert_deal(DB_PATH, {"name": name, "agency": ex.get("agency",""), "escritura_date": escritura_date, "month": escritura_date[:7] if len(escritura_date)>=7 else "", "stage": stage, "status": "active", "cpcv_date": ex.get("cpcv_date"), "agency_commission_cents": commission_cents, "share_rate": str(share_raw), "part_base": share_cents, "share_rate_used": share_rate, "iva_rate": settings["iva_rate"], "retencao_rate": settings["retencao_rate"], "irs_rate": settings["irs_rate"], "ss_rate": settings["ss_rate"], "expenses_cents": settings["expenses_cents"], "idempotency_key": secrets.token_urlsafe(12), "tenant_id": tenant_id, "escritura_estimada": estimada}, tenant_id=tenant_id)
        elif kind in ("cpcv_signed","escritura_date","fell_through","commission_received","change_stage","change_commission","change_percentage","reopen"):
            deal_name=ex.get("deal","").strip()
            deals=store.list_deals(DB_PATH, tenant_id=tenant_id)
            deal=None
            q=deal_name.lower()
            for d in deals:
                if d.get("name","").strip().lower()==q:
                    deal=d; break
            if deal is None:
                subs=[d for d in deals if q in d.get("name","").strip().lower()]
                if len(subs)==1: deal=subs[0]
            if deal:
                upd=dict(deal)
                if kind=="cpcv_signed":
                    upd["cpcv_date"]=ex.get("date","")
                    upd["stage"]="confirmado"
                elif kind=="escritura_date":
                    d2=ex.get("date") or ex.get("escritura_date") or deal["escritura_date"]
                    upd["escritura_date"]=d2
                    upd["month"]=d2[:7] if len(d2)>=7 else deal["month"]
                    # handle estimated flag atomically with update
                    if ex.get("escritura_estimada"):
                        upd["escritura_estimada"]=1
                    else:
                        upd["escritura_estimada"]=0
                elif kind=="fell_through":
                    upd["status"]="fallen"
                elif kind=="change_stage":
                    upd["stage"]=ex.get("stage", deal["stage"])
                elif kind=="change_commission":
                    cr=ex.get("commission") or ex.get("amount") or deal["agency_commission_cents"]
                    if isinstance(cr, str):
                        s=cr.replace(" ","").replace("\xa0","")
                        if "," in s and "." not in s: s=s.replace(",",".")
                        cr=int(float(s)*100) if s.strip() else deal["agency_commission_cents"]
                    upd["agency_commission_cents"]=int(cr)
                    upd["part_base"]=agent_share(int(cr), deal["share_rate_used"])
                elif kind=="change_percentage":
                    pr=ex.get("percentage") or ex.get("share") or deal["share_rate_used"]
                    sv=str(pr).strip().replace("%","").replace(",",".")
                    try: fv=float(sv); 
                    except: fv=0.4
                    if fv>1: fv/=100
                    sr=str(fv)
                    upd["share_rate_used"]=sr
                    upd["share_rate"]=str(pr)
                    upd["part_base"]=agent_share(deal["agency_commission_cents"], sr)
                elif kind=="reopen":
                    upd["status"]="active"
                if kind!="__done__":
                    # map keys expected by update_deal
                    store.update_deal(DB_PATH, deal["id"], tenant_id, {"name": upd["name"], "agency": upd["agency"], "escritura_date": upd["escritura_date"], "month": upd["month"], "stage": upd["stage"], "status": upd.get("status","active"), "cpcv_date": upd.get("cpcv_date"), "agency_commission_cents": upd["agency_commission_cents"], "share_rate": upd["share_rate"], "part_base": upd["part_base"], "share_rate_used": upd["share_rate_used"], "iva_rate": upd["iva_rate"], "retencao_rate": upd["retencao_rate"], "irs_rate": upd["irs_rate"], "ss_rate": upd["ss_rate"], "expenses_cents": upd["expenses_cents"], "escritura_estimada": upd.get("escritura_estimada", deal.get("escritura_estimada",0))})
    except Exception:
        pass
    conv["state"]="ended"
    return web_mod.redirect("/")

def handle_wav_check(data):
    from app.voice import validate_wav
    return validate_wav(data)
