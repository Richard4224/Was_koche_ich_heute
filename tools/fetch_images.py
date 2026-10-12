"""Download the photos chosen on the review page and store their credits.

Run:   python tools/fetch_images.py [path/to/bildauswahl.json]

Without a path the file is taken from your Downloads folder. Every chosen photo is saved to static/images/ in web
size, and its author, licence and source go into images.sql (the credits of all photos) and into recipes.db.
"Kein Bild" removes a recipe's photo and credit. Photos that are already in place are skipped, so the script can
simply be run again after an interruption.
"""

import io
import json
import os
import sqlite3
import sys
import time
import urllib.request

from contextlib import closing
from PIL import Image, ImageOps

from find_images import (PIXABAY_LICENSE, ROOT, USER_AGENT, author, commons, free_license, pixabay, pixabay_key,
                         plain)

IMAGES = os.path.join(ROOT, "static", "images")
CREDITS = os.path.join(ROOT, "images.sql")
WIDTH = 960  # wide enough for the recipe page, small enough for a few hundred photos in the repository
FIELDS = ("image_author", "image_license", "image_license_url", "image_source")


def photo_info(title):
    """Download URL and credit of a photo on Commons, or None if it is gone or no longer freely licensed."""
    data = commons({
        "action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1280,
    })
    page = next(iter(data.get("query", {}).get("pages", {}).values()), {})
    info = (page.get("imageinfo") or [{}])[0]
    meta = info.get("extmetadata", {})
    license_name = plain(meta.get("LicenseShortName", {}).get("value", ""))
    if not info.get("thumburl") or not free_license(license_name):
        return None
    return {
        "url": info["thumburl"],
        "image_author": author(meta),
        "image_license": license_name,
        "image_license_url": meta.get("LicenseUrl", {}).get("value") or None,
        "image_source": info["descriptionurl"],
    }


def pixabay_info(title):
    """Download URL and credit of a Pixabay photo, or None if it is gone. Its links expire, so ask anew."""
    hits = pixabay({"id": title.removeprefix("Pixabay ")}, pixabay_key()).get("hits", [])
    if not hits:
        return None
    return {
        "url": hits[0]["largeImageURL"],
        "image_author": hits[0]["user"],
        "image_license": "Pixabay-Lizenz",
        "image_license_url": PIXABAY_LICENSE,
        "image_source": hits[0]["pageURL"],
    }


def download(url, path):
    """Save the photo at url as a web-size JPEG."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                image = Image.open(io.BytesIO(response.read()))
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(5 + attempt * 10)
    image = ImageOps.exif_transpose(image).convert("RGB")
    if image.width > WIDTH:
        image = image.resize((WIDTH, round(image.height * WIDTH / image.width)), Image.LANCZOS)
    image.save(path, "JPEG", quality=75, optimize=True, progressive=True)


def load_credits():
    """The recipes as a fresh build of the database would have them: schema.sql, seed.sql and images.sql."""
    db = sqlite3.connect(":memory:")
    for script in ("schema.sql", "seed.sql", "images.sql"):
        path = os.path.join(ROOT, script)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as file:
                db.executescript(file.read())
    return db


def quote(value):
    return "NULL" if value is None else "'" + value.replace("'", "''") + "'"


def save_credits(db):
    """Write the credits of all photos to images.sql and copy them into recipes.db."""
    rows = db.execute(f"SELECT name, {', '.join(FIELDS)} FROM recipes WHERE image_author IS NOT NULL ORDER BY name")
    lines = [
        "-- Photo credits, written by tools/fetch_images.py. The photos are from Wikimedia Commons and live in",
        "-- static/images/; get_db() runs this file after seed.sql when it builds recipes.db.",
        "",
        "BEGIN TRANSACTION;",
    ]
    for name, *values in rows:
        settings = ", ".join(f"{field} = {quote(value)}" for field, value in zip(FIELDS, values))
        lines.append(f"UPDATE recipes SET {settings} WHERE name = {quote(name)};")
    lines.append("COMMIT;")
    with open(CREDITS, "w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(lines) + "\n")

    database = os.path.join(ROOT, "recipes.db")
    if os.path.exists(database):
        with closing(sqlite3.connect(database)) as live:
            columns = {row[1] for row in live.execute("PRAGMA table_info(recipes)")}
            for field in FIELDS:
                if field not in columns:  # built from an older schema.sql
                    live.execute(f"ALTER TABLE recipes ADD COLUMN {field} TEXT")
            live.execute(f"UPDATE recipes SET {', '.join(field + ' = NULL' for field in FIELDS)}")
            with open(CREDITS, encoding="utf-8") as file:
                live.executescript(file.read())


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "Downloads", "bildauswahl.json")
    with open(path, encoding="utf-8") as file:
        choices = json.load(file)

    db = load_credits()
    saved = removed = failed = 0
    try:
        for number, choice in enumerate(choices, 1):
            name, photo = choice["recipe"], choice["photo"]
            row = db.execute("SELECT image, image_source FROM recipes WHERE name = ?", (name,)).fetchone()
            if not row or not row[0]:
                continue
            file_path = os.path.join(IMAGES, row[0])

            if not photo:
                if os.path.exists(file_path) or row[1]:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    db.execute(f"UPDATE recipes SET {', '.join(field + ' = NULL' for field in FIELDS)} WHERE name = ?",
                               (name,))
                    removed += 1
                    print(f"[{number}/{len(choices)}] {name}: Foto entfernt", flush=True)
                continue

            if row[1] == photo["source"] and os.path.exists(file_path):
                continue  # already there
            info = pixabay_info(photo["title"]) if photo["title"].startswith("Pixabay ") else photo_info(photo["title"])
            if not info:
                failed += 1
                print(f"[{number}/{len(choices)}] {name}: {photo['title']} nicht mehr frei verfügbar", flush=True)
                continue
            try:
                download(info["url"], file_path)
            except OSError as error:
                failed += 1
                print(f"[{number}/{len(choices)}] {name}: Download fehlgeschlagen ({error})", flush=True)
                continue
            db.execute(f"UPDATE recipes SET {', '.join(field + ' = ?' for field in FIELDS)} WHERE name = ?",
                       (*(info[field] for field in FIELDS), name))
            saved += 1
            print(f"[{number}/{len(choices)}] {name}: gespeichert ({info['image_license']})", flush=True)
            time.sleep(0.5)
    finally:
        save_credits(db)  # also after an interruption, so nothing downloaded goes uncredited

    print(f"\nFertig: {saved} Fotos gespeichert, {removed} entfernt, {failed} fehlgeschlagen.")


if __name__ == "__main__":
    main()
