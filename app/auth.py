"""Sign-in tokens, sessions and rate limits, standard library only.

Tokens are random (``secrets``) and stored only as SHA-256 hashes.
Links are single use and valid 15 minutes. Sessions last 30 days
from sign-in and are never extended by visits. Rate limits cap link
requests per email address and per IP address. The client address
comes from ``X-Forwarded-For`` only when the request arrived
through the local Caddy proxy, otherwise from the socket address.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

LINK_TTL = timedelta(minutes=15)

SESSION_TTL = timedelta(days=30)

EMAIL_LIMIT = 5

IP_LIMIT = 20

PROXY_LOOPBACKS = ("127.0.0.1", "::1")


def normalize_email(address):
    """Lower-case and trim the address, the canonical tenant email."""
    return (address or "").strip().lower()


def valid_email(address):
    """Accept a plain ``local@domain`` address, refusing the rest."""
    cleaned = normalize_email(address)
    if not cleaned or " " in cleaned:
        return False
    local, sep, domain = cleaned.partition("@")
    if not sep or not local or not domain:
        return False
    if "@" in domain or "." not in domain:
        return False
    return True


def generate_token():
    """A fresh random URL-safe token, carried once by the link."""
    return secrets.token_urlsafe(32)


def hash_token(raw):
    """SHA-256 hex of the token: what is stored, never the raw value."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def link_valid(created_at, now):
    """Links stay valid 15 minutes from creation, inclusive."""
    return now <= created_at + LINK_TTL


def link_expires_at(created_at):
    """Expiry timestamp of a link created at ``created_at``."""
    return created_at + LINK_TTL


def session_valid(created_at, now):
    """Sessions last 30 days from sign-in, never sliding."""
    return now <= created_at + SESSION_TTL


def session_expires_at(created_at):
    """Expiry timestamp of a session created at ``created_at``."""
    return created_at + SESSION_TTL


def email_allowed(sent_recently):
    """Per-email cap: at most five link requests in the window."""
    return sent_recently < EMAIL_LIMIT


def ip_allowed(seen_recently):
    """Per-IP cap: at most twenty link requests in the window."""
    return seen_recently < IP_LIMIT


def client_ip(environ):
    """Real client address, proxy-aware per the build amendment.

    ``X-Forwarded-For`` is trusted only when the socket peer is the
    local proxy; otherwise the socket address is the address, so a
    direct visitor cannot spoof their IP.
    """
    remote = (environ.get("REMOTE_ADDR", "") or "").strip() or "unknown"
    if remote not in PROXY_LOOPBACKS:
        return remote
    forwarded = environ.get("HTTP_X_FORWARDED_FOR", "") or ""
    first = forwarded.split(",")[0].strip()
    return first or remote


def utcnow():
    """Current UTC time, one seam for the app and the tests."""
    return datetime.now(timezone_utc())


def timezone_utc():
    """UTC tzinfo without importing more than needed elsewhere."""
    from datetime import timezone

    return timezone.utc
