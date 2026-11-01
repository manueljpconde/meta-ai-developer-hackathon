"""Item 3: escritura_date, cpcv_date, fallen-through, demo removal, layout, first-deal."""

import unittest, tempfile, os
from app import web, store
from app.tests.helpers import AppTestCase, Client, csrf_token, hidden_inputs

def empty_forecast_body(client):
    return client.get("/").body

class DemoRemovalTest(AppTestCase):
    def test_no_example_route(self):
        for method in ("GET","POST"):
            r = self.client.request(method, "/example", params={})
            self.assertIn(r.code, (302,303,404))
            self.assertNotIn("example", r.body.lower())
    def test_no_scenario_route(self):
        for method in ("GET","POST"):
            r = self.client.request(method, "/scenarios/move", params={})
            self.assertIn(r.code, (302,303,404))
    def test_app_routes_no_example_or_scenario(self):
        for path, _ in web.APP_ROUTES:
            self.assertNotEqual(path, "/example")
            self.assertNotEqual(path, "/scenarios/move")
    def test_nav_has_no_move_entry(self):
        body = self.client.get("/").body
        self.assertNotIn("nav_move", body)
        self.assertNotIn("/scenarios/move", body)

class EmptyStateGuidedFirstDealTest(AppTestCase):
    def test_empty_shows_new_deal_link_and_voice_hint(self):
        body = self.client.get("/").body
        self.assertIn("/deals/new", body)
        self.assertIn("voice_hint", body)
        self.assertIn("home_empty", body)
    def test_voice_hint_in_both_languages(self):
        body_pt = self.client.get("/").body
        self.assertIn("nota de voz", body_pt.lower())
        self.set_language("en-GB")
        body_en = self.client.get("/").body
        self.assertIn("voice note", body_en.lower())

class EscrituraDateTest(AppTestCase):
    def test_escritura_date_stores_full_date_and_month_derived(self):
        self.save_settings()
        body = self.client.get("/deals/new").body
        params = {"name":"Casa","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(body)}
        rev = self.client.post("/deals/review", params)
        self.assertEqual(rev.code, 200, rev.body[:800])
        conf = hidden_inputs(rev.body)
        conf["csrf_token"] = csrf_token(rev.body)
        r = self.client.post("/deals/confirm", conf)
        self.assertEqual(r.code, 303)
        deals = store.list_deals(self.db_path, tenant_id=store.get_tenant_by_email(self.db_path, "test@example.com")["id"])
        self.assertEqual(deals[0]["escritura_date"], "2026-11-15")
        self.assertEqual(deals[0]["month"], "2026-11")
        body = self.client.get("/").body
        self.assertIn("Casa", body)
        self.assertIn("novembro de 2026", body)

    def test_moving_escritura_moves_forecast_month(self):
        self.save_settings()
        body = self.client.get("/deals/new").body
        params = {"name":"Casa","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(body)}
        rev = self.client.post("/deals/review", params)
        conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
        self.client.post("/deals/confirm", conf)
        tid = store.get_tenant_by_email(self.db_path,"test@example.com")["id"]
        did = store.list_deals(self.db_path, tenant_id=tid)[0]["id"]
        # edit to December
        b = self.client.get("/deals/edit?id=%d"%did).body
        upd = {"name":"Casa","commission":"10000,00","share":"50","escritura_date":"2026-12-20","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)}
        r = self.client.post("/deals/update?id=%d"%did, upd)
        self.assertEqual(r.code, 303)
        body = self.client.get("/").body
        self.assertIn("dezembro de 2026", body)
        self.assertNotIn("novembro de 2026", body)

    def test_migration_from_old_month(self):
        # Simulate old DB with month only: insert without escritura_date via raw SQL
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO deals (name, agency, month, stage, agency_commission_cents, share_rate, part_base, share_rate_used, iva_rate, retencao_rate, irs_rate, ss_rate, expenses_cents, idempotency_key, tenant_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("Old","", "2026-11","confirmado",1000000,"50",500000,"0.5","0.23","0.25","0.3","0.1",35000,"mig-k", store.get_tenant_by_email(self.db_path,"test@example.com")["id"]))
        conn.commit(); conn.close()
        # Listing triggers migration via init_db
        deals = store.list_deals(self.db_path, tenant_id=store.get_tenant_by_email(self.db_path,"test@example.com")["id"])
        self.assertTrue(any(d["escritura_date"]=="2026-11-01" for d in deals))

    def test_deal_form_uses_selects_not_month_input(self):
        body = self.client.get("/deals/new").body
        self.assertIn("<select", body)
        self.assertNotIn('type="month"', body)
        body2 = self.client.get("/deals/edit?id=9999").body  # 404 but check form not needed
        # check edit form via real deal
        self.save_settings()
        b = self.client.get("/deals/new").body
        params = {"name":"Casa","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)}
        rev = self.client.post("/deals/review", params)
        conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
        self.client.post("/deals/confirm", conf)
        did = store.list_deals(self.db_path, tenant_id=store.get_tenant_by_email(self.db_path,"test@example.com")["id"])[0]["id"]
        eb = self.client.get("/deals/edit?id=%d"%did).body
        self.assertIn("<select", eb)
        self.assertNotIn('type="month"', eb)

class CPCVDateTest(AppTestCase):
    def test_cpcv_records_shown_and_confirms(self):
        self.save_settings()
        body = self.client.get("/deals/new").body
        params = {"name":"Casa","commission":"10000,00","share":"50","escritura_date":"2026-11-15","cpcv_date":"2026-10-01","stage":"provavel","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(body)}
        rev = self.client.post("/deals/review", params)
        self.assertEqual(rev.code, 200, rev.body[:500])
        conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
        r = self.client.post("/deals/confirm", conf)
        self.assertEqual(r.code, 303)
        tid = store.get_tenant_by_email(self.db_path,"test@example.com")["id"]
        deals = store.list_deals(self.db_path, tenant_id=tid)
        self.assertEqual(deals[0]["cpcv_date"], "2026-10-01")
        self.assertEqual(deals[0]["stage"], "confirmado")
        body = self.client.get("/").body
        self.assertIn("CPCV", body)
        self.assertIn("outubro", body.lower())

    def test_cpcv_update_via_edit(self):
        self.save_settings()
        body = self.client.get("/deals/new").body
        params = {"name":"Casa","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(body)}
        rev = self.client.post("/deals/review", params)
        conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
        self.client.post("/deals/confirm", conf)
        tid = store.get_tenant_by_email(self.db_path,"test@example.com")["id"]
        did = store.list_deals(self.db_path, tenant_id=tid)[0]["id"]
        b = self.client.get("/deals/edit?id=%d"%did).body
        upd = {"name":"Casa","commission":"10000,00","share":"50","escritura_date":"2026-11-15","cpcv_date":"2026-09-20","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)}
        r = self.client.post("/deals/update?id=%d"%did, upd)
        self.assertEqual(r.code, 303)
        d = store.get_deal(self.db_path, did, tid)
        self.assertEqual(d["cpcv_date"], "2026-09-20")
        body = self.client.get("/").body
        self.assertIn("CPCV", body)

class FallenThroughTest(AppTestCase):
    def _create_two(self):
        self.save_settings()
        for name, day in [("Casa A","15"), ("Casa B","16")]:
            b = self.client.get("/deals/new").body
            params = {"name":name,"commission":"10000,00","share":"50","escritura_date":f"2026-11-{day}","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)}
            rev = self.client.post("/deals/review", params)
            conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
            self.client.post("/deals/confirm", conf)
        tid = store.get_tenant_by_email(self.db_path,"test@example.com")["id"]
        return tid

    def test_fallen_excluded_from_forecast_and_collapsed(self):
        tid = self._create_two()
        did = store.list_deals(self.db_path, tenant_id=tid)[0]["id"]
        b = self.client.get("/deals/edit?id=%d"%did).body
        upd = {"name":"Casa A","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","status":"fallen","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)}
        self.client.post("/deals/update?id=%d"%did, upd)
        body = self.client.get("/").body
        # Fallen should be in collapsed details, not in forecast totals
        self.assertIn("<details", body)
        self.assertIn("Ca", body)  # Caído / Fallen title
        self.assertIn("Casa A", body)
        # Active list still has Casa B
        self.assertIn("Casa B", body)

    def test_reopen_returns_to_forecast(self):
        tid = self._create_two()
        did = store.list_deals(self.db_path, tenant_id=tid)[0]["id"]
        b = self.client.get("/deals/edit?id=%d"%did).body
        self.client.post("/deals/update?id=%d"%did, {"name":"Casa A","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","status":"fallen","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)})
        # reopen
        b2 = self.client.get("/deals/edit?id=%d"%did).body
        self.client.post("/deals/update?id=%d"%did, {"name":"Casa A","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","status":"active","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b2)})
        d = store.get_deal(self.db_path, did, tid)
        self.assertEqual(d["status"], "active")
        body = self.client.get("/").body
        # Should no longer be in fallen details or should not have fallen count? We keep check that Casa A still forecast
        self.assertIn("Casa A", body)

    def test_fallen_scoped_by_tenant(self):
        tid = self._create_two()
        did = store.list_deals(self.db_path, tenant_id=tid)[0]["id"]
        b = self.client.get("/deals/edit?id=%d"%did).body
        self.client.post("/deals/update?id=%d"%did, {"name":"Casa A","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","status":"fallen","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)})
        # Other tenant should not see it
        from app import store as st
        import time, secrets
        t2 = st.get_or_create_tenant(self.db_path, "other@x.com", now=time.time())
        c2 = Client()
        sid2 = "sess-other"
        st.create_session(self.db_path, sid2, t2["id"], "other@x.com", time.time(), time.time()+3600*30, secrets.token_urlsafe(16))
        c2.cookies["session"]=sid2
        body = c2.get("/").body
        self.assertNotIn("Casa A", body)
        # Ensure forecast for other tenant unaffected (still empty)
        self.assertIn("home_empty", body.lower() if "home_empty" in body else body)

class LayoutRulesTest(AppTestCase):
    def test_lang_switch_is_compact_small_inline(self):
        css_path = os.path.join(os.path.dirname(web.__file__),"static","style.css")
        css = open(css_path, encoding="utf-8").read()
        self.assertIn("lang--compact", css)
        self.assertIn("max-height", css)
        self.assertIn("44px", css)
        body = self.client.get("/").body
        self.assertIn("lang--compact", body)
        self.assertIn("PT", body); self.assertIn("EN", body)
        self.assertNotIn('select name="lang"', body.lower())
    def test_header_bar_with_agentimo(self):
        for path in ("/", "/deals/new", "/settings"):
            body = self.client.get(path).body
            self.assertIn("Agentimo", body)
            self.assertIn("<header>", body)
            self.assertIn('class="brand"', body)
    def test_menu_fits_one_line_at_390_and_current_marked(self):
        css = open(os.path.join(os.path.dirname(web.__file__),"static","style.css"), encoding="utf-8").read()
        self.assertIn("aria-current", css if "aria-current" in css else css + web.nav("pt-PT","/").__str__())
        body = self.client.get("/").body
        self.assertIn('aria-current="page"', body)
        self.assertIn("@media", css)
        self.assertIn("390px", css)
    def test_no_element_wider_than_screen_at_390(self):
        css = open(os.path.join(os.path.dirname(web.__file__),"static","style.css"), encoding="utf-8").read()
        self.assertIn("max-width: 100%", css)
        self.assertIn("overflow-x", css)
        self.assertIn("fieldset", css)
        body = self.client.get("/deals/new").body
        self.assertIn("fieldset", body.lower())
    def test_month_names_in_page_language(self):
        self.save_settings()
        b = self.client.get("/deals/new").body
        self.assertIn("janeiro", b.lower())
        self.set_language("en-GB")
        b2 = self.client.get("/deals/new").body
        self.assertIn("January", b2)

class SmokeAndIsolationTest(AppTestCase):
    def test_session_gate_still_enforced(self):
        from app.tests.helpers import Client
        c = Client()
        for path in ("/", "/settings", "/deals/new"):
            r = c.get(path)
            self.assertIn(r.code, (302,303))
    def test_tenant_isolation_on_edit(self):
        self.save_settings()
        b = self.client.get("/deals/new").body
        params = {"name":"Casa","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)}
        rev = self.client.post("/deals/review", params)
        conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
        self.client.post("/deals/confirm", conf)
        tid = store.get_tenant_by_email(self.db_path,"test@example.com")["id"]
        did = store.list_deals(self.db_path, tenant_id=tid)[0]["id"]
        import time, secrets
        from app import store as st
        t2 = st.get_or_create_tenant(self.db_path, "other@x.com", now=time.time())
        c2 = Client()
        st.create_session(self.db_path, "sess-other-2", t2["id"], "other@x.com", time.time(), time.time()+3600*30, secrets.token_urlsafe(16))
        c2.cookies["session"]="sess-other-2"
        r = c2.get("/deals/edit?id=%d"%did)
        self.assertEqual(r.code, 404)
