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
from zoneinfo import ZoneInfo

from scaling import format_amount, format_duration, scale_text, servings_unit_name

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "recipes.db")
DATABASE_SOURCES = ("schema.sql", "seed.sql", "images.sql")  # recipes.db is built from these, in this order
MAX_SERVINGS = 1000

# Diet filters as they appear in the URL (?vegan=1), mapped to their column in the ingredients table
DIETS = {"vegan": "vegan", "vegetarisch": "vegetarian", "glutenfrei": "gluten_free"}

# Ingredient categories assumed to be in every kitchen (spices, oils, flour, sugar, onions, …),
# so they never count as missing
PANTRY_CATEGORIES = ("gewürz", "öl", "vorrat")

# Main ingredient groups for the quick bar ("Geflügel", "ohne Schwein"), by their category in the database
MAIN_GROUPS = {
    "geflügel": "Geflügel",
    "rind": "Rind & Kalb",
    "schwein": "Schwein",
    "lamm-wild": "Lamm & Wild",
    "fisch": "Fisch",
    "meeresfrüchte": "Meeresfrüchte",
    "ei": "Ei",
    "käse": "Käse",
    "tofu": "Tofu",
    "hülsenfrüchte": "Hülsenfrüchte",
    "pilze": "Pilze",
    "kartoffel": "Kartoffeln",
    "nudeln": "Nudeln",
    "reis": "Reis",
}

# The site is German, so meal times and days follow German time, whatever clock the server runs on
TIMEZONE = ZoneInfo("Europe/Berlin")

# Fallback location for the weather when neither the browser nor the IP address reveal one
LATITUDE = 52.52
LONGITUDE = 13.41
PLACE = "Berlin"
WEATHER_CACHE_SECONDS = 15 * 60
_weather_cache = {}  # (latitude, longitude) -> (timestamp, weather data)
_place_cache = {}  # (latitude, longitude) -> place name or None
_ip_location_cache = {}  # shortened IP address -> (latitude, longitude, city) or None

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

def local_now():
    """The current date and time in Germany (without time zone, like datetime.now())."""

    return datetime.now(TIMEZONE).replace(tzinfo=None)


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
        date = local_now()

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



def get_dish_of_the_day(now=None, latitude=LATITUDE, weather=None):
    """Return the recipe that best fits this moment (see daily_dish.py), with the reason in "reason"."""

    import daily_dish  # imported here because daily_dish itself uses helpers

    recipe_id, reason = daily_dish.choose(now or local_now(), latitude, weather)
    dish = get_recipe(recipe_id)
    dish["reason"] = reason
    return dish



def database_version():
    """Make sure recipes.db is up to date and return when it was built (changes whenever it is rebuilt).

    recipes.db is built from schema.sql, seed.sql and images.sql, and built anew as soon as one of them is newer,
    e.g. after editing the recipes or pulling new ones with git.
    """

    sources = [os.path.join(BASE_DIR, name) for name in DATABASE_SOURCES]
    sources = [path for path in sources if os.path.exists(path)]  # images.sql only exists once photos are chosen
    built = os.path.getmtime(DATABASE) if os.path.exists(DATABASE) else None
    if built is None or any(os.path.getmtime(path) > built for path in sources):
        # Build next to it and swap it in at once, so other requests never see a half-built database
        temporary = f"{DATABASE}.{os.getpid()}.tmp"
        if os.path.exists(temporary):
            os.remove(temporary)
        with closing(sqlite3.connect(temporary)) as db:
            for path in sources:
                with open(path, encoding="utf-8") as file:
                    db.executescript(file.read())
        try:
            os.replace(temporary, DATABASE)
        except PermissionError:  # Windows won't replace a file that is open; the next request tries again
            os.remove(temporary)
            if built is None:
                raise
    return os.path.getmtime(DATABASE)


def get_db():
    """Open the recipe database, (re)building it first if needed (see database_version)."""

    database_version()
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    # SQLite's own lower() and LIKE ignore case only for A-Z, so "kürbis" wouldn't find "Kürbis"
    db.create_function("casefold", 1, lambda text: text.casefold() if text else text, deterministic=True)
    return db


def get_ingredient_names():
    """Return the names of all ingredients, sorted."""

    with closing(get_db()) as db:
        return [row["name"] for row in db.execute("SELECT name FROM ingredients ORDER BY name")]


def get_pantry_names():
    """Return the names of all ingredients assumed to be in every kitchen, sorted."""

    placeholders = ", ".join("?" * len(PANTRY_CATEGORIES))
    with closing(get_db()) as db:
        rows = db.execute(f"SELECT name FROM ingredients WHERE category IN ({placeholders}) ORDER BY name", PANTRY_CATEGORIES)
        return [row["name"] for row in rows]


def search_recipes(query="", diets=(), have=(), exclude=(), with_groups=(), without_groups=(), limit=-1, offset=0):
    """Find recipes by name, diet, main ingredient and the ingredients someone has at home or doesn't want.

    query:          part of the recipe name, any case
    diets:          keys of DIETS a recipe must satisfy, e.g. ["vegan"]
    have:           ingredient names someone has; then only recipes using at least one of them are found,
                    the ones missing the fewest ingredients first
    exclude:        ingredient names someone doesn't want; recipes containing any of them are left out
    with_groups:    keys of MAIN_GROUPS a recipe must contain, e.g. ["geflügel", "reis"] (all of them)
    without_groups: keys of MAIN_GROUPS a recipe must not contain, e.g. ["schwein"]

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
    for group in with_groups:
        conditions.append("""
            EXISTS (SELECT 1 FROM recipe_ingredients
                    JOIN ingredients ON ingredients.id = recipe_ingredients.ingredient_id
                    WHERE recipe_ingredients.recipe_id = recipes.id AND ingredients.category = ?)""")
        params.append(group)
    if without_groups:
        placeholders = ", ".join("?" * len(without_groups))
        conditions.append(f"""
            NOT EXISTS (SELECT 1 FROM recipe_ingredients
                        JOIN ingredients ON ingredients.id = recipe_ingredients.ingredient_id
                        WHERE recipe_ingredients.recipe_id = recipes.id AND ingredients.category IN ({placeholders}))""")
        params.extend(without_groups)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with closing(get_db()) as db:
        rows = db.execute(
            f"SELECT id, name, preparation_time FROM recipes {where} ORDER BY name", params
        ).fetchall()
        ingredients = {}
        for row in db.execute(
            """
            SELECT recipe_ingredients.recipe_id, ingredients.name, recipe_ingredients.amount, ingredients.category
            FROM recipe_ingredients
            JOIN ingredients ON ingredients.id = recipe_ingredients.ingredient_id
            ORDER BY recipe_ingredients.rowid
            """
        ):
            pantry = row["category"] in PANTRY_CATEGORIES or row["amount"] is None  # always at hand, or "to taste"
            ingredients.setdefault(row["recipe_id"], []).append((row["name"], pantry))

    have = set(have)
    recipes = []
    for row in rows:
        names = [name for name, pantry in ingredients[row["id"]]]
        # The card shows what makes the dish, not salt and pepper
        main = [name for name, pantry in ingredients[row["id"]] if not pantry]
        recipe = {
            "id": row["id"],
            "name": row["name"],
            "time": format_duration(row["preparation_time"]),
            "ingredients": main or names,
            "missing": None,
        }
        if have:
            used = [name for name in names if name in have]
            if not used:
                continue
            recipe["missing"] = [name for name in main if name not in have]
            recipe["used"] = len(used)
        recipes.append(recipe)

    if have:
        recipes.sort(key=lambda recipe: (len(recipe["missing"]), -recipe["used"], recipe["name"]))

    end = None if limit < 0 else offset + limit
    return recipes[offset:end], len(recipes)


def image_credit(recipe):
    """The photo credit of a recipe as {"author", "license", "license_url", "source"}, or None if it has none."""

    if not recipe["image_author"]:
        return None
    return {
        "author": recipe["image_author"],
        "license": recipe["image_license"],
        "license_url": recipe["image_license_url"],
        "source": recipe["image_source"],
    }


def get_image_credits():
    """All recipes that have a photo, with its credit, sorted by name (for the "Bildnachweise" page)."""

    with closing(get_db()) as db:
        rows = db.execute("SELECT * FROM recipes WHERE image_author IS NOT NULL ORDER BY name").fetchall()
    return [
        {"id": row["id"], "name": row["name"], "image": row["image"], "credit": image_credit(row)}
        for row in rows
        if os.path.isfile(os.path.join(BASE_DIR, "static", "images", row["image"]))
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
        **split_instructions(scale_text(recipe["instructions"], factor)),
        "image": image,
        "credit": image_credit(recipe) if image else None,
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


def get_weather_data(latitude=LATITUDE, longitude=LONGITUDE):
    """Return the current weather at a location as {"temperature", "feels_like", "code", "description"},
    or None if the weather service can't be reached."""

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
        weather = {
            "temperature": round(current["temperature_2m"]),
            "feels_like": round(current["apparent_temperature"]),
            "code": current["weather_code"],
            "description": WEATHER_CODES.get(current["weather_code"], "Unbekannt"),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None

    _weather_cache[location] = (time.time(), weather)
    return weather


def describe_weather(weather):
    """Return weather data as text, e.g. "12 °C (gefühlt 9 °C), Bewölkt"."""

    if weather is None:
        return "Das Wetter verbirgt sich gerade im Nebel."
    text = f"{weather['temperature']} °C"
    if weather["feels_like"] != weather["temperature"]:
        text += f" (gefühlt {weather['feels_like']} °C)"
    return text + f", {weather['description']}"


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


def shorten_ip(ip):
    """Cut an IP address down to its network, e.g. 203.0.113.42 to 203.0.113.0 (IPv6: the first 48 bits).
    That still tells the city, but no longer the visitor. Returns None for an invalid address."""

    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False).network_address)


def get_ip_location(ip):
    """Return (latitude, longitude, city) roughly locating an IP address, or None if unknown.
    Only the shortened address (see shorten_ip) is looked up and remembered."""

    short = shorten_ip(ip)
    if short in _ip_location_cache:
        return _ip_location_cache[short]

    # A local address (e.g. 127.0.0.1 while developing) means the visitor is on this machine,
    # so ask about this machine's own public IP instead
    is_public = short is not None and ipaddress.ip_address(ip).is_global
    url = f"https://ipinfo.io/{short}/json" if is_public else "https://ipinfo.io/json"

    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
        latitude, longitude = (float(value) for value in data["loc"].split(","))
        location = (latitude, longitude, data.get("city"))
    except (OSError, ValueError, KeyError):
        return None

    _ip_location_cache[short] = location
    return location


