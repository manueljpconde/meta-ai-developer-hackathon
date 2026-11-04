"""Owner hotfix 1b: an expense by voice, through the one Falar button (item 6 B4, B5)."""
from app import store
from app.tests.test_item6_expenses import ExpenseBase
from app.tests.voice_support import ScriptedExtraction, stub_clients


def expense(**fields):
    reply = {"intent": "expense", "kind": "expense", "language": fields.pop("language", "pt")}
    reply.update(fields)
    return reply


class VoiceExpenseTest(ExpenseBase):
    def talk(self, extraction, *texts, lang="pt-PT"):
        out, cid = [], ""
        with stub_clients(extraction):
            token = self.page_token(lang)
            for text in texts:
                data = self.voice("/voice/extract", token, accept_language=lang, conversation_id=cid, text=text)
                cid = data.get("conversation_id", "")
                out.append(data)
        return out

    def test_lunch_with_a_client_of_a_deal_today_paid_then_sim_saves(self):
        deal_id = self.add_deal("T2 Alvalade", date="2026-12-15")
        said = "Almocei com o cliente Alberto, do negócio Alvalade, 120 euros de almoço"
        first, saved = self.talk(ScriptedExtraction(
            expense(description="Almoço com o cliente Alberto", amount=120, deal="Alvalade", status="paid")),
            said, "sim")
        self.assertEqual(first["state"], "confirm", first)
        self.assertEqual(first["readback"], "Almoço com o cliente Alberto, 120 €, hoje, negócio T2 Alvalade. Confirmas?")
        self.assertEqual(saved["state"], "saved")
        [row] = store.list_expenses(self.db_path, self.tenant)
        self.assertEqual((row["description"], row["amount_cents"], row["expense_date"], row["status"], row["deal_id"]),
                         ("Almoço com o cliente Alberto", 12000, self.TODAY, "paid", deal_id))

    def test_vou_ter_de_pagar_is_planned_with_its_date_and_no_deal(self):
        first, _ = self.talk(ScriptedExtraction(
            expense(description="Gasóleo", amount=50, date="2026-11-20", status="planned")),
            "Vou ter de pagar 50 euros de gasóleo no dia 20", "sim")
        self.assertEqual(first["readback"], "Gasóleo, 50 €, 20 nov, prevista. Confirmas?")
        [row] = store.list_expenses(self.db_path, self.tenant)
        self.assertEqual((row["status"], row["expense_date"], row["deal_id"]), ("planned", "2026-11-20", None))

    def test_an_unclear_deal_asks_one_question_naming_the_candidates(self):
        self.add_deal("T2 Alvalade", date="2026-12-15")
        second = self.add_deal("T3 Alvalade", date="2027-01-15")
        asked, confirmed = self.talk(ScriptedExtraction(
            expense(description="Almoço", amount=30, deal="Alvalade"),
            {"intent": "update", "language": "pt", "deal": "T3 Alvalade"}),
            "Almoço de 30 euros do negócio Alvalade", "o T3")
        self.assertEqual(asked["state"], "ask")
        self.assertEqual(asked["question"], "Qual destes negócios: T2 Alvalade, T3 Alvalade?")
        self.assertEqual(confirmed["state"], "confirm", confirmed)
        self.assertIn("negócio T3 Alvalade", confirmed["readback"])
        self.assertEqual(self.voice_saved_deal(confirmed), second)

    def voice_saved_deal(self, confirmed):
        with stub_clients(ScriptedExtraction()):
            self.voice("/voice/extract", self.page_token(), conversation_id=confirmed["conversation_id"], text="sim")
        return store.list_expenses(self.db_path, self.tenant)[0]["deal_id"]

    def test_a_day_said_without_a_month_is_this_month(self):
        first, _ = self.talk(ScriptedExtraction(expense(description="gasóleo", amount=45, day=20, status="planned")),
                             "Vou ter de pagar 45 euros de gasóleo no dia 20.", "sim")
        self.assertEqual(first["readback"], "Gasóleo, 45 €, 20 nov, prevista. Confirmas?")
        self.assertEqual(store.list_expenses(self.db_path, self.tenant)[0]["expense_date"], "2026-11-20")

    def test_a_missing_amount_is_asked(self):
        asked, = self.talk(ScriptedExtraction(expense(description="Almoço")), "Almocei com um cliente")
        self.assertEqual((asked["state"], asked["question"]), ("ask", "Qual é o valor?"))

    def test_in_english(self):
        first, _ = self.talk(ScriptedExtraction(
            expense(language="en", description="Lunch with client Alberto", amount=120, status="paid")),
            "I had lunch with client Alberto, 120 euros", "yes", lang="en-GB")
        self.assertEqual(first["readback"], "Lunch with client Alberto, €120, today. Do you confirm?")
        self.assertEqual(store.list_expenses(self.db_path, self.tenant)[0]["amount_cents"], 12000)

    def test_a_deal_of_another_agent_is_never_matched(self):
        import time
        mine = self.tenant
        store.get_or_create_tenant(self.db_path, "other@example.com", now=time.time())
        self.tenant = store.get_tenant_by_email(self.db_path, "other@example.com")["id"]
        self.add_deal("Segredo", date="2026-12-15")
        self.tenant = mine
        self.add_deal("Meu", date="2026-12-15")
        asked, = self.talk(ScriptedExtraction(expense(description="Almoço", amount=30, deal="Segredo")), "almoço do Segredo")
        self.assertEqual(asked["state"], "ask")
        self.assertTrue(asked["question"].endswith("Qual destes negócios: Meu?"), asked["question"])
