"""Tests for daily_dish.py: the points for season, time of day, weather and moon, and choosing the dish of the day."""

from contextlib import closing
from datetime import date, datetime, timedelta

import pytest

import daily_dish
from daily_dish import (choose, dice, easter, moon_fit, occasion_on, rank, reason, season_fit, season_on, time_slot,
                        weather_fit, week_before)
from helpers import get_db, get_recipe, get_season

BERLIN = 52.52
SYDNEY = -33.87


def recipe(**traits):
    """A recipe as the scoring sees it, with only the traits a test is about."""
    return {"name": "Eintopf", "season": "Herbst", "occasion": None, "meal": "hauptgericht", "warm": True,
            "ingredients": set(), "categories": set(), "vegan": False, **traits}


def test_dice_are_always_the_same_for_the_same_parts():
    assert dice("2026-10-14", 1) == dice("2026-10-14", 1)
    assert dice("2026-10-14", 1) != dice("2026-10-15", 1)
    assert all(0 <= dice(day, 7) < 1 for day in range(100))


@pytest.mark.parametrize("hour, slot", [
    (0, "nacht"), (4, "nacht"), (5, "frühstück"), (9, "frühstück"), (10, "mittag"), (13, "mittag"),
    (14, "kaffee"), (17, "abend"), (21, "abend"), (22, "nacht"), (23, "nacht"),
])
def test_time_slot(hour, slot):
    assert time_slot(hour) == slot


@pytest.mark.parametrize("year, sunday", [
    (2024, date(2024, 3, 31)),
    (2025, date(2025, 4, 20)),
    (2026, date(2026, 4, 5)),
    (2038, date(2038, 4, 25)),  # the latest possible
    (2285, date(2285, 3, 22)),  # the earliest possible
])
def test_easter(year, sunday):
    assert easter(year) == sunday


@pytest.mark.parametrize("day, occasion", [
    (date(2026, 11, 30), None),
    (date(2026, 12, 1), "weihnachten"),
    (date(2026, 12, 26), "weihnachten"),
    (date(2026, 12, 27), "silvester"),
    (date(2027, 1, 1), "silvester"),
    (date(2027, 1, 2), None),
    (date(2026, 4, 1), None),
    (date(2026, 4, 2), "ostern"),  # Maundy Thursday
    (date(2026, 4, 6), "ostern"),  # Easter Monday
    (date(2026, 4, 7), None),
    (date(2026, 10, 19), None),
    (date(2026, 10, 20), "halloween"),
    (date(2026, 10, 31), "halloween"),
    (date(2026, 9, 18), None),
    (date(2026, 9, 19), "oktoberfest"),  # the Saturday after 15 September
    (date(2026, 10, 4), "oktoberfest"),  # the first Sunday in October
    (date(2026, 10, 5), None),
    (date(2023, 10, 3), "oktoberfest"),  # never ends before German Unity Day
    (date(2023, 10, 4), None),
])
def test_occasion_on(day, occasion):
    assert occasion_on(day) == occasion


def test_season_on_agrees_with_the_season_on_the_page():
    day = date(2026, 1, 1)
    while day.year == 2026:
        for latitude in (BERLIN, SYDNEY):
            assert season_on(day, latitude) == get_season(datetime(day.year, day.month, day.day), latitude)
        day += timedelta(days=1)


@pytest.mark.parametrize("traits, season, occasion, fit, phrase", [
    ({"season": "Herbst"}, "Herbst", None, 1.0, "Ein Herbstgericht"),
    ({"season": "Frühling"}, "Frühling", None, 1.0, "Ein Frühlingsgericht"),
    ({"season": "Ganzjährig"}, "Herbst", None, 0.55, "Ein Gericht für jede Jahreszeit"),
    ({"season": "Sommer"}, "Herbst", None, 0.3, "Ein letzter Gruß vom Sommer"),
    ({"season": "Winter"}, "Herbst", None, 0.3, "Ein Vorgeschmack auf den Winter"),
    ({"season": "Frühling"}, "Herbst", None, 0.0, ""),
    ({"season": "Winter"}, "Frühling", None, 0.3, "Ein letzter Gruß vom Winter"),  # round the year
    ({"season": "Winter", "occasion": "weihnachten"}, "Winter", "weihnachten", 1.5, "Es weihnachtet"),
    ({"season": "Winter", "occasion": "weihnachten"}, "Winter", None, 0.5, "Ein Wintergericht"),  # cookies in February
])
def test_season_fit(traits, season, occasion, fit, phrase):
    assert season_fit(recipe(**traits), season, occasion) == (pytest.approx(fit), phrase)


def weather(feels_like, code=3):
    return {"temperature": feels_like, "feels_like": feels_like, "code": code}


SOUP = {"meal": "suppe", "warm": True, "name": "Kürbissuppe"}
SALAD = {"meal": "salat", "warm": False, "name": "Gurkensalat"}
GRILL = {"meal": "hauptgericht", "warm": True, "name": "Hähnchen-Gemüse-Spieße vom Grill"}
CAKE = {"meal": "kuchen", "warm": False, "name": "Apfelkuchen"}


@pytest.mark.parametrize("traits, conditions, fit, phrase", [
    (SOUP, None, 0.5, None),  # weather unknown
    (SOUP, weather(3), 1.0, "wärmt bei 3 °C"),
    (SALAD, weather(3), 0.1, None),
    (SOUP, weather(15), 0.6, None),
    (SALAD, weather(30), 1.0, "erfrischt bei 30 °C"),
    (SOUP, weather(30), 0.15, None),
    (GRILL, weather(23), 1.0, "passt zum Grillwetter"),
    (GRILL, weather(23, code=61), 0.05, None),  # no grilling in the rain
    (SOUP, weather(12, code=61), 0.9, "passt zum Regenwetter"),
    (SOUP, weather(-2, code=73), 1.2, "passt zum Schnee"),
    (CAKE, weather(-2, code=73), 0.5, None),  # cake suits any weather
])
def test_weather_fit(traits, conditions, fit, phrase):
    assert weather_fit(recipe(**traits), conditions) == (pytest.approx(fit), phrase)


@pytest.mark.parametrize("traits, phase, phrase", [
    ({"name": "Heidelbeer-Pfannkuchen"}, 4, "ist rund wie der Vollmond"),
    ({"name": "Heidelbeer-Pfannkuchen"}, 3, None),
    ({"ingredients": {"Rote Bete"}}, 0, "ist dunkel wie die Neumondnacht"),
    ({"name": "Vanillekipferl", "meal": "kuchen"}, 1, "ist geformt wie die Mondsichel"),
    ({"categories": {"rind"}}, 2, "gibt Kraft, solange der Mond zunimmt"),
    ({"meal": "salat"}, 6, "bleibt leicht, solange der Mond abnimmt"),
    ({"vegan": True}, 5, "bleibt leicht, solange der Mond abnimmt"),
    ({}, 4, None),
])
def test_moon_fit(traits, phase, phrase):
    assert moon_fit(recipe(**traits), phase) == ((1.0, phrase) if phrase else (0.0, None))


def test_rank_is_deterministic_and_best_first():
    ranked = rank(date(2026, 10, 14), 19, BERLIN, weather(8, code=61))
    assert ranked == rank(date(2026, 10, 14), 19, BERLIN, weather(8, code=61))
    points = [entry["points"] for entry in ranked]
    assert points == sorted(points, reverse=True)


def test_rank_leaves_out_what_isnt_a_dish():
    ranked = {entry["id"] for entry in rank(date(2026, 10, 14), 19, BERLIN, None)}
    with closing(get_db()) as db:
        for row in db.execute("SELECT id, meal FROM recipes"):
            assert (row["id"] in ranked) == (row["meal"] not in daily_dish.NEVER)


def test_every_meal_and_occasion_in_the_recipes_is_known():
    with closing(get_db()) as db:
        meals = {row["meal"] for row in db.execute("SELECT meal FROM recipes")}
        occasions = {row["occasion"] for row in db.execute("SELECT occasion FROM recipes WHERE occasion IS NOT NULL")}
    assert meals <= set(daily_dish.MEAL_FIT) | daily_dish.NEVER
    assert occasions <= set(daily_dish.OCCASION_PHRASES)


def test_choose_is_the_same_all_day_long_for_the_same_meal():
    dish = choose(datetime(2026, 10, 14, 19, 5), BERLIN)
    assert choose(datetime(2026, 10, 14, 20, 55), BERLIN) == dish
    assert get_recipe(dish[0]) is not None


def test_no_dish_comes_back_within_a_week():
    dishes = [choose(datetime(2026, 10, 1, 19) + timedelta(days=day), BERLIN)[0] for day in range(21)]
    for day, dish in enumerate(dishes):
        assert dish not in dishes[max(0, day - daily_dish.REPEAT_DAYS):day]


def test_breakfast_is_something_for_breakfast():
    for day in range(1, 8):
        dish = get_recipe(choose(datetime(2026, 10, day, 8), BERLIN)[0])
        with closing(get_db()) as db:
            meal = db.execute("SELECT meal FROM recipes WHERE id = ?", (dish["id"],)).fetchone()["meal"]
        assert daily_dish.MEAL_FIT[meal]["frühstück"] >= 0.2, dish["name"]


def test_choose_on_the_southern_hemisphere():
    dish_id, text = choose(datetime(2026, 7, 1, 19), SYDNEY)
    assert get_recipe(dish_id) is not None and text.endswith(".")


def test_week_before_stays_in_the_same_year():
    assert week_before(date(2026, 1, 3)) == [date(2026, 1, 2), date(2026, 1, 1)]
    assert len(week_before(date(2026, 10, 14))) == daily_dish.REPEAT_DAYS


@pytest.mark.parametrize("entry, text", [
    ({"occasion": False, "season": "Ein Herbstgericht", "time": "zum Abendessen",
      "extras": ["wärmt bei 8 °C", "ist rund wie der Vollmond"]},
     "Ein Herbstgericht zum Abendessen. Wärmt bei 8 °C und ist rund wie der Vollmond."),
    ({"occasion": True, "season": "Es weihnachtet", "time": "zu Kaffee und Kuchen", "extras": []},
     "Es weihnachtet – genau das Richtige zu Kaffee und Kuchen."),
    ({"occasion": False, "season": "", "time": None, "extras": []}, "Die Sterne haben gewählt."),
])
def test_reason(entry, text):
    assert reason(entry) == text
