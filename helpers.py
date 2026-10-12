#todo: implement these for real

import ipaddress
import json
import os
import re
import sqlite3
import time
import urllib.request

from contextlib import closing
from flask import render_template
from datetime import datetime, timezone

from scaling import format_amount, format_duration, scale_text, servings_unit_name

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "recipes.db")
MAX_SERVINGS = 1000

# Diet filters as they appear in the URL (?vegan=1), mapped to their column in the ingredients table
DIETS = {"vegan": "vegan", "vegetarisch": "vegetarian", "glutenfrei": "gluten_free"}

# Assumed to be in every kitchen, so never reported as missing
STAPLES = {"Salz", "Pfeffer"}

# Fallback location for the weather when neither the browser nor the IP address reveal one
LATITUDE = 52.52
LONGITUDE = 13.41
PLACE = "Berlin"
WEATHER_CACHE_SECONDS = 15 * 60
_weather_cache = {}  # (latitude, longitude) -> (timestamp, weather string)
_place_cache = {}  # (latitude, longitude) -> place name or None
_ip_location_cache = {}  # IP address -> (latitude, longitude, city) or None

# Nominatim (OpenStreetMap) requires an identifying User-Agent
USER_AGENT = "WasKocheIchHeute/1.0 (https://github.com/Richard4224/recipe-search)"

# WMO weather codes used by Open-Meteo: https://open-meteo.com/en/docs
WEATHER_CODES = {
    0: "Klar",
    1: "Überwiegend klar",
    2: "Teilweise bewölkt",
    3: "Bewölkt",
    45: "Nebel",
    48: "Reifnebel",
    51: "Leichter Nieselregen",
    53: "Nieselregen",
    55: "Starker Nieselregen",
    56: "Gefrierender Nieselregen",
    57: "Gefrierender Nieselregen",
    61: "Leichter Regen",
    63: "Regen",
    65: "Starker Regen",
    66: "Gefrierender Regen",
    67: "Gefrierender Regen",
    71: "Leichter Schneefall",
    73: "Schneefall",
    75: "Starker Schneefall",
    77: "Schneegriesel",
    80: "Leichte Regenschauer",
    81: "Regenschauer",
    82: "Heftige Regenschauer",
    85: "Schneeschauer",
    86: "Starke Schneeschauer",
    95: "Gewitter",
    96: "Gewitter mit Hagel",
    99: "Gewitter mit starkem Hagel",
}

SECONDS_IN_A_DAY = 86400
SYNODIC_MONTH = 29.530588853  # days from one new moon to the next
MOON_PHASES = [
    "Neumond",
    "Zunehmende Sichel",
    "Zunehmender Halbmond",
    "Zunehmender Mond",
    "Vollmond",
    "Abnehmender Mond",
    "Abnehmender Halbmond",
    "Abnehmende Sichel",
]

def get_moon_phase(date=None):
    """Return the moon phase for date (default: now), e.g. "Vollmond". Accurate to about ±1 day."""

    return MOON_PHASES[get_moon_phase_index(date)]


def get_moon_phase_index(date=None):
    """Return the moon phase for date (default: now) as 0 (new moon) to 7, with 4 = full moon."""

    reference_point = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)  # a known new moon
    if date is None:
        date = datetime.now(timezone.utc)

    time_delta = date - reference_point
    days_since_reference = time_delta.total_seconds() / SECONDS_IN_A_DAY

    # Position in the current cycle: 0 = new moon, ~14.8 = full moon
    moon_age = days_since_reference % SYNODIC_MONTH

    # Split the cycle into 8 phases; round so each exact phase sits in the middle of its slot
    return round(moon_age / (SYNODIC_MONTH / 8)) % 8



def get_season(date=None, latitude=LATITUDE):
    """Return the astronomical season for date (default: today) at latitude."""

    if date is None:
        date = datetime.now()

    # Equinoxes and solstices shift by a day or two between years; these dates are close enough
    day = (date.month, date.day)
    if (3, 20) <= day < (6, 21):
        season = "Frühling"
    elif (6, 21) <= day < (9, 23):
        season = "Sommer"
    elif (9, 23) <= day < (12, 21):
        season = "Herbst"
    else:
        season = "Winter"

    # The southern hemisphere has the opposite season
    if latitude < 0:
        season = {"Frühling": "Herbst", "Sommer": "Winter", "Herbst": "Frühling", "Winter": "Sommer"}[season]

    return season



def get_dish_of_the_day():
    """Return dish which best suits the current day."""

    # TODO: choose by moon phase, season and weather
    return get_recipe(1)



def get_db():
    """Open the recipe database, building it from schema.sql and seed.sql on first use."""

    is_new = not os.path.exists(DATABASE)
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    # SQLite's own lower() and LIKE ignore case only for A-Z, so "kürbis" wouldn't find "Kürbis"
    db.create_function("casefold", 1, lambda text: text.casefold() if text else text, deterministic=True)

    if is_new:
        for script in ("schema.sql", "seed.sql"):
            with open(os.path.join(BASE_DIR, script), encoding="utf-8") as file:
                db.executescript(file.read())
    return db


def get_ingredient_names():
    """Return the names of all ingredients, sorted."""

    with closing(get_db()) as db:
        return [row["name"] for row in db.execute("SELECT name FROM ingredients ORDER BY name")]


def get_common_ingredients(limit=16):
    """Return the ingredients used in the most recipes, most common first.

    Staples and uses "to taste" (no amount) don't count: those are assumed to be in the kitchen anyway.
    """

    placeholders = ", ".join("?" * len(STAPLES))
    with closing(get_db()) as db:
        rows = db.execute(
            f"""
            SELECT ingredients.name FROM recipe_ingredients
            JOIN ingredients ON ingredients.id = recipe_ingredients.ingredient_id
            WHERE ingredients.name NOT IN ({placeholders}) AND recipe_ingredients.amount IS NOT NULL
            GROUP BY ingredients.id
            ORDER BY count(*) DESC, ingredients.name
            LIMIT ?
            """,
            (*STAPLES, limit),
        )
        return [row["name"] for row in rows]


def search_recipes(query="", diets=(), have=(), exclude=(), limit=-1, offset=0):
    """Find recipes by name, diet and the ingredients someone has at home or doesn't want.

    query:   part of the recipe name, any case
    diets:   keys of DIETS a recipe must satisfy, e.g. ["vegan"]
    have:    ingredient names someone has; then only recipes using at least one of them are found,
             the ones missing the fewest ingredients first
    exclude: ingredient names someone doesn't want; recipes containing any of them are left out

    Returns (recipes, total): the requested slice and how many recipes match in all.
    """

    conditions, params = [], []
    if query:
        # % and _ are wildcards in LIKE; escape them so they are searched for literally
        escaped = query.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append("casefold(recipes.name) LIKE ? ESCAPE '\\'")
        params.append(f"%{escaped}%")
    for diet in diets:
        # A recipe is vegan (etc.) if none of its ingredients isn't; the column name comes from DIETS
        conditions.append(f"""
            NOT EXISTS (SELECT 1 FROM recipe_ingredients
                        JOIN ingredients ON ingredients.id = recipe_ingredients.ingredient_id
                        WHERE recipe_ingredients.recipe_id = recipes.id AND ingredients.{DIETS[diet]} = 0)""")
    if exclude:
        placeholders = ", ".join("?" * len(exclude))
        conditions.append(f"""
            NOT EXISTS (SELECT 1 FROM recipe_ingredients
                        JOIN ingredients ON ingredients.id = recipe_ingredients.ingredient_id
                        WHERE recipe_ingredients.recipe_id = recipes.id AND ingredients.name IN ({placeholders}))""")
        params.extend(exclude)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with closing(get_db()) as db:
        rows = db.execute(
            f"SELECT id, name, preparation_time FROM recipes {where} ORDER BY name", params
        ).fetchall()
        ingredients = {}
        for row in db.execute(
            """
            SELECT recipe_ingredients.recipe_id, ingredients.name, recipe_ingredients.amount
            FROM recipe_ingredients
            JOIN ingredients ON ingredients.id = recipe_ingredients.ingredient_id
            ORDER BY recipe_ingredients.rowid
            """
        ):
            ingredients.setdefault(row["recipe_id"], []).append((row["name"], row["amount"]))

    have = set(have)
    recipes = []
    for row in rows:
        recipe = {
            "id": row["id"],
            "name": row["name"],
            "time": format_duration(row["preparation_time"]),
            "ingredients": [name for name, amount in ingredients[row["id"]]],
            "missing": None,
        }
        if have:
            used = [name for name in recipe["ingredients"] if name in have]
            if not used:
                continue
            # Staples and anything "to taste" (no amount) don't count as missing
            recipe["missing"] = [name for name, amount in ingredients[row["id"]]
                                 if name not in have and name not in STAPLES and amount is not None]
            recipe["used"] = len(used)
        recipes.append(recipe)

    if have:
        recipes.sort(key=lambda recipe: (len(recipe["missing"]), -recipe["used"], recipe["name"]))

    end = None if limit < 0 else offset + limit
    return recipes[offset:end], len(recipes)


def get_recipe(recipe_id, servings=None):
    """Return a recipe with amounts scaled to servings (default: its own), or None if it doesn't exist."""

    with closing(get_db()) as db:
        recipe = db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if recipe is None:
            return None
        ingredients = db.execute(
            """
            SELECT ingredients.name, recipe_ingredients.amount, recipe_ingredients.unit
            FROM recipe_ingredients
            JOIN ingredients ON ingredients.id = recipe_ingredients.ingredient_id
            WHERE recipe_ingredients.recipe_id = ?
            ORDER BY recipe_ingredients.rowid
            """,
            (recipe_id,),
        ).fetchall()

    # Only whole numbers, so recipes for a baking tin scale to whole tins
    if servings is None or not 1 <= servings <= MAX_SERVINGS:
        servings = recipe["servings"]
    factor = servings / recipe["servings"]

    image = recipe["image"]
    if image and not os.path.isfile(os.path.join(BASE_DIR, "static", "images", image)):
        image = None

    return {
        "id": recipe["id"],
        "name": recipe["name"],
        "time": format_duration(recipe["preparation_time"]),
        "season": recipe["season"],
        "servings": servings,
        "servings_unit": servings_unit_name(servings, recipe["servings_unit"]),
        "ingredients": [
            {
                "name": row["name"],
                "amount": None if row["amount"] is None else format_amount(row["amount"] * factor, row["unit"]),
            }
            for row in ingredients
        ],
        **split_instructions(scale_text(recipe["instructions"], factor)),
        "image": image,
    }


def split_instructions(text):
    """Split "1. Do this\n2. Do that\n\nGuten Appetit!" into steps and closing lines."""

    steps, closing_lines = [], []
    for line in text.splitlines():
        match = re.match(r"\d+\.\s+(.*)", line)
        if match:
            steps.append(match.group(1))
        elif line.strip():
            closing_lines.append(line.strip())
    return {"steps": steps, "closing": " ".join(closing_lines)}


def return_error(message="Da ist etwas schiefgelaufen.", code=400):
    """Render an error page with an HTTP status code."""

    return render_template("error.html", message=message, code=code), code


def get_weather(latitude=LATITUDE, longitude=LONGITUDE):
    """Return the current weather at a location, e.g. "12 °C (gefühlt 9 °C), Bewölkt"."""

    # Round to ~1 km so nearby visitors share a cache entry
    location = (round(latitude, 2), round(longitude, 2))

    # Weather changes slowly, so don't ask the API on every page load
    cached = _weather_cache.get(location)
    if cached and time.time() - cached[0] < WEATHER_CACHE_SECONDS:
        return cached[1]

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={location[0]}&longitude={location[1]}"
        "&current=temperature_2m,apparent_temperature,weather_code"
    )
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            current = json.load(response)["current"]
    except (OSError, ValueError, KeyError):
        return "Das Wetter verbirgt sich gerade im Nebel."

    description = WEATHER_CODES.get(current["weather_code"], "Unbekannt")
    temperature = round(current["temperature_2m"])
    feels_like = round(current["apparent_temperature"])

    weather = f"{temperature} °C"
    if feels_like != temperature:
        weather += f" (gefühlt {feels_like} °C)"
    weather += f", {description}"

    _weather_cache[location] = (time.time(), weather)
    return weather


def get_place(latitude=LATITUDE, longitude=LONGITUDE):
    """Return a place name like "Woltmershausen, Bremen" for a location, or None if unknown."""

    if (latitude, longitude) == (LATITUDE, LONGITUDE):
        return PLACE

    location = (round(latitude, 2), round(longitude, 2))
    if location in _place_cache:
        return _place_cache[location]

    url = (
        "https://nominatim.openstreetmap.org/reverse"
        f"?lat={location[0]}&lon={location[1]}&format=jsonv2&zoom=14&accept-language=de"
    )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=5) as response:
            address = json.load(response).get("address", {})
    except (OSError, ValueError):
        return None

    # District (e.g. "Woltmershausen") plus town (e.g. "Bremen"), whichever exist
    district = address.get("suburb") or address.get("city_district")
    town = address.get("city") or address.get("town") or address.get("village") or address.get("municipality")
    parts = [part for part in dict.fromkeys([district, town]) if part]
    place = ", ".join(parts) or None

    _place_cache[location] = place
    return place


def get_ip_location(ip):
    """Return (latitude, longitude, city) roughly locating an IP address, or None if unknown."""

    if ip in _ip_location_cache:
        return _ip_location_cache[ip]

    # A local address (e.g. 127.0.0.1 while developing) means the visitor is on this machine,
    # so ask about this machine's own public IP instead
    try:
        is_public = ipaddress.ip_address(ip).is_global
    except ValueError:
        is_public = False
    url = f"https://ipinfo.io/{ip}/json" if is_public else "https://ipinfo.io/json"

    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
        latitude, longitude = (float(value) for value in data["loc"].split(","))
        location = (latitude, longitude, data.get("city"))
    except (OSError, ValueError, KeyError):
        return None

    _ip_location_cache[ip] = location
    return location


