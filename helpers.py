#todo: implement these for real

import ipaddress
import json
import os
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
    0: ("☀️", "Klar"),
    1: ("🌤️", "Überwiegend klar"),
    2: ("⛅", "Teilweise bewölkt"),
    3: ("☁️", "Bewölkt"),
    45: ("🌫️", "Nebel"),
    48: ("🌫️", "Reifnebel"),
    51: ("🌦️", "Leichter Nieselregen"),
    53: ("🌦️", "Nieselregen"),
    55: ("🌦️", "Starker Nieselregen"),
    56: ("🌧️", "Gefrierender Nieselregen"),
    57: ("🌧️", "Gefrierender Nieselregen"),
    61: ("🌧️", "Leichter Regen"),
    63: ("🌧️", "Regen"),
    65: ("🌧️", "Starker Regen"),
    66: ("🌧️", "Gefrierender Regen"),
    67: ("🌧️", "Gefrierender Regen"),
    71: ("🌨️", "Leichter Schneefall"),
    73: ("🌨️", "Schneefall"),
    75: ("🌨️", "Starker Schneefall"),
    77: ("🌨️", "Schneegriesel"),
    80: ("🌦️", "Leichte Regenschauer"),
    81: ("🌦️", "Regenschauer"),
    82: ("🌧️", "Heftige Regenschauer"),
    85: ("🌨️", "Schneeschauer"),
    86: ("🌨️", "Starke Schneeschauer"),
    95: ("⛈️", "Gewitter"),
    96: ("⛈️", "Gewitter mit Hagel"),
    99: ("⛈️", "Gewitter mit starkem Hagel"),
}

SECONDS_IN_A_DAY = 86400
SYNODIC_MONTH = 29.530588853  # days from one new moon to the next
MOON_PHASES = [
    "🌑 Neumond",
    "🌒 Zunehmende Sichel",
    "🌓 Zunehmender Halbmond",
    "🌔 Zunehmender Mond",
    "🌕 Vollmond",
    "🌖 Abnehmender Mond",
    "🌗 Abnehmender Halbmond",
    "🌘 Abnehmende Sichel",
]

def get_moon_phase(date=None):
    """Return the moon phase for date (default: now). Accurate to about ±1 day."""

    reference_point = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)  # a known new moon
    if date is None:
        date = datetime.now(timezone.utc)

    time_delta = date - reference_point
    days_since_reference = time_delta.total_seconds() / SECONDS_IN_A_DAY

    # Position in the current cycle: 0 = new moon, ~14.8 = full moon
    moon_age = days_since_reference % SYNODIC_MONTH

    # Split the cycle into 8 phases; round so each exact phase sits in the middle of its slot
    index = round(moon_age / (SYNODIC_MONTH / 8)) % 8

    return MOON_PHASES[index]



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

    return "Kürbissuppe"



def get_db():
    """Open the recipe database, building it from schema.sql and seed.sql on first use."""

    is_new = not os.path.exists(DATABASE)
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    if is_new:
        for script in ("schema.sql", "seed.sql"):
            with open(os.path.join(BASE_DIR, script), encoding="utf-8") as file:
                db.executescript(file.read())
    return db


def get_recipes():
    """Return all recipes with their ingredient names, sorted by name."""

    with closing(get_db()) as db:
        rows = db.execute(
            """
            SELECT recipes.id, recipes.name, recipes.preparation_time,
                   group_concat(ingredients.name, char(31)) AS ingredients
            FROM recipes
            JOIN recipe_ingredients ON recipe_ingredients.recipe_id = recipes.id
            JOIN ingredients ON ingredients.id = recipe_ingredients.ingredient_id
            GROUP BY recipes.id
            ORDER BY recipes.name
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "time": format_duration(row["preparation_time"]),
            "ingredients": row["ingredients"].split(chr(31)),
        }
        for row in rows
    ]


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
        "instructions": scale_text(recipe["instructions"], factor),
        "image": image,
    }


def return_error(message="Da ist etwas schiefgelaufen.", code=400):
    """Render an error page with an HTTP status code."""

    return render_template("error.html", message=message, code=code), code


def get_weather(latitude=LATITUDE, longitude=LONGITUDE):
    """Return the current weather at a location, e.g. "☁️ 12 °C (gefühlt 9 °C), Bewölkt"."""

    # Round to ~1 km so nearby visitors share a cache entry
    location = (round(latitude, 2), round(longitude, 2))

    # Weather changes slowly, so don't ask the API on every page load
    cached = _weather_cache.get(location)
    if cached and time.time() - cached[0] < WEATHER_CACHE_SECONDS:
        return cached[1]

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={location[0]}&longitude={location[1]}"
        "&current=temperature_2m,apparent_temperature,weather_code,is_day"
    )
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            current = json.load(response)["current"]
    except (OSError, ValueError, KeyError):
        return "Das Wetter verbirgt sich gerade im Nebel."

    emoji, description = WEATHER_CODES.get(current["weather_code"], ("🌡️", "Unbekannt"))
    if not current["is_day"] and current["weather_code"] in (0, 1):
        emoji = "🌙"  # no sun in a clear night sky
    temperature = round(current["temperature_2m"])
    feels_like = round(current["apparent_temperature"])

    weather = f"{emoji} {temperature} °C"
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


