"""Email-link sign-up and sign-in logic."""

import hashlib
import secrets
import time
import re

from app import store

LINK_EXPIRY_SECONDS = 15 * 60
SESSION_EXPIRY_SECONDS = 30 * 24 * 3600

EMAIL_RATE_LIMIT = 5
IP_RATE_LIMIT = 20

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def validate_email(email):
    if not email or not email.strip():
        return False
    return bool(EMAIL_RE.match(email.strip()))


def request_link(path, email, ip, lang="pt-PT", now=None, token=None):
    if now is None:
        now = time.time()
    email = email.strip().lower() if email else ""
    if not validate_email(email):
        return False, "err_email"
    if not store.check_rate_limit(path, "email", email, now, EMAIL_RATE_LIMIT):
        return False, "err_rate_email"
    if ip and not store.check_rate_limit(path, "ip", ip, now, IP_RATE_LIMIT):
        return False, "err_rate_ip"
    if token is None:
        token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)
    expires_at = now + LINK_EXPIRY_SECONDS
    if ip:
        try:
            store.record_email_ip(path, email, ip)
        except Exception:
            pass
    try:
        store.create_login_link(path, token_hash, email, lang, now, expires_at)
    except Exception:
        return False, "err_rate_email"
    return True, token


def verify_link(path, token, now=None):
    if now is None:
        now = time.time()
    token_hash = hash_token(token)
    link = store.get_login_link(path, token_hash)
    if link is None:
        return None
    if link["used"]:
        return None
    if now > link["expires_at"]:
        return None
    store.mark_link_used(path, token_hash)
    tenant = store.get_or_create_tenant(path, link["email"], now=now)
    link["tenant_id"] = tenant["id"]
    return link


def create_session_for_link(path, link, now=None):
    if now is None:
        now = time.time()
    session_id = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    expires_at = now + SESSION_EXPIRY_SECONDS
    store.create_session(path, session_id, link["tenant_id"], link["email"], now, expires_at, csrf)
    return {"id": session_id, "csrf_token": csrf, "expires_at": expires_at}


def get_valid_session(path, session_id, now=None):
    if now is None:
        now = time.time()
    if not session_id:
        return None
    sess = store.get_session(path, session_id)
    if sess is None:
        return None
    if now > sess["expires_at"]:
        store.delete_session(path, session_id)
        return None
    return sess
