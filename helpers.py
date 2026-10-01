#todo: implement these for real

from flask import render_template

def get_moon_phase():
    """Return current moon phase."""

    return "Vollmond"


def get_season():
    """Return current season."""

    return "Herbst"



def get_dish_of_the_day():
    """Return dish which best suits the current day."""

    return "Kürbissuppe"



def get_recipes():
    """Return a list of recipes."""

    return [{"recipe_id": 1, "name": "Kürbissuppe", "preparation_time": 20, "ingredients": ["1 Hokkaido-Kürbis (ca. 1 kg)", "1 Zwiebel", "2 Knoblauchzehen", "1 Stück Ingwer (ca. 2 cm)", "2 EL Olivenöl", "800 ml Gemüsebrühe", "200 ml Kokosmilch", "Salz", "Pfeffer", "Muskatnuss", "Kürbiskerne zum Garnieren"], "manual": "Kürbissuppe (4 Portionen)\n\nZutaten:\n- 1 Hokkaido-Kürbis (ca. 1 kg)\n- 1 Zwiebel\n- 2 Knoblauchzehen\n- 1 Stück Ingwer (ca. 2 cm)\n- 2 EL Olivenöl\n- 800 ml Gemüsebrühe\n- 200 ml Kokosmilch oder Sahne\n- Salz, Pfeffer, Muskatnuss\n- Kürbiskerne zum Garnieren\n\nZubereitung:\n1. Kürbis waschen, halbieren, entkernen und in Würfel schneiden (Hokkaido muss nicht geschält werden).\n2. Zwiebel, Knoblauch und Ingwer schälen und fein hacken.\n3. Olivenöl in einem Topf erhitzen und Zwiebel, Knoblauch und Ingwer darin 3 Minuten andünsten.\n4. Kürbiswürfel dazugeben und 2 Minuten mitbraten.\n5. Mit der Gemüsebrühe ablöschen und ca. 20 Minuten köcheln lassen, bis der Kürbis weich ist.\n6. Kokosmilch oder Sahne hinzufügen und alles fein pürieren.\n7. Mit Salz, Pfeffer und Muskatnuss abschmecken.\n8. In Schüsseln füllen und mit gerösteten Kürbiskernen garnieren.\n\nGuten Appetit!"}]

def return_error(message="You've run into an error", code=400):
    """Return an HTTP Error Message to the user."""

    return render_template("error.html", message=message, code=code)

def get_weather():

    return "18 Grad, Wolkig"


