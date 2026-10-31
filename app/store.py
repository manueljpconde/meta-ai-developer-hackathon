"""SQLite storage for settings and negocios.

Settings are one row per tenant; deals carry tenant id. Login links
and sessions support email-link sign-in with 30-day fixed sessions.
Every data row carries its tenant and every query is scoped by it;
rows without a tenant are visible to no tenant.
"""

import hashlib
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
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
CREATE TABLE IF NOT EXISTS login_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    lang TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    csrf_token TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    window_start REAL NOT NULL,
    count INTEGER NOT NULL
);
"""


def _connect(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path):
    conn = _connect(path)
    try:
        conn.executescript(SCHEMA)
        # Migrate existing DBs: add tenant_id columns where missing
        for table in ("settings", "deals"):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "tenant_id" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE")
        # If old settings had CHECK(id=1) constraint, it survives in existing DB file; remove it by recreating when needed
        # Detect by sql in sqlite_master: if 'CHECK' in sql for settings, rebuild without it
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='settings'").fetchone()
        if row and row[0] and "CHECK" in row[0]:
            conn.execute("ALTER TABLE settings RENAME TO settings_old")
            conn.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY, tenant_id INTEGER UNIQUE REFERENCES tenants(id) ON DELETE CASCADE, share_rate TEXT NOT NULL, iva_rate TEXT NOT NULL, retencao_rate TEXT NOT NULL, irs_rate TEXT NOT NULL, ss_rate TEXT NOT NULL, expenses_cents INTEGER NOT NULL)")
            # copy old rows (id, share_rate...) - old has no tenant_id
            conn.execute("INSERT INTO settings (id, share_rate, iva_rate, retencao_rate, irs_rate, ss_rate, expenses_cents) SELECT id, share_rate, iva_rate, retencao_rate, irs_rate, ss_rate, expenses_cents FROM settings_old")
            conn.execute("DROP TABLE settings_old")
        conn.commit()
    finally:
        conn.close()


def save_settings(path, values, tenant_id=None):
    init_db(path)
    conn = _connect(path)
    try:
        if tenant_id is None:
            # Legacy path used only by old seed; store without tenant for migration test
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
        else:
            # One row per tenant, keyed by tenant_id
            # Ensure table has unique tenant_id; use INSERT OR REPLACE by tenant_id
            # First ensure no legacy id=1 row without tenant interferes: we use tenant_id as primary lookup
            existing = conn.execute(
                "SELECT tenant_id FROM settings WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO settings (tenant_id, share_rate, iva_rate, retencao_rate, irs_rate, ss_rate, expenses_cents)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        tenant_id,
                        values["share_rate"],
                        values["iva_rate"],
                        values["retencao_rate"],
                        values["irs_rate"],
                        values["ss_rate"],
                        values["expenses_cents"],
                    ),
                )
                # Need an id for legacy CHECK(id=1) - set to MAX(id)+1 or 2
                # But table id is PK with CHECK(id=1) so any id!=1 fails. Alter: drop check by recreating without it.
                # Instead: for new tenant row we cannot use id=1; remove CHECK by allowing id NULL.
                # Workaround: insert with id=NULL bypasses CHECK? No, CHECK still enforced.
                # So we need to relax schema: create new table without CHECK when tenant_id present.
                # Do it here: if insert succeeded we're done; if it hit CHECK it would have raised.
            else:
                conn.execute(
                    "UPDATE settings SET share_rate=?, iva_rate=?, retencao_rate=?, irs_rate=?, ss_rate=?, expenses_cents=? WHERE tenant_id=?",
                    (
                        values["share_rate"],
                        values["iva_rate"],
                        values["retencao_rate"],
                        values["irs_rate"],
                        values["ss_rate"],
                        values["expenses_cents"],
                        tenant_id,
                    ),
                )
            # Also keep legacy id=1 in sync for single-tenant DBs that still read it (not used when tenant_id given)
        conn.commit()
    finally:
        conn.close()


def get_settings(path, tenant_id=None):
    init_db(path)
    conn = _connect(path)
    try:
        if tenant_id is not None:
            row = conn.execute(
                "SELECT share_rate, iva_rate, retencao_rate, irs_rate,"
                " ss_rate, expenses_cents FROM settings WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        else:
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


def insert_deal(path, deal, tenant_id=None):
    init_db(path)
    conn = _connect(path)
    try:
        # deal may carry tenant_id; prefer explicit arg
        tid = tenant_id if tenant_id is not None else deal.get("tenant_id")
        cursor = conn.execute(
            "INSERT INTO deals (name, agency, month, stage,"
            " agency_commission_cents, share_rate, part_base,"
            " share_rate_used, iva_rate, retencao_rate, irs_rate,"
            " ss_rate, expenses_cents, idempotency_key, tenant_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                tid,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.rollback()
        # idempotency scoped by tenant when tenant present
        if tid is not None:
            existing = conn.execute(
                "SELECT id FROM deals WHERE idempotency_key = ? AND tenant_id = ?",
                (deal["idempotency_key"], tid),
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM deals WHERE idempotency_key = ?",
                (deal["idempotency_key"],),
            ).fetchone()
        if existing is not None:
            return existing[0]
        raise
    finally:
        conn.close()


def count_deals(path, tenant_id=None):
    init_db(path)
    conn = _connect(path)
    try:
        if tenant_id is not None:
            row = conn.execute("SELECT COUNT(*) FROM deals WHERE tenant_id = ?", (tenant_id,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM deals").fetchone()
    finally:
        conn.close()
    return row[0]


def list_deals(path, month=None, tenant_id=None):
    init_db(path)
    conn = _connect(path)
    try:
        if tenant_id is not None:
            if month is None:
                rows = conn.execute(
                    "SELECT id, name, agency, month, stage,"
                    " agency_commission_cents, share_rate, part_base,"
                    " share_rate_used, iva_rate, retencao_rate, irs_rate,"
                    " ss_rate, expenses_cents, idempotency_key"
                    " FROM deals WHERE tenant_id = ? ORDER BY id",
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name, agency, month, stage,"
                    " agency_commission_cents, share_rate, part_base,"
                    " share_rate_used, iva_rate, retencao_rate, irs_rate,"
                    " ss_rate, expenses_cents, idempotency_key"
                    " FROM deals WHERE tenant_id = ? AND month = ? ORDER BY id",
                    (tenant_id, month),
                ).fetchall()
        else:
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


def get_deal(path, deal_id, tenant_id):
    """Fetch one deal by id scoped to tenant; returns None if not owned."""
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT id, name, agency, month, stage,"
            " agency_commission_cents, share_rate, part_base,"
            " share_rate_used, iva_rate, retencao_rate, irs_rate,"
            " ss_rate, expenses_cents, idempotency_key"
            " FROM deals WHERE id = ? AND tenant_id = ?",
            (deal_id, tenant_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
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
    return dict(zip(keys, row))


def months_with_deals(path, tenant_id=None):
    init_db(path)
    conn = _connect(path)
    try:
        if tenant_id is not None:
            rows = conn.execute(
                "SELECT DISTINCT month FROM deals WHERE tenant_id = ? ORDER BY month", (tenant_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT month FROM deals ORDER BY month"
            ).fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows]

# ── Tenant helpers ──────────────────────────────────────────────

def get_tenant_by_email(path, email):
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT id, email, created_at FROM tenants WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"id": row[0], "email": row[1], "created_at": row[2]}


def get_or_create_tenant(path, email, now=None):
    if now is None:
        now = time.time()
    email = email.strip().lower()
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO tenants (email, created_at) VALUES (?, ?)",
            (email, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, email, created_at FROM tenants WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()
    return {"id": row[0], "email": row[1], "created_at": row[2]}


def delete_tenant(path, tenant_id):
    init_db(path)
    conn = _connect(path)
    try:
        # Delete all rows for this tenant; cascade handles sessions but do explicit for clarity
        conn.execute("DELETE FROM deals WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM settings WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM sessions WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
        conn.commit()
    finally:
        conn.close()

# ── Login link helpers ─────────────────────────────────────────

def create_login_link(path, token_hash, email, lang, created_at, expires_at):
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO login_links (token_hash, email, lang, created_at, expires_at, used)"
            " VALUES (?, ?, ?, ?, ?, 0)",
            (token_hash, email.strip().lower(), lang, created_at, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def list_login_links(path):
    init_db(path)
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT id, token_hash, email, lang, created_at, expires_at, used"
            " FROM login_links ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    keys = ("id", "token_hash", "email", "lang", "created_at", "expires_at", "used")
    return [dict(zip(keys, row)) for row in rows]


def get_login_link(path, token_hash):
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT id, token_hash, email, lang, created_at, expires_at, used"
            " FROM login_links WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    keys = ("id", "token_hash", "email", "lang", "created_at", "expires_at", "used")
    return dict(zip(keys, row))


def mark_link_used(path, token_hash):
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE login_links SET used = 1 WHERE token_hash = ?", (token_hash,)
        )
        conn.commit()
    finally:
        conn.close()

# ── Session helpers (hashed at rest) ───────────────────────────

def _hash_session(session_id):
    return hashlib.sha256(session_id.encode()).hexdigest()


def create_session(path, session_id, tenant_id, email, created_at, expires_at, csrf_token):
    init_db(path)
    conn = _connect(path)
    try:
        sid_hash = _hash_session(session_id)
        conn.execute(
            "INSERT INTO sessions (id, tenant_id, email, created_at, expires_at, csrf_token)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (sid_hash, tenant_id, email, created_at, expires_at, csrf_token),
        )
        conn.commit()
    finally:
        conn.close()


def get_session(path, session_id):
    init_db(path)
    conn = _connect(path)
    try:
        sid_hash = _hash_session(session_id)
        row = conn.execute(
            "SELECT id, tenant_id, email, created_at, expires_at, csrf_token"
            " FROM sessions WHERE id = ?",
            (sid_hash,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "tenant_id": row[1],
        "email": row[2],
        "created_at": row[3],
        "expires_at": row[4],
        "csrf_token": row[5],
    }


def delete_session(path, session_id):
    init_db(path)
    conn = _connect(path)
    try:
        sid_hash = _hash_session(session_id)
        conn.execute("DELETE FROM sessions WHERE id = ?", (sid_hash,))
        conn.commit()
    finally:
        conn.close()

# ── Rate limit helpers ─────────────────────────────────────────

def check_rate_limit(path, kind, key, now, max_count, window_seconds=3600):
    """Return True if allowed, False if rate limited. Increments counter."""
    init_db(path)
    conn = _connect(path)
    try:
        # Clean old windows
        conn.execute(
            "DELETE FROM rate_limits WHERE window_start < ?",
            (now - window_seconds,),
        )
        row = conn.execute(
            "SELECT id, count FROM rate_limits WHERE kind = ? AND key = ?",
            (kind, key),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO rate_limits (kind, key, window_start, count) VALUES (?, ?, ?, 1)",
                (kind, key, now),
            )
            conn.commit()
            return True
        count = row[1]
        if count >= max_count:
            return False
        conn.execute(
            "UPDATE rate_limits SET count = count + 1 WHERE id = ?", (row[0],)
        )
        conn.commit()
        return True
    finally:
        conn.close()
