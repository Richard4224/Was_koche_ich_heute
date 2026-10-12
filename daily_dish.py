"""The dish of the day.

Every recipe gets points for how well it fits the season (and the occasion: Advent, Easter, …), the time of
day, the weather and the moon. The one with the most points wins. Two "dice", calculated from the date and the
recipe instead of rolled, vary the winner among similar dishes from day to day and from year to year.

It is deterministic: the same day, time of day and weather always give the same dish, so reloading the page
doesn't change it, but the next meal time or a change in the weather can.
"""

import hashlib
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

# How much each part counts: the season most, the moon least
WEIGHTS = {"season": 4.0, "time": 3.0, "weather": 2.0, "moon": 1.0}
OFF_HOURS = 5.0    # taken off dishes that don't suit the time of day at all (no roast for breakfast)
DAILY_DICE = 1.4   # picks a different one of similar dishes each day
YEARLY_DICE = 1.0  # makes every year favour different dishes

SEASONS = ["Frühling", "Sommer", "Herbst", "Winter"]

# Not dishes of their own
NEVER = {"eingemachtes", "beilage", "getränk"}

# Meal times by local hour
TIME_SLOTS = [(5, "frühstück"), (10, "mittag"), (14, "kaffee"), (17, "abend"), (22, "nacht")]

# How well each kind of dish fits each meal time (0 to 1)
MEAL_FIT = {
    "frühstück":          {"frühstück": 1.0, "mittag": 0.15, "kaffee": 0.3, "abend": 0.05, "nacht": 0.2},
    "hauptgericht":       {"frühstück": 0.0, "mittag": 1.0, "kaffee": 0.15, "abend": 1.0, "nacht": 0.35},
    "suppe":              {"frühstück": 0.0, "mittag": 1.0, "kaffee": 0.15, "abend": 0.9, "nacht": 0.35},
    "salat":              {"frühstück": 0.05, "mittag": 0.9, "kaffee": 0.2, "abend": 0.75, "nacht": 0.3},
    "süßes hauptgericht": {"frühstück": 0.3, "mittag": 0.8, "kaffee": 0.8, "abend": 0.35, "nacht": 0.3},
    "kuchen":             {"frühstück": 0.35, "mittag": 0.1, "kaffee": 1.0, "abend": 0.15, "nacht": 0.3},
    "dessert":            {"frühstück": 0.05, "mittag": 0.25, "kaffee": 0.7, "abend": 0.45, "nacht": 0.6},
    "snack":              {"frühstück": 0.1, "mittag": 0.4, "kaffee": 0.5, "abend": 0.6, "nacht": 0.9},
}

TIME_PHRASES = {
    "frühstück": "zum Frühstück",
    "mittag": "fürs Mittagessen",
    "kaffee": "zu Kaffee und Kuchen",
    "abend": "zum Abendessen",
    "nacht": "für den späten Hunger",
}

OCCASION_PHRASES = {
    "weihnachten": "Es weihnachtet",
    "silvester": "Zum Jahreswechsel",
    "ostern": "Frohe Ostern",
    "halloween": "Halloween naht",
    "oktoberfest": "O'zapft is",
}

# Weather codes with rain, drizzle, snow or thunder (see WEATHER_CODES in helpers.py)
WET = set(range(51, 68)) | set(range(71, 78)) | set(range(80, 87)) | {95, 96, 99}
SNOW = set(range(71, 78)) | {85, 86}

# Moon traits, judged from the recipe's name and ingredients
ROUND = ("pfannkuchen", "pizza", "torte", "kuchen", "klöße", "knödel", "tortilla", "frikadellen", "burger", "puffer",
         "clafoutis", "quiche", "tarte", "muffins", "makronen", "plätzchen", "pie", "waffeln", "bratapfel", "klopse",
         "balls", "spiegelei", "pajeon", "datschi")
CRESCENT = ("kipferl",)
DARK = {"Zartbitterschokolade", "Backkakao", "Schwarze Bohnen", "Belugalinsen", "Rote Bete", "Blutwurst", "Mohn",
        "Nori", "Rotkohl", "Heidelbeeren"}
PROTEIN = {"geflügel", "rind", "schwein", "lamm-wild", "fisch", "meeresfrüchte", "ei", "hülsenfrüchte"}
MAIN_MEALS = {"hauptgericht", "suppe", "salat"}


def dice(*parts):
    """A number between 0 and 1 that is always the same for the same parts, but looks random."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def time_slot(hour):
    slot = TIME_SLOTS[-1][1]  # before 5 in the morning it's still night
    for start, name in TIME_SLOTS:
        if hour >= start:
            slot = name
    return slot


def easter(year):
    """Easter Sunday (the "anonymous Gregorian" computus)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    month = (h + l - 7 * m + 90) // 25
    return date(year, month, (h + l - 7 * m + 33 * month + 19) % 32)


def occasion_on(day):
    """The occasion a day belongs to, if any."""
    md = (day.month, day.day)
    if (12, 1) <= md <= (12, 26):
        return "weihnachten"
    if md >= (12, 27) or md == (1, 1):
        return "silvester"
    if easter(day.year) - timedelta(days=3) <= day <= easter(day.year) + timedelta(days=1):
        return "ostern"  # from Maundy Thursday (Grüne Soße!) to Easter Monday
    if (10, 20) <= md <= (10, 31):
        return "halloween"
    # Oktoberfest: from the Saturday after 15 September to the first Sunday of October (at least 3 October)
    start = date(day.year, 9, 16) + timedelta(days=(5 - date(day.year, 9, 16).weekday()) % 7)
    end = date(day.year, 10, 1) + timedelta(days=(6 - date(day.year, 10, 1).weekday()) % 7)
    if start <= day <= max(end, date(day.year, 10, 3)):
        return "oktoberfest"
    return None


def season_on(day, latitude):
    """The astronomical season on a day, flipped on the southern hemisphere."""
    md = (day.month, day.day)
    if (3, 20) <= md < (6, 21):
        index = 0
    elif (6, 21) <= md < (9, 23):
        index = 1
    elif (9, 23) <= md < (12, 21):
        index = 2
    else:
        index = 3
    if latitude < 0:
        index = (index + 2) % 4
    return SEASONS[index]


def season_fit(recipe, season, occasion):
    """Points and a phrase for how well a recipe fits the season and today's occasion."""
    if recipe["occasion"] and recipe["occasion"] == occasion:
        return 1.5, OCCASION_PHRASES[occasion]
    here = SEASONS.index(season)
    if recipe["season"] == season:
        fit, phrase = 1.0, f"Ein {season}sgericht" if season == "Frühling" else f"Ein {season}gericht"
    elif recipe["season"] == "Ganzjährig":
        fit, phrase = 0.55, "Ein Gericht für jede Jahreszeit"
    elif recipe["season"] == SEASONS[here - 1]:
        fit, phrase = 0.3, "Ein letzter Gruß vom " + recipe["season"]
    elif recipe["season"] == SEASONS[(here + 1) % 4]:
        fit, phrase = 0.3, "Ein Vorgeschmack auf den " + recipe["season"]
    else:
        fit, phrase = 0.0, ""
    if recipe["occasion"]:
        fit *= 0.5  # Christmas cookies belong to Advent, not to February
    return fit, phrase


def weather_fit(recipe, weather):
    """Points and a phrase for how well a recipe fits the weather (neutral if the weather is unknown)."""
    if weather is None or (recipe["meal"] == "kuchen" and not recipe["warm"]):
        return 0.5, None  # unknown weather, or cake: fits any weather (only a warm strudel warms you up)
    feels, code = weather["feels_like"], weather["code"]
    wet = code in WET
    soup = recipe["meal"] == "suppe"
    grill = "grill" in recipe["name"].lower() or "spieße" in recipe["name"].lower()

    if feels < 10:      # frosty or cold: something warm
        fit = 1.0 if recipe["warm"] else 0.1
        phrase = f"wärmt bei {weather['feels_like']} °C" if recipe["warm"] else None
    elif feels < 20:    # mild: anything goes
        fit, phrase = (0.6 if recipe["warm"] else 0.5), None
    elif feels < 27:    # warm: rather something fresh, or the grill
        fit = 0.35 if recipe["warm"] else 0.9
        phrase = None if recipe["warm"] else f"erfrischt bei {weather['feels_like']} °C"
        if grill and not wet:
            fit, phrase = 1.0, "passt zum Grillwetter"
    else:               # hot: only cold things
        fit = 0.15 if recipe["warm"] else 1.0
        phrase = None if recipe["warm"] else f"erfrischt bei {weather['feels_like']} °C"

    if wet and recipe["warm"]:
        fit += 0.3 if soup else 0.1
        if soup:
            phrase = "passt zum Schnee" if code in SNOW else "passt zum Regenwetter"
    if wet and grill:
        fit -= 0.4
    return max(0.0, min(fit, 1.2)), phrase


def moon_fit(recipe, phase):
    """Points and a phrase for how well a recipe fits the moon phase (0 = new moon, 4 = full moon)."""
    name = recipe["name"].lower()
    if phase == 4 and any(word in name for word in ROUND):
        return 1.0, "ist rund wie der Vollmond"
    if phase == 0 and recipe["ingredients"] & DARK:
        return 1.0, "ist dunkel wie die Neumondnacht"
    if phase in (1, 7) and any(word in name for word in CRESCENT):
        return 1.0, "ist geformt wie die Mondsichel"
    if phase in (1, 2, 3) and recipe["meal"] in MAIN_MEALS and recipe["categories"] & PROTEIN:
        return 1.0, "gibt Kraft, solange der Mond zunimmt"
    if phase in (5, 6, 7) and (recipe["meal"] == "salat" or (recipe["vegan"] and recipe["meal"] in MAIN_MEALS)):
        return 1.0, "bleibt leicht, solange der Mond abnimmt"
    return 0.0, None


@lru_cache(maxsize=1)
def load_recipes():
    """Everything the scoring needs about every possible dish of the day (read once, the recipes don't change)."""
    from helpers import get_db

    with closing(get_db()) as db:
        recipes = {
            row["id"]: {"id": row["id"], "name": row["name"], "season": row["season"], "meal": row["meal"],
                        "warm": bool(row["warm"]), "occasion": row["occasion"], "ingredients": set(),
                        "categories": set(), "vegan": True}
            for row in db.execute("SELECT id, name, season, meal, warm, occasion FROM recipes")
            if row["meal"] not in NEVER
        }
        for row in db.execute(
            """
            SELECT recipe_ingredients.recipe_id, ingredients.name, ingredients.category, ingredients.vegan
            FROM recipe_ingredients JOIN ingredients ON ingredients.id = recipe_ingredients.ingredient_id
            """
        ):
            recipe = recipes.get(row["recipe_id"])
            if recipe:
                recipe["ingredients"].add(row["name"])
                recipe["categories"].add(row["category"])
                recipe["vegan"] = recipe["vegan"] and bool(row["vegan"])
    return list(recipes.values())


def rank(day, hour, latitude, weather):
    """All candidates with their points and reasons, best first."""
    from helpers import get_moon_phase_index

    season = season_on(day, latitude)
    occasion = occasion_on(day)
    slot = time_slot(hour)
    phase = get_moon_phase_index(datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc))

    ranked = []
    for recipe in load_recipes():
        season_points, season_phrase = season_fit(recipe, season, occasion)
        time_points = MEAL_FIT[recipe["meal"]][slot]
        weather_points, weather_phrase = weather_fit(recipe, weather)
        moon_points, moon_phrase = moon_fit(recipe, phase)
        points = (WEIGHTS["season"] * season_points + WEIGHTS["time"] * time_points
                  + WEIGHTS["weather"] * weather_points + WEIGHTS["moon"] * moon_points
                  + DAILY_DICE * dice(day.isoformat(), recipe["id"]) + YEARLY_DICE * dice(day.year, recipe["id"]))
        if time_points < 0.2:
            points -= OFF_HOURS
        ranked.append({
            "id": recipe["id"],
            "points": points,
            "season": season_phrase,
            "occasion": bool(recipe["occasion"]) and recipe["occasion"] == occasion,
            "time": TIME_PHRASES[slot] if time_points >= 0.7 else None,
            "extras": [phrase for phrase in (weather_phrase, moon_phrase) if phrase],
        })
    ranked.sort(key=lambda entry: (-entry["points"], entry["id"]))
    return ranked


REPEAT_DAYS = 7  # a dish doesn't come back within a week (at the same time of day)

# The dishes of past days, worked out once: (southern hemisphere?, meal time) -> {day: recipe id}
_history = {}


def week_before(day):
    """The days before a day that a dish must not repeat, within the same year (every year starts afresh)."""
    return [day - timedelta(days=n) for n in range(1, REPEAT_DAYS + 1) if (day - timedelta(days=n)).year == day.year]


def chosen_on(day, hour, latitude):
    """The dish of a day at a meal time, judged without weather (past weather is unknown).

    Which dish a day gets depends on the days before it (no repeats within a week), so the days of a year are
    worked out one after another from 1 January, and remembered.
    """
    history = _history.setdefault((latitude < 0, time_slot(hour)), {})
    if day not in history:
        known = [past for past in history if past.year == day.year and past < day]
        current = max(known) + timedelta(days=1) if known else date(day.year, 1, 1)
        while current <= day:
            recent = {history[past] for past in week_before(current)}
            history[current] = next(entry["id"] for entry in rank(current, hour, latitude, None) if entry["id"] not in recent)
            current += timedelta(days=1)
    return history[day]


def choose(now, latitude, weather=None):
    """Pick the dish of the day for a local time; returns (recipe id, reason text)."""
    day = now.date()
    recent = {chosen_on(past, now.hour, latitude) for past in week_before(day)}
    best = next(entry for entry in rank(day, now.hour, latitude, weather) if entry["id"] not in recent)
    return best["id"], reason(best)


def reason(entry):
    """Turn the reasons into a sentence or two, e.g. "Ein Herbstgericht zum Abendessen. Wärmt bei 8 °C."."""
    if entry["occasion"] and entry["time"]:
        first = f"{entry['season']} – genau das Richtige {entry['time']}"  # "Es weihnachtet – genau das Richtige …"
    else:
        first = " ".join(part for part in (entry["season"], entry["time"]) if part) or "Die Sterne haben gewählt"
    text = first + "."
    if entry["extras"]:
        rest = " und ".join(entry["extras"])
        text += " " + rest[0].upper() + rest[1:] + "."
    return text
