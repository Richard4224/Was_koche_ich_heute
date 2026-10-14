"""Tests for tools/find_images.py: which photos are usable, how they are searched for, and the page to choose them."""

import json
import shutil
import time
import urllib.error

import pytest

import find_images
from find_images import (author, find, find_pixabay, free_license, photos, pixabay, pixabay_key, plain, related,
                         search_pixabay, search_terms, tidy_author, wikipedia, write_review)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """The tools pause between requests to be polite; the tests don't need to."""
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def out(tmp_path, monkeypatch):
    """The tools' working folder, so tests never touch tools/images/ (or the API key in it)."""
    monkeypatch.setattr(find_images, "OUT", str(tmp_path))
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    return tmp_path


def commons_file(title, index=1, mime="image/jpeg", width=1600, height=1000, license_name="CC BY-SA 4.0"):
    """A file as the Commons API describes it."""
    return {"title": title, "index": index, "imageinfo": [{
        "mime": mime, "width": width, "height": height, "thumburl": f"https://upload.example/{title}",
        "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
        "extmetadata": {"LicenseShortName": {"value": license_name}, "Artist": {"value": "<a href='/u'>Anna</a>"}},
    }]}


def photo(title):
    return {"title": title, "thumb": "", "source": "", "author": "", "license": "", "size": ""}


@pytest.mark.parametrize("name, usable", [
    ("CC BY-SA 4.0", True),
    ("CC BY-SA 3.0 de", True),
    ("CC BY 2.0", True),
    ("CC0", True),
    ("cc-zero", True),
    ("Public domain", True),
    ("CC BY-NC 2.0", False),
    ("CC BY-NC-SA 4.0", False),
    ("CC BY-ND 3.0", False),
    ("GFDL", False),
])
def test_free_license(name, usable):
    assert free_license(name) == usable


def test_plain():
    assert plain("<a href='x'>Anna</a>  &amp;\n Bob ") == "Anna & Bob"


@pytest.mark.parametrize("raw, name", [
    ("No machine-readable author provided. Elya assumed (based on copyright claims).", "Elya"),
    ("File:Apfelkuchen.jpg: Anna", "Anna"),
    ("Cake.JPG: Anna derivative work: Bob", "Anna, bearbeitet von Bob"),
    ("Elya (talk) 10:54, 29 August 2021 (UTC)", "Elya"),
    ("User:Some_Body", "Some Body"),
    ("© Anna", "Anna"),
    ("Unknown author", "Unbekannt"),
    ("", "Unbekannt"),
])
def test_tidy_author(raw, name):
    assert tidy_author(raw) == name


def test_author_from_commons_metadata():
    assert author({"Artist": {"value": "<span><a href='/wiki/User:Anna'>Anna</a></span>"}}) == "Anna"
    assert author({}) == "Unbekannt"


@pytest.mark.parametrize("name, terms", [
    ("Kürbissuppe", ["Kürbissuppe"]),
    ("Lammkeule mit Rosmarin und Knoblauch", ["Lammkeule mit Rosmarin und Knoblauch", "Lammkeule"]),
    ("Hollerküchle (gebackene Holunderblüten)",
     ["Hollerküchle (gebackene Holunderblüten)", "Hollerküchle", "gebackene Holunderblüten"]),
])
def test_search_terms(name, terms):
    assert search_terms(name) == terms


def test_photos_keeps_only_usable_ones_in_the_apis_order():
    pages = {
        "1": commons_file("File:Second.jpg", index=2),
        "2": commons_file("File:First.jpg", index=1, width=1200, height=900),
        "3": commons_file("File:Drawing.png", mime="image/png"),
        "4": commons_file("File:Private.jpg", license_name="CC BY-NC 2.0"),
        "5": commons_file("File:Small.jpg", width=600, height=400),
        "6": commons_file("File:Tall.jpg", width=800, height=1600),
        "7": commons_file("File:Panorama.jpg", width=4000, height=1000),
    }
    found = photos(pages)
    assert [photo["title"] for photo in found] == ["File:First.jpg", "File:Second.jpg"]
    assert found[0]["author"] == "Anna" and found[0]["size"] == "1200×900"


@pytest.mark.parametrize("term, title, fits", [
    ("Maultasche", "Geschmälzte Maultaschen", True),
    ("Kerbelsuppe", "Liste Münchner Straßennamen/K", False),
    ("Bratapfel", "Bratapfel", True),
])
def test_related(term, title, fits):
    assert related(term, title) == fits


def test_commons_tries_again_and_says_who_asks(internet):
    internet.answer("commons.wikimedia.org", OSError("timeout"), {"query": {"pages": {}}})
    assert find_images.commons({"action": "query"}) == {"query": {"pages": {}}}
    assert len(internet.requests) == 2
    assert internet.requests[0].get_header("User-agent") == find_images.USER_AGENT


def test_commons_gives_up_after_three_tries(internet):
    internet.answer("commons.wikimedia.org", OSError("timeout"))
    assert find_images.commons({"action": "query"}) == {}
    assert len(internet.requests) == 3


def test_wikipedia_leads_to_the_articles_photo_and_english_title(internet):
    internet.answer("list=search", {"query": {"search": [{"title": "Liste von Speisen"}, {"title": "Bratapfel"}]}})
    internet.answer("lllang=en", {"query": {"pages": {"1": {"pageimage": "Bratapfel.jpg",
                                                            "langlinks": [{"*": "Baked apple"}]}}}})
    internet.answer("commons.wikimedia.org", {"query": {"pages": {"1": commons_file("File:Bratapfel.jpg")}}})
    article, found, english = wikipedia(["Bratapfel"])
    assert (article, english) == ("Bratapfel", "Baked apple")
    assert [photo["title"] for photo in found] == ["File:Bratapfel.jpg"]


def test_wikipedia_without_a_fitting_article(internet):
    internet.answer("list=search", {"query": {"search": [{"title": "Liste Münchner Straßennamen/K"}]}})
    assert wikipedia(["Kerbelsuppe"]) == (None, [], None)


def test_find_searches_the_name_then_wikipedia_then_the_english_title(monkeypatch):
    results = {"Bratapfel": [photo("A")], '"Baked apple"': [photo("B"), photo("A")]}
    monkeypatch.setattr(find_images, "search", lambda term: results.get(term, []))
    monkeypatch.setattr(find_images, "wikipedia", lambda terms: ("Bratapfel", [photo("C")], "Baked apple"))
    found = find("Bratapfel")
    assert [(photo["title"], photo["via"]) for photo in found] == [
        ("A", "Bratapfel"), ("C", "Wikipedia: Bratapfel"), ("B", "Baked apple"),
    ]


def test_find_stops_when_there_are_enough(monkeypatch):
    many = [photo(str(number)) for number in range(10)]
    monkeypatch.setattr(find_images, "search", lambda term: many)
    monkeypatch.setattr(find_images, "wikipedia", lambda terms: pytest.fail("no need to ask Wikipedia"))
    assert len(find("Bratapfel")) == find_images.CANDIDATES


def test_pixabay_key_from_the_environment(monkeypatch, out):
    (out / "pixabay-key.txt").write_text("from-the-file", encoding="utf-8")
    monkeypatch.setenv("PIXABAY_API_KEY", "from-the-environment")
    assert pixabay_key() == "from-the-environment"


def test_pixabay_key_from_the_file(out):
    (out / "pixabay-key.txt").write_text(" from-the-file\n", encoding="utf-8")
    assert pixabay_key() == "from-the-file"


def test_pixabay_key_missing():
    with pytest.raises(SystemExit):
        pixabay_key()


def test_pixabay_waits_when_asked_too_often(internet):
    too_many = urllib.error.HTTPError(find_images.PIXABAY, 429, "Too Many Requests", {}, None)
    internet.answer("pixabay.com/api", too_many, {"hits": []})
    assert pixabay({"q": "Kuchen"}, "test-key") == {"hits": []}
    assert "key=test-key" in internet.urls[0]


def test_pixabay_passes_on_other_errors(internet):
    internet.answer("pixabay.com/api", urllib.error.HTTPError(find_images.PIXABAY, 400, "Bad Request", {}, None))
    with pytest.raises(urllib.error.HTTPError):
        pixabay({"q": "Kuchen"}, "test-key")


PIXABAY_HIT = {"id": 123, "webformatURL": "https://pixabay.com/get/preview.jpg",
               "pageURL": "https://pixabay.com/photos/kuchen-123/", "user": "Anna",
               "imageWidth": 4000, "imageHeight": 2500}


def test_search_pixabay_keeps_answers_for_a_day(internet):
    internet.answer("pixabay.com/api", {"hits": [PIXABAY_HIT]})
    cache = {}
    found = search_pixabay("Apfelkuchen", "test-key", cache)
    assert found == [{"title": "Pixabay 123", "thumb": PIXABAY_HIT["webformatURL"], "source": PIXABAY_HIT["pageURL"],
                      "author": "Anna", "license": "Pixabay-Lizenz", "size": "4000×2500"}]
    assert search_pixabay("Apfelkuchen", "test-key", cache) == found
    assert len(internet.requests) == 1
    cache["Apfelkuchen"]["time"] -= 24 * 60 * 60
    search_pixabay("Apfelkuchen", "test-key", cache)
    assert len(internet.requests) == 2


def test_find_pixabay_tries_the_dish_alone(monkeypatch):
    asked = []

    def search(term, key, cache):
        asked.append(term)
        return [photo("Pixabay 1")] if term == "Lammkeule" else []

    monkeypatch.setattr(find_images, "search_pixabay", search)
    found = find_pixabay("Lammkeule mit Rosmarin und Knoblauch (Ostern)", "test-key", {})
    assert asked == ["Lammkeule mit Rosmarin und Knoblauch", "Lammkeule"]
    assert found[0]["via"] == "Lammkeule"


def test_review_page(out):
    write_review([{"recipe": "Kuchen </script>", "file": "kuchen.jpg", "candidates": []}], "pixabay")
    page = (out / "review.html").read_text(encoding="utf-8")
    assert "__DATA__" not in page and "__SOURCE__" not in page
    assert '"bildauswahl-pixabay"' in page
    assert "Kuchen <\\/script>" in page  # a recipe name can't end the script early


def test_main_searches_only_recipes_without_a_credited_photo(tmp_path, out, monkeypatch, database):
    root = tmp_path / "project"
    (root / "static" / "images").mkdir(parents=True)
    shutil.copy(database, root / "recipes.db")
    (root / "static" / "images" / "kuerbissuppe.jpg").write_bytes(b"")  # credited and there
    monkeypatch.setattr(find_images, "ROOT", str(root))
    searched = []
    monkeypatch.setattr(find_images, "find", lambda name: searched.append(name) or [photo("File:A.jpg")])
    monkeypatch.setattr("sys.argv", ["find_images.py"])

    find_images.main()

    assert "Kürbissuppe" not in searched and "Bärlauchsuppe" in searched
    candidates = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert [entry["recipe"] for entry in candidates] == searched
    assert (out / "review.html").exists()
