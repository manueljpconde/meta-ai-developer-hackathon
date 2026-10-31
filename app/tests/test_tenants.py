"""Tenant-scoped storage: accounts, links, sessions, deals, settings.

Fail-first tests for the tenant model: every stored row carries
its tenant and every read and write is scoped by it in SQL, link
rows store only the token hash with a 15-minute expiry and a used
flag, sessions expire exactly 30 days after creation, deletion
removes every row of the tenant, old unowned rows are dropped by
the migration, and one agent cannot read or change another
agent's deals, notes or settings, including by guessing ids. No
test calls the network.
"""

import sqlite3

from app import auth, store
from app.tests.helpers import AppTestCase


def tenant_id(test_case, email="ana@example.pt"):
    return store.ensure_tenant(test_case.db_path, email)


class TenantTest(AppTestCase):
    def test_first_link_creates_tenant_lowercased(self):
        ident = tenant_id(self, "  Ana@Example.PT ")
        self.assertTrue(ident)
        self.assertEqual(store.tenant_email(self.db_path, ident),
                         "ana@example.pt")

    def test_same_email_returns_same_tenant(self):
        first = tenant_id(self, "ana@example.pt")
        self.assertEqual(store.ensure_tenant(self.db_path, "ANA@example.pt"),
                         first)

    def test_settings_scoped_per_tenant(self):
        first = tenant_id(self, "ana@example.pt")
        second = tenant_id(self, "bruno@example.pt")
        store.save_settings(self.db_path, {
            "share_rate": "0.5", "iva_rate": "0.23",
            "retencao_rate": "0.25", "irs_rate": "0.30",
            "ss_rate": "0.10", "expenses_cents": 35000,
        }, tenant=first)
        self.assertEqual(
            store.get_settings(self.db_path, tenant=first)["expenses_cents"],
            35000,
        )
        self.assertIsNone(store.get_settings(self.db_path, tenant=second))

    def test_deals_scoped_per_tenant(self):
        first = tenant_id(self, "ana@example.pt")
        second = tenant_id(self, "bruno@example.pt")
        ident = store.insert_deal(self.db_path, {
            "name": "Benfica", "agency": "", "month": "2026-11",
            "stage": "confirmado", "agency_commission_cents": 1000000,
            "share_rate": "50", "part_base": 500000,
            "share_rate_used": "0.5", "iva_rate": "0.23",
            "retencao_rate": "0.25", "irs_rate": "0.30",
            "ss_rate": "0.10", "expenses_cents": 35000,
            "idempotency_key": "ana-one",
        }, tenant=first)
        self.assertEqual(store.count_deals(self.db_path, tenant=first), 1)
        self.assertEqual(store.count_deals(self.db_path, tenant=second), 0)
        self.assertEqual(len(store.list_deals(self.db_path, tenant=second)), 0)
        self.assertEqual(
            store.list_deals(self.db_path, tenant=first)[0]["id"], ident
        )
        self.assertEqual(
            store.months_with_deals(self.db_path, tenant=second), []
        )

    def test_guessing_another_tenants_id_yields_nothing(self):
        first = tenant_id(self, "ana@example.pt")
        second = tenant_id(self, "bruno@example.pt")
        ident = store.insert_deal(self.db_path, {
            "name": "Benfica", "agency": "", "month": "2026-11",
            "stage": "confirmado", "agency_commission_cents": 1000000,
            "share_rate": "50", "part_base": 500000,
            "share_rate_used": "0.5", "iva_rate": "0.23",
            "retencao_rate": "0.25", "irs_rate": "0.30",
            "ss_rate": "0.10", "expenses_cents": 35000,
            "idempotency_key": "ana-one",
        }, tenant=first)
        self.assertIsNone(
            store.get_deal(self.db_path, ident, tenant=second))
        self.assertFalse(
            store.update_deal(self.db_path, ident, tenant=second,
                              values={"stage": "potencial"}))
        kept = store.get_deal(self.db_path, ident, tenant=first)
        self.assertEqual(kept["stage"], "confirmado")

    def test_settings_update_scoped_per_tenant(self):
        first = tenant_id(self, "ana@example.pt")
        second = tenant_id(self, "bruno@example.pt")
        store.save_settings(self.db_path, {
            "share_rate": "0.5", "iva_rate": "0.23",
            "retencao_rate": "0.25", "irs_rate": "0.30",
            "ss_rate": "0.10", "expenses_cents": 35000,
        }, tenant=first)
        store.save_settings(self.db_path, {
            "share_rate": "0.5", "iva_rate": "0.23",
            "retencao_rate": "0.25", "irs_rate": "0.30",
            "ss_rate": "0.10", "expenses_cents": 100,
        }, tenant=second)
        self.assertEqual(
            store.get_settings(self.db_path, tenant=first)["expenses_cents"],
            35000,
        )

    def test_link_rows_store_hashes_never_raw_tokens(self):
        raw = auth.generate_token()
        digest = auth.hash_token(raw)
        store.create_link(self.db_path, "ana@example.pt",
                          digest, "pt-PT", "203.0.113.7")
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT token_hash FROM login_links"
                " WHERE token_hash = ?", (digest,)).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], auth.hash_token(raw))
        self.assertNotIn(raw, rows[0][0])

    def test_consume_link_single_use(self):
        raw = auth.generate_token()
        digest = auth.hash_token(raw)
        store.create_link(self.db_path, "ana@example.pt", digest,
                          "pt-PT", "203.0.113.7")
        found = store.consume_link(self.db_path, digest)
        self.assertIsNotNone(found)
        self.assertEqual(found["email"], "ana@example.pt")
        self.assertIsNone(store.consume_link(self.db_path, digest))

    def test_expired_link_consumes_nothing(self):
        raw = auth.generate_token()
        digest = auth.hash_token(raw)
        store.create_link(self.db_path, "ana@example.pt", digest,
                          "pt-PT", "203.0.113.7",
                          created_at="2026-10-31 11:00:00")
        self.assertIsNone(store.consume_link(
            self.db_path, digest, now="2026-10-31 12:16:00"))
        # The expired row is pruned without authenticating anyone.
        self.assertIsNone(store.consume_link(
            self.db_path, digest, now="2026-10-31 12:17:00"))

    def test_guessed_token_consumes_nothing(self):
        raw = auth.generate_token()
        store.create_link(self.db_path, "ana@example.pt",
                          auth.hash_token(raw), "pt-PT", "203.0.113.7")
        self.assertIsNone(store.consume_link(
            self.db_path, auth.hash_token(auth.generate_token())))

    def test_rate_counters_scope_email_and_ip(self):
        store.create_link(self.db_path, "ana@example.pt", "h1",
                          "pt-PT", "203.0.113.7")
        store.create_link(self.db_path, "ana@example.pt", "h2",
                          "pt-PT", "203.0.113.7")
        # The harness signs in once first, so one link row and one
        # counter row already exist for this address.
        self.assertEqual(
            store.count_recent_links(self.db_path, email="ana@example.pt"),
            3,
        )
        self.assertEqual(
            store.count_recent_links(self.db_path, ip="203.0.113.7"), 2
        )
        self.assertEqual(
            store.count_recent_links(self.db_path,
                                     email="bruno@example.pt"), 0
        )

    def test_session_expires_thirty_days_after_creation(self):
        ident = tenant_id(self)
        digest = auth.hash_token(auth.generate_token())
        store.create_session(self.db_path, digest, ident,
                             created_at="2026-10-01 12:00:00")
        self.assertIsNotNone(store.find_session(
            self.db_path, digest, now="2026-10-30 12:00:00"))
        self.assertIsNone(store.find_session(
            self.db_path, digest, now="2026-10-31 12:00:01"))

    def test_session_ids_stored_hashed(self):
        ident = tenant_id(self)
        raw = auth.generate_token()
        digest = auth.hash_token(raw)
        store.create_session(self.db_path, digest, ident)
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT session_hash FROM sessions"
                " WHERE session_hash = ?", (digest,)).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        self.assertNotIn(raw, rows[0][0])

    def test_sign_out_ends_only_that_session(self):
        ident = tenant_id(self)
        first = auth.hash_token(auth.generate_token())
        second = auth.hash_token(auth.generate_token())
        store.create_session(self.db_path, first, ident)
        store.create_session(self.db_path, second, ident)
        store.delete_session(self.db_path, first)
        self.assertIsNone(store.find_session(self.db_path, first))
        self.assertIsNotNone(store.find_session(self.db_path, second))

    def test_delete_tenant_removes_every_row(self):
        ident = tenant_id(self, "ana@example.pt")
        other = tenant_id(self, "bruno@example.pt")
        store.save_settings(self.db_path, {
            "share_rate": "0.5", "iva_rate": "0.23",
            "retencao_rate": "0.25", "irs_rate": "0.30",
            "ss_rate": "0.10", "expenses_cents": 35000,
        }, tenant=ident)
        store.insert_deal(self.db_path, {
            "name": "Benfica", "agency": "", "month": "2026-11",
            "stage": "confirmado", "agency_commission_cents": 1000000,
            "share_rate": "50", "part_base": 500000,
            "share_rate_used": "0.5", "iva_rate": "0.23",
            "retencao_rate": "0.25", "irs_rate": "0.30",
            "ss_rate": "0.10", "expenses_cents": 35000,
            "idempotency_key": "ana-one",
        }, tenant=ident)
        store.insert_deal(self.db_path, {
            "name": "Porto", "agency": "", "month": "2026-11",
            "stage": "confirmado", "agency_commission_cents": 640000,
            "share_rate": "50", "part_base": 320000,
            "share_rate_used": "0.5", "iva_rate": "0.23",
            "retencao_rate": "0.25", "irs_rate": "0.30",
            "ss_rate": "0.10", "expenses_cents": 35000,
            "idempotency_key": "bruno-one",
        }, tenant=other)
        store.create_session(self.db_path, "s1", ident)
        store.create_link(self.db_path, "ana@example.pt", "h1",
                          "pt-PT", "203.0.113.7")
        store.delete_tenant(self.db_path, ident)
        self.assertIsNone(store.tenant_email(self.db_path, ident))
        self.assertEqual(store.count_deals(self.db_path, tenant=ident), 0)
        self.assertIsNone(store.get_settings(self.db_path, tenant=ident))
        conn = sqlite3.connect(self.db_path)
        try:
            tables = ("tenants", "settings", "deals", "login_links",
                      "sessions", "link_requests")
            leftovers = {}
            for table in tables:
                try:
                    rows = conn.execute(
                        "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
                except sqlite3.OperationalError:
                    rows = 0
                leftovers[table] = rows
        finally:
            conn.close()
        # Only Bruno's tenant, settings and deal rows survive.
        self.assertEqual(leftovers["tenants"], 1)
        self.assertEqual(store.count_deals(self.db_path, tenant=other), 1)

    def test_migrate_drops_unowned_rows(self):
        store.init_db(self.db_path)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DROP TABLE IF EXISTS settings")
            conn.execute("DROP TABLE IF EXISTS deals")
            conn.execute(
                "CREATE TABLE settings ("
                "id INTEGER PRIMARY KEY CHECK (id = 1),"
                " share_rate TEXT NOT NULL, iva_rate TEXT NOT NULL,"
                " retencao_rate TEXT NOT NULL, irs_rate TEXT NOT NULL,"
                " ss_rate TEXT NOT NULL, expenses_cents INTEGER NOT NULL)")
            conn.execute(
                "INSERT OR REPLACE INTO settings (id, share_rate, iva_rate,"
                " retencao_rate, irs_rate, ss_rate, expenses_cents)"
                " VALUES (1, '0.5', '0.23', '0.25', '0.30', '0.10', 35000)")
            conn.execute(
                "CREATE TABLE deals ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " name TEXT NOT NULL, agency TEXT NOT NULL,"
                " month TEXT NOT NULL, stage TEXT NOT NULL,"
                " agency_commission_cents INTEGER NOT NULL,"
                " share_rate TEXT NOT NULL, part_base INTEGER NOT NULL,"
                " share_rate_used TEXT NOT NULL, iva_rate TEXT NOT NULL,"
                " retencao_rate TEXT NOT NULL, irs_rate TEXT NOT NULL,"
                " ss_rate TEXT NOT NULL, expenses_cents INTEGER NOT NULL,"
                " idempotency_key TEXT NOT NULL UNIQUE)")
            conn.execute(
                "INSERT INTO deals (name, agency, month, stage,"
                " agency_commission_cents, share_rate, part_base,"
                " share_rate_used, iva_rate, retencao_rate, irs_rate,"
                " ss_rate, expenses_cents, idempotency_key)"
                " VALUES ('Deal Name 1', '', '2026-11', 'confirmado',"
                " 1000000, '50', 500000, '0.5', '0.23', '0.25', '0.30',"
                " '0.10', 35000, 'legacy-one')")
            conn.commit()
        finally:
            conn.close()
        store.migrate(self.db_path)
        self.assertEqual(store.count_deals(self.db_path, tenant=1), 0)
        ident = tenant_id(self, "ana@example.pt")
        self.assertEqual(store.count_deals(self.db_path, tenant=ident), 0)
        self.assertIsNone(store.get_settings(self.db_path, tenant=ident))


if __name__ == "__main__":
    import unittest

    unittest.main()
