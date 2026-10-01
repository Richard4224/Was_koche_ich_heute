# Idea brainstorming, pseudocode and databank layout from Claude

from flask import Flask, render_template, request
from helpers import get_moon_phase, get_season, get_dish_of_the_day, get_recipes, return_error, get_weather

app = Flask(__name__)

@app.route("/")
def index():

    if request.method == "GET":
            searched_value = request.form.get("q")
    
    moon_phase = get_moon_phase()
    season = get_season()
    dish_of_the_day = get_dish_of_the_day()
    recipes = get_recipes()
    weather = get_weather()
    

    return render_template("index.html", moon_phase=moon_phase, season=season, dish_of_the_day=dish_of_the_day, recipes=recipes, weather=weather)

@app.route("/recipe/<int:recipe_id>")
def recipe(recipe_id):

    if recipe_id not in get_recipes():

        return_error("Recipe was not found", 404)

    return render_template("recipe.html")




