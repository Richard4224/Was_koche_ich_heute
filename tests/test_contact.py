"""Tests for contact.py: checking a message, the limits against spam, and passing it on to FormSubmit."""

import json
import time

import pytest

import contact

NAME, EMAIL, TEXT = "Anna", "anna@example.org", "Mir fehlt ein Rezept für Grünkohl."
VISITOR = "84.132.10.0"
SITE = "https://waskocheichheute.duckdns.org/"


@pytest.fixture
def formsubmit(internet, monkeypatch):
    """FormSubmit taking every message, sent to the address in the Impressum."""
    monkeypatch.delenv("FORMSUBMIT_TO", raising=False)
    internet.answer("formsubmit.co", {"success": "true", "message": "The form was submitted successfully."})
    return internet


# ---- Checking a message

@pytest.mark.parametrize("name", [NAME, ""])  # the name is optional
def test_check_accepts_a_proper_message(name):
    assert contact.check(name, EMAIL, TEXT) is None


@pytest.mark.parametrize("name, email, message, problem", [
    (NAME, "anna", TEXT, "E-Mail-Adresse"),
    (NAME, "anna@example", TEXT, "E-Mail-Adresse"),
    (NAME, "an na@example.org", TEXT, "E-Mail-Adresse"),
    (NAME, "a" * 200 + "@example.org", TEXT, "E-Mail-Adresse"),
    ("A" * (contact.MAX_NAME + 1), EMAIL, TEXT, "Name"),
    (NAME, EMAIL, "Hallo", "kurz"),
    (NAME, EMAIL, "x" * (contact.MAX_MESSAGE + 1), "höchstens"),
])
def test_check_finds_problems(name, email, message, problem):
    assert problem in contact.check(name, email, message)


# ---- Limits against spam

def test_a_visitor_may_send_three_messages_an_hour(formsubmit):
    for _ in range(3):
        assert contact.allowed(VISITOR)
        contact.send(NAME, EMAIL, TEXT, VISITOR, SITE)
    assert not contact.allowed(VISITOR)
    assert contact.allowed("217.0.0.0")  # everyone else still may


def test_a_visitor_may_send_again_an_hour_later():
    contact._sent[VISITOR] = [time.time() - 2 * 60 * 60] * 3
    assert contact.allowed(VISITOR)


def test_at_most_thirty_messages_a_day_in_all():
    contact._sent.update({f"10.0.{number}.0": [time.time() - 2 * 60 * 60] for number in range(30)})
    assert not contact.allowed(VISITOR)


def test_messages_are_forgotten_after_a_day():
    contact._sent[VISITOR] = [time.time() - 25 * 60 * 60]
    contact.allowed("217.0.0.0")
    assert VISITOR not in contact._sent


# ---- Sending

def test_send_passes_the_message_to_formsubmit(formsubmit):
    contact.send(NAME, EMAIL, TEXT, VISITOR, SITE)
    request = formsubmit.requests[0]
    assert request.full_url == contact.FORMSUBMIT + contact.OWNER
    assert request.get_header("Origin") == "https://waskocheichheute.duckdns.org"
    assert request.get_header("Referer") == "https://waskocheichheute.duckdns.org/kontakt"
    data = json.loads(request.data)
    assert (data["name"], data["email"], data["message"]) == (NAME, EMAIL, TEXT)
    assert NAME in data["_subject"]
    assert "84.132.10" not in request.data.decode()  # the visitor's address stays here
    assert len(contact._sent[VISITOR]) == 1


def test_send_without_a_name(formsubmit):
    contact.send("", EMAIL, TEXT, VISITOR, SITE)
    data = json.loads(formsubmit.requests[0].data)
    assert data["name"] == "(kein Name)"
    assert EMAIL in data["_subject"]


def test_send_to_the_alias(formsubmit, monkeypatch):
    monkeypatch.setenv("FORMSUBMIT_TO", "a1b2c3d4")
    contact.send(NAME, EMAIL, TEXT, VISITOR, SITE)
    assert formsubmit.urls == [contact.FORMSUBMIT + "a1b2c3d4"]


def test_send_refused_by_formsubmit(internet):
    internet.answer("formsubmit.co", {"success": "false", "message": "This form needs Activation."})
    with pytest.raises(contact.NotSent, match="Activation"):
        contact.send(NAME, EMAIL, TEXT, VISITOR, SITE)
    assert VISITOR not in contact._sent  # doesn't count against the limit


def test_send_without_internet():
    with pytest.raises(OSError):
        contact.send(NAME, EMAIL, TEXT, VISITOR, SITE)
