"""SQLite storage, scoped by tenant.

Every stored row carries its tenant id and every read and write is
scoped by it in SQL (``WHERE tenant = ?``), never by filtering in
Python. Link rows store only the token hash with a 15-minute
expiry and a used flag; session rows store only the hashed
session id with a fixed 30-day expiry. Deleting the tenant row
cascades to every row of that tenant in one transaction.
"""

import sqlite3
from datetime import datetime as _datetime

from app import auth

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant INTEGER NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
    share_rate TEXT NOT NULL,
    iva_rate TEXT NOT NULL,
    retencao_rate TEXT NOT NULL,
    irs_rate TEXT NOT NULL,
    ss_rate TEXT NOT NULL,
    expenses_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    agency TEXT NOT NULL,
    month TEXT NOT NULL,
    escritura_date TEXT NOT NULL,
    cpcv_date TEXT,
    fallen INTEGER NOT NULL DEFAULT 0,
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
    email TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    lang TEXT NOT NULL,
    ip TEXT NOT NULL,
    created_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS link_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    ip TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_hash TEXT NOT NULL UNIQUE,
    tenant INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
"""


def _connect(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _utc_text(moment=None):
    if moment is None:
        return auth.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return str(moment)


def _parse_text(value):
    from datetime import datetime

    return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=auth.timezone_utc())


def _check_full_date(value, name):
    """Validate a full calendar date, returning its forecast month."""
    if not isinstance(value, str):
        raise ValueError(name + " must be a date like YYYY-MM-DD")
    try:
        parsed = _datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(name + " must be a date like YYYY-MM-DD")
    return "%04d-%02d" % (parsed.year, parsed.month)


def _check_optional_date(value, name):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(name + " must be a date like YYYY-MM-DD")
    try:
        _datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(name + " must be a date like YYYY-MM-DD")
    return value


def _columns(conn, table):
    try:
        return [column[1] for column in
                conn.execute("PRAGMA table_info(%s)" % table).fetchall()]
    except sqlite3.OperationalError:
        return []


def init_db(path):
    conn = _connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def migrate(path):
    """Create the tenant schema and drop unowned legacy rows.

    Going live drops the shared demo-era rows (Deal Name 1 and the
    single-row demo settings); the first real account starts empty.
    """
    conn = _connect(path)
    try:
        try:
            columns = conn.execute("PRAGMA table_info(deals)").fetchall()
            if not any(column[1] == "tenant" for column in columns):
                conn.execute("DROP TABLE IF EXISTS deals")
        except sqlite3.OperationalError:
            pass
        try:
            columns = conn.execute("PRAGMA table_info(settings)").fetchall()
            if not any(column[1] == "tenant" for column in columns):
                conn.execute("DROP TABLE IF EXISTS settings")
        except sqlite3.OperationalError:
            pass
        conn.executescript(SCHEMA)
        columns = _columns(conn, "deals")
        if "escritura_date" not in columns:
            conn.execute(
                "ALTER TABLE deals ADD COLUMN escritura_date TEXT")
        if "cpcv_date" not in columns:
            conn.execute("ALTER TABLE deals ADD COLUMN cpcv_date TEXT")
        if "fallen" not in columns:
            conn.execute(
                "ALTER TABLE deals ADD COLUMN fallen INTEGER"
                " NOT NULL DEFAULT 0")
        try:
            conn.execute(
                "UPDATE deals SET escritura_date = month || '-01'"
                " WHERE escritura_date IS NULL OR escritura_date = ''")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute(
                "UPDATE deals SET fallen = 0"
                " WHERE fallen IS NULL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute(
                "DELETE FROM settings WHERE tenant IS NULL"
                " OR tenant NOT IN (SELECT id FROM tenants)")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute(
                "DELETE FROM deals"
                " WHERE tenant IS NULL"
                " OR tenant NOT IN (SELECT id FROM tenants)"
                " OR escritura_date IS NULL OR escritura_date = ''")
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()


def ensure_tenant(path, email):
    init_db(path)
    conn = _connect(path)
    try:
        normalized = auth.normalize_email(email)
        conn.execute(
            "INSERT OR IGNORE INTO tenants (email, created_at)"
            " VALUES (?, ?)",
            (normalized, _utc_text()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM tenants WHERE email = ?", (normalized,)
        ).fetchone()
        return row[0]
    finally:
        conn.close()


def tenant_email(path, tenant):
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT email FROM tenants WHERE id = ?", (tenant,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return row[0]


def tenant_by_email(path, email):
    init_db(path)
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT id FROM tenants WHERE email = ?",
            (auth.normalize_email(email),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return row[0]


def delete_tenant(path, tenant):
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute("DELETE FROM tenants WHERE id = ?", (tenant,))
        conn.commit()
    finally:
        conn.close()


def save_settings(path, values, tenant=None):
    init_db(path)
    if tenant is None:
        raise ValueError("settings require a tenant")
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO settings (tenant, share_rate, iva_rate,"
            " retencao_rate, irs_rate, ss_rate, expenses_cents)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(tenant) DO UPDATE SET"
            " share_rate=excluded.share_rate,"
            " iva_rate=excluded.iva_rate,"
            " retencao_rate=excluded.retencao_rate,"
            " irs_rate=excluded.irs_rate,"
            " ss_rate=excluded.ss_rate,"
            " expenses_cents=excluded.expenses_cents",
            (
                tenant,
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


def get_settings(path, tenant=None):
    init_db(path)
    if tenant is None:
        raise ValueError("settings require a tenant")
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT share_rate, iva_rate, retencao_rate, irs_rate,"
            " ss_rate, expenses_cents FROM settings WHERE tenant = ?",
            (tenant,),
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


def _row_to_deal(row):
    keys = (
        "id",
        "name",
        "agency",
        "month",
        "escritura_date",
        "cpcv_date",
        "fallen",
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
    deal = dict(zip(keys, row))
    deal["fallen"] = bool(deal["fallen"])
    return deal


DEAL_COLUMNS = (
    "id, name, agency, month, escritura_date, cpcv_date, fallen,"
    " stage, agency_commission_cents, share_rate, part_base,"
    " share_rate_used, iva_rate, retencao_rate, irs_rate,"
    " ss_rate, expenses_cents, idempotency_key"
)


def insert_deal(path, deal, tenant=None):
    init_db(path)
    if tenant is None:
        raise ValueError("deals require a tenant")
    month = _check_full_date(deal.get("escritura_date"), "escritura date")
    cpcv = _check_optional_date(deal.get("cpcv_date"), "CPCV date")
    fallen = 1 if deal.get("fallen") else 0
    conn = _connect(path)
    try:
        cursor = conn.execute(
            "INSERT INTO deals (tenant, name, agency, month,"
            " escritura_date, cpcv_date, fallen, stage,"
            " agency_commission_cents, share_rate, part_base,"
            " share_rate_used, iva_rate, retencao_rate, irs_rate,"
            " ss_rate, expenses_cents, idempotency_key)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tenant,
                deal["name"],
                deal["agency"],
                month,
                deal["escritura_date"],
                cpcv,
                fallen,
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
            "SELECT id, tenant FROM deals WHERE idempotency_key = ?",
            (deal["idempotency_key"],),
        ).fetchone()
        if existing is not None and existing[1] == tenant:
            return existing[0]
        raise
    finally:
        conn.close()


def get_deal(path, ident, tenant=None):
    if tenant is None:
        raise ValueError("deals require a tenant")
    rows = [
        deal for deal in list_deals(path, tenant=tenant)
        if deal["id"] == ident
    ]
    if not rows:
        return None
    return rows[0]


def update_deal(path, ident, tenant=None, values=None):
    """Update one deal of the tenant; False when it is not theirs."""
    init_db(path)
    if tenant is None:
        raise ValueError("deals require a tenant")
    allowed = {"name", "agency", "month", "stage", "escritura_date",
               "cpcv_date", "fallen"}
    changes = {}
    if values:
        for key in allowed:
            if key not in values or values.get(key) is None:
                continue
            if key == "escritura_date":
                _check_full_date(values[key], "escritura date")
                changes[key] = values[key]
                changes["month"] = _check_full_date(
                    values[key], "escritura date")
            elif key == "cpcv_date":
                changes[key] = _check_optional_date(
                    values[key], "CPCV date")
            elif key == "fallen":
                changes[key] = 1 if values[key] else 0
            elif key == "month":
                # The forecast month always derives from the
                # escritura date; a bare month never changes a deal.
                continue
            else:
                changes[key] = values[key]
    if not changes:
        return False
    conn = _connect(path)
    try:
        cursor = conn.execute(
            "UPDATE deals SET %s WHERE id = ? AND tenant = ?"
            % ", ".join("%s = ?" % key for key in sorted(changes)),
            tuple(changes[key] for key in sorted(changes)) + (ident, tenant),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def count_deals(path, tenant=None, include_fallen=False):
    init_db(path)
    if tenant is None:
        raise ValueError("deals require a tenant")
    conn = _connect(path)
    try:
        if include_fallen:
            row = conn.execute(
                "SELECT COUNT(*) FROM deals WHERE tenant = ?",
                (tenant,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM deals WHERE tenant = ?"
                " AND fallen = 0",
                (tenant,),
            ).fetchone()
    finally:
        conn.close()
    return row[0]


def list_deals(path, month=None, tenant=None, include_fallen=False):
    init_db(path)
    if tenant is None:
        raise ValueError("deals require a tenant")
    fallen_clause = "" if include_fallen else " AND fallen = 0"
    conn = _connect(path)
    try:
        if month is None:
            rows = conn.execute(
                "SELECT %s FROM deals WHERE tenant = ?%s ORDER BY id"
                % (DEAL_COLUMNS, fallen_clause),
                (tenant,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT %s FROM deals WHERE tenant = ? AND month = ?%s"
                " ORDER BY id" % (DEAL_COLUMNS, fallen_clause),
                (tenant, month),
            ).fetchall()
    finally:
        conn.close()
    return [_row_to_deal(row) for row in rows]


def months_with_deals(path, tenant=None):
    init_db(path)
    if tenant is None:
        raise ValueError("deals require a tenant")
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT month FROM deals"
            " WHERE tenant = ? AND fallen = 0 ORDER BY month",
            (tenant,),
        ).fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows]


def create_link(path, email, token_hash, lang, ip, created_at=None):
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO login_links (email, token_hash, lang, ip,"
            " created_at, used) VALUES (?, ?, ?, ?, ?, 0)",
            (auth.normalize_email(email), token_hash, lang, ip,
             _utc_text(created_at)),
        )
        conn.execute(
            "INSERT INTO link_requests (email, ip, created_at)"
            " VALUES (?, ?, ?)",
            (auth.normalize_email(email), ip, _utc_text(created_at)),
        )
        conn.commit()
    finally:
        conn.close()


def consume_link(path, token_hash, now=None):
    """Use one unused unexpired link row; None when it cannot sign in."""
    init_db(path)
    moment = _utc_text(now) if now is not None else _utc_text()
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT id, email, created_at, used FROM login_links"
            " WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None or row[3]:
            return None
        created = _parse_text(row[2])
        current = _parse_text(moment)
        if not auth.link_valid(created, current):
            conn.execute(
                "DELETE FROM login_links WHERE token_hash = ?",
                (token_hash,),
            )
            conn.commit()
            return None
        conn.execute(
            "UPDATE login_links SET used = 1 WHERE token_hash = ? AND used = 0",
            (token_hash,),
        )
        if conn.total_changes == 0:
            conn.rollback()
            return None
        conn.commit()
        kept = conn.execute(
            "SELECT email, lang FROM login_links WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        return {"email": kept[0], "lang": kept[1]}
    finally:
        conn.close()


def count_recent_links(path, email=None, ip=None, window_minutes=60):
    init_db(path)
    conn = _connect(path)
    try:
        if email is not None:
            row = conn.execute(
                "SELECT COUNT(*) FROM link_requests WHERE email = ?",
                (auth.normalize_email(email),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM link_requests WHERE ip = ?",
                (ip,),
            ).fetchone()
    finally:
        conn.close()
    return row[0]


def create_session(path, session_hash, tenant, created_at=None):
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO sessions (session_hash, tenant, created_at)"
            " VALUES (?, ?, ?)",
            (session_hash, tenant, _utc_text(created_at)),
        )
        conn.commit()
    finally:
        conn.close()


def find_session(path, session_hash, now=None):
    """Tenant of a live session; None for unknown or expired rows."""
    init_db(path)
    moment = _utc_text(now) if now is not None else _utc_text()
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT tenant, created_at FROM sessions"
            " WHERE session_hash = ?",
            (session_hash,),
        ).fetchone()
        if row is None:
            return None
        if not auth.session_valid(_parse_text(row[1]), _parse_text(moment)):
            return None
        return row[0]
    finally:
        conn.close()


def delete_session(path, session_hash):
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "DELETE FROM sessions WHERE session_hash = ?",
            (session_hash,),
        )
        conn.commit()
    finally:
        conn.close()
