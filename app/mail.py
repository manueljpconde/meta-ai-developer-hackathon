"""Sign-in mail through the PropWare relay, standard library only.

The relay host, sender and credentials come from the app's
environment; tests never construct the live client and assert
against the stub outbox instead, so no test touches the network.
"""

import logging
import os
import smtplib
from contextlib import contextmanager
from email.message import EmailMessage

logger = logging.getLogger("app.mail")

RELAY_HOST = "smtp-relay.gmail.com"

RELAY_PORT = 587

SENDER = "hello@propware.pt"

_outbox = None

outbox = []


def send_subject(lang):
    """Sign-in subject in the page language at request time."""
    if lang == "en-GB":
        return "Your Agentimo sign-in link"
    return "O teu link de acesso ao Agentimo"


def send_body(lang, link, minutes=15):
    """Sign-in body in the page language at request time."""
    if lang == "en-GB":
        return (
            "Use the link below to sign in to Agentimo. "
            "It is valid for %d minutes and can be used once.\n\n%s\n"
            % (minutes, link)
        )
    return (
        "Usa o link abaixo para entrar no Agentimo. "
        "É válido por %d minutos e só pode ser usado uma vez.\n\n%s\n"
        % (minutes, link)
    )


def smtp_settings(environ=None):
    """Relay settings from the app's environment file."""
    source = environ if environ is not None else os.environ
    port = str(source.get("APP_SMTP_PORT", RELAY_PORT))
    return {
        "host": source.get("APP_SMTP_HOST", RELAY_HOST),
        "port": int(port),
        "username": source.get("APP_SMTP_USER", ""),
        "password": source.get("APP_SMTP_PASS", ""),
        "sender": source.get("APP_MAIL_SENDER", SENDER),
        "use_tls": source.get("APP_SMTP_STARTTLS", "1") != "0",
    }


@contextmanager
def stub_outbox():
    """Record messages in ``outbox`` instead of opening a socket."""
    global _outbox
    previous = _outbox
    _outbox = outbox
    outbox.clear()
    try:
        yield _outbox
    finally:
        _outbox = previous
        outbox.clear()


def send_signin_link(to_address, link, lang, settings=None):
    """Queue or send the sign-in message; never logs the token."""
    subject = send_subject(lang)
    body = send_body(lang, link)
    if _outbox is not None:
        _outbox.append({"to": to_address, "subject": subject, "body": body})
        logger.info("signin link queued for %s", to_address)
        return
    active = settings if settings is not None else smtp_settings()
    message = EmailMessage()
    message["From"] = active["sender"]
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(active["host"], active["port"]) as smtp:
        if active["use_tls"]:
            smtp.starttls()
        if active["username"]:
            smtp.login(active["username"], active["password"])
        smtp.send_message(message)
    logger.info("signin link sent to %s", to_address)
