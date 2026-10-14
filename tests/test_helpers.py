"""Tests for helpers.py: moon, season, weather, place and IP location, and reading recipes from the database."""

import os
import shutil
from contextlib import closing
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import helpers
from helpers import (database_version, describe_weather, get_db, get_dish_of_the_day, get_image_credits,
                     get_ingredient_names, get_ip_location, get_moon_phase, get_moon_phase_index, get_pantry_names,
                     get_place, get_recipe, get_season, get_weather_data, local_now, recipe_diets, search_recipes,
                     shorten_ip, split_instructions)

KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
PUBLIC_IP = "84.132.10.77"  # IP addresses from the documentation ranges (203.0.113.x) don't count as public
OPEN_METEO = {"current": {"temperature_2m": 8.4, "apparent_temperature": 5.6, "weather_code": 61}}


def names(recipes):
    return [recipe["name"] for recipe in recipes]


def categories(recipe_id):
    with closing(get_db()) as db:
        return {row["category"] for row in db.execute(
            "SELECT category FROM ingredients JOIN recipe_ingredients ON ingredient_id = ingredients.id "
            "WHERE recipe_id = ?", (recipe_id,))}


# ---- Moon, season and time

def test_moon_phases_through_a_whole_cycle():
    for index, name in enumerate(helpers.MOON_PHASES):
        date = KNOWN_NEW_MOON + timedelta(days=index * helpers.SYNODIC_MONTH / 8)
        assert get_moon_phase_index(date) == index
        assert get_moon_phase(date) == name


@pytest.mark.parametrize("moment, phase", [
    (datetime(2024, 1, 11, 11, 57, tzinfo=timezone.utc), "Neumond"),
    (datetime(2024, 1, 25, 17, 54, tzinfo=timezone.utc), "Vollmond"),
    (datetime(2025, 1, 13, 22, 27, tzinfo=timezone.utc), "Vollmond"),
])
def test_moon_phase_of_real_moons(moment, phase):
    assert get_moon_phase(moment) == phase


def test_moon_phase_now():
    assert get_moon_phase() in helpers.MOON_PHASES


@pytest.mark.parametrize("month, day, season", [
    (1, 15, "Winter"),
    (3, 19, "Winter"),
    (3, 20, "Frühling"),
    (6, 20, "Frühling"),
    (6, 21, "Sommer"),
    (9, 22, "Sommer"),
    (9, 23, "Herbst"),
    (12, 20, "Herbst"),
    (12, 21, "Winter"),
])
def test_season(month, day, season):
    assert get_season(datetime(2026, month, day)) == season


def test_season_is_flipped_south_of_the_equator():
    assert get_season(datetime(2026, 7, 1), latitude=-33.9) == "Winter"
    assert get_season(datetime(2026, 1, 1), latitude=-33.9) == "Sommer"


def test_local_now_is_german_time_without_time_zone():
    now = local_now()
    assert now.tzinfo is None
    assert abs(datetime.now(ZoneInfo("Europe/Berlin")).replace(tzinfo=None) - now) < timedelta(seconds=5)


# ---- IP address and location

@pytest.mark.parametrize("ip, shortened", [
    ("84.132.10.77", "84.132.10.0"),
    ("2001:db8:1234:5678::1", "2001:db8:1234::"),
    ("not an address", None),
    (None, None),
])
def test_shorten_ip(ip, shortened):
    assert shorten_ip(ip) == shortened


def test_ip_location_asks_only_with_the_shortened_address(internet):
    internet.answer("ipinfo.io", {"loc": "53.0758,8.8072", "city": "Bremen"})
    assert get_ip_location(PUBLIC_IP) == (53.0758, 8.8072, "Bremen")
    assert internet.urls == ["https://ipinfo.io/84.132.10.0/json"]


def test_ip_location_is_remembered_for_the_whole_network(internet):
    internet.answer("ipinfo.io", {"loc": "53.0758,8.8072", "city": "Bremen"})
    get_ip_location(PUBLIC_IP)
    assert get_ip_location("84.132.10.200") == (53.0758, 8.8072, "Bremen")
    assert len(internet.requests) == 1


def test_ip_location_of_a_local_visitor_is_this_machines(internet):
    internet.answer("ipinfo.io", {"loc": "53.0758,8.8072", "city": "Bremen"})
    get_ip_location("127.0.0.1")
    assert internet.urls == ["https://ipinfo.io/json"]


@pytest.mark.parametrize("answer", [OSError("offline"), {"city": "Bremen"}, {"loc": "nowhere"}])
def test_ip_location_unknown(internet, answer):
    internet.answer("ipinfo.io", answer)
    assert get_ip_location(PUBLIC_IP) is None


# ---- Weather and place

def test_weather(internet):
    internet.answer("api.open-meteo.com", OPEN_METEO)
    assert get_weather_data(53.0758, 8.8072) == {
        "temperature": 8, "feels_like": 6, "code": 61, "description": "Leichter Regen",
    }
    assert "latitude=53.08&longitude=8.81" in internet.urls[0]


def test_weather_is_remembered_for_nearby_places(internet):
    internet.answer("api.open-meteo.com", OPEN_METEO)
    get_weather_data(53.0758, 8.8072)
    get_weather_data(53.0761, 8.8069)
    assert len(internet.requests) == 1


def test_weather_with_an_unknown_code(internet):
    internet.answer("api.open-meteo.com", {"current": {**OPEN_METEO["current"], "weather_code": 42}})
    assert get_weather_data()["description"] == "Unbekannt"


@pytest.mark.parametrize("answer", [OSError("offline"), {"current": {}}, {"error": True}])
def test_weather_unavailable(internet, answer):
    internet.answer("api.open-meteo.com", answer)
    assert get_weather_data() is None


@pytest.mark.parametrize("weather, text", [
    (None, "Das Wetter verbirgt sich gerade im Nebel."),
    ({"temperature": 12, "feels_like": 12, "description": "Bewölkt"}, "12 °C, Bewölkt"),
    ({"temperature": 8, "feels_like": 6, "description": "Leichter Regen"}, "8 °C (gefühlt 6 °C), Leichter Regen"),
])
def test_describe_weather(weather, text):
    assert describe_weather(weather) == text


def test_place_of_the_default_location_needs_no_request(internet):
    assert get_place() == helpers.PLACE
    assert internet.requests == []


@pytest.mark.parametrize("address, place", [
    ({"suburb": "Woltmershausen", "city": "Bremen"}, "Woltmershausen, Bremen"),
    ({"city_district": "Altona", "city": "Hamburg"}, "Altona, Hamburg"),
    ({"village": "Worpswede"}, "Worpswede"),
    ({"suburb": "Hamburg", "city": "Hamburg"}, "Hamburg"),
    ({}, None),
])
def test_place(internet, address, place):
    internet.answer("nominatim.openstreetmap.org", {"address": address})
    assert get_place(53.0758, 8.8072) == place


def test_place_request_identifies_the_app(internet):
    internet.answer("nominatim.openstreetmap.org", {"address": {"city": "Bremen"}})
    get_place(53.0758, 8.8072)
    get_place(53.0758, 8.8072)
    assert len(internet.requests) == 1  # remembered
    assert internet.requests[0].get_header("User-agent") == helpers.USER_AGENT


def test_place_unknown_when_offline(internet):
    assert get_place(53.0758, 8.8072) is None


# ---- Building the database

@pytest.fixture
def sources(tmp_path, monkeypatch):
    """A copy of the SQL files in a folder of its own, where the database gets built."""
    for name in helpers.DATABASE_SOURCES:
        shutil.copy(os.path.join(helpers.BASE_DIR, name), tmp_path)
    monkeypatch.setattr(helpers, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(helpers, "DATABASE", str(tmp_path / "recipes.db"))
    return tmp_path


def test_database_is_built_on_first_use(sources):
    version = database_version()
    assert (sources / "recipes.db").exists()
    assert database_version() == version  # not built again while nothing changed
    assert list(sources.glob("*.tmp")) == []


def test_database_is_rebuilt_when_a_source_is_newer(sources):
    old = database_version()
    os.utime(sources / "recipes.db", (old - 60, old - 60))
    seed = sources / "seed.sql"
    seed.write_text(seed.read_text(encoding="utf-8").replace("'Kürbissuppe'", "'Kürbiscremesuppe'"), encoding="utf-8")
    assert database_version() != old
    assert names(search_recipes("Kürbiscremesuppe")[0]) == ["Kürbiscremesuppe"]


def test_database_without_photo_credits(sources):
    (sources / "images.sql").unlink()
    database_version()
    assert get_image_credits() == []


# ---- Reading recipes

def test_ingredient_names():
    ingredients = get_ingredient_names()
    assert ingredients == sorted(ingredients)
    assert len(ingredients) == len(set(ingredients))
    assert "Hokkaido-Kürbis" in ingredients


def test_pantry_names():
    pantry = get_pantry_names()
    assert {"Salz", "Zwiebel", "Olivenöl"} <= set(pantry)
    assert "Hokkaido-Kürbis" not in pantry
    assert set(pantry) <= set(get_ingredient_names())


def test_search_everything_in_slices():
    everything, total = search_recipes()
    assert len(everything) == total
    assert names(everything) == sorted(names(everything))
    page, page_total = search_recipes(limit=12, offset=24)
    assert page_total == total
    assert page == everything[24:36]


def test_search_ignores_case_including_umlauts():
    found = names(search_recipes("KÜRBIS")[0])
    assert "Kürbissuppe" in found
    assert "Ofenkürbis mit Feta und Walnüssen" in found
    assert all("kürbis" in name.casefold() for name in found)


@pytest.mark.parametrize("query", ["%", "_", "\\"])
def test_search_takes_wildcards_literally(query):
    assert search_recipes(query) == ([], 0)


def test_diet_filters_agree_with_the_diet_badges():
    everything = search_recipes()[0]
    diets = {recipe["id"]: get_recipe(recipe["id"])["diets"] for recipe in everything}
    for diet, badges in [("vegan", {"vegan"}), ("vegetarisch", {"vegan", "vegetarisch"}), ("glutenfrei", {"glutenfrei"})]:
        found = {recipe["id"] for recipe in search_recipes(diets=[diet])[0]}
        assert found == {recipe_id for recipe_id, shown in diets.items() if badges & set(shown)}, diet


def test_search_without_an_ingredient():
    found = search_recipes(exclude=["Ei"])[0]
    assert found
    for recipe in found:
        assert "Ei" not in [ingredient["name"] for ingredient in get_recipe(recipe["id"])["ingredients"]]


def test_search_with_main_ingredient_groups():
    found = search_recipes(with_groups=["geflügel", "reis"])[0]
    assert "Paella" in names(found)
    for recipe in found:
        assert {"geflügel", "reis"} <= categories(recipe["id"])


def test_search_without_a_main_ingredient_group():
    found = search_recipes(without_groups=["schwein"])[0]
    assert found
    assert all("schwein" not in categories(recipe["id"]) for recipe in found)


def test_search_by_what_is_at_home_ranks_by_what_is_missing():
    found = search_recipes(have=["Hokkaido-Kürbis"])[0]
    assert found
    assert [len(recipe["missing"]) for recipe in found] == sorted(len(recipe["missing"]) for recipe in found)
    soup = next(recipe for recipe in found if recipe["name"] == "Kürbissuppe")
    assert soup["missing"] == ["Ingwer", "Kokosmilch"]  # salt, oil, onions & co. are assumed to be there


def test_search_finds_what_can_be_cooked_right_away_first():
    found = search_recipes(have=["Hokkaido-Kürbis", "Ingwer", "Kokosmilch"])[0]
    assert found[0]["name"] == "Kürbissuppe"
    assert found[0]["missing"] == []


def test_recipe_cards_leave_out_salt_and_pepper():
    soup = search_recipes("Kürbissuppe")[0][0]
    assert "Hokkaido-Kürbis" in soup["ingredients"]
    assert "Salz" not in soup["ingredients"]


def test_recipe():
    soup = get_recipe(1)
    assert soup["name"] == "Kürbissuppe"
    assert soup["description"]
    assert soup["servings"] == 4 and soup["servings_unit"] == "Portionen"
    assert soup["diets"] == ["vegan", "glutenfrei"]
    amounts = {ingredient["name"]: ingredient["amount"] for ingredient in soup["ingredients"]}
    assert amounts["Gemüsebrühe"] == "800 ml"
    assert amounts["Salz"] is None  # to taste
    assert len(soup["steps"]) == 8
    assert soup["tip"].startswith("Die Suppe lässt sich gut einfrieren")
    assert soup["closing"] == "Guten Appetit!"
    assert soup["image"] == "kuerbissuppe.jpg"
    assert soup["credit"]["author"]


def test_recipe_for_more_servings():
    soup = get_recipe(1, servings=8)
    amounts = {ingredient["name"]: ingredient["amount"] for ingredient in soup["ingredients"]}
    assert amounts["Gemüsebrühe"] == "1,6 l"
    assert amounts["Knoblauchzehe"] == "4"
    assert any("4 Knoblauchzehen" in step for step in soup["steps"])  # amounts in the steps scale too


def test_recipe_for_one():
    soup = get_recipe(1, servings=1)
    assert soup["servings_unit"] == "Portion"
    assert {ingredient["name"]: ingredient["amount"] for ingredient in soup["ingredients"]}["Knoblauchzehe"] == "½"


@pytest.mark.parametrize("servings", [0, -2, helpers.MAX_SERVINGS + 1])
def test_recipe_with_impossible_servings_keeps_its_own(servings):
    assert get_recipe(1, servings)["servings"] == 4


def test_recipe_for_two_cake_tins():
    cake = get_recipe(14, servings=2)
    assert cake["servings_unit"] == "Springformen (26 cm)"


def test_recipe_without_a_photo_file():
    with closing(get_db()) as db:
        missing = next(row["id"] for row in db.execute("SELECT id, image FROM recipes")
                       if not os.path.isfile(os.path.join(helpers.BASE_DIR, "static", "images", row["image"])))
    recipe = get_recipe(missing)
    assert recipe["image"] is None and recipe["credit"] is None


def test_recipe_that_does_not_exist():
    assert get_recipe(99999) is None


def test_image_credits():
    credits = get_image_credits()
    assert names(credits) == sorted(names(credits))
    for item in credits:
        assert os.path.isfile(os.path.join(helpers.BASE_DIR, "static", "images", item["image"]))
        assert item["credit"]["author"] and item["credit"]["license"] and item["credit"]["source"]


def rows(*flags):
    return [{"vegan": vegan, "vegetarian": vegetarian, "gluten_free": gluten_free}
            for vegan, vegetarian, gluten_free in flags]


@pytest.mark.parametrize("ingredients, diets", [
    (rows((1, 1, 1), (1, 1, 1)), ["vegan", "glutenfrei"]),
    (rows((1, 1, 0), (0, 1, 1)), ["vegetarisch"]),  # vegan only if everything is
    (rows((0, 0, 1)), ["glutenfrei"]),
    (rows((1, 1, 1), (0, 0, 0)), []),
])
def test_recipe_diets(ingredients, diets):
    assert recipe_diets(ingredients) == diets


def test_split_instructions():
    text = "1. Schneiden.\n2. Kochen, {2} Minuten.\n\nTipp: Mit Brot.\n\nGuten Appetit!"
    assert split_instructions(text) == {
        "steps": ["Schneiden.", "Kochen, {2} Minuten."], "tip": "Mit Brot.", "closing": "Guten Appetit!",
    }


def test_split_instructions_without_tip_and_closing():
    assert split_instructions("1. Mischen.") == {"steps": ["Mischen."], "tip": None, "closing": ""}


def test_dish_of_the_day():
    dish = get_dish_of_the_day(datetime(2026, 10, 14, 19))
    assert dish["name"] and dish["reason"].endswith(".")
