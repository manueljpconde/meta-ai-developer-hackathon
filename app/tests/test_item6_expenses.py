"""Owner hotfix 1a: recorded expenses (item 6 A, C) and the Previsão dashboard (item 5 A).

Settings: IVA 23, retencao 25, IRS 30, SS 10, estimate 350 a month. Today is 10 November 2026.
A 10 000 EUR deal at 40 % gives 3 920 EUR in the bank, 1 520 EUR to set aside, 2 400 EUR yours.
"""
import os
import re
import time

from app import store, web
from app.tests.helpers import Client, csrf_token
from app.tests.test_item4f import deal_money, euros
from app.tests.voice_support import VoiceTestCase

DEAL = deal_money(1000000, 40)
ESTIMATE = 35000


class ExpenseBase(VoiceTestCase):
    TODAY = "2026-11-10"

    def setUp(self):
        super().setUp()
        old = os.environ.get("APP_NL_TODAY")
        os.environ["APP_NL_TODAY"] = self.TODAY
        self.addCleanup(lambda: os.environ.__setitem__("APP_NL_TODAY", old) if old is not None
                        else os.environ.pop("APP_NL_TODAY", None))

    def expense(self, date, cents, status="paid", deal_id=None, description="Almoço"):
        return store.insert_expense(self.db_path, self.tenant, {
            "description": description, "amount_cents": cents, "expense_date": date,
            "status": status, "deal_id": deal_id})

    def rule(self, month):
        return web.expense_rule(self.tenant)(month)

    def home(self, query="", lang="pt-PT"):
        return self.client.get("/" + query, accept_language=lang).body

    def card(self, body, month_label):
        start = body.index("<h2>%s</h2>" % month_label)
        return body[start:body.index("</section>", start)]

    def card_value(self, card, key):
        return re.search(r'data-i18n="%s">[^<]*</dt><dd>([^<]*)</dd>' % key, card).group(1)

    def post_form(self, path, fields, page="/expenses"):
        params = dict(fields)
        params.setdefault("form_locale", "pt-PT")
        params["csrf_token"] = csrf_token(self.client.get(page).body)
        return self.client.post(path, params)


class MonthRuleTest(ExpenseBase):
    def test_a_past_month_subtracts_only_its_recorded_expenses(self):
        self.add_deal("Outubro", date="2026-10-20")
        card = self.card(self.home(), "outubro de 2026")
        self.assertEqual(self.card_value(card, "m_expenses"), euros(0, "pt-PT"))
        self.assertEqual(self.card_value(card, "m_really"), euros(DEAL["bank"] - DEAL["aside"], "pt-PT"))
        self.expense("2026-10-03", 12000)
        self.expense("2026-10-30", 500, status="planned")
        card = self.card(self.home(), "outubro de 2026")
        self.assertEqual(self.card_value(card, "m_expenses"), euros(12500, "pt-PT"))
        self.assertEqual(self.card_value(card, "m_really"), euros(DEAL["bank"] - DEAL["aside"] - 12500, "pt-PT"))

    def test_a_future_month_subtracts_the_estimate_plus_planned_expenses_labelled_as_estimated(self):
        self.add_deal("Dezembro", date="2026-12-15")
        self.expense("2026-12-01", 20000, status="planned")
        card = self.card(self.home(), "dezembro de 2026")
        self.assertEqual(self.card_value(card, "m_expenses_est"), euros(ESTIMATE + 20000, "pt-PT"))
        self.assertIn("Despesas estimadas", card)
        self.assertIn("Estimated expenses", self.card(self.home(lang="en-GB"), "December 2026"))

    def test_the_current_month_takes_the_larger_of_recorded_and_estimate(self):
        self.assertEqual(self.rule("2026-11"), (ESTIMATE, True))
        self.expense("2026-11-02", 10000)
        self.assertEqual(self.rule("2026-11"), (ESTIMATE, True))
        self.expense("2026-11-05", 30000)
        self.assertEqual(self.rule("2026-11"), (40000, False))

    def test_a_backdated_expense_changes_only_its_own_month(self):
        months = ["2026-%02d" % m for m in range(6, 13)] + ["2027-01"]
        before = {m: self.rule(m) for m in months}
        self.expense("2026-09-14", 7700)
        after = {m: self.rule(m) for m in months}
        self.assertEqual({m for m in months if before[m] != after[m]}, {"2026-09"})
        self.assertEqual(after["2026-09"], (7700, False))

    def test_changing_the_estimate_changes_current_and_future_months_never_a_past_one(self):
        self.expense("2026-10-01", 1000)
        past, current, future = self.rule("2026-10"), self.rule("2026-11"), self.rule("2027-03")
        self.save_settings(dict(self.settings_values(), expenses="999,00"))
        self.assertEqual(self.rule("2026-10"), past)
        self.assertNotEqual(self.rule("2026-11"), current)
        self.assertEqual(self.rule("2027-03"), (99900, True))
        self.assertNotEqual(future, self.rule("2027-03"))

    def settings_values(self):
        from app.tests.helpers import SETTINGS_PT
        return SETTINGS_PT

    def test_dashboard_rows_match_the_month_cards_to_the_cent(self):
        self.add_deal("Nov", date="2026-11-20")
        self.add_deal("Dez A", date="2026-12-03", stage="provavel")
        self.add_deal("Dez B", commission=500000, date="2026-12-20", stage="potencial")
        self.expense("2026-12-05", 4000, status="planned")
        rule = web.expense_rule(self.tenant)
        deals = store.list_active_deals(self.db_path, self.tenant)
        body = self.home()
        for month, label in (("2026-11", "novembro de 2026"), ("2026-12", "dezembro de 2026")):
            row = web.dashboard_month(month, deals, rule)
            self.assertEqual(euros(row["really"], "pt-PT"), self.card_value(self.card(body, label), "m_really"))
            # each stage is counted before expenses and the month's expenses once
            self.assertEqual(sum(row["stages"].values()) - row["expenses"], row["really"])


class DashboardTest(ExpenseBase):
    def test_the_default_window_is_three_past_months_then_this_month_and_the_next_two(self):
        self.assertEqual(web.dashboard_months("2026-11", 0),
                         (["2026-08", "2026-09", "2026-10"], ["2026-11", "2026-12", "2027-01"]))
        self.assertEqual(web.dashboard_window({}), (0, 1))
        self.assertEqual(web.dashboard_window({"w": "-3", "step": "2"}), (-3, 2))
        for bad in ({"w": "x"}, {"w": "1.5"}, {"step": "3"}, {"step": "-"}):
            self.assertIn(web.dashboard_window(bad)[1], (1, 2))
        self.assertEqual(web.dashboard_window({"w": "40"}), (12, 1))
        self.assertEqual(web.dashboard_window({"w": "-40"}), (-12, 1))

    def test_the_arrows_move_by_the_step_and_are_disabled_at_each_limit(self):
        body = self.home("?w=0&step=2")
        self.assertIn('href="/?w=-2&amp;step=2"', body)
        self.assertIn('href="/?w=2&amp;step=2"', body)
        at_start = self.home("?w=-12&step=1")
        self.assertRegex(at_start, r'<span class="dash-arrow dash-off" aria-disabled="true"[^>]*>◀</span>')
        self.assertIn('href="/?w=-11&amp;step=1"', at_start)
        near_end = self.home("?w=11&step=2")
        self.assertIn('href="/?w=12&amp;step=2"', near_end, "a step past the limit stops at the limit")
        at_end = self.home("?w=12")
        self.assertRegex(at_end, r'<span class="dash-arrow dash-off" aria-disabled="true"[^>]*>▶</span>')
        self.assertIn('<a class="dash-today" href="/"', at_end)

    def test_the_headline_sums_the_three_previsto_months_and_its_confirmed_part(self):
        self.add_deal("Conf", date="2026-11-20", stage="confirmado")
        self.add_deal("Prov", date="2027-01-20", stage="provavel")
        body = self.home()
        really = (DEAL["bank"] - DEAL["aside"]) * 2 - 3 * ESTIMATE
        confirmed = DEAL["bank"] - DEAL["aside"]
        self.assertIn("Próximos 3 meses: <b>%s</b> realmente teus, <span class=\"dash-confirmed\">%s</span> confirmados"
                      % (euros(really, "pt-PT"), euros(confirmed, "pt-PT")), body)
        en = self.home(lang="en-GB")
        self.assertIn("Next 3 months: <b>%s</b> really yours" % euros(really, "en-GB"), en)
        shifted = self.home("?w=1")
        self.assertIn("dez 2026 – fev 2027: <b>", shifted)

    def test_recebido_shows_past_deals_and_recorded_expenses_and_previsto_the_split(self):
        self.add_deal("Setembro", date="2026-09-10")
        self.expense("2026-09-11", 6000)
        self.add_deal("Est", date="2026-12-10", stage="potencial", estimated=1)
        body = self.home()
        received = body[body.index("dash-received"):body.index("dash-expected")]
        self.assertIn("set 2026", received)
        self.assertIn(euros(DEAL["bank"], "pt-PT"), received)
        self.assertIn("despesas %s · realmente teu %s" % (euros(6000, "pt-PT"),
                                                         euros(DEAL["bank"] - DEAL["aside"] - 6000, "pt-PT")), received)
        expected = body[body.index("dash-expected"):]
        self.assertIn("despesas estimadas %s" % euros(ESTIMATE, "pt-PT"), expected)
        self.assertIn("1 negócio(s) com data estimada", expected)
        # one scale for both cards: September's 3 920 EUR bar is the longest, December's 2 400 EUR is 12/20
        self.assertIn("dash-seg--confirmado w20", received)
        self.assertIn("dash-seg--potencial w12", expected)

    def test_works_without_javascript_and_without_deals(self):
        body = self.home()
        self.assertIn("dash-headline", body)
        self.assertIn('href="/?w=1&amp;step=1"', body)
        self.assertIn('href="/?w=0&amp;step=2"', body)

    def test_the_dashboard_is_above_the_month_cards(self):
        self.add_deal("Nov", date="2026-11-20")
        body = self.home()
        self.assertLess(body.index("dash-headline"), body.index("forecast-grid"))

    def test_the_past_block_is_called_closed(self):
        self.assertIn('data-i18n="dash_received">Fechado</h2>', self.home())
        self.assertIn('data-i18n="dash_received">Closed</h2>', self.home(lang="en-GB"))


class ExpensePagesTest(ExpenseBase):
    def test_nav_has_despesas_between_new_deal_and_settings(self):
        for lang, word in (("pt-PT", "Despesas"), ("en-GB", "Expenses")):
            body = self.client.get("/expenses", accept_language=lang).body
            nav = body[body.index("<nav>"):body.index("</nav>")]
            self.assertLess(nav.index("/deals/new"), nav.index("/expenses"))
            self.assertLess(nav.index("/expenses"), nav.index("/settings"))
            self.assertIn('href="/expenses" data-i18n="nav_expenses" aria-current="page">%s<' % word, nav)

    def test_add_edit_and_delete_an_expense_linked_to_a_deal(self):
        deal_id = self.add_deal("T2 Alvalade", date="2026-12-15")
        response = self.post_form("/expenses/add", {
            "description": "Almoço com o cliente Alberto", "amount": "120,50",
            "expense_date_year": "2026", "expense_date_month": "10", "expense_date_day": "28",
            "status": "paid", "deal_id": str(deal_id)})
        self.assertEqual(response.code, 303, response.body[:400])
        page = self.client.get("/expenses?month=2026-10").body
        self.assertIn("Almoço com o cliente Alberto", page)
        self.assertIn(euros(12050, "pt-PT"), page)
        self.assertIn("T2 Alvalade", page)
        [item] = store.list_expenses(self.db_path, self.tenant)
        self.assertEqual((item["amount_cents"], item["deal_id"], item["status"]), (12050, deal_id, "paid"))
        deal_page = self.client.get("/deals/edit?id=%d" % deal_id).body
        self.assertIn("Despesas deste negócio", deal_page)
        self.assertIn("Almoço com o cliente Alberto", deal_page)
        edit = self.client.get("/expenses/edit?id=%d" % item["id"])
        self.assertEqual(edit.code, 200)
        response = self.post_form("/expenses/update?id=%d" % item["id"], {
            "description": "Almoço", "amount": "90", "expense_date": "2026-12-02",
            "status": "planned", "deal_id": ""})
        self.assertEqual(response.code, 303)
        [item] = store.list_expenses(self.db_path, self.tenant)
        self.assertEqual((item["amount_cents"], item["deal_id"], item["status"], item["expense_date"]),
                         (9000, None, "planned", "2026-12-02"))
        self.assertEqual(self.post_form("/expenses/delete?id=%d" % item["id"], {}).code, 303)
        self.assertEqual(store.list_expenses(self.db_path, self.tenant), [])

    def test_month_navigation_and_today(self):
        body = self.client.get("/expenses?month=2026-10").body
        self.assertIn('href="/expenses?month=2026-09"', body)
        self.assertIn('href="/expenses?month=2026-11"', body)
        self.assertIn('<a class="dash-today" href="/expenses"', body)
        self.assertIn("outubro de 2026", body)
        self.assertIn("novembro de 2026", self.client.get("/expenses?month=garbage").body)

    def test_bad_values_are_refused_with_the_form_kept(self):
        for amount, message in (("0", "maior que zero"), ("-5", "Valor inválido"), ("abc", "Valor inválido")):
            response = self.post_form("/expenses/add", {"description": "Gasóleo", "amount": amount,
                                                        "expense_date": "2026-11-03", "status": "paid"})
            self.assertEqual(response.code, 200)
            self.assertIn('value="Gasóleo"', response.body)
        missing = self.post_form("/expenses/add", {"description": " ", "amount": "10",
                                                   "expense_date": "2026-02-30", "status": "paid"})
        self.assertIn("Escreve uma descrição.", missing.body)
        self.assertIn("Escolhe uma data válida.", missing.body)
        self.assertEqual(store.list_expenses(self.db_path, self.tenant), [])

    def test_every_change_needs_the_csrf_token(self):
        eid = self.expense("2026-11-03", 1000)
        for path in ("/expenses/add", "/expenses/update?id=%d" % eid, "/expenses/delete?id=%d" % eid):
            response = self.client.post(path, {"description": "x", "amount": "1", "expense_date": "2026-11-03",
                                               "status": "paid", "csrf_token": "wrong"})
            self.assertEqual(response.code, 403, path)
        self.assertEqual(len(store.list_expenses(self.db_path, self.tenant)), 1)

    def test_markup_in_a_description_is_escaped(self):
        self.expense("2026-11-03", 1000, description='<script>alert(1)</script>')
        body = self.client.get("/expenses").body
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_settings_explains_the_estimate_and_warns_at_zero(self):
        body = self.client.get("/settings").body
        self.assertIn("Despesas mensais estimadas (€)", body)
        self.assertIn("Serve para te proteger: é descontado nos meses futuros", body)
        self.assertNotIn("Com 0 € de despesas", body)
        from app.tests.helpers import SETTINGS_PT
        self.save_settings(dict(SETTINGS_PT, expenses="0"))
        self.assertIn("Com 0 € de despesas, a previsão pode mostrar mais dinheiro do que vais ter.",
                      self.client.get("/settings").body)
        self.assertIn("With €0 expenses", self.client.get("/settings", accept_language="en-GB").body)


class ExpenseTenantTest(ExpenseBase):
    def other_client(self):
        email = "other@example.com"
        store.get_or_create_tenant(self.db_path, email, now=time.time())
        other = store.get_tenant_by_email(self.db_path, email)
        store.create_session(self.db_path, "s-other", other["id"], email, time.time(), time.time() + 3600, "tok-other")
        client = Client()
        client.cookies["session"] = "s-other"
        return client, other["id"]

    def test_another_agent_cannot_see_edit_delete_or_link(self):
        deal_id = self.add_deal("Meu", date="2026-11-20")
        eid = self.expense("2026-11-03", 4321, description="Segredo", deal_id=deal_id)
        client, other = self.other_client()
        self.assertNotIn("Segredo", client.get("/expenses?month=2026-11").body)
        self.assertEqual(client.get("/expenses/edit?id=%d" % eid).code, 404)
        for path in ("/expenses/update?id=%d" % eid, "/expenses/delete?id=%d" % eid):
            self.assertEqual(client.post(path, {"csrf_token": "tok-other", "description": "x", "amount": "1",
                                                "expense_date": "2026-11-03", "status": "paid"}).code, 404)
        refused = client.post("/expenses/add", {"csrf_token": "tok-other", "description": "x", "amount": "1",
                                                "expense_date": "2026-11-03", "status": "paid",
                                                "deal_id": str(deal_id), "form_locale": "pt-PT"})
        self.assertEqual(refused.code, 200)
        self.assertEqual(store.list_expenses(self.db_path, other), [])
        with self.assertRaises(ValueError):
            store.insert_expense(self.db_path, other, {"description": "x", "amount_cents": 1,
                                                       "expense_date": "2026-11-03", "status": "paid",
                                                       "deal_id": deal_id})
        self.assertEqual(store.expense_totals(self.db_path, other), {})
        self.assertEqual(store.get_expense(self.db_path, self.tenant, eid)["amount_cents"], 4321)

    def test_deleting_a_deal_keeps_its_expenses_unlinked_and_deleting_the_account_removes_them(self):
        deal_id = self.add_deal("Vai", date="2026-11-20")
        eid = self.expense("2026-11-03", 1000, deal_id=deal_id)
        store.delete_deal(self.db_path, deal_id, self.tenant)
        self.assertIsNone(store.get_expense(self.db_path, self.tenant, eid)["deal_id"])
        store.delete_tenant(self.db_path, self.tenant)
        conn = __import__("sqlite3").connect(self.db_path)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], 0)
        finally:
            conn.close()

    def test_store_refuses_non_positive_amounts_and_unknown_status(self):
        for fields in ({"amount_cents": 0}, {"amount_cents": -1}, {"status": "maybe"}, {"description": " "}):
            values = {"description": "x", "amount_cents": 1, "expense_date": "2026-11-03", "status": "paid"}
            values.update(fields)
            with self.assertRaises(ValueError):
                store.insert_expense(self.db_path, self.tenant, values)


class SigninWidthTest(ExpenseBase):
    def test_the_signin_form_keeps_a_form_width_on_desktop(self):
        from app.tests.test_item4f import declarations
        self.assertIn("max-width:28rem", declarations(".signin"))
        self.assertIn('<div class="signin">', Client().get("/signin").body)


class DashboardChartTest(ExpenseBase):
    def chart(self, body):
        return body[body.index('<section class="dash-card dash-chart">'):body.index("dash-blocks")]

    def test_one_column_per_window_month_with_its_value_and_a_today_mark(self):
        self.add_deal("Out", date="2026-10-20")
        self.add_deal("Dez", date="2026-12-10", stage="provavel")
        chart = self.chart(self.home())
        self.assertEqual(chart.count("<title>"), 6)
        for label in (">ago 2026<", ">set<", ">out<", ">nov<", ">dez<", ">jan 2027<"):
            self.assertIn(label, chart)
        self.assertIn(">2 400 €</text>", chart)  # October: no recorded expenses
        self.assertIn(">2 050 €</text>", chart)  # December: less the 350 EUR estimate
        self.assertIn('fill="#a7cec0"', chart)
        self.assertIn(">hoje</text>", chart)
        self.assertNotIn("<script", chart)

    def test_a_negative_month_is_flagged_in_chart_row_and_headline(self):
        body = self.home()
        chart = self.chart(body)
        self.assertIn('fill="#9e2f25"', chart)
        self.assertIn("⚠ -350 €", chart)
        self.assertIn("As despesas são maiores do que o que entra: faltam 350,00 €.", body)
        self.assertIn("⚠ 3 mês(es) negativo(s)", body)
        self.assertIn("3 negative month(s)", self.home(lang="en-GB"))

    def test_the_chart_follows_the_window(self):
        self.assertIn("jan 2028", self.chart(self.home("?w=12")))
        self.assertIn("ago 2025", self.chart(self.home("?w=-12")))


class OneFalarButtonTest(ExpenseBase):
    def test_below_1024_the_header_falar_is_hidden_by_the_last_rule_that_sets_its_display(self):
        from app.tests.test_item4f import CSS, css_rules
        last = None
        for media, selector, decl in css_rules(CSS):
            if selector == ".voice-falar-header" and "display:" in decl and (media == "" or "1023px" in media):
                last = (media, decl)
        self.assertIn("1023px", last[0])
        self.assertIn("display:none", last[1])
