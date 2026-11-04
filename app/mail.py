"""Mail through the PropWare relay. Stub outbox for tests."""

import os
import smtplib
from email.message import EmailMessage

# In-memory outbox for tests; when set, send() appends here instead of SMTP
OUTBOX = None


def send_signin_link(email, token, lang, base_url, config=None):
    """Send sign-in link email. Uses relay when config present, else records in OUTBOX."""
    from app import i18n
    subject = i18n.text(lang, "mail_subject")
    link = "%s/auth/verify?token=%s" % (base_url.rstrip("/"), token)
    body_pt = "Abre este link para entrares (válido 15 minutos):\n%s\n" % link
    body_en = "Open this link to sign in (valid for 15 minutes):\n%s\n" % link
    body = body_pt if lang == "pt-PT" else body_en

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "hello@propware.pt"
    msg["To"] = email
    msg.set_content(body)

    if OUTBOX is not None:
        OUTBOX.append({"to": email, "subject": subject, "body": body, "link": link, "lang": lang})
        return
    _relay(msg)


def send_new_account_notice(email, created_at):
    """Tell the owner (OWNER_NOTIFY_EMAIL) that an account was created; nothing when unset."""
    owner = os.environ.get("OWNER_NOTIFY_EMAIL", "").strip()
    if not owner:
        return
    from datetime import datetime, timezone
    when = datetime.fromtimestamp(created_at, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = "Nova conta no Agentimo: %s" % email
    body = "Foi criada uma conta no Agentimo.\n\nEmail: %s\nData: %s\n" % (email, when)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "hello@propware.pt"
    msg["To"] = owner
    msg.set_content(body)
    if OUTBOX is not None:
        OUTBOX.append({"to": owner, "subject": subject, "body": body})
        return
    _relay(msg)


def _relay(msg):
    relay_host = os.environ.get("PROPWARE_RELAY_HOST", "")
    relay_port = int(os.environ.get("PROPWARE_RELAY_PORT", "587") or "587")
    relay_user = os.environ.get("PROPWARE_RELAY_USER", "")
    relay_pass = os.environ.get("PROPWARE_RELAY_PASS", "")
    if not relay_host:
        return
    with smtplib.SMTP(relay_host, relay_port) as smtp:
        smtp.starttls()
        if relay_user:
            smtp.login(relay_user, relay_pass)
        smtp.send_message(msg)
