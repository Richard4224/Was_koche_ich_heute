# Idea brainstorming, pseudocode and databank layout from Claude

from urllib.parse import urlencode

from flask import Flask, jsonify, render_template, request
from helpers import get_moon_phase, get_moon_phase_index, get_season, get_dish_of_the_day, search_recipes, get_ingredient_names, get_pantry_names, get_recipe, return_error, get_weather, get_place, get_ip_location, DIETS, MAIN_GROUPS

app = Flask(__name__)

PAGE_SIZE = 12  # recipes per batch; scrolling to the end of the results loads the next ones
MAX_SHOWN = 400
DIET_LABELS = {"vegan": "Vegan", "vegetarisch": "Vegetarisch", "glutenfrei": "Glutenfrei"}


def read_filters():
    """Read the search and filters from the URL (?q=…&vegan=1&zutat=Zwiebel&ohne=Ei&mit=geflügel&kein=schwein),
    ignoring anything unknown."""

    names = {name.casefold(): name for name in get_ingredient_names()}

    def ingredients(param):
        found = []
        for typed in request.args.getlist(param):
            name = names.get(typed.strip().casefold())
            if name and name not in found:
                found.append(name)
        return found

    def groups(param):
        chosen = request.args.getlist(param)
        return [group for group in MAIN_GROUPS if group in chosen]

    exclude = ingredients("ohne")
    without_groups = groups("kein")
    return {
        "q": request.args.get("q", "").strip()[:100],
        "diets": [diet for diet in DIETS if request.args.get(diet)],
        "have": [name for name in ingredients("zutat") if name not in exclude],  # "without" wins
        "exclude": exclude,
        "with_groups": [group for group in groups("mit") if group not in without_groups],
        "without_groups": without_groups,
    }


def is_filtered(filters):
    return any(filters.values())


def filter_url(filters, **extra):
    """Return the start page URL for these filters, e.g. "/?q=suppe&ohne=Ei#rezepte"."""

    params = [("q", filters["q"])] if filters["q"] else []
    params += [(diet, "1") for diet in filters["diets"]]
    params += [("zutat", name) for name in filters["have"]]
    params += [("ohne", name) for name in filters["exclude"]]
    params += [("mit", group) for group in filters["with_groups"]]
    params += [("kein", group) for group in filters["without_groups"]]
    params += list(extra.items())
    return "/?" + urlencode(params) + "#rezepte" if params else "/#rezepte"


def quick_groups(filters):
    """The quick bar: main ingredient groups with links that add them ("mit") or leave them out ("ohne"), or undo that."""

    items = []
    for group, label in MAIN_GROUPS.items():
        chosen, excluded = group in filters["with_groups"], group in filters["without_groups"]
        others_with = [other for other in filters["with_groups"] if other != group]
        others_without = [other for other in filters["without_groups"] if other != group]
        items.append({
            "group": group,
            "label": label,
            "chosen": chosen,
            "excluded": excluded,
            "with_url": filter_url({**filters, "with_groups": others_with if chosen else others_with + [group],
                                    "without_groups": others_without}),
            "without_url": filter_url({**filters, "without_groups": others_without if excluded else others_without + [group],
                                       "with_groups": others_with}),
        })
    return items


def count_label(shown, total, filters):
    """Describe how many recipes are shown, e.g. "12 von 318 Rezepten" or "3 Treffer"."""

    if not is_filtered(filters):
        return f"{shown} von {total} Rezepten"
    if total == 0:
        return "Keine Treffer"
    if shown < total:
        return f"{shown} von {total} Treffern"
    return "1 Treffer" if total == 1 else f"{total} Treffer"


def find(filters, limit, offset=0):
    return search_recipes(filters["q"], filters["diets"], filters["have"], filters["exclude"],
                          filters["with_groups"], filters["without_groups"], limit=limit, offset=offset)


@app.route("/")
def index():

    moon_phase = get_moon_phase()
    moon_phase_index = get_moon_phase_index()
    season = get_season()
    dish_of_the_day = get_dish_of_the_day()

    # ?n= keeps the results loaded further down the list when coming back from a recipe
    filters = read_filters()
    limit = min(max(request.args.get("n", PAGE_SIZE, type=int), PAGE_SIZE), MAX_SHOWN)
    recipes, total = find(filters, limit)

    return render_template(
        "index.html", moon_phase=moon_phase, moon_phase_index=moon_phase_index, season=season,
        dish_of_the_day=dish_of_the_day, recipes=recipes, total=total, filters=filters,
        filtered=is_filtered(filters), count=count_label(len(recipes), total, filters),
        more_url=filter_url(filters, n=len(recipes) + PAGE_SIZE), quick=quick_groups(filters),
        ingredient_names=get_ingredient_names(), pantry_names=get_pantry_names(), diet_labels=DIET_LABELS,
    )


@app.route("/recipes")
def recipes():
    """Return the matching recipe cards as HTML, for the live search on the start page."""

    filters = read_filters()
    offset = max(request.args.get("offset", 0, type=int), 0)
    found, total = find(filters, PAGE_SIZE, offset)
    shown = offset + len(found)

    return jsonify(
        html=render_template("recipe_cards.html", recipes=found),
        total=total,
        shown=shown,
        count=count_label(shown, total, filters),
    )


@app.route("/weather")
def weather():
    """Return weather, place and season as JSON, for the browser's location if it sent one."""

    latitude = request.args.get("lat", type=float)
    longitude = request.args.get("lon", type=float)

    if latitude is None or longitude is None or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):

        # No location from the browser: guess the city from the IP address, else use the default
        ip_location = get_ip_location(request.remote_addr)
        if ip_location is None:
            return jsonify(weather=get_weather(), place=get_place(), season=get_season())

        latitude, longitude, city = ip_location
        return jsonify(
            weather=get_weather(latitude, longitude),
            place=city,  # only city-level accurate, so don't look up a district
            season=get_season(latitude=latitude),
        )

    return jsonify(
        weather=get_weather(latitude, longitude),
        place=get_place(latitude, longitude),
        season=get_season(latitude=latitude),
    )

@app.route("/recipe/<int:recipe_id>")
def recipe(recipe_id):
    """Show a recipe, scaled to ?servings=N if given."""

    recipe = get_recipe(recipe_id, request.args.get("servings", type=int))
    if recipe is None:
        return return_error("Dieses Rezept gibt es nicht.", 404)

    return render_template("recipe.html", recipe=recipe)




