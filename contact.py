"""The contact form: checks a message and passes it on to FormSubmit (https://formsubmit.co), which emails it to the
site's owner. The server sends it, not the visitor's browser, so FormSubmit never sees the visitor's IP address.

The first message ever sent makes FormSubmit email an "Activate Form" link to the owner; until that is clicked,
messages are not delivered. After activating, FormSubmit also sends a random alias for the address, which can be
put into FORMSUBMIT_TO (in .env) so the address itself isn't sent along.
"""

import json
import os
import re
import time
import urllib.request

OWNER = "brickwellbenedikt@gmail.com"  # as in the Impressum
FORMSUBMIT = "https://formsubmit.co/ajax/"

MAX_NAME = 100
MAX_EMAIL = 200
MIN_MESSAGE = 10
MAX_MESSAGE = 5000

# Against spam: at most this many messages per visitor (by shortened IP address) and in all
PER_VISITOR = (3, 60 * 60)       # 3 an hour
IN_ALL = (30, 24 * 60 * 60)      # 30 a day
_sent = {}  # shortened IP address -> times of the messages sent from it (only in memory)

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class NotSent(OSError):
    """FormSubmit didn't take the message (e.g. the form isn't activated yet)."""


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


def send(name, email, message, visitor, site):
    """Pass a checked message on to FormSubmit; site is this site's address (e.g. "https://example.org/"), which
    FormSubmit wants to know. Raises OSError (NotSent if FormSubmit refused it) if that fails."""

    target = os.environ.get("FORMSUBMIT_TO") or OWNER
    data = json.dumps({
        "name": name or "(kein Name)",
        "email": email,  # FormSubmit makes this the Reply-To
        "message": message,
        "_subject": f"Was koche ich heute? Nachricht von {name or email}",
        "_template": "box",
    }).encode()
    request = urllib.request.Request(FORMSUBMIT + target, data=data, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        # FormSubmit only takes messages from forms on a website, which it tells by these
        "Origin": site.rstrip("/"),
        "Referer": site + "kontakt",
    })
    with urllib.request.urlopen(request, timeout=15) as response:
        answer = json.load(response)
    if str(answer.get("success")).lower() != "true":
        raise NotSent(answer.get("message", "no reason given"))
    _sent.setdefault(visitor, []).append(time.time())
