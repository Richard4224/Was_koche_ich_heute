"""Shared setup for all tests: the modules of the app and the tools can be imported, the tests build a database of
their own (recipes.db stays untouched), and no test goes out to the internet.

Run from the project folder:  python -m pytest
"""

import io
import json
import os
import sys
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]

import contact  # noqa: E402  (importable only with the path above)
import helpers  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def database(tmp_path_factory):
    """Build the recipes from schema.sql, seed.sql and images.sql into a database of the tests' own."""
    path = str(tmp_path_factory.mktemp("database") / "recipes.db")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(helpers, "DATABASE", path)
        yield path


class FakeInternet:
    """Stands in for urllib.request.urlopen: notes every request and answers only what a test has set up."""

    def __init__(self):
        self.requests = []
        self.answers = []

    def answer(self, url_part, *bodies):
        """Answer requests whose URL contains url_part with these bodies in turn (the last one repeats). A body is
        JSON data, bytes, or an exception to raise."""
        self.answers.append((url_part, list(bodies)))

    @property
    def urls(self):
        return [url_of(request) for request in self.requests]

    def __call__(self, request, timeout=None):
        url = url_of(request)
        self.requests.append(request)
        for part, bodies in self.answers:
            if part in url:
                body = bodies.pop(0) if len(bodies) > 1 else bodies[0]
                if isinstance(body, BaseException):
                    raise body
                return io.BytesIO(body if isinstance(body, bytes) else json.dumps(body).encode())
        raise OSError(f"Tests don't go online, and no answer was set up for {url}")


def url_of(request):
    return request if isinstance(request, str) else request.full_url


@pytest.fixture(autouse=True)
def internet(monkeypatch):
    """No test reaches the real internet. Tests that need an answer ask for this fixture and set it up."""
    fake = FakeInternet()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


@pytest.fixture(autouse=True)
def empty_caches():
    """Every test starts without remembered weather, places, IP locations or sent messages."""
    for cache in (helpers._weather_cache, helpers._place_cache, helpers._ip_location_cache, contact._sent):
        cache.clear()
