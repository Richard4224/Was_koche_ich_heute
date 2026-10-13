"""The contact form: checks a message and sends it by email (e.g. through Gmail) to the site's owner.

Configured by environment variables (or a .env file next to app.py, see README):
    MAIL_USERNAME   the account that sends, e.g. name@gmail.com
    MAIL_PASSWORD   its password; for Gmail an app password (https://myaccount.google.com/apppasswords)
    CONTACT_TO      where messages go (default: MAIL_USERNAME)
    MAIL_SERVER     default smtp.gmail.com, MAIL_PORT default 465 (SSL)

Without MAIL_USERNAME and MAIL_PASSWORD the form says it is unavailable and points to the email address in the
Impressum instead.
"""

import os
import re
import smtplib
import time
from email.message import EmailMessage

MAX_NAME = 100
MAX_EMAIL = 200
MIN_MESSAGE = 10
MAX_MESSAGE = 5000

# Against spam: at most this many messages per visitor (by shortened IP address) and in all
PER_VISITOR = (3, 60 * 60)       # 3 an hour
IN_ALL = (30, 24 * 60 * 60)      # 30 a day
_sent = {}  # shortened IP address -> times of the messages sent from it (only in memory)

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def is_configured():
    return bool(os.environ.get("MAIL_USERNAME") and os.environ.get("MAIL_PASSWORD"))


def check(name, email, message):
    """Return what's wrong with a message, or None if it can be sent."""

    if not EMAIL.fullmatch(email) or len(email) > MAX_EMAIL:
        return "Bitte gib eine gültige E-Mail-Adresse an, damit ich dir antworten kann."
    if len(name) > MAX_NAME:
        return f"Der Name darf höchstens {MAX_NAME} Zeichen lang sein."
    if len(message) < MIN_MESSAGE:
        return "Deine Nachricht ist etwas kurz geraten."
    if len(message) > MAX_MESSAGE:
        return f"Deine Nachricht darf höchstens {MAX_MESSAGE} Zeichen lang sein."
    return None


def allowed(visitor):
    """Whether this visitor (and everyone together) may send another message now."""

    now = time.time()
    for key in list(_sent):
        _sent[key] = [sent for sent in _sent[key] if now - sent < IN_ALL[1]]
        if not _sent[key]:
            del _sent[key]
    recent = [sent for sent in _sent.get(visitor, []) if now - sent < PER_VISITOR[1]]
    total = sum(len(times) for times in _sent.values())
    return len(recent) < PER_VISITOR[0] and total < IN_ALL[0]


def send(name, email, message, visitor):
    """Send a checked message to the owner, with Reply-To set to the visitor. Raises OSError if that fails."""

    username, password = os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"]
    mail = EmailMessage()
    mail["From"] = username
    mail["To"] = os.environ.get("CONTACT_TO") or username
    mail["Reply-To"] = email
    mail["Subject"] = f"Was koche ich heute? Nachricht von {name or email}"
    mail.set_content(f"{message}\n\n--\n{name or '(kein Name)'} <{email}>\nÜber das Kontaktformular von „Was koche ich heute?“")

    server = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    port = int(os.environ.get("MAIL_PORT", 465))
    with smtplib.SMTP_SSL(server, port, timeout=15) as smtp:
        smtp.login(username, password)
        smtp.send_message(mail)
    _sent.setdefault(visitor, []).append(time.time())
