"""Deal record dates and the fallen-through flag, scoped by tenant.

Fail-first tests for the record changes: a deal stores its
escritura date as a full calendar date and the forecast month
derives from it, the CPCV signing date is nullable and shown on
reads, fallen-through deals are excluded from the working lists
until reopened, every write stays scoped by tenant, and the
migration backfills an escritura date for rows written before
the column existed. No test calls the network.
"""

from app import store
from app.tests.helpers import AppTestCase
from app.tests.test_tenants import tenant_id


def deal_values(**overrides):
    values = {
        "name": "Benfica",
        "agency": "",
        "escritura_date": "2026-11-14",
        "stage": "provavel",
        "agency_commission_cents": 1000000,
        "share_rate": "50",
        "part_base": 500000,
        "share_rate_used": "0.5",
        "iva_rate": "0.23",
        "retencao_rate": "0.25",
        "irs_rate": "0.30",
        "ss_rate": "0.10",
        "expenses_cents": 35000,
        "idempotency_key": "record-one",
    }
    values.update(overrides)
    return values


class EscrituraDateTest(AppTestCase):
    def test_insert_stores_escritura_date_and_derives_month(self):
        ident = tenant_id(self)
        row_id = store.insert_deal(
            self.db_path, deal_values(), tenant=ident)
        kept = store.get_deal(self.db_path, row_id, tenant=ident)
        self.assertEqual(kept["escritura_date"], "2026-11-14")
        self.assertEqual(kept["month"], "2026-11")

    def test_invalid_escritura_date_refused(self):
        ident = tenant_id(self)
        with self.assertRaises(ValueError):
            store.insert_deal(
                self.db_path,
                deal_values(escritura_date="2026-13-40"),
                tenant=ident,
            )
        self.assertEqual(store.count_deals(self.db_path, tenant=ident), 0)

    def test_missing_escritura_date_refused(self):
        ident = tenant_id(self)
        values = deal_values()
        del values["escritura_date"]
        with self.assertRaises(ValueError):
            store.insert_deal(self.db_path, values, tenant=ident)

    def test_moving_escritura_date_moves_forecast_month(self):
        ident = tenant_id(self)
        row_id = store.insert_deal(
            self.db_path, deal_values(), tenant=ident)
        self.assertTrue(store.update_deal(
            self.db_path, row_id, tenant=ident,
            values={"escritura_date": "2027-01-05"},
        ))
        kept = store.get_deal(self.db_path, row_id, tenant=ident)
        self.assertEqual(kept["escritura_date"], "2027-01-05")
        self.assertEqual(kept["month"], "2027-01")
        self.assertEqual(
            store.months_with_deals(self.db_path, tenant=ident),
            ["2027-01"],
        )
        self.assertEqual(
            len(store.list_deals(self.db_path, "2026-11", tenant=ident)),
            0,
        )
        self.assertEqual(
            len(store.list_deals(self.db_path, "2027-01", tenant=ident)),
            1,
        )


class CpcvDateTest(AppTestCase):
    def test_cpcv_date_nullable_and_shown_on_reads(self):
        ident = tenant_id(self)
        row_id = store.insert_deal(
            self.db_path, deal_values(), tenant=ident)
        self.assertIsNone(
            store.get_deal(self.db_path, row_id, tenant=ident)["cpcv_date"]
        )
        self.assertTrue(store.update_deal(
            self.db_path, row_id, tenant=ident,
            values={"cpcv_date": "2026-10-02", "stage": "confirmado"},
        ))
        kept = store.get_deal(self.db_path, row_id, tenant=ident)
        self.assertEqual(kept["cpcv_date"], "2026-10-02")
        self.assertEqual(kept["stage"], "confirmado")

    def test_invalid_cpcv_date_refused_without_change(self):
        ident = tenant_id(self)
        row_id = store.insert_deal(
            self.db_path, deal_values(), tenant=ident)
        with self.assertRaises(ValueError):
            store.update_deal(
                self.db_path, row_id, tenant=ident,
                values={"cpcv_date": "not-a-date"},
            )
        kept = store.get_deal(self.db_path, row_id, tenant=ident)
        self.assertIsNone(kept["cpcv_date"])
        self.assertEqual(kept["stage"], "provavel")


class FallenThroughTest(AppTestCase):
    def test_fallen_deals_excluded_until_reopened(self):
        ident = tenant_id(self)
        row_id = store.insert_deal(
            self.db_path, deal_values(), tenant=ident)
        self.assertTrue(store.update_deal(
            self.db_path, row_id, tenant=ident, values={"fallen": True}))
        self.assertEqual(
            store.list_deals(self.db_path, tenant=ident), [])
        self.assertEqual(
            store.months_with_deals(self.db_path, tenant=ident), [])
        fallen = store.list_deals(
            self.db_path, tenant=ident, include_fallen=True)
        self.assertEqual(len(fallen), 1)
        self.assertTrue(fallen[0]["fallen"])
        self.assertTrue(store.update_deal(
            self.db_path, row_id, tenant=ident, values={"fallen": False}))
        self.assertEqual(
            len(store.list_deals(self.db_path, tenant=ident)), 1)
        self.assertEqual(
            store.months_with_deals(self.db_path, tenant=ident),
            ["2026-11"],
        )

    def test_fallen_update_scoped_by_tenant(self):
        first = tenant_id(self, "ana@example.pt")
        second = tenant_id(self, "bruno@example.pt")
        row_id = store.insert_deal(
            self.db_path, deal_values(), tenant=first)
        self.assertFalse(store.update_deal(
            self.db_path, row_id, tenant=second, values={"fallen": True}))
        kept = store.get_deal(self.db_path, row_id, tenant=first)
        self.assertFalse(kept["fallen"])


class RecordMigrationTest(AppTestCase):
    def test_migrate_backfills_escritura_date_from_month(self):
        import sqlite3

        store.init_db(self.db_path)
        ident = tenant_id(self)
        conn = sqlite3.connect(self.db_path)
        try:
            names = [row[1] for row in conn.execute(
                "PRAGMA table_info(deals)").fetchall()]
            for column in ("escritura_date", "cpcv_date", "fallen"):
                if column in names:
                    conn.execute("ALTER TABLE deals DROP COLUMN %s" % column)
            conn.execute(
                "INSERT INTO deals (tenant, name, agency, month, stage,"
                " agency_commission_cents, share_rate, part_base,"
                " share_rate_used, iva_rate, retencao_rate, irs_rate,"
                " ss_rate, expenses_cents, idempotency_key)"
                " VALUES (?, 'Old Row', '', '2026-11', 'confirmado',"
                " 1000000, '50', 500000, '0.5', '0.23', '0.25', '0.30',"
                " '0.10', 35000, 'legacy-month-row')",
                (ident,),
            )
            conn.commit()
        finally:
            conn.close()
        store.migrate(self.db_path)
        kept = store.list_deals(self.db_path, tenant=ident)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["escritura_date"], "2026-11-01")
        self.assertEqual(kept[0]["month"], "2026-11")


if __name__ == "__main__":
    import unittest

    unittest.main()
