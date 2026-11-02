"""The voice conversation over the JSON endpoints the page script uses (criteria A0 to 7d, 11 to 13).

Extraction and transcription are stubbed; nothing touches the network.
"""
import json
import re

from app import store, voice_flow
from app.tests.helpers import csrf_token
from app.tests.voice_support import (VoiceTestCase, ScriptedExtraction, ScriptedTranscription,
                                     make_wav, stub_clients, update)


class OneQuestionTest(VoiceTestCase):
    def test_panel_open_has_no_greeting_or_question(self):
        for lang in ("pt-PT", "en-GB"):
            body = self.client.get("/", accept_language=lang).body
            panel = body[body.index('id="voicePanel"'):]
            panel = panel[:panel.index("</form>")]
            for text in re.findall(r">([^<]+)<", panel):
                self.assertNotRegex(text, r"\?|Olá|Hello|Hi,")
            self.assertEqual(re.search(r'id="voiceQuestion"[^>]*></div>', body) is not None, True)

    def test_new_deal_missing_two_fields_one_question_pt_and_en(self):
        cases = (("pt-PT", "pt", "Qual é a comissão e a tua percentagem?"),
                 ("en-GB", "en", "What is the commission and your share?"))
        for page_lang, code, expected in cases:
            with self.subTest(lang=page_lang):
                extraction = ScriptedExtraction(update("new_deal", code, name="T3 Benfica", stage="confirmado",
                                                       escritura_date="2026-12-15"))
                with stub_clients(extraction):
                    token = self.page_token(page_lang)
                    data = self.voice("/voice/extract", token, page_lang, text="new deal T3 Benfica")
                self.assertEqual(data["state"], "ask")
                self.assertEqual(data["question"], expected)
                self.assertEqual(data["question"].count("?"), 1)
                self.assertEqual(self.deals(), [])

    def test_only_date_missing_asks_the_escritura_question(self):
        cases = (("pt-PT", "pt", "Qual é a data da escritura, mesmo aproximada?"),
                 ("en-GB", "en", "When is the escritura, even roughly?"))
        for page_lang, code, expected in cases:
            with self.subTest(lang=page_lang):
                extraction = ScriptedExtraction(update("new_deal", code, name="T1 Alvalade", stage="provavel",
                                                       commission="10000", share="40"))
                with stub_clients(extraction):
                    data = self.voice("/voice/extract", self.page_token(page_lang), page_lang, text="x")
                self.assertEqual(data["question"], expected)

    def test_missing_fields_are_decided_by_app_code(self):
        self.assertEqual(voice_flow.missing_for("new_deal", {"name": "T1"}),
                         ["commission", "share", "escritura_date", "stage"])
        self.assertEqual(voice_flow.missing_for("commission_received", {"deal": "T1", "amount": 5}), ["date"])
        # the model's own claim about what is missing is ignored
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T1", missing=[], stage="provavel"))
        with stub_clients(extraction):
            data = self.voice("/voice/extract", self.page_token(), text="x")
        self.assertEqual(data["state"], "ask")


class FullConversationTest(VoiceTestCase):
    def run_new_deal(self, page_lang, code, yes):
        extraction = ScriptedExtraction(
            update("new_deal", code, name="T3 Benfica", stage="confirmado", escritura_date="2026-12-15"),
            update("new_deal", code, commission="10000", share="40"))
        with stub_clients(extraction):
            token = self.page_token(page_lang)
            first = self.voice("/voice/extract", token, page_lang, text="novo T3 Benfica")
            self.assertEqual(first["state"], "ask")
            self.assertEqual(self.deals(), [])
            second = self.voice("/voice/extract", token, page_lang, conversation_id=first["conversation_id"],
                                text="10 000 euros e 40 %")
            self.assertEqual(second["state"], "confirm")
            self.assertEqual(second["conversation_id"], first["conversation_id"])
            self.assertEqual(self.deals(), [], "nothing is stored before the yes")
            done = self.voice("/voice/extract", token, page_lang, conversation_id=second["conversation_id"], text=yes)
        return first, second, done

    def test_full_pt_conversation(self):
        first, second, done = self.run_new_deal("pt-PT", "pt", "sim")
        self.assertEqual(second["readback"],
                         "T3 Benfica, 10\u00a0000 €, 40 %, a tua parte 4\u00a0000 €, escritura 15 dez. Confirmas?")
        self.assertEqual(done["state"], "saved")
        [deal] = self.deals()
        self.assertEqual((deal["name"], deal["agency_commission_cents"], deal["part_base"], deal["escritura_date"],
                          deal["escritura_estimada"]), ("T3 Benfica", 1000000, 400000, "2026-12-15", 0))

    def test_full_en_conversation(self):
        first, second, done = self.run_new_deal("en-GB", "en", "yes")
        self.assertEqual(second["readback"],
                         "T3 Benfica, €10,000, 40%, your share €4,000, escritura Dec 15. Do you confirm?")
        self.assertEqual(first["question"], "What is the commission and your share?")
        self.assertEqual(done["state"], "saved")
        self.assertEqual(len(self.deals()), 1)

    def test_voice_no_saves_nothing_and_asks_what_to_fix(self):
        extraction = ScriptedExtraction(
            update("new_deal", "pt", name="T2 Estrela", stage="confirmado", commission="8000", share="50",
                   escritura_date="2026-12-10"),
            update("new_deal", "pt", share="40"))
        with stub_clients(extraction):
            token = self.page_token()
            first = self.voice("/voice/extract", token, text="novo T2 Estrela")
            self.assertEqual(first["state"], "confirm")
            no = self.voice("/voice/extract", token, conversation_id=first["conversation_id"], text="não")
            self.assertEqual((no["state"], self.deals()), ("ask", []))
            fixed = self.voice("/voice/extract", token, conversation_id=no["conversation_id"], text="40 por cento")
        self.assertEqual(fixed["state"], "confirm")
        self.assertIn("40 %", fixed["readback"])
        self.assertIn("a tua parte 3\u00a0200 €", fixed["readback"])
        self.assertEqual(self.deals(), [])

    def test_confirm_button_saves_and_voice_yes_is_the_only_other_way(self):
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T2 Button", stage="provavel",
                                               commission="9000", share="40", escritura_date="2026-12-01"))
        with stub_clients(extraction):
            token = self.page_token()
            first = self.voice("/voice/extract", token, text="x")
            self.assertEqual(self.deals(), [])
            early = self.voice("/voice/confirm", token, conversation_id="not-a-conversation")
            self.assertEqual((early["state"], self.deals()), ("error", []))
            done = self.voice("/voice/confirm", token, conversation_id=first["conversation_id"])
        self.assertEqual(done["state"], "saved")
        self.assertEqual(len(self.deals()), 1)

    def test_confirm_before_the_read_back_saves_nothing(self):
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T2 Early", stage="provavel"))
        with stub_clients(extraction):
            token = self.page_token()
            first = self.voice("/voice/extract", token, text="x")
            data = self.voice("/voice/confirm", token, conversation_id=first["conversation_id"])
        self.assertEqual((data["state"], self.deals()), ("error", []))

    def test_double_confirm_saves_once(self):
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T2 Twice", stage="provavel",
                                               commission="9000", share="40", escritura_date="2026-12-01"))
        with stub_clients(extraction):
            token = self.page_token()
            first = self.voice("/voice/extract", token, text="x")
            self.voice("/voice/confirm", token, conversation_id=first["conversation_id"])
            again = self.voice("/voice/confirm", token, conversation_id=first["conversation_id"])
        self.assertEqual((again["state"], len(self.deals())), ("error", 1))


class StopsTest(VoiceTestCase):
    def test_cancel_saves_nothing_and_shows_what_was_understood(self):
        cases = (("pt-PT", "pt", "cancelar", "Cancelado. Nada foi guardado."),
                 ("en-GB", "en", "cancel", "Cancelled. Nothing was saved."))
        for page_lang, code, word, message in cases:
            with self.subTest(lang=page_lang):
                extraction = ScriptedExtraction(update("new_deal", code, name="T4 Cancel", stage="provavel"))
                with stub_clients(extraction):
                    token = self.page_token(page_lang)
                    first = self.voice("/voice/extract", token, page_lang, text="novo T4 Cancel")
                    data = self.voice("/voice/extract", token, page_lang, conversation_id=first["conversation_id"],
                                      text=word)
                self.assertEqual(data["state"], "cancelled")
                self.assertEqual(data["message"], message)
                self.assertIn("T4 Cancel", data["understood"])
                self.assertIn("novo T4 Cancel", data["transcript"])
                self.assertEqual(len(extraction.calls), 1, "cancel needs no model call")
                self.assertEqual(self.deals(), [])

    def test_cancel_button_endpoint(self):
        extraction = ScriptedExtraction(update("new_deal", "en", name="T4 Button", stage="provavel"))
        with stub_clients(extraction):
            token = self.page_token("en-GB")
            first = self.voice("/voice/extract", token, "en-GB", text="new deal T4 Button")
            data = self.voice("/voice/cancel", token, "en-GB", conversation_id=first["conversation_id"])
        self.assertEqual(data["message"], "Cancelled. Nothing was saved.")
        self.assertEqual(data["conversation_id"], "")
        self.assertEqual(self.deals(), [])

    def test_six_questions_without_completing_stop_the_conversation(self):
        for page_lang, code, message in (("pt-PT", "pt", "Demasiadas perguntas. Nada foi guardado."),
                                         ("en-GB", "en", "Too many questions. Nothing was saved.")):
            with self.subTest(lang=page_lang):
                extraction = ScriptedExtraction(*[update("new_deal", code, name="T5 Loop")] * 7)
                with stub_clients(extraction):
                    token = self.page_token(page_lang)
                    cid, states = "", []
                    for _ in range(7):
                        data = self.voice("/voice/extract", token, page_lang, conversation_id=cid, text="hmm")
                        states.append(data["state"])
                        cid = data["conversation_id"]
                        if data["state"] != "ask":
                            break
                self.assertEqual(states, ["ask"] * 6 + ["ended"])
                self.assertEqual(data["message"], message)
                self.assertIn("T5 Loop", data["understood"])
                self.assertEqual(self.deals(), [])

    def test_question_intent_gets_the_short_reply_and_saves_nothing(self):
        for page_lang, code, reply in (("pt-PT", "pt", "Ainda não sei responder a perguntas."),
                                       ("en-GB", "en", "I can't answer questions yet.")):
            extraction = ScriptedExtraction({"intent": "question", "language": code})
            with stub_clients(extraction):
                data = self.voice("/voice/extract", self.page_token(page_lang), page_lang, text="quanto?")
            self.assertEqual((data["state"], data["message"]), ("ended", reply))
            self.assertEqual(self.deals(), [])

    def test_daily_limit_refused_without_model_call_in_page_language(self):
        for _ in range(store.VOICE_DAILY_LIMIT):
            self.assertTrue(store.check_voice_limit(self.db_path, self.tenant))
        for page_lang, message in (("pt-PT", "Limite diário atingido. Tenta amanhã."),
                                   ("en-GB", "Daily limit reached. Try again tomorrow.")):
            extraction = ScriptedExtraction()
            transcription = ScriptedTranscription()
            with stub_clients(extraction, transcription):
                token = self.page_token(page_lang)
                typed = self.voice("/voice/extract", token, page_lang, text="novo T1")
                audio = self.client.request(
                    "POST", "/voice/transcribe?format=json&csrf_token=" + token, body=make_wav(1),
                    content_type="audio/wav", accept_language=page_lang)
            self.assertEqual(typed["message"], message)
            self.assertEqual(json.loads(audio.body)["message"], message)
            self.assertEqual((extraction.calls, transcription.audio), ([], []))

    def test_turns_of_one_conversation_do_not_use_up_the_daily_limit(self):
        extraction = ScriptedExtraction(*[update("new_deal", "pt", name="T6 Turns")] * 5)
        with stub_clients(extraction):
            token = self.page_token()
            cid = ""
            for _ in range(5):
                cid = self.voice("/voice/extract", token, conversation_id=cid, text="hmm")["conversation_id"]
        self.assertFalse(store.voice_limit_reached(self.db_path, self.tenant))


class SharePercentageInputTest(VoiceTestCase):
    """A percentage is read as a percentage; a bad share is asked again, never saved."""

    def new_deal(self, share, code="en"):
        return ScriptedExtraction(update("new_deal", code, name="Share check", stage="confirmado",
                                         escritura_date="2026-12-15", commission="10000", share=share))

    def test_one_percent_is_one_percent_not_a_hundred(self):
        for raw in ("1%", "1 %", "1 percent", "1 por cento", "1"):
            with self.subTest(share=raw):
                voice_flow.CONVERSATIONS.clear()
                for deal in self.deals():
                    store.delete_deal(self.db_path, deal["id"], self.tenant)
                with stub_clients(self.new_deal(raw)):
                    token = self.page_token("en-GB")
                    data = self.voice("/voice/extract", token, "en-GB", text="x")
                    self.assertEqual(data["state"], "confirm", data)
                    self.assertIn(", 1%,", data["readback"])
                    self.assertIn("your share €100,", data["readback"])
                    self.voice("/voice/confirm", token, "en-GB", conversation_id=data["conversation_id"])
                [deal] = self.deals()
                self.assertEqual((deal["share_rate_used"], deal["part_base"]), ("0.01", 10000))

    def test_a_percentage_sign_always_means_percent_and_a_plain_rate_is_kept(self):
        for raw, rate in (("40%", "0.4"), ("40", "0.4"), ("0.4", "0.4"), ("0,5%", "0.005"), ("100%", "1"),
                          ("12.5 percent", "0.125")):
            with self.subTest(raw=raw):
                self.assertEqual(voice_flow.parse_rate(raw), rate)

    def test_a_negative_or_out_of_range_share_is_never_a_rate(self):
        for raw in ("-40", "\u221240", "-1%", "0", "0%", "101%", "150", "1000", "abc", True):
            with self.subTest(raw=raw):
                self.assertIsNone(voice_flow.parse_rate(raw))

    def test_a_negative_or_out_of_range_share_is_asked_again_and_nothing_is_saved(self):
        for raw in ("-40", "-40%", "150", "0"):
            with self.subTest(share=raw):
                voice_flow.CONVERSATIONS.clear()
                with stub_clients(self.new_deal(raw)):
                    token = self.page_token("en-GB")
                    data = self.voice("/voice/extract", token, "en-GB", text="x")
                    self.assertEqual(data["state"], "ask", data)
                    early = self.voice("/voice/confirm", token, "en-GB", conversation_id=data["conversation_id"])
                    self.assertEqual(early["state"], "error")
                self.assertEqual(self.deals(), [])

    def test_a_valid_share_after_a_refused_one_is_saved_as_given(self):
        extraction = ScriptedExtraction(
            update("new_deal", "en", name="Share retry", stage="confirmado", escritura_date="2026-12-15",
                   commission="10000", share="-40"),
            update("new_deal", "en", share="40"))
        with stub_clients(extraction):
            token = self.page_token("en-GB")
            first = self.voice("/voice/extract", token, "en-GB", text="x")
            self.assertEqual(first["state"], "ask")
            second = self.voice("/voice/extract", token, "en-GB", conversation_id=first["conversation_id"],
                                text="40 percent")
            self.assertEqual(second["state"], "confirm", second)
            self.assertIn("40%", second["readback"])
            self.voice("/voice/confirm", token, "en-GB", conversation_id=second["conversation_id"])
        self.assertEqual([d["share_rate_used"] for d in self.deals()], ["0.4"])

    def test_a_refused_share_replaces_a_share_kept_earlier(self):
        extraction = ScriptedExtraction(
            update("new_deal", "en", name="Share swap", stage="confirmado", escritura_date="2026-12-15",
                   commission="10000", share="40"),
            update("new_deal", "en", share="-40"))
        with stub_clients(extraction):
            token = self.page_token("en-GB")
            first = self.voice("/voice/extract", token, "en-GB", text="x")
            self.assertEqual(first["state"], "confirm")
            second = self.voice("/voice/extract", token, "en-GB", conversation_id=first["conversation_id"],
                                text="make it minus 40")
            self.assertEqual(second["state"], "ask", second)
            self.voice("/voice/confirm", token, "en-GB", conversation_id=second["conversation_id"])
        self.assertEqual(self.deals(), [])

    def test_a_changed_percentage_that_is_negative_or_too_large_is_never_saved(self):
        did = self.add_deal("T3 Benfica", commission=1000000, rate="0.4")
        for raw in ("-45%", "150%"):
            with self.subTest(percentage=raw):
                voice_flow.CONVERSATIONS.clear()
                extraction = ScriptedExtraction(update("change_percentage", "pt", deal="T3 Benfica", percentage=raw))
                with stub_clients(extraction):
                    token = self.page_token()
                    data = self.voice("/voice/extract", token, text="x")
                    self.assertEqual(data["state"], "ask", data)
                    self.voice("/voice/confirm", token, conversation_id=data["conversation_id"])
                deal = store.get_deal(self.db_path, did, self.tenant)
                self.assertEqual((deal["share_rate_used"], deal["part_base"]), ("0.4", 400000))

    def test_a_changed_percentage_of_one_percent_is_one_percent(self):
        did = self.add_deal("T3 Benfica", commission=1000000, rate="0.4")
        extraction = ScriptedExtraction(update("change_percentage", "pt", deal="T3 Benfica", percentage="1%"))
        with stub_clients(extraction):
            token = self.page_token()
            data = self.voice("/voice/extract", token, text="x")
            self.assertEqual(data["state"], "confirm", data)
            self.voice("/voice/confirm", token, conversation_id=data["conversation_id"])
        deal = store.get_deal(self.db_path, did, self.tenant)
        self.assertEqual((deal["share_rate_used"], deal["part_base"]), ("0.01", 10000))


class EstimatedDateTest(VoiceTestCase):
    def test_month_only_is_stored_as_the_15th_estimated_and_counts_in_the_forecast(self):
        extraction = ScriptedExtraction(update(
            "new_deal", "pt", name="T1 Alvalade", stage="confirmado", commission="10000", share="40",
            escritura_date="ainda não está marcada, mas deve ser em março"))
        with stub_clients(extraction):
            token = self.page_token()
            data = self.voice("/voice/extract", token, text="x")
            self.assertIn("meados de março 2027 (estimada)", data["readback"])
            self.voice("/voice/extract", token, conversation_id=data["conversation_id"], text="sim")
        [deal] = self.deals()
        self.assertEqual((deal["escritura_date"], deal["escritura_estimada"]), ("2027-03-15", 1))
        page = self.client.get("/?month=2027-03").body
        self.assertIn("T1 Alvalade", page)
        self.assertIn("(estimada)", page)
        self.assertIn("4\u00a0000", page.replace(" ", "\u00a0"))

    def test_english_read_back_says_mid_month_estimated(self):
        extraction = ScriptedExtraction(update(
            "new_deal", "en", name="T1 Alvalade", stage="confirmado", commission="10000", share="40",
            escritura_date="2027-03"))
        with stub_clients(extraction):
            data = self.voice("/voice/extract", self.page_token("en-GB"), "en-GB", text="x")
        self.assertIn("mid-March 2027 (estimated)", data["readback"])

    def test_an_exact_day_stays_exact(self):
        extraction = ScriptedExtraction(update(
            "new_deal", "pt", name="T1 Exact", stage="confirmado", commission="10000", share="40",
            escritura_date="2026-12-15"))
        with stub_clients(extraction):
            token = self.page_token()
            data = self.voice("/voice/extract", token, text="x")
            self.voice("/voice/confirm", token, conversation_id=data["conversation_id"])
        self.assertEqual(self.deals()[0]["escritura_estimada"], 0)

    def test_an_exact_date_with_a_day_keeps_its_day_and_is_stored_as_exact(self):
        cases = (("en-GB", "en", "15 March 2027", "Mar 15", "2027-03-15"),
                 ("en-GB", "en", "March 15th, 2027", "Mar 15", "2027-03-15"),
                 ("pt-PT", "pt", "15 de março de 2027", "15 mar 2027", "2027-03-15"),
                 ("pt-PT", "pt", "15/03/2027", "15 mar 2027", "2027-03-15"),
                 ("en-GB", "en", "1st of April 2027", "Apr 1", "2027-04-01"))
        for page_lang, code, raw, shown, iso in cases:
            with self.subTest(date=raw):
                voice_flow.CONVERSATIONS.clear()
                for deal in self.deals():
                    store.delete_deal(self.db_path, deal["id"], self.tenant)
                extraction = ScriptedExtraction(update(
                    "new_deal", code, name="Exact day", stage="confirmado", commission="10000", share="40",
                    escritura_date=raw))
                with stub_clients(extraction):
                    token = self.page_token(page_lang)
                    data = self.voice("/voice/extract", token, page_lang, text="x")
                    self.assertEqual(data["state"], "confirm", data)
                    self.assertIn(shown, data["readback"])
                    for word in ("estimat", "mid-", "meados"):
                        self.assertNotIn(word, data["readback"])
                    self.voice("/voice/confirm", token, page_lang, conversation_id=data["conversation_id"])
                [deal] = self.deals()
                self.assertEqual((deal["escritura_date"], deal["escritura_estimada"]), (iso, 0))

    def test_parse_date_keeps_a_day_exact_and_a_month_alone_estimated(self):
        self.assertEqual(voice_flow.parse_date("15 March 2027"), ("2027-03-15", False))
        self.assertEqual(voice_flow.parse_date("march 3 2027"), ("2027-03-03", False))
        self.assertEqual(voice_flow.parse_date("2027-03-15"), ("2027-03-15", False))
        self.assertEqual(voice_flow.parse_date("March 2027"), ("2027-03-15", True))
        self.assertEqual(voice_flow.parse_date("2027-03"), ("2027-03-15", True))
        self.assertEqual(voice_flow.parse_date("31 February 2027"), (None, False))

    def test_a_later_exact_date_by_voice_clears_the_flag(self):
        did = self.add_deal("T3 Benfica", date="2027-03-15", estimated=1)
        extraction = ScriptedExtraction(update("escritura_date", "pt", deal="T3 Benfica", date="2027-03-20"))
        with stub_clients(extraction):
            token = self.page_token()
            data = self.voice("/voice/extract", token, text="x")
            self.assertNotIn("estimada", data["readback"])
            self.voice("/voice/confirm", token, conversation_id=data["conversation_id"])
        deal = store.get_deal(self.db_path, did, self.tenant)
        self.assertEqual((deal["escritura_date"], deal["month"], deal["escritura_estimada"]), ("2027-03-20", "2027-03", 0))

    def test_a_later_exact_date_on_the_form_clears_the_flag(self):
        did = self.add_deal("T3 Form", date="2027-03-15", estimated=1)
        body = self.client.get("/deals/edit?id=%d" % did).body
        self.assertIn('name="escritura_estimada"', body)
        self.assertRegex(body, r'name="escritura_estimada"[^>]*checked')
        params = {"csrf_token": csrf_token(body), "name": "T3 Form", "commission": "10000,00", "share": "40",
                  "escritura_date": "2027-03-20", "stage": "confirmado", "agency": "", "status": "active",
                  "form_locale": "pt-PT"}
        response = self.client.post("/deals/update?id=%d" % did, params)
        self.assertEqual(response.code, 303, response.body[:400])
        deal = store.get_deal(self.db_path, did, self.tenant)
        self.assertEqual((deal["escritura_date"], deal["escritura_estimada"]), ("2027-03-20", 0))

    def test_the_deal_form_has_the_estimated_date_checkbox_in_both_languages(self):
        for lang, label in (("pt-PT", "Data estimada"), ("en-GB", "Estimated date")):
            body = self.client.get("/deals/new", accept_language=lang).body
            self.assertRegex(body, r'<input type="checkbox" name="escritura_estimada" value="1"> %s' % label)

    def test_estimated_deals_show_the_marker_in_the_table_and_the_cards(self):
        self.add_deal("T5 Estimated", date="2026-12-15", estimated=1)
        self.add_deal("T5 Exact", date="2026-12-16", estimated=0)
        for lang, marker in (("pt-PT", "(estimada)"), ("en-GB", "(estimated)")):
            body = self.client.get("/?month=2026-12", accept_language=lang).body
            row = re.search(r'<tr class="deal-row">(?:(?!</tr>).)*T5 Estimated.*?</tr>', body).group(0)
            card = re.search(r'<article class="deal-card">(?:(?!</article>).)*T5 Estimated.*?</article>', body).group(0)
            self.assertIn(marker, row)
            self.assertIn(marker, card)
            exact_row = re.search(r'<tr class="deal-row">(?:(?!</tr>).)*T5 Exact.*?</tr>', body).group(0)
            self.assertNotIn(marker, exact_row)

    def test_the_form_can_save_an_estimated_date_without_voice(self):
        body = self.client.get("/deals/new").body
        params = {"csrf_token": csrf_token(body), "name": "T6 Form Est", "commission": "10000,00", "share": "40",
                  "escritura_date": "2026-12-15", "month": "2026-12", "stage": "confirmado", "agency": "",
                  "form_locale": "pt-PT", "escritura_estimada": "1"}
        review = self.client.post("/deals/review", params)
        hidden = dict(re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', review.body))
        self.assertEqual(hidden.get("escritura_estimada"), "1")
        hidden["csrf_token"] = csrf_token(review.body)
        self.assertEqual(self.client.post("/deals/confirm", hidden).code, 303)
        self.assertEqual(self.deals()[0]["escritura_estimada"], 1)

    def test_a_deal_is_never_saved_without_a_date(self):
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T1 NoDate", stage="provavel",
                                               commission="9000", share="40"))
        with stub_clients(extraction):
            token = self.page_token()
            data = self.voice("/voice/extract", token, text="x")
            self.assertEqual(data["question"], "Qual é a data da escritura, mesmo aproximada?")
            confirm = self.voice("/voice/confirm", token, conversation_id=data["conversation_id"])
        self.assertEqual((confirm["state"], self.deals()), ("error", []))
        with self.assertRaises(ValueError):
            self.add_deal("T1 Blank", date="")




class OtherUpdatesTest(VoiceTestCase):
    def confirm(self, reply, text="x", lang="pt-PT"):
        extraction = ScriptedExtraction(reply)
        with stub_clients(extraction):
            token = self.page_token(lang)
            data = self.voice("/voice/extract", token, lang, text=text)
            self.assertEqual(data["state"], "confirm", data)
            done = self.voice("/voice/extract", token, lang, conversation_id=data["conversation_id"],
                              text="sim" if lang == "pt-PT" else "yes")
        self.assertEqual(done["state"], "saved")
        return data

    def test_cpcv_signed_sets_the_date_and_confirms_the_deal(self):
        did = self.add_deal("T3 Benfica", stage="provavel")
        data = self.confirm(update("cpcv_signed", "pt", deal="T3 Benfica", date="2026-11-01"))
        self.assertEqual(data["readback"], "CPCV de T3 Benfica assinado a 1 nov.. Confirmas?".replace("nov..", "nov."))
        deal = store.get_deal(self.db_path, did, self.tenant)
        self.assertEqual((deal["cpcv_date"], deal["stage"]), ("2026-11-01", "confirmado"))

    def test_escritura_date_set_or_moved(self):
        did = self.add_deal("T2 Estrela", date="2026-12-15")
        self.confirm(update("escritura_date", "pt", deal="T2 Estrela", date="2027-01-20"))
        deal = store.get_deal(self.db_path, did, self.tenant)
        self.assertEqual((deal["escritura_date"], deal["month"]), ("2027-01-20", "2027-01"))

    def test_fell_through_then_reopen(self):
        did = self.add_deal("T1 Chiado")
        self.confirm(update("fell_through", "pt", deal="T1 Chiado"))
        self.assertEqual(store.get_deal(self.db_path, did, self.tenant)["status"], "fallen")
        data = self.confirm(update("reopen", "pt", deal="T1 Chiado"))
        self.assertEqual(data["readback"], "T1 Chiado volta a estar em curso. Confirmas?")
        self.assertEqual(store.get_deal(self.db_path, did, self.tenant)["status"], "active")

    def test_reopen_only_matches_fallen_deals(self):
        self.add_deal("T1 Active")
        extraction = ScriptedExtraction(update("reopen", "pt", deal="T1 Active"))
        with stub_clients(extraction):
            data = self.voice("/voice/extract", self.page_token(), text="x")
        self.assertEqual(data["state"], "ended")

    def test_commission_received_records_a_receipt(self):
        did = self.add_deal("T3 Benfica")
        data = self.confirm(update("commission_received", "pt", deal="T3 Benfica", amount="4 000 euros",
                                   date="2026-11-02"))
        self.assertEqual(data["readback"], "Comissão recebida de T3 Benfica: 4\u00a0000 €, a 2 nov. Confirmas?")
        self.assertEqual(store.list_receipts(self.db_path, self.tenant, did),
                         [{"id": 1, "deal_id": did, "amount_cents": 400000, "received_date": "2026-11-02"}])

    def test_commission_received_asks_for_amount_and_date_in_one_question(self):
        self.add_deal("T3 Benfica")
        extraction = ScriptedExtraction(update("commission_received", "en", deal="T3 Benfica"))
        with stub_clients(extraction):
            data = self.voice("/voice/extract", self.page_token("en-GB"), "en-GB", text="x")
        self.assertEqual(data["question"], "What is the amount and the date?")

    def test_change_stage(self):
        did = self.add_deal("T3 Benfica", stage="potencial")
        data = self.confirm(update("change_stage", "pt", deal="T3 Benfica", stage="confirmado"))
        self.assertEqual(data["readback"], "T3 Benfica passa a Confirmado. Confirmas?")
        self.assertEqual(store.get_deal(self.db_path, did, self.tenant)["stage"], "confirmado")

    def test_change_commission_recomputes_the_share_with_engine_calc(self):
        did = self.add_deal("T3 Benfica", commission=1000000, rate="0.4")
        data = self.confirm(update("change_commission", "en", deal="T3 Benfica", commission="12500"), lang="en-GB")
        self.assertEqual(data["readback"], "T3 Benfica: commission €12,500, your share €5,000. Do you confirm?")
        deal = store.get_deal(self.db_path, did, self.tenant)
        self.assertEqual((deal["agency_commission_cents"], deal["part_base"]), (1250000, 500000))

    def test_change_percentage_recomputes_the_share(self):
        did = self.add_deal("T3 Benfica", commission=1000000, rate="0.4")
        self.confirm(update("change_percentage", "pt", deal="T3 Benfica", percentage="45 %"))
        deal = store.get_deal(self.db_path, did, self.tenant)
        self.assertEqual((deal["share_rate_used"], deal["part_base"]), ("0.45", 450000))

    def test_missing_deal_field_asks_one_question(self):
        self.add_deal("T3 Benfica")
        extraction = ScriptedExtraction(update("change_commission", "pt", deal="T3 Benfica"))
        with stub_clients(extraction):
            data = self.voice("/voice/extract", self.page_token(), text="x")
        self.assertEqual(data["question"], "Qual é a comissão?")


class DealMatchingTest(VoiceTestCase):
    def test_no_match_asks_naming_the_candidates(self):
        self.add_deal("T3 Benfica")
        self.add_deal("T2 Estrela")
        extraction = ScriptedExtraction(update("fell_through", "pt", deal="Moradia Sintra"))
        with stub_clients(extraction):
            data = self.voice("/voice/extract", self.page_token(), text="x")
        self.assertEqual(data["state"], "ask")
        self.assertIn("Moradia Sintra", data["question"])
        self.assertIn("T3 Benfica", data["question"])
        self.assertIn("T2 Estrela", data["question"])
        self.assertEqual(data["question"].count("?"), 1)

    def test_several_matches_ask_naming_them_and_the_answer_picks_one(self):
        first = self.add_deal("T3 Benfica")
        self.add_deal("T3 Alvalade")
        extraction = ScriptedExtraction(update("fell_through", "pt", deal="T3"),
                                        update("fell_through", "pt", deal="T3 Benfica"))
        with stub_clients(extraction):
            token = self.page_token()
            ask = self.voice("/voice/extract", token, text="o T3 caiu")
            self.assertIn("T3 Benfica", ask["question"])
            self.assertIn("T3 Alvalade", ask["question"])
            confirm = self.voice("/voice/extract", token, conversation_id=ask["conversation_id"], text="Benfica")
            self.assertEqual(confirm["state"], "confirm")
            self.voice("/voice/confirm", token, conversation_id=confirm["conversation_id"])
        self.assertEqual(store.get_deal(self.db_path, first, self.tenant)["status"], "fallen")

    def test_deals_of_other_agents_are_never_matched(self):
        other = store.get_or_create_tenant(self.db_path, "other@example.com", now=1)["id"]
        store.insert_deal(self.db_path, {
            "name": "T9 Secret", "agency": "", "escritura_date": "2026-12-15", "month": "2026-12",
            "stage": "confirmado", "status": "active", "cpcv_date": None, "agency_commission_cents": 100,
            "share_rate": "40", "part_base": 40, "share_rate_used": "0.4", "iva_rate": "23",
            "retencao_rate": "25", "irs_rate": "30", "ss_rate": "10", "expenses_cents": 0,
            "idempotency_key": "other-1", "tenant_id": other}, tenant_id=other)
        extraction = ScriptedExtraction(update("fell_through", "pt", deal="T9 Secret"))
        with stub_clients(extraction):
            data = self.voice("/voice/extract", self.page_token(), text="x")
        self.assertEqual(data["state"], "ended")
        self.assertEqual(data["message"], "Ainda não tens negócios.")

    def test_another_agent_cannot_use_my_conversation(self):
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T7 Mine", stage="provavel",
                                               commission="9000", share="40", escritura_date="2026-12-01"))
        with stub_clients(extraction):
            data = self.voice("/voice/extract", self.page_token(), text="x")
        conv = voice_flow.get_conversation(data["conversation_id"])
        self.assertIsNone(voice_flow.get_conversation(data["conversation_id"], tenant_id=conv["tenant_id"] + 1))


class LanguageTest(VoiceTestCase):
    def test_an_english_answer_on_a_portuguese_page_gets_english_questions(self):
        extraction = ScriptedExtraction(
            update("new_deal", "pt", name="T3 Lang"),
            update("new_deal", "en", commission="10000"))
        with stub_clients(extraction):
            token = self.page_token("pt-PT")
            first = self.voice("/voice/extract", token, "pt-PT", text="novo T3 Lang")
            self.assertEqual(first["lang"], "pt-PT")
            self.assertTrue(first["question"].startswith("Qual é"))
            second = self.voice("/voice/extract", token, "pt-PT", conversation_id=first["conversation_id"],
                                text="the commission is ten thousand")
        self.assertEqual(second["lang"], "en-GB")
        self.assertTrue(second["question"].startswith("What is"), second["question"])

    def test_a_short_answer_keeps_the_conversations_language(self):
        extraction = ScriptedExtraction(
            update("new_deal", "en", name="T3 Short", stage="provavel", escritura_date="2026-12-15"),
            update("new_deal", "pt", share="40"))
        with stub_clients(extraction):
            token = self.page_token("pt-PT")
            first = self.voice("/voice/extract", token, "pt-PT", text="new deal T3 Short")
            self.assertEqual(first["lang"], "en-GB")
            second = self.voice("/voice/extract", token, "pt-PT", conversation_id=first["conversation_id"], text="40")
        self.assertEqual(second["lang"], "en-GB")
        self.assertEqual(second["state"], "ask")
        self.assertEqual(second["question"], "What is the commission?")

    def test_a_bare_number_fills_the_one_numeric_field_asked(self):
        extraction = ScriptedExtraction(
            update("new_deal", "pt", name="T3 Bare", stage="provavel", escritura_date="2026-12-15",
                   commission="10000"),
            update("new_deal", "pt"))
        with stub_clients(extraction):
            token = self.page_token()
            first = self.voice("/voice/extract", token, text="novo T3 Bare, comissão 10000")
            self.assertEqual(first["question"], "Qual é a tua percentagem?")
            second = self.voice("/voice/extract", token, conversation_id=first["conversation_id"], text="40")
        self.assertEqual(second["state"], "confirm")


class TypedConversationTest(VoiceTestCase):
    def test_typed_conversation_stays_in_the_panel_and_keeps_the_conversation_id(self):
        extraction = ScriptedExtraction(
            update("new_deal", "pt", name="T1 Alvalade", stage="confirmado", escritura_date="março"),
            update("new_deal", "pt", commission="10000", share="40"))
        with stub_clients(extraction):
            token = self.page_token()
            first = self.voice("/voice/extract", token, text="Novo negócio T1 em Alvalade, escritura lá para março")
            second = self.voice("/voice/extract", token, conversation_id=first["conversation_id"],
                                text="10 000 euros, 40 por cento")
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        self.assertEqual(second["state"], "confirm")
        self.assertIn("(estimada)", second["readback"])
        self.assertIn("Novo negócio T1 em Alvalade", second["transcript"])
        self.assertIn("10 000 euros, 40 por cento", second["transcript"])

    def test_without_the_script_the_endpoint_answers_a_page_with_the_same_forms(self):
        extraction = ScriptedExtraction(update("new_deal", "en", name="T1 Plain"))
        with stub_clients(extraction):
            token = self.page_token("en-GB")
            response = self.client.post("/voice/extract", {"csrf_token": token, "text": "new T1 Plain"})
        self.assertIn("What is", response.body)
        self.assertIn('placeholder="Type here…"', response.body)
        self.assertIn(">Cancel<", response.body)
        self.assertIn(">Send<", response.body)
        self.assertNotIn("Cancelar", response.body)

    def test_a_transcription_or_extraction_failure_is_an_error_with_the_typed_path_open(self):
        from app.voice import ModelError
        extraction = ScriptedExtraction(ModelError("boom"))
        with stub_clients(extraction):
            data = self.voice("/voice/extract", self.page_token(), text="x")
        self.assertEqual(data["state"], "error")
        self.assertEqual(data["message"], "Não consegui perceber. Escreve em baixo.")
        self.assertNotIn("boom", str(data))
        self.assertEqual(self.deals(), [])

    def test_wrong_csrf_is_refused_with_no_model_call(self):
        extraction = ScriptedExtraction()
        with stub_clients(extraction):
            response = self.client.request("POST", "/voice/extract",
                                           params={"csrf_token": "wrong", "format": "json", "text": "x"})
        self.assertEqual(response.code, 403)
        self.assertEqual(extraction.calls, [])


class SpokenConversationTest(VoiceTestCase):
    def post_audio(self, token, wav, lang="pt-PT", cid=""):
        url = "/voice/transcribe?format=json&csrf_token=%s&conversation_id=%s" % (token, cid)
        response = self.client.request("POST", url, body=wav, content_type="audio/wav", accept_language=lang)
        self.assertEqual(response.code, 200, response.body[:300])
        return json.loads(response.body)

    def test_a_wav_body_is_transcribed_then_handled_like_typed_text(self):
        transcription = ScriptedTranscription("novo T1 Voz")
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T1 Voz", stage="provavel",
                                               commission="9000", share="40", escritura_date="2026-12-02"))
        wav = make_wav(2)
        with stub_clients(extraction, transcription):
            data = self.post_audio(self.page_token(), wav)
        self.assertEqual(transcription.audio, [wav])
        self.assertEqual(extraction.calls, ["novo T1 Voz"])
        self.assertEqual(data["state"], "confirm")
        self.assertEqual(data["transcript"], "novo T1 Voz")

    def test_a_bad_wav_is_refused_before_any_model_call_in_the_page_language(self):
        bad = {"not riff": b"x" * 100, "stereo": make_wav(1, channels=2), "44 kHz": make_wav(1, rate=44100),
               "8 bit": make_wav(1, bits=8), "not pcm": make_wav(1, fmt=3), "over 60 s": make_wav(62)}
        for lang, message in (("pt-PT", "Áudio inválido. Envia WAV mono 16-bit a 16000 Hz, até 60 s."),
                              ("en-GB", "Invalid audio. Send mono 16-bit WAV at 16000 Hz, up to 60 s.")):
            for name, wav in bad.items():
                with self.subTest(lang=lang, wav=name):
                    transcription = ScriptedTranscription()
                    extraction = ScriptedExtraction()
                    with stub_clients(extraction, transcription):
                        data = self.post_audio(self.page_token(lang), wav, lang)
                    self.assertEqual((data["state"], data["message"]), ("error", message))
                    self.assertEqual((transcription.audio, extraction.calls), ([], []))

    def test_a_good_60_second_wav_is_accepted(self):
        transcription = ScriptedTranscription("olá")
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T1"))
        with stub_clients(extraction, transcription):
            data = self.post_audio(self.page_token(), make_wav(60))
        self.assertEqual(data["state"], "ask")

    def test_no_audio_is_stored(self):
        transcription = ScriptedTranscription("novo T1 Audio")
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T1 Audio"))
        wav = make_wav(1)
        with stub_clients(extraction, transcription):
            self.post_audio(self.page_token(), wav)
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            dump = "\n".join(conn.iterdump())
        self.assertNotIn("RIFF", dump)
        with open(self.db_path, "rb") as handle:
            self.assertNotIn(b"RIFF", handle.read())
        self.assertEqual(
            sqlite3.connect(self.db_path).execute("SELECT transcript FROM voice_conversations").fetchall(),
            [("novo T1 Audio",)])

    def test_an_empty_transcript_is_an_error_and_makes_no_extraction_call(self):
        transcription = ScriptedTranscription("   ")
        extraction = ScriptedExtraction()
        with stub_clients(extraction, transcription):
            data = self.post_audio(self.page_token(), make_wav(1))
        self.assertEqual((data["state"], extraction.calls), ("error", []))

    def test_an_oversized_body_is_refused_before_it_is_read(self):
        extraction = ScriptedExtraction()
        with stub_clients(extraction, ScriptedTranscription()):
            data = self.post_audio(self.page_token(), make_wav(75))
        self.assertEqual(data["state"], "error")
        self.assertEqual(extraction.calls, [])
