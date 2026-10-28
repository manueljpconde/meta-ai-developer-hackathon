"""SQLite storage for settings and negocios.

Settings are one row: exact decimal rate strings and monthly expenses
in integer cents. A negocio stores its name, agency, month, stage
code, agency commission and share in cents, the frozen settings used
at confirmation, and a server-generated idempotency key.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    share_rate TEXT NOT NULL,
    iva_rate TEXT NOT NULL,
    retencao_rate TEXT NOT NULL,
    irs_rate TEXT NOT NULL,
    ss_rate TEXT NOT NULL,
    expenses_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    agency TEXT NOT NULL,
    month TEXT NOT NULL,
    stage TEXT NOT NULL,
    agency_commission_cents INTEGER NOT NULL,
    share_rate TEXT NOT NULL,
    part_base INTEGER NOT NULL,
    share_rate_used TEXT NOT NULL,
    iva_rate TEXT NOT NULL,
    retencao_rate TEXT NOT NULL,
    irs_rate TEXT NOT NULL,
    ss_rate TEXT NOT NULL,
    expenses_cents INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);
"""


def _connect(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(path):
    conn = _connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def save_settings(path, values):
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO settings (id, share_rate, iva_rate, retencao_rate,"
            " irs_rate, ss_rate, expenses_cents)"
            " VALUES (1, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " share_rate=excluded.share_rate,"
            " iva_rate=excluded.iva_rate,"
            " retencao_rate=excluded.retencao_rate,"
            " irs_rate=excluded.irs_rate,"
            " ss_rate=excluded.ss_rate,"
            " expenses_cents=excluded.expenses_cents",
            (
                values["share_rate"],
                values["iva_rate"],
                values["retencao_rate"],
                values["irs_rate"],
                values["ss_rate"],
                values["expenses_cents"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_settings(path):
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT share_rate, iva_rate, retencao_rate, irs_rate,"
            " ss_rate, expenses_cents FROM settings WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "share_rate": row[0],
        "iva_rate": row[1],
        "retencao_rate": row[2],
        "irs_rate": row[3],
        "ss_rate": row[4],
        "expenses_cents": row[5],
    }


def insert_deal(path, deal):
    init_db(path)
    conn = _connect(path)
    try:
        cursor = conn.execute(
            "INSERT INTO deals (name, agency, month, stage,"
            " agency_commission_cents, share_rate, part_base,"
            " share_rate_used, iva_rate, retencao_rate, irs_rate,"
            " ss_rate, expenses_cents, idempotency_key)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                deal["name"],
                deal["agency"],
                deal["month"],
                deal["stage"],
                deal["agency_commission_cents"],
                deal["share_rate"],
                deal["part_base"],
                deal["share_rate_used"],
                deal["iva_rate"],
                deal["retencao_rate"],
                deal["irs_rate"],
                deal["ss_rate"],
                deal["expenses_cents"],
                deal["idempotency_key"],
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.rollback()
        existing = conn.execute(
            "SELECT id FROM deals WHERE idempotency_key = ?",
            (deal["idempotency_key"],),
        ).fetchone()
        if existing is not None:
            return existing[0]
        raise
    finally:
        conn.close()


def count_deals(path):
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM deals").fetchone()
    finally:
        conn.close()
    return row[0]


def list_deals(path, month=None):
    init_db(path)
    conn = _connect(path)
    try:
        if month is None:
            rows = conn.execute(
                "SELECT id, name, agency, month, stage,"
                " agency_commission_cents, share_rate, part_base,"
                " share_rate_used, iva_rate, retencao_rate, irs_rate,"
                " ss_rate, expenses_cents, idempotency_key"
                " FROM deals ORDER BY id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, agency, month, stage,"
                " agency_commission_cents, share_rate, part_base,"
                " share_rate_used, iva_rate, retencao_rate, irs_rate,"
                " ss_rate, expenses_cents, idempotency_key"
                " FROM deals WHERE month = ? ORDER BY id",
                (month,),
            ).fetchall()
    finally:
        conn.close()
    keys = (
        "id",
        "name",
        "agency",
        "month",
        "stage",
        "agency_commission_cents",
        "share_rate",
        "part_base",
        "share_rate_used",
        "iva_rate",
        "retencao_rate",
        "irs_rate",
        "ss_rate",
        "expenses_cents",
        "idempotency_key",
    )
    return [dict(zip(keys, row)) for row in rows]


def months_with_deals(path):
    init_db(path)
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT month FROM deals ORDER BY month"
        ).fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows]
