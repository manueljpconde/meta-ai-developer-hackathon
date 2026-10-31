"""Tenant scoping and isolation: cross-tenant read/change blocked, guessed ids, null-tenant rows."""

import unittest
from app.tests.helpers import AppTestCase, csrf_token, SETTINGS_PT


def make_client_for(email, db_path):
    from app.tests.helpers import Client
    from app import store
    import time, secrets
    store.get_or_create_tenant(db_path, email, now=time.time())
    tenant = store.get_tenant_by_email(db_path, email)
    sid = "iso-session-" + email
    csrf = secrets.token_urlsafe(16)
    store.create_session(db_path, sid, tenant["id"], email, time.time(), time.time() + 3600*24*30, csrf)
    c = Client()
    c.cookies["session"] = sid
    return c


class TenantIsolationTest(AppTestCase):
    def _seed_tenant(self, email, n_deals=1):
        client = make_client_for(email, self.db_path)
        # save settings for that tenant
        body = client.get("/settings").body
        params = dict(SETTINGS_PT)
        params["csrf_token"] = csrf_token(body)
        client.post("/settings", params)
        for i in range(n_deals):
            body = client.get("/deals/new").body
            params = {
                "name": "Deal-%s-%d" % (email, i),
                "commission": "10000,00",
                "share": "50",
                "month": "2026-11",
                "stage": "confirmado",
                "agency": "Agency",
                "form_locale": "pt-PT",
                "csrf_token": csrf_token(body),
            }
            rev = client.post("/deals/review", params)
            from app.tests.helpers import hidden_inputs
            h = hidden_inputs(rev.body)
            h["csrf_token"] = csrf_token(rev.body)
            client.post("/deals/confirm", h)
        return client

    def test_other_tenant_deals_not_visible(self):
        from app import store
        self._seed_tenant("a@a.com", 1)
        b_client = self._seed_tenant("b@b.com", 1)
        # b should not see a's deal
        body = b_client.get("/").body
        self.assertNotIn("Deal-a@a.com", body)
        self.assertIn("Deal-b@b.com", body)
        # and count scoped
        from app import store as _s
        ta = _s.get_tenant_by_email(self.db_path, "a@a.com")
        tb = _s.get_tenant_by_email(self.db_path, "b@b.com")
        self.assertEqual(len(_s.list_deals(self.db_path, tenant_id=tb["id"])), 1)

    def test_guessed_deal_id_yields_no_data(self):
        from app import store
        a_client = self._seed_tenant("a@a.com", 1)
        # a has a deal with some id; b tries guessed id via store API
        ta = store.get_tenant_by_email(self.db_path, "a@a.com")
        tb = store.get_tenant_by_email(self.db_path, "b@b.com") if store.get_tenant_by_email(self.db_path, "b@b.com") else None
        if tb is None:
            self._seed_tenant("b@b.com", 0)
            tb = store.get_tenant_by_email(self.db_path, "b@b.com")
        deals_a = store.list_deals(self.db_path, tenant_id=ta["id"])
        guessed_id = deals_a[0]["id"]
        # scoped get should return None for wrong tenant
        self.assertIsNone(store.get_deal(self.db_path, guessed_id, tb["id"]))

    def test_other_tenant_settings_not_visible(self):
        a_client = self._seed_tenant("a@a.com", 0)
        b_client = self._seed_tenant("b@b.com", 0)
        # b saves different expenses
        body = b_client.get("/settings").body
        params = dict(SETTINGS_PT)
        params["expenses"] = "999,00"
        params["csrf_token"] = csrf_token(body)
        b_client.post("/settings", params)
        # a still sees old
        from app import store as _s
        ta = _s.get_tenant_by_email(self.db_path, "a@a.com")
        tb = _s.get_tenant_by_email(self.db_path, "b@b.com")
        self.assertEqual(_s.get_settings(self.db_path, tenant_id=ta["id"])["expenses_cents"], 35000)
        self.assertEqual(_s.get_settings(self.db_path, tenant_id=tb["id"])["expenses_cents"], 99900)

    def test_rows_without_tenant_visible_to_no_tenant(self):
        from app import store
        import sqlite3
        # Insert a deal with NULL tenant_id directly (pre-existing data)
        store.init_db(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO deals (name, agency, month, stage, agency_commission_cents, share_rate, part_base, share_rate_used, iva_rate, retencao_rate, irs_rate, ss_rate, expenses_cents, idempotency_key, tenant_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     ("Orphan", "", "2026-11", "confirmado", 1000000, "50", 500000, "0.5", "0.23", "0.25", "0.30", "0.10", 35000, "orphan-key", None))
        conn.commit()
        conn.close()
        c = self._seed_tenant("a@a.com", 0)
        body = c.get("/").body
        self.assertNotIn("Orphan", body)
        ta = store.get_tenant_by_email(self.db_path, "a@a.com")
        self.assertEqual(len(store.list_deals(self.db_path, tenant_id=ta["id"])), 0)

    def test_account_deletion_leaves_no_rows(self):
        from app import store
        c = self._seed_tenant("del@x.com", 1)
        ta = store.get_tenant_by_email(self.db_path, "del@x.com")
        # delete via store helper (typed-address path tested in test_auth_web; here verify leaves no rows)
        store.delete_tenant(self.db_path, ta["id"])
        self.assertIsNone(store.get_tenant_by_email(self.db_path, "del@x.com"))
        self.assertEqual(len(store.list_deals(self.db_path, tenant_id=ta["id"])), 0)
        self.assertIsNone(store.get_settings(self.db_path, tenant_id=ta["id"]))
