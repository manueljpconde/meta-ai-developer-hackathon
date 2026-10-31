"""Cross-tenant web-route tests: B sending A's deal id to every deal-changing route
yields no data and leaves A's deal unchanged. Deletion through typed-address
page proves no tenant rows of any kind remain.
"""

import unittest
from app.tests.helpers import AppTestCase, Client, csrf_token, SETTINGS_PT, hidden_inputs


def make_client(db_path, email):
    from app import store
    import time, secrets
    store.get_or_create_tenant(db_path, email, now=time.time())
    tenant = store.get_tenant_by_email(db_path, email)
    sid = "hardening-session-" + email
    csrf = secrets.token_urlsafe(16)
    store.create_session(db_path, sid, tenant["id"], email, time.time(), time.time() + 3600*24*30, csrf)
    c = Client()
    c.cookies["session"] = sid
    return c

DEAL_A_ROWS = {
    "name": "Deal-Alpha",
    "commission": "10000,00",
    "share": "50",
    "month": "2026-11",
    "stage": "confirmado",
    "agency": "Agency-A",
    "form_locale": "pt-PT",
}

class CrossTenantWebRouteTest(AppTestCase):
    def _seed_deal_for(self, email):
        client = make_client(self.db_path, email)
        body = client.get("/settings").body
        p = dict(SETTINGS_PT)
        p["csrf_token"] = csrf_token(body)
        client.post("/settings", p)
        body = client.get("/deals/new").body
        p = dict(DEAL_A_ROWS)
        p["csrf_token"] = csrf_token(body)
        rev = client.post("/deals/review", p)
        h = hidden_inputs(rev.body)
        h["csrf_token"] = csrf_token(rev.body)
        client.post("/deals/confirm", h)
        return client

    def _deals_for(self, email):
        from app import store
        t = store.get_tenant_by_email(self.db_path, email)
        return store.list_deals(self.db_path, tenant_id=t["id"])

    def _deal_id_for(self, email):
        return self._deals_for(email)[0]["id"]

    def test_agent_b_cannot_read_or_change_a_deal_via_edit_route(self):
        a_client = self._seed_deal_for("a@hardening.com")
        b_client = self._seed_deal_for("b@hardening.com")
        a_id = self._deal_id_for("a@hardening.com")
        a_before = self._deals_for("a@hardening.com")[0]
        # B GET edit with A's id -> 404, no data
        resp = b_client.get("/deals/edit?id=%d" % a_id)
        self.assertEqual(resp.code, 404, resp.body[:500])
        self.assertNotIn("Deal-Alpha", resp.body)
        # B POST update with A's id -> 404, no change to A's deal
        body = b_client.get("/deals/new").body
        resp2 = b_client.request("POST", "/deals/update?id=%d" % a_id, {
            "name": "Intruded",
            "commission": "9999,00",
            "share": "10",
            "month": "2026-12",
            "stage": "potencial",
            "agency": "",
            "form_locale": "pt-PT",
            "csrf_token": csrf_token(body),
        })
        self.assertEqual(resp2.code, 404, resp2.body[:500])
        # A's deal unchanged
        a_after = self._deals_for("a@hardening.com")[0]
        self.assertEqual(a_before["name"], a_after["name"])
        self.assertEqual(a_before["month"], a_after["month"])
        self.assertEqual(a_before["part_base"], a_after["part_base"])

    def test_agent_b_cannot_change_a_deal_via_confirm_route_sending_a_id(self):
        a_client = self._seed_deal_for("a2@hardening.com")
        a_id = self._deal_id_for("a2@hardening.com")
        a_before = self._deals_for("a2@hardening.com")[0]
        # B is a different tenant; confirm route does not take an id param (insert-only)
        # but we prove B's confirm does not modify A's deal even if B tries to send A's id as hidden field
        b_client = make_client(self.db_path, "b2@hardening.com")
        body = b_client.get("/settings").body
        p = dict(SETTINGS_PT)
        p["csrf_token"] = csrf_token(body)
        b_client.post("/settings", p)
        # B reviews and confirms with an extra id field set to A's id - must not affect A
        body = b_client.get("/deals/new").body
        params = dict(DEAL_A_ROWS)
        params["name"] = "Intrusion-via-confirm"
        params["csrf_token"] = csrf_token(body)
        rev = b_client.post("/deals/review", params)
        h = hidden_inputs(rev.body)
        h["csrf_token"] = csrf_token(rev.body)
        h["id"] = str(a_id)
        b_client.post("/deals/confirm", h)
        # A unchanged
        a_after = self._deals_for("a2@hardening.com")[0]
        self.assertEqual(a_before["name"], a_after["name"])
        self.assertEqual(a_before["part_base"], a_after["part_base"])
        # A's row count unchanged (1)
        self.assertEqual(len(self._deals_for("a2@hardening.com")), 1)
        # B did not leak into A
        self.assertNotIn("Intrusion", a_after["name"])

    def test_agent_b_cannot_change_a_deal_via_move_scenario_sending_a_id(self):
        a_client = self._seed_deal_for("a3@hardening.com")
        b_client = self._seed_deal_for("b3@hardening.com")
        a_id = self._deal_id_for("a3@hardening.com")
        a_before_month = self._deals_for("a3@hardening.com")[0]["month"]
        # B's move page must not list A's deal
        body = b_client.get("/scenarios/move").body
        self.assertNotIn("Deal-Alpha", body)
        # B posts a move referencing A's deal id - must not affect A
        body = b_client.get("/scenarios/move").body
        csrf = csrf_token(body)
        resp = b_client.post("/scenarios/move", {"sentence": "move Deal-Alpha to December", "csrf_token": csrf, "deal_id": str(a_id)})
        self.assertEqual(resp.code, 200)
        # A's month unchanged
        a_after_month = self._deals_for("a3@hardening.com")[0]["month"]
        self.assertEqual(a_before_month, a_after_month)

    def test_deletion_through_typed_address_page_proves_no_rows_remain(self):
        from app import store
        import sqlite3
        from app import auth
        email = "delhardening@x.com"
        client = make_client(self.db_path, email)
        # capture tenant id before deletion
        tenant_before = store.get_tenant_by_email(self.db_path, email)
        tenant_id = tenant_before["id"]
        # Settings + deal
        body = client.get("/settings").body
        p = dict(SETTINGS_PT)
        p["csrf_token"] = csrf_token(body)
        client.post("/settings", p)
        body = client.get("/deals/new").body
        p = dict(DEAL_A_ROWS)
        p["csrf_token"] = csrf_token(body)
        rev = client.post("/deals/review", p)
        h = hidden_inputs(rev.body)
        h["csrf_token"] = csrf_token(rev.body)
        client.post("/deals/confirm", h)
        # Create login link + IP rate limit for this tenant
        auth.request_link(self.db_path, email, "5.6.7.8", now=2000.0, token="deletion-test-token")
        # Extra rate limit for another IP for same email to ensure both cleaned
        auth.request_link(self.db_path, email, "9.9.9.9", now=2001.0, token="deletion-test-token2")
        # Go through typed-address page
        body = client.get("/account/delete").body
        self.assertIn("delete", body.lower())
        resp = client.post("/account/delete", {"email": email, "csrf_token": csrf_token(body)})
        self.assertEqual(resp.code, 200)
        self.assertIn("delete_done", resp.body)
        # Tenant gone
        self.assertIsNone(store.get_tenant_by_email(self.db_path, email))
        conn = sqlite3.connect(self.db_path)
        # Zero deals for deleted tenant
        deals_for_deleted = conn.execute("SELECT count(*) FROM deals WHERE tenant_id=?", (tenant_id,)).fetchone()[0]
        self.assertEqual(deals_for_deleted, 0, "deals for deleted tenant must be 0")
        # Zero settings for deleted tenant
        settings_for_deleted = conn.execute("SELECT count(*) FROM settings WHERE tenant_id=?", (tenant_id,)).fetchone()[0]
        self.assertEqual(settings_for_deleted, 0, "settings for deleted tenant must be 0")
        # Zero sessions for deleted tenant
        sessions_for_deleted = conn.execute("SELECT count(*) FROM sessions WHERE tenant_id=?", (tenant_id,)).fetchone()[0]
        self.assertEqual(sessions_for_deleted, 0, "sessions for deleted tenant must be 0")
        # Zero login_links for that email
        links = conn.execute("SELECT count(*) FROM login_links WHERE email=?", (email,)).fetchone()[0]
        self.assertEqual(links, 0, "login_links for deleted tenant must be 0")
        # Zero rate_limits for email key
        rl_email = conn.execute("SELECT count(*) FROM rate_limits WHERE key=?", (email,)).fetchone()[0]
        self.assertEqual(rl_email, 0, "rate_limits email key for deleted tenant must be 0")
        # Zero rate_limits for IP keys that belonged to this tenant
        rl_ip1 = conn.execute("SELECT count(*) FROM rate_limits WHERE key=?", ("5.6.7.8",)).fetchone()[0]
        self.assertEqual(rl_ip1, 0, "rate_limits IP key 5.6.7.8 for deleted tenant must be 0")
        rl_ip2 = conn.execute("SELECT count(*) FROM rate_limits WHERE key=?", ("9.9.9.9",)).fetchone()[0]
        self.assertEqual(rl_ip2, 0, "rate_limits IP key 9.9.9.9 for deleted tenant must be 0")
        conn.close()
        # Also via helper API: list_deals for that tenant id returns empty, settings none
        # (using raw tenant_id since tenant row gone, query with old id)
        import sqlite3 as _sql
        c2 = _sql.connect(self.db_path)
        self.assertEqual(c2.execute("SELECT count(*) FROM deals WHERE tenant_id=?", (tenant_id,)).fetchone()[0], 0)
        c2.close()
