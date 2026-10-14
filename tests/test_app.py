"""Tests for app.py: every page, the live search, the weather for the start page and the contact form."""

import importlib

import pytest

import app as app_module
import contact
from app import count_label, filter_url, quick_groups
from helpers import get_recipe, search_recipes

MESSAGE = {"name": "  Anna \n Beispiel ", "email": "anna@example.org", "message": "Mir fehlt ein Rezept für Grünkohl."}
NO_FILTERS = {"q": "", "diets": [], "have": [], "exclude": [], "with_groups": [], "without_groups": []}


@pytest.fixture
def client():
    return app_module.app.test_client()


def cards(html):
    return html.count('class="glass recipe-card"')


# ---- Start page and search

def test_start_page(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Gericht des Tages" in html and "Aus dem Rezeptbuch" in html
    assert cards(html) == app_module.PAGE_SIZE
    assert f"{app_module.PAGE_SIZE} von {search_recipes()[1]} Rezepten" in html


def test_start_page_with_a_search(client):
    html = client.get("/?q=kürbis").get_data(as_text=True)
    assert "Kürbissuppe" in html
    assert f"{search_recipes('kürbis')[1]} Treffer" in html
    assert 'id="reset-link" hidden' not in html


@pytest.mark.parametrize("n, shown", [(24, 24), (1, app_module.PAGE_SIZE), (99999, None)])
def test_start_page_keeps_more_results_loaded(client, n, shown):
    total = search_recipes()[1]
    html = client.get(f"/?n={n}").get_data(as_text=True)
    assert cards(html) == (shown or min(total, app_module.MAX_SHOWN))


def test_start_page_ignores_unknown_ingredients(client):
    html = client.get("/?zutat=Drachenfrucht-Eis").get_data(as_text=True)
    assert "Rezepten" in html and "Treffer" not in html  # as if nothing was filtered


def test_read_filters():
    url = "/?q=++Suppe++&vegan=1&zutat=ei&ohne=EI&mit=geflügel&kein=geflügel&mit=reis&mit=quatsch"
    with app_module.app.test_request_context(url):
        assert app_module.read_filters() == {
            "q": "Suppe",
            "diets": ["vegan"],
            "have": [],  # "ohne" wins
            "exclude": ["Ei"],
            "with_groups": ["reis"],
            "without_groups": ["geflügel"],
        }


@pytest.mark.parametrize("filters, extra, url", [
    ({}, {}, "/#rezepte"),
    ({"q": "suppe", "exclude": ["Ei"]}, {}, "/?q=suppe&ohne=Ei#rezepte"),
    ({"diets": ["vegan"], "have": ["Kürbis"]}, {"n": 24}, "/?vegan=1&zutat=K%C3%BCrbis&n=24#rezepte"),
    ({"with_groups": ["reis"], "without_groups": ["schwein"]}, {}, "/?mit=reis&kein=schwein#rezepte"),
])
def test_filter_url(filters, extra, url):
    assert filter_url({**NO_FILTERS, **filters}, **extra) == url


@pytest.mark.parametrize("shown, total, filtered, label", [
    (12, 318, False, "12 von 318 Rezepten"),
    (0, 0, True, "Keine Treffer"),
    (12, 40, True, "12 von 40 Treffern"),
    (1, 1, True, "1 Treffer"),
    (5, 5, True, "5 Treffer"),
])
def test_count_label(shown, total, filtered, label):
    assert count_label(shown, total, {**NO_FILTERS, "q": "x" if filtered else ""}) == label


def test_quick_bar_links_add_and_undo():
    items = {item["group"]: item for item in quick_groups({**NO_FILTERS, "with_groups": ["reis"]})}
    assert items["reis"]["chosen"] and not items["reis"]["excluded"]
    assert items["reis"]["with_url"] == "/#rezepte"  # clicking it again takes it out
    assert items["reis"]["without_url"] == "/?kein=reis#rezepte"  # "ohne" replaces "mit"
    assert items["pilze"]["with_url"] == "/?mit=reis&mit=pilze#rezepte"
    assert items["pilze"]["without_url"] == "/?mit=reis&kein=pilze#rezepte"


def test_live_search(client):
    data = client.get("/recipes?q=suppe").get_json()
    total = search_recipes("suppe")[1]
    assert data["total"] == total
    assert data["shown"] == min(total, app_module.PAGE_SIZE)
    assert cards(data["html"]) == data["shown"]


def test_live_search_loads_the_next_ones(client):
    total = search_recipes()[1]
    data = client.get("/recipes?offset=12").get_json()
    assert data["shown"] == 24
    assert data["count"] == f"24 von {total} Rezepten"


def test_live_search_with_a_negative_offset_starts_at_the_top(client):
    assert client.get("/recipes?offset=-5").get_json()["shown"] == app_module.PAGE_SIZE


# ---- Recipe pages

def test_recipe_page(client):
    html = client.get("/recipe/1").get_data(as_text=True)
    assert "<h1>Kürbissuppe</h1>" in html
    assert "Vegan" in html and "Glutenfrei" in html and "Vegetarisch" not in html
    assert "800 ml" in html
    assert "n. G." in html  # salt and pepper "to taste"
    assert 'class="recipe-tip"' in html
    assert get_recipe(1)["description"] in html


def test_recipe_page_for_more_servings(client):
    html = client.get("/recipe/1?servings=8").get_data(as_text=True)
    assert "1,6 l" in html and 'value="8"' in html


@pytest.mark.parametrize("url", ["/recipe/99999", "/recipe/abc", "/gibt-es-nicht"])
def test_pages_that_do_not_exist(client, url):
    response = client.get(url)
    assert response.status_code == 404


def test_error_page(client):
    html = client.get("/recipe/99999").get_data(as_text=True)
    assert "Du hast dich im Wald verirrt." in html and "Dieses Rezept gibt es nicht." in html


@pytest.mark.parametrize("url, text", [
    ("/bildnachweise", "Open-Meteo"),
    ("/impressum", "§ 5 Digitale-Dienste-Gesetz"),
    ("/datenschutz", 'id="kontakt"'),
    ("/kontakt", "Absenden"),
])
def test_pages(client, url, text):
    response = client.get(url)
    assert response.status_code == 200
    assert text in response.get_data(as_text=True)


@pytest.mark.parametrize("url", ["/", "/recipe/1", "/bildnachweise", "/impressum", "/datenschutz", "/kontakt"])
def test_every_page_links_imprint_and_privacy(client, url):
    html = client.get(url).get_data(as_text=True)
    assert 'href="/impressum"' in html and 'href="/datenschutz"' in html and 'href="/kontakt"' in html


# ---- Weather for the start page

def test_weather_without_internet_falls_back(client, internet):
    data = client.get("/weather").get_json()
    assert data["weather"] == "Das Wetter verbirgt sich gerade im Nebel."
    assert data["place"] == "Berlin"
    assert data["season"] in ("Frühling", "Sommer", "Herbst", "Winter")
    assert f'data-recipe="{data["dish"]}"' in data["dish_html"]
    assert any("ipinfo.io" in url for url in internet.urls)  # it tried to guess the place first


def test_weather_at_the_browsers_location(client, internet):
    internet.answer("api.open-meteo.com", {"current": {"temperature_2m": 8.4, "apparent_temperature": 5.6,
                                                       "weather_code": 61}})
    internet.answer("nominatim.openstreetmap.org", {"address": {"suburb": "Woltmershausen", "city": "Bremen"}})
    data = client.get("/weather?lat=53.08&lon=8.81").get_json()
    assert data["weather"] == "8 °C (gefühlt 6 °C), Leichter Regen"
    assert data["place"] == "Woltmershausen, Bremen"
    assert not any("ipinfo.io" in url for url in internet.urls)


def test_weather_at_the_place_of_the_ip_address(client, internet):
    internet.answer("ipinfo.io", {"loc": "-33.87,151.21", "city": "Sydney"})
    data = client.get("/weather?lat=200&lon=8.81").get_json()  # impossible coordinates are ignored
    assert data["place"] == "Sydney"
    assert data["season"] == {"Frühling": "Herbst", "Sommer": "Winter", "Herbst": "Frühling",
                              "Winter": "Sommer"}[app_module.get_season()]
    assert not any("nominatim" in url for url in internet.urls)  # only city-level, no district


@pytest.mark.parametrize("hour, expected", [("8", 8), ("0", 0), ("24", None), ("abc", None)])
def test_weather_picks_the_dish_for_the_browsers_hour(client, monkeypatch, hour, expected):
    seen = []

    def dish(now, latitude, weather):
        seen.append(now)
        return {**get_recipe(1), "reason": "Die Sterne haben gewählt."}

    monkeypatch.setattr(app_module, "get_dish_of_the_day", dish)
    client.get(f"/weather?stunde={hour}")
    if expected is not None:
        assert seen[0].hour == expected
    else:
        assert abs((seen[0] - app_module.local_now()).total_seconds()) < 60  # the server's own clock


# ---- Contact form

@pytest.fixture
def sent(monkeypatch):
    """The messages contact.send was given, instead of sending them."""
    messages = []
    monkeypatch.setattr(contact, "send", lambda *args: messages.append(args))
    return messages


def test_contact_page_after_sending(client):
    assert "Danke für deine Nachricht!" in client.get("/kontakt?gesendet").get_data(as_text=True)


def test_contact_form_sends_the_message(client, sent):
    response = client.post("/kontakt", data=MESSAGE)
    assert response.status_code == 302 and response.headers["Location"] == "/kontakt?gesendet"
    assert sent == [("Anna Beispiel", "anna@example.org", MESSAGE["message"], "127.0.0.0", "http://localhost/")]


def test_contact_form_with_a_mistake_keeps_what_was_typed(client, sent):
    response = client.post("/kontakt", data={**MESSAGE, "email": "anna"})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "gültige E-Mail-Adresse" in html
    assert MESSAGE["message"] in html
    assert sent == []


def test_contact_form_pretends_to_send_for_bots(client, sent):
    response = client.post("/kontakt", data={**MESSAGE, "website": "https://spam.example"})
    assert response.headers["Location"] == "/kontakt?gesendet"
    assert sent == []


def test_contact_form_refuses_too_many_messages(client, sent, monkeypatch):
    monkeypatch.setattr(contact, "allowed", lambda visitor: False)
    response = client.post("/kontakt", data=MESSAGE)
    assert response.status_code == 429
    assert sent == []


def test_contact_form_when_sending_fails(client, monkeypatch):
    def fail(*args):
        raise contact.NotSent("This form needs Activation.")

    monkeypatch.setattr(contact, "send", fail)
    response = client.post("/kontakt", data=MESSAGE)
    assert response.status_code == 502
    assert contact.OWNER in response.get_data(as_text=True)


def test_behind_a_proxy_the_visitor_comes_from_its_header(monkeypatch, sent):
    monkeypatch.setenv("PROXY_COUNT", "1")
    try:
        proxied = importlib.reload(app_module)
        proxied.app.test_client().post("/kontakt", data=MESSAGE, headers={"X-Forwarded-For": "84.132.10.77"})
    finally:
        monkeypatch.delenv("PROXY_COUNT")
        importlib.reload(app_module)
    assert sent[0][3] == "84.132.10.0"


def test_without_a_proxy_its_header_is_not_trusted(client, sent):
    client.post("/kontakt", data=MESSAGE, headers={"X-Forwarded-For": "84.132.10.77"})
    assert sent[0][3] == "127.0.0.0"
