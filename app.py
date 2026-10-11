# Idea brainstorming, pseudocode and databank layout from Claude

from flask import Flask, jsonify, render_template, request
from helpers import get_moon_phase, get_moon_phase_index, get_season, get_dish_of_the_day, get_recipes, get_recipe, count_recipes, return_error, get_weather, get_place, get_ip_location

app = Flask(__name__)

@app.route("/")
def index():

    if request.method == "GET":
            searched_value = request.form.get("q")
    
    moon_phase = get_moon_phase()
    moon_phase_index = get_moon_phase_index()
    season = get_season()
    dish_of_the_day = get_dish_of_the_day()
    recipes = get_recipes(limit=10)
    recipe_count = count_recipes()


    return render_template("index.html", moon_phase=moon_phase, moon_phase_index=moon_phase_index, season=season, dish_of_the_day=dish_of_the_day, recipes=recipes, recipe_count=recipe_count)

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




