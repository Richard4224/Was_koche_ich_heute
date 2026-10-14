"""Tests for the recipe data in schema.sql, seed.sql and images.sql: is everything complete and consistent?"""

import os
import re
from contextlib import closing

import pytest

from find_images import free_license
from helpers import BASE_DIR, get_db, split_instructions
from scaling import PLACEHOLDER

IMAGES = os.path.join(BASE_DIR, "static", "images")
MEAT_AND_FISH = ("geflügel", "rind", "schwein", "lamm-wild", "fisch", "meeresfrüchte")


@pytest.fixture(scope="module")
def recipes():
    with closing(get_db()) as db:
        return [dict(row) for row in db.execute("SELECT * FROM recipes")]


@pytest.fixture(scope="module")
def ingredients():
    with closing(get_db()) as db:
        return [dict(row) for row in db.execute("SELECT * FROM ingredients")]


def test_every_recipe_has_a_description_and_ingredients(recipes):
    with closing(get_db()) as db:
        counts = dict(db.execute("SELECT recipe_id, COUNT(*) FROM recipe_ingredients GROUP BY recipe_id"))
    for recipe in recipes:
        assert recipe["description"], recipe["name"]
        assert counts.get(recipe["id"], 0) >= 2, recipe["name"]


def test_instructions_are_numbered_steps_with_a_closing_line(recipes):
    for recipe in recipes:
        numbers = [int(number) for number in re.findall(r"^(\d+)\.\s", recipe["instructions"], re.MULTILINE)]
        assert numbers == list(range(1, len(numbers) + 1)), recipe["name"]
        parts = split_instructions(recipe["instructions"])
        assert len(parts["steps"]) >= 2, recipe["name"]
        assert parts["closing"] in ("Guten Appetit!", "Zum Wohl!"), recipe["name"]


def test_every_amount_in_the_instructions_is_a_proper_placeholder(recipes):
    """Leftover braces after taking out the placeholders mean a typo like {100g} or {1,5 EL}, which wouldn't scale."""
    for recipe in recipes:
        assert not re.search(r"[{}]", PLACEHOLDER.sub("", recipe["instructions"])), recipe["name"]


def test_every_ingredient_is_used_and_sorted_into_a_category(ingredients):
    with closing(get_db()) as db:
        used = {row[0] for row in db.execute("SELECT ingredient_id FROM recipe_ingredients")}
    for ingredient in ingredients:
        assert ingredient["id"] in used, ingredient["name"]
        assert ingredient["category"] != "sonstiges", ingredient["name"]


def test_diet_flags_make_sense(ingredients):
    for ingredient in ingredients:
        if ingredient["vegan"]:
            assert ingredient["vegetarian"], ingredient["name"]
        if ingredient["category"] in MEAT_AND_FISH:
            assert not ingredient["vegetarian"], ingredient["name"]


def test_photo_names_and_files(recipes):
    names = [recipe["image"] for recipe in recipes]
    assert len(names) == len(set(names))
    assert all(re.fullmatch(r"[a-z0-9-]+\.jpg", name) for name in names)
    assert set(os.listdir(IMAGES)) <= set(names)  # no photo without its recipe


def test_every_photo_is_credited_under_a_free_licence(recipes):
    files = set(os.listdir(IMAGES))
    for recipe in recipes:
        assert (recipe["image"] in files) == bool(recipe["image_author"]), recipe["name"]
        if recipe["image_author"]:
            assert recipe["image_source"].startswith(("https://commons.wikimedia.org/", "https://pixabay.com/"))
            assert free_license(recipe["image_license"]) or recipe["image_license"] == "Pixabay-Lizenz"
