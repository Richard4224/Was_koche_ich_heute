"""Tests for tools/fetch_images.py: downloading the chosen photos and writing their credits to images.sql."""

import io
import json
import os
import sqlite3
import time

import pytest

pytest.importorskip("PIL", reason="the photo tools need Pillow (pip install -r tools/requirements.txt)")

from PIL import Image  # noqa: E402

import fetch_images  # noqa: E402
from fetch_images import download, load_credits, photo_info, pixabay_info, quote, save_credits  # noqa: E402

CREDITS = f"SELECT name, {', '.join(fetch_images.FIELDS)} FROM recipes ORDER BY name"


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """The tool pauses between downloads to be polite; the tests don't need to."""
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


@pytest.fixture
def credits_file(tmp_path, monkeypatch):
    """Where save_credits writes, instead of the real images.sql."""
    path = tmp_path / "images.sql"
    monkeypatch.setattr(fetch_images, "CREDITS", str(path))
    return path


def read(path):
    with open(path, encoding="utf-8") as file:
        return file.read()


def image_bytes(width, height):
    data = io.BytesIO()
    Image.new("RGB", (width, height), "orange").save(data, "PNG")
    return data.getvalue()


@pytest.mark.parametrize("value, sql", [(None, "NULL"), ("Anna", "'Anna'"), ("Jack O'Brien", "'Jack O''Brien'")])
def test_quote(value, sql):
    assert quote(value) == sql


def test_images_sql_is_exactly_what_save_credits_writes(credits_file):
    save_credits(load_credits())
    assert read(credits_file) == read(os.path.join(fetch_images.ROOT, "images.sql"))


def test_saved_credits_build_the_same_database(credits_file):
    db = load_credits()
    db.execute("UPDATE recipes SET image_author = 'Jack O''Brien' WHERE name = 'Kürbissuppe'")
    save_credits(db)
    rebuilt = sqlite3.connect(":memory:")
    for path in (os.path.join(fetch_images.ROOT, "schema.sql"), os.path.join(fetch_images.ROOT, "seed.sql"),
                 credits_file):
        rebuilt.executescript(read(path))
    assert rebuilt.execute(CREDITS).fetchall() == db.execute(CREDITS).fetchall()


def test_download_shrinks_big_photos_to_web_size(internet, tmp_path):
    internet.answer("upload.example", image_bytes(2000, 1000))
    download("https://upload.example/big.png", tmp_path / "big.jpg")
    with Image.open(tmp_path / "big.jpg") as saved:
        assert saved.format == "JPEG"
        assert saved.size == (fetch_images.WIDTH, fetch_images.WIDTH // 2)


def test_download_keeps_small_photos_as_they_are(internet, tmp_path):
    internet.answer("upload.example", OSError("timeout"), image_bytes(500, 300))  # and tries again
    download("https://upload.example/small.png", tmp_path / "small.jpg")
    with Image.open(tmp_path / "small.jpg") as saved:
        assert saved.size == (500, 300)


def test_download_gives_up_after_three_tries(internet, tmp_path):
    internet.answer("upload.example", OSError("timeout"))
    with pytest.raises(OSError):
        download("https://upload.example/gone.png", tmp_path / "gone.jpg")
    assert len(internet.requests) == 3


def commons_answer(license_name="CC BY-SA 4.0", thumb="https://upload.example/Apfelkuchen.jpg"):
    return {"query": {"pages": {"1": {"imageinfo": [{
        "thumburl": thumb, "descriptionurl": "https://commons.wikimedia.org/wiki/File:Apfelkuchen.jpg",
        "extmetadata": {"LicenseShortName": {"value": license_name}, "Artist": {"value": "Anna"},
                        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"}},
    }]}}}}


def test_photo_info_from_commons(monkeypatch):
    monkeypatch.setattr(fetch_images, "commons", lambda params: commons_answer())
    assert photo_info("File:Apfelkuchen.jpg") == {
        "url": "https://upload.example/Apfelkuchen.jpg",
        "image_author": "Anna",
        "image_license": "CC BY-SA 4.0",
        "image_license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "image_source": "https://commons.wikimedia.org/wiki/File:Apfelkuchen.jpg",
    }


@pytest.mark.parametrize("answer", [commons_answer(license_name="CC BY-NC 2.0"), commons_answer(thumb=None), {}])
def test_photo_info_of_photos_no_longer_usable(monkeypatch, answer):
    monkeypatch.setattr(fetch_images, "commons", lambda params: answer)
    assert photo_info("File:Apfelkuchen.jpg") is None


def test_pixabay_info(monkeypatch):
    asked = []
    monkeypatch.setattr(fetch_images, "pixabay_key", lambda: "test-key")
    monkeypatch.setattr(fetch_images, "pixabay", lambda params, key: asked.append(params) or {"hits": [{
        "largeImageURL": "https://pixabay.com/get/large.jpg", "user": "Anna",
        "pageURL": "https://pixabay.com/photos/kuchen-123/",
    }]})
    info = pixabay_info("Pixabay 123")
    assert asked == [{"id": "123"}]
    assert info["url"] == "https://pixabay.com/get/large.jpg"
    assert (info["image_author"], info["image_license"]) == ("Anna", "Pixabay-Lizenz")


def test_pixabay_info_of_a_deleted_photo(monkeypatch):
    monkeypatch.setattr(fetch_images, "pixabay_key", lambda: "test-key")
    monkeypatch.setattr(fetch_images, "pixabay", lambda params, key: {"hits": []})
    assert pixabay_info("Pixabay 123") is None


def test_main_downloads_removes_and_skips(tmp_path, credits_file, monkeypatch, capsys):
    images = tmp_path / "images"
    images.mkdir()
    monkeypatch.setattr(fetch_images, "IMAGES", str(images))
    (images / "kuerbissuppe.jpg").write_bytes(b"")
    (images / "baerlauchsuppe.jpg").write_bytes(b"")
    soup_source = load_credits().execute("SELECT image_source FROM recipes WHERE name = 'Kürbissuppe'").fetchone()[0]

    new = {"url": "https://upload.example/Neu.jpg", "image_author": "Anna", "image_license": "CC0",
           "image_license_url": None, "image_source": "https://commons.wikimedia.org/wiki/File:Neu.jpg"}
    monkeypatch.setattr(fetch_images, "photo_info", lambda title: new if title == "File:Neu.jpg" else None)
    downloads = []
    monkeypatch.setattr(fetch_images, "download", lambda url, path: downloads.append(url) or open(path, "wb").close())

    choices = tmp_path / "bildauswahl.json"
    choices.write_text(json.dumps([
        {"recipe": "Kürbissuppe", "photo": {"title": "File:Alt.jpg", "source": soup_source}},  # already there
        {"recipe": "Bärlauchsuppe", "photo": None},  # "Kein Bild"
        {"recipe": "Spargel-Risotto", "photo": {"title": "File:Neu.jpg", "source": new["image_source"]}},
        {"recipe": "Spargelcremesuppe", "photo": {"title": "File:Weg.jpg", "source": "https://example.org/weg"}},
        {"recipe": "Gibt es nicht", "photo": None},
    ]), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["fetch_images.py", str(choices)])

    fetch_images.main()

    assert downloads == ["https://upload.example/Neu.jpg"]
    assert not (images / "baerlauchsuppe.jpg").exists()
    assert (images / "spargel-risotto.jpg").exists()
    saved = read(credits_file)
    assert "image_author = 'Anna'" in saved and "WHERE name = 'Spargel-Risotto';" in saved
    assert "WHERE name = 'Bärlauchsuppe';" not in saved
    assert "WHERE name = 'Kürbissuppe';" in saved
    assert "Fertig: 1 Fotos gespeichert, 1 entfernt, 1 fehlgeschlagen." in capsys.readouterr().out
