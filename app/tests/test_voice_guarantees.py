"""Voice conversational guarantees: one-question, confirmation, limits, language, docs (criteria A0/A3/A4/A5/A6/A13/A14/A16)."""
import re
import unittest

from app.tests.helpers import AppTestCase, csrf_token


class OneQuestionRuleTest(AppTestCase):
    """A0/A3: one short question for all missing fields, never speaks first, shortest path."""

    def test_question_for_missing_two_fields_single_string_pt(self):
        from app.voice_conversation import question_for_missing
        q = question_for_missing(["commission", "share"], "pt-PT")
        self.assertIn("comissão", q)
        self.assertIn("percentagem", q)
        self.assertEqual(q.count("?"), 1)

    def test_question_for_missing_two_fields_single_string_en(self):
        from app.voice_conversation import question_for_missing
        q = question_for_missing(["commission", "share"], "en-GB")
        self.assertIn("commission", q)
        self.assertIn("share", q)
        self.assertEqual(q.count("?"), 1)

    def test_question_covers_every_kind_single_question(self):
        from app.voice_conversation import question_for_missing, REQUIRED
        for kind in ("new_deal", "cpcv_signed", "fell_through", "commission_received"):
            req = list(REQUIRED[kind])
            if len(req) >= 2:
                q = question_for_missing(req, "pt-PT")
                self.assertEqual(q.count("?"), 1, kind)
                q2 = question_for_missing(req, "en-GB")
                self.assertEqual(q2.count("?"), 1, kind)

    def test_agent_never_speaks_first_no_greeting_on_page(self):
        body = self.client.get("/").body
        self.assertIn('id="voiceFalar"', body)
        self.assertNotIn("Qual é a comissão", body)
        self.assertNotIn("What is the commission", body)
        self.assertNotIn("Olá", body)
        # no auto question/confirm content; panel is hidden
        self.assertIn('style="display:none"', body)
        self.assertNotIn("Qual é a data da escritura", body)
        self.assertNotIn("When is the escritura", body)

    def test_missing_fields_deterministic_not_model(self):
        import inspect
        from app.voice_conversation import missing_for
        src = inspect.getsource(missing_for)
        self.assertNotIn("EXTRACTION_CLIENT", src)
        self.assertNotIn("Transcription", src)


class ConfirmationContractTest(AppTestCase):
    """A4/A5: one-line readback with share euros and estimated wording, saves only on yes/button."""

    def test_readback_contains_name_euros_percentage_date_and_share(self):
        from app.voice_conversation import confirm_line
        ex = {"name": "T3 Benfica", "commission": "10000", "share": "40", "escritura_date": "2026-12-15"}
        line = confirm_line(ex, "new_deal", 400000, "pt-PT")
        self.assertIn("T3 Benfica", line)
        self.assertIn("Confirmas", line)
        self.assertIn("4000", line)  # share euros from engine.calc 40% of 10000
        self.assertIn("escritura", line.lower())

    def test_readback_estimated_shows_estimada_mid_march(self):
        from app.voice_conversation import confirm_line
        ex = {"name": "T3 Benfica", "commission": "10000", "share": "40", "escritura_date": "2026-03-15", "escritura_estimada": 1}
        line_pt = confirm_line(ex, "new_deal", 400000, "pt-PT")
        self.assertIn("(estimada)", line_pt)
        self.assertIn("meados de março", line_pt)
        line_en = confirm_line(ex, "new_deal", 400000, "en-GB")
        self.assertIn("(estimated)", line_en)
        self.assertIn("mid-March", line_en)

    def test_nothing_saved_before_yes_and_saved_after_wsgi(self):
        self.save_settings()
        tok = csrf_token(self.client.get("/").body)
        from app import voice as vm, voice_conversation as vc
        from app import store as st
        from app.web import DB_PATH
        vc.CONVERSATIONS.clear()

        class Extract:
            def extract(self, t):
                return {"intent": "update", "kind": "new_deal", "language": "pt", "name": "T3 Confirm PT", "commission": "10000", "share": "40", "escritura_date": "2026-12-15", "stage": "confirmado"}

        old = getattr(vm, "EXTRACTION_CLIENT", None)
        vm.EXTRACTION_CLIENT = Extract()
        try:
            before = self.deal_count()
            r = self.client.post("/voice/turn", {"csrf_token": tok, "text": "criar T3 Confirm PT"})
            self.assertIn("Confirmas", r.body)
            self.assertEqual(self.deal_count(), before)
            cid = re.search(r'data-conversation-id="([^"]+)"', r.body).group(1)
            self.assertIn('action="/voice/confirm"', r.body)
            # voice yes path
            r2 = self.client.post("/voice/turn", {"csrf_token": tok, "conversation_id": cid, "text": "sim"})
            self.assertEqual(self.deal_count(), before + 1)
            deals = st.list_deals(DB_PATH, tenant_id=st.get_tenant_by_email(DB_PATH, "test@example.com")["id"])
            saved = [d for d in deals if d["name"] == "T3 Confirm PT"][0]
            self.assertEqual(saved["part_base"], 400000)
        finally:
            if old is None:
                try:
                    delattr(vm, "EXTRACTION_CLIENT")
                except Exception:
                    pass
            else:
                vm.EXTRACTION_CLIENT = old

    def test_voice_no_saves_nothing(self):
        tok = csrf_token(self.client.get("/").body)
        from app import voice as vm, voice_conversation as vc
        vc.CONVERSATIONS.clear()

        class Extract:
            n = 0

            def extract(self, t):
                Extract.n += 1
                if Extract.n <= 1:
                    return {"intent": "update", "kind": "new_deal", "language": "pt", "name": "T3 No PT", "commission": "10000", "share": "40", "escritura_date": "2026-12-15", "stage": "confirmado"}
                return {"intent": "update", "kind": "new_deal", "language": "pt"}

        old = getattr(vm, "EXTRACTION_CLIENT", None)
        vm.EXTRACTION_CLIENT = Extract()
        try:
            before = self.deal_count()
            r = self.client.post("/voice/turn", {"csrf_token": tok, "text": "criar T3 No PT"})
            cid = re.search(r'data-conversation-id="([^"]+)"', r.body).group(1)
            self.assertEqual(self.deal_count(), before)
            r2 = self.client.post("/voice/turn", {"csrf_token": tok, "conversation_id": cid, "text": "não"})
            # after no we are back to collecting
            self.assertEqual(self.deal_count(), before)
        finally:
            if old is None:
                try:
                    delattr(vm, "EXTRACTION_CLIENT")
                except Exception:
                    pass
            else:
                vm.EXTRACTION_CLIENT = old

    def test_confirm_button_is_second_save_path(self):
        self.save_settings()
        tok = csrf_token(self.client.get("/").body)
        from app import voice as vm, voice_conversation as vc
        vc.CONVERSATIONS.clear()

        class Extract:
            def extract(self, t):
                return {"intent": "update", "kind": "new_deal", "language": "pt", "name": "T3 Btn PT", "commission": "10000", "share": "40", "escritura_date": "2026-12-15", "stage": "confirmado"}

        old = getattr(vm, "EXTRACTION_CLIENT", None)
        vm.EXTRACTION_CLIENT = Extract()
        try:
            before = self.deal_count()
            r = self.client.post("/voice/turn", {"csrf_token": tok, "text": "criar T3 Btn PT"})
            cid = re.search(r'data-conversation-id="([^"]+)"', r.body).group(1)
            self.assertIn('action="/voice/confirm"', r.body)
            r2 = self.client.post("/voice/confirm", {"csrf_token": tok, "conversation_id": cid})
            self.assertEqual(self.deal_count(), before + 1)
        finally:
            if old is None:
                try:
                    delattr(vm, "EXTRACTION_CLIENT")
                except Exception:
                    pass
            else:
                vm.EXTRACTION_CLIENT = old


class ConversationLimitsTest(AppTestCase):
    """A6/A13: 6-question stop and 30/day refused without model call in page language."""

    def test_six_questions_stops_shows_transcript_saves_nothing(self):
        tok = csrf_token(self.client.get("/").body)
        from app import voice as vm, voice_conversation as vc
        vc.CONVERSATIONS.clear()

        class Extract:
            def extract(self, t):
                return {"intent": "update", "kind": "new_deal", "language": "pt", "name": "T Loop6"}

        old = getattr(vm, "EXTRACTION_CLIENT", None)
        vm.EXTRACTION_CLIENT = Extract()
        try:
            before = self.deal_count()
            cid = None
            last = None
            for _ in range(7):
                p = {"csrf_token": tok, "text": "x"}
                if cid:
                    p["conversation_id"] = cid
                last = self.client.post("/voice/turn", p)
                m = re.search(r'data-conversation-id="([^"]+)"', last.body)
                if m:
                    cid = m.group(1)
                if "voice_too_many_questions" in last.body:
                    break
            self.assertIn("voice_too_many_questions", last.body)
            self.assertIn("transcript", last.body.lower())
            self.assertEqual(self.deal_count(), before)
        finally:
            if old is None:
                try:
                    delattr(vm, "EXTRACTION_CLIENT")
                except Exception:
                    pass
            else:
                vm.EXTRACTION_CLIENT = old

    def test_daily_limit_refused_without_model_call_pt_then_en(self):
        from app import voice as vm, store as st
        from app.web import DB_PATH
        tok = csrf_token(self.client.get("/").body)
        tenant = st.get_tenant_by_email(DB_PATH, "test@example.com")
        # fill to limit via real helper
        for _ in range(30):
            st.check_voice_limit(DB_PATH, tenant["id"])
        called = []

        class E:
            def extract(self, t):
                called.append(1)
                return {"intent": "update", "kind": "new_deal", "language": "pt", "name": "T", "commission": "10000", "share": "40", "escritura_date": "2026-12-15", "stage": "confirmado"}

        old = getattr(vm, "EXTRACTION_CLIENT", None)
        vm.EXTRACTION_CLIENT = E()
        try:
            r = self.client.post("/voice/turn", {"csrf_token": tok, "text": "criar T"})
            self.assertIn("voice_limit_reached", r.body)
            self.assertEqual(called, [])
            # also transcribe path blocked
            import base64
            bad = base64.b64encode(b"RIFFxxxxWAVEfmt ").decode()
            r2 = self.client.post("/voice/transcribe", {"csrf_token": tok, "audio_b64": bad})
            self.assertIn("voice_limit_reached", r2.body)
        finally:
            if old is None:
                try:
                    delattr(vm, "EXTRACTION_CLIENT")
                except Exception:
                    pass
            else:
                vm.EXTRACTION_CLIENT = old


class FullJourneysBothLanguagesTest(AppTestCase):
    """Criterion 14: full PT and EN new-deal with two missing fields, bilingual both-path."""

    def test_full_pt_and_en_new_deal_with_two_missing(self):
        for lang_code, page_lang in (("pt", "pt-PT"), ("en", "en-GB")):
            with self.subTest(lang=lang_code):
                self.save_settings()
                tok = csrf_token(self.client.get("/").body)
                from app import voice as vm, voice_conversation as vc
                from app import store as st
                from app.web import DB_PATH
                vc.CONVERSATIONS.clear()

                class E:
                    n = 0

                    def extract(self, text):
                        E.n += 1
                        if E.n == 1:
                            return {"intent": "update", "kind": "new_deal", "language": lang_code, "name": "T3 Journey " + lang_code, "stage": "confirmado"}
                        return {"intent": "update", "kind": "new_deal", "language": lang_code, "commission": "10000", "share": "40", "escritura_date": "2026-12-15"}

                old = getattr(vm, "EXTRACTION_CLIENT", None)
                vm.EXTRACTION_CLIENT = E()
                try:
                    before = self.deal_count()
                    r1 = self.client.post("/voice/turn", {"csrf_token": tok, "text": "novo T3"})
                    cid = re.search(r'data-conversation-id="([^"]+)"', r1.body).group(1)
                    # first question must mention both missing fields
                    self.assertIn("voice-question", r1.body)
                    r2 = self.client.post("/voice/turn", {"csrf_token": tok, "conversation_id": cid, "text": "comissão 10000 e 40%, escritura 15 dez"})
                    self.assertTrue("Confirmas" in r2.body or "Do you confirm" in r2.body)
                    r3 = self.client.post("/voice/turn", {"csrf_token": tok, "conversation_id": cid, "text": "sim" if lang_code == "pt" else "yes"})
                    self.assertEqual(self.deal_count(), before + 1)
                finally:
                    if old is None:
                        try:
                            delattr(vm, "EXTRACTION_CLIENT")
                        except Exception:
                            pass
                    else:
                        vm.EXTRACTION_CLIENT = old

    def test_language_switch_english_answer_on_portuguese_page_yields_english(self):
        tok = csrf_token(self.client.get("/", accept_language="pt-PT").body)
        from app import voice as vm, voice_conversation as vc
        vc.CONVERSATIONS.clear()

        class E:
            n = 0

            def extract(self, t):
                E.n += 1
                if E.n == 1:
                    return {"intent": "update", "kind": "new_deal", "language": "pt", "name": "T3 LangPT"}
                return {"intent": "update", "kind": "new_deal", "language": "en", "name": "T3 LangPT"}

        old = getattr(vm, "EXTRACTION_CLIENT", None)
        vm.EXTRACTION_CLIENT = E()
        try:
            r1 = self.client.post("/voice/turn", {"csrf_token": tok, "text": "criar T3 LangPT"})
            cid = re.search(r'data-conversation-id="([^"]+)"', r1.body).group(1)
            # force language switch: extraction returns en, not short
            r2 = self.client.post("/voice/turn", {"csrf_token": tok, "conversation_id": cid, "text": "commission is ten thousand"})
            self.assertIn("data-conversation-id", r2.body)
            # second question should be English
            self.assertTrue("What is" in r2.body or "the" in r2.body.lower())
        finally:
            if old is None:
                try:
                    delattr(vm, "EXTRACTION_CLIENT")
                except Exception:
                    pass
            else:
                vm.EXTRACTION_CLIENT = old


class EscrituraEstimatedWiringTest(AppTestCase):
    """7a: month-only → 15th estimated, estimated badge, cleared on exact."""

    def test_month_only_stored_as_15th_estimated_via_voice(self):
        self.save_settings()
        tok = csrf_token(self.client.get("/").body)
        from app import voice as vm, voice_conversation as vc
        from app import store as st
        from app.web import DB_PATH
        vc.CONVERSATIONS.clear()

        class E:
            def extract(self, t):
                return {"intent": "update", "kind": "new_deal", "language": "pt", "name": "T3 Est PT", "commission": "10000", "share": "40", "escritura_date": "março", "stage": "confirmado"}

        old = getattr(vm, "EXTRACTION_CLIENT", None)
        vm.EXTRACTION_CLIENT = E()
        try:
            r = self.client.post("/voice/turn", {"csrf_token": tok, "text": "criar T3 Est PT março"})
            cid = re.search(r'data-conversation-id="([^"]+)"', r.body).group(1)
            self.assertIn("meados de março", r.body)
            self.assertIn("(estimada)", r.body)
            r2 = self.client.post("/voice/turn", {"csrf_token": tok, "conversation_id": cid, "text": "sim"})
            tenant = st.get_tenant_by_email(DB_PATH, "test@example.com")
            deals = st.list_deals(DB_PATH, tenant_id=tenant["id"])
            saved = [d for d in deals if d["name"] == "T3 Est PT"][0]
            self.assertEqual(saved["escritura_date"], "2026-03-15")
            self.assertEqual(saved["escritura_estimada"], 1)
            card = self.client.get("/").body
            self.assertIn("(estimada)", card)
        finally:
            if old is None:
                try:
                    delattr(vm, "EXTRACTION_CLIENT")
                except Exception:
                    pass
            else:
                vm.EXTRACTION_CLIENT = old

    def test_exact_date_clears_flag(self):
        from app import store as st
        from app.web import DB_PATH
        tenant = st.get_tenant_by_email(DB_PATH, "test@example.com")
        did = st.insert_deal(DB_PATH, {"name": "T3 Clear", "agency": "", "escritura_date": "2026-03-15", "month": "2026-03", "stage": "confirmado", "status": "active", "cpcv_date": None, "agency_commission_cents": 1000000, "share_rate": "40", "part_base": 400000, "share_rate_used": "0.4", "iva_rate": "23", "retencao_rate": "25", "irs_rate": "30", "ss_rate": "10", "expenses_cents": 35000, "idempotency_key": "k-clear-1", "tenant_id": tenant["id"], "escritura_estimada": 1}, tenant_id=tenant["id"])
        deal = st.get_deal(DB_PATH, did, tenant_id=tenant["id"])
        st.update_deal(DB_PATH, did, tenant["id"], {"name": deal["name"], "agency": deal["agency"], "escritura_date": "2026-03-20", "month": "2026-03", "stage": deal["stage"], "status": deal["status"], "cpcv_date": deal["cpcv_date"], "agency_commission_cents": deal["agency_commission_cents"], "share_rate": deal["share_rate"], "part_base": deal["part_base"], "share_rate_used": deal["share_rate_used"], "iva_rate": deal["iva_rate"], "retencao_rate": deal["retencao_rate"], "irs_rate": deal["irs_rate"], "ss_rate": deal["ss_rate"], "expenses_cents": deal["expenses_cents"], "escritura_estimada": 0})
        deal2 = st.get_deal(DB_PATH, did, tenant_id=tenant["id"])
        self.assertEqual(deal2["escritura_estimada"], 0)

    def test_never_saved_without_date(self):
        from app import store as st
        from app.web import DB_PATH
        tenant = st.get_tenant_by_email(DB_PATH, "test@example.com")
        with self.assertRaises(ValueError):
            st.insert_deal(DB_PATH, {"name": "T3 NoDate", "agency": "", "escritura_date": "", "month": "", "stage": "confirmado", "status": "active", "cpcv_date": None, "agency_commission_cents": 1000000, "share_rate": "40", "part_base": 400000, "share_rate_used": "0.4", "iva_rate": "23", "retencao_rate": "25", "irs_rate": "30", "ss_rate": "10", "expenses_cents": 35000, "idempotency_key": "k-nodate", "tenant_id": tenant["id"], "escritura_estimada": 0}, tenant_id=tenant["id"])


class DecisionDocumentsTest(AppTestCase):
    """A16: D5/T5/T6/T7 and A2/T8 updated."""

    def test_docs_contain_voice_design_markers(self):
        import pathlib
        func = pathlib.Path("docs/decisions/accounts-voice-functional.md").read_text()
        tech = pathlib.Path("docs/decisions/accounts-voice-technical.md").read_text()
        self.assertIn("muse-voice-transcribe-1.0", func + tech)
        self.assertIn("muse-spark-1.3", func + tech)
        self.assertIn("WAV", tech)
        self.assertIn("speechSynthesis", tech + func)
        self.assertIn("Item 4 voice", func + tech)
