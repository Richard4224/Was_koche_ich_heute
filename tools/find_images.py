"""Find freely licensed photos for the recipes on Wikimedia Commons and build a page to choose them.

Run:   python tools/find_images.py            (all recipes without a photo)
       python tools/find_images.py --all      (all recipes, also those that have one)

Writes tools/images/review.html. Open it in a browser, check the pre-selected photo of every recipe (click
another one or "Kein Bild"), then click "Auswahl speichern" and run tools/fetch_images.py with the saved file.

Only photos usable on this site are offered: public domain, CC0, CC BY and CC BY-SA (credit the author,
share alike), landscape-ish and at least 800 pixels wide.
"""

import html
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tools", "images")
API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA = "https://de.wikipedia.org/w/api.php"
USER_AGENT = "WasKocheIchHeute/1.0 (https://github.com/Richard4224/recipe-search) recipe photo search"
CANDIDATES = 6
IMAGE_INFO = {"prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 360}


def commons(params, api=API):
    """Ask the Wikimedia Commons (or Wikipedia) API, politely (identified, one request at a time)."""
    url = api + "?" + urllib.parse.urlencode({"format": "json", **params})
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.load(response)
            time.sleep(0.3)
            return data
        except OSError:
            time.sleep(2 + attempt * 3)
    return {}


def free_license(name):
    """True for licences this site can use: public domain, CC0, CC BY, CC BY-SA (not NC/ND, not GFDL-only)."""
    name = name.upper()
    if {"NC", "ND"} & set(re.split(r"[ -]+", name)):  # non-commercial or no-derivatives
        return False
    return name.startswith(("CC0", "CC BY", "PUBLIC DOMAIN", "PD")) or name == "CC-ZERO"


def plain(text):
    """Strip HTML from a Commons metadata value."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


def author(meta):
    """The photographer as plain text, or "Unbekannt" if Commons doesn't know."""
    return tidy_author(plain(meta.get("Artist", {}).get("value", "")))


def tidy_author(name):
    """Turn the usual Commons phrasings into a plain name."""
    assumed = re.match(r"No machine-readable author provided\. (.+?) assumed", name)
    if assumed:
        name = assumed.group(1)
    name = re.sub(r"^(File:)?[^:]+\.(jpe?g|png|tiff?)\s*:\s*", "", name, flags=re.I)  # "File:Cake.jpg: Anna"
    name = re.sub(r"\s+derivative work:\s*", ", bearbeitet von ", name)
    name = re.sub(r"\s*\((talk|photographer)\).*$", "", name)  # "Elya (talk) 10:54, 29 August 2021 (UTC)"
    name = re.sub(r"^(©\s*|User:)", "", name).replace("_", " ").strip()
    return "Unbekannt" if not name or "unknown author" in name.lower() else name


def search_terms(name):
    """The recipe name, without and only the part in brackets, and the dish alone ("Lammkeule mit Rosmarin")."""
    bare = re.sub(r"\s*\(.*?\)", "", name).strip()
    dish = re.split(r"\s+(?:mit|in|im|aus|auf|nach|vom|von|an|und)\s+", bare)[0]
    return [term for term in dict.fromkeys([name, bare, *re.findall(r"\((.*?)\)", name), dish]) if term]


def photos(pages):
    """The usable photos among the files of an API answer, in the order the API ranked them."""
    found = []
    for page in sorted(pages.values(), key=lambda page: page.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        license_name = plain(meta.get("LicenseShortName", {}).get("value", ""))
        width, height = info.get("width", 0), info.get("height", 0)
        if (info.get("mime") != "image/jpeg" or not free_license(license_name)
                or width < 800 or height < 450 or not 0.75 <= width / height <= 2.4):
            continue
        found.append({
            "title": page["title"],
            "thumb": info.get("thumburl"),
            "source": info.get("descriptionurl"),
            "author": author(meta),
            "license": license_name,
            "size": f"{width}×{height}",
        })
    return found


def search(term):
    """Photos on Commons whose title or description match term."""
    data = commons({
        "action": "query", "generator": "search", "gsrsearch": f"{term} filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": 12, **IMAGE_INFO,
    })
    return photos(data.get("query", {}).get("pages", {}))


def related(term, title):
    """True if term and an article title share a word, so "Maultasche" fits "Geschmälzte Maultaschen", but
    "Liste Münchner Straßennamen/K" (with a photo of Kafka) doesn't fit "Kerbelsuppe"."""
    words = [[word for word in re.split(r"[\W_]+", text.casefold()) if len(word) >= 4] for text in (term, title)]
    return any(a in b or b in a for a in words[0] for b in words[1])


def wikipedia(terms):
    """The German Wikipedia article that best matches one of terms: its main photo and its English title.

    Most photos on Commons are described in English only, so "Bratapfel" finds little, but its article leads to
    its photo and to "Baked apple".
    """
    for term in terms:
        data = commons({
            "action": "query", "list": "search", "srsearch": term, "srnamespace": 0, "srlimit": 3,
            "srprop": "redirecttitle",
        }, WIKIPEDIA)
        for hit in data.get("query", {}).get("search", []):
            if not (related(term, hit["title"]) or related(term, hit.get("redirecttitle", ""))):
                continue
            data = commons({
                "action": "query", "titles": hit["title"], "prop": "langlinks|pageimages", "lllang": "en",
                "piprop": "name",
            }, WIKIPEDIA)
            page = next(iter(data.get("query", {}).get("pages", {}).values()), {})
            found = []
            if page.get("pageimage"):
                data = commons({"action": "query", "titles": "File:" + page["pageimage"], **IMAGE_INFO})
                found = photos(data.get("query", {}).get("pages", {}))
            return hit["title"], found, (page.get("langlinks") or [{}])[0].get("*")
    return None, [], None


def find(name):
    """Up to CANDIDATES usable photos for a recipe, best first, each with the term it was found by."""
    found, seen = [], set()

    def add(photos, term):
        for photo in photos:
            if photo["title"] not in seen:
                seen.add(photo["title"])
                found.append({**photo, "via": term})
        return len(found) >= CANDIDATES

    terms = search_terms(name)
    if add(search(terms[0]), terms[0]):
        return found[:CANDIDATES]
    article, article_photos, english = wikipedia(dict.fromkeys([terms[0], terms[-1]]))
    if add(article_photos, f"Wikipedia: {article}"):
        return found[:CANDIDATES]
    for term in terms[1:]:
        if add(search(term), term):
            return found[:CANDIDATES]
    if english:
        add(search(f'"{english}"'), english)
    return found[:CANDIDATES]


def main():
    db = sqlite3.connect(os.path.join(ROOT, "recipes.db"))
    rows = db.execute("SELECT name, image FROM recipes ORDER BY name").fetchall()
    if "--all" not in sys.argv:
        rows = [(name, image) for name, image in rows
                if not (image and os.path.isfile(os.path.join(ROOT, "static", "images", image))
                        and db.execute("SELECT image_author FROM recipes WHERE name = ?", (name,)).fetchone()[0])]

    os.makedirs(OUT, exist_ok=True)
    results = []
    for number, (name, image) in enumerate(rows, 1):
        candidates = find(name)
        results.append({"recipe": name, "file": image, "candidates": candidates})
        print(f"[{number}/{len(rows)}] {name}: {len(candidates)} Fotos", flush=True)

    with open(os.path.join(OUT, "candidates.json"), "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=1)
    write_review(results)
    found = sum(1 for result in results if result["candidates"])
    print(f"\nFertig: für {found} von {len(results)} Rezepten Fotos gefunden.")
    print(f"Jetzt im Browser öffnen: {os.path.join(OUT, 'review.html')}")


def write_review(results):
    """The page to choose the photos on, with the search results built in."""
    with open(os.path.join(OUT, "review.html"), "w", encoding="utf-8") as file:
        file.write(REVIEW_PAGE.replace("__DATA__", json.dumps(results, ensure_ascii=False).replace("</", "<\\/")))


REVIEW_PAGE = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>Fotos auswählen</title>
<style>
    body { margin: 0; padding: 1.5rem 2rem 6rem; background: #110f1e; color: #e7e2ef; font: 15px system-ui, sans-serif; }
    h1 { margin: 0 0 0.25rem; font-weight: 600; }
    .hint { margin: 0 0 1.5rem; color: #a8a2c9; }
    .recipe { margin-bottom: 1.25rem; padding: 0.9rem 1rem; border: 1px solid #322c4a; border-radius: 10px; }
    .recipe h2 { margin: 0 0 0.6rem; font-size: 1.05rem; }
    .recipe.none h2::after { content: " · kein Bild"; color: #e88aa8; font-weight: 400; }
    .options { display: flex; gap: 0.6rem; overflow-x: auto; padding-bottom: 0.25rem; }
    .option { flex: none; width: 200px; padding: 0; border: 3px solid transparent; border-radius: 8px; background: #1c1930;
              color: inherit; text-align: left; cursor: pointer; }
    .option img { display: block; width: 100%; height: 130px; object-fit: cover; border-radius: 5px 5px 0 0; }
    .option span { display: block; padding: 0.35rem 0.5rem; font-size: 0.75rem; color: #a8a2c9; overflow-wrap: anywhere; }
    .option.chosen { border-color: #ffb547; }
    .option.skip { display: grid; place-items: center; height: 186px; color: #e88aa8; text-align: center; }
    .bar { position: fixed; inset: auto 0 0 0; display: flex; gap: 1rem; align-items: center; padding: 0.9rem 2rem;
           background: #1c1930; border-top: 1px solid #322c4a; }
    .bar button { padding: 0.6rem 1.4rem; border: 0; border-radius: 999px; background: #ffb547; color: #2a1405;
                  font-weight: 600; cursor: pointer; }
</style></head><body>
<h1>Fotos auswählen</h1>
<p class="hint">Bei jedem Rezept ist das erste Foto schon gewählt. Klick ein anderes an, wenn es besser passt, oder
"Kein Bild", wenn keins passt. Ein Klick auf das Foto mit gedrückter Strg-Taste öffnet es auf Commons.
Deine Auswahl bleibt auch nach dem Neuladen erhalten.</p>
<div id="list"></div>
<div class="bar"><button id="save">Auswahl speichern</button><span id="status"></span></div>
<script>
    const data = __DATA__;
    let saved = {};  // choices made before a reload or a new search
    try { saved = JSON.parse(localStorage.getItem("bildauswahl")) || {}; } catch {}
    const choice = {};
    const list = document.getElementById("list");
    const status = document.getElementById("status");

    function update() {
        const chosen = Object.values(choice).filter(Boolean).length;
        status.textContent = `${chosen} Rezepte mit Foto, ${data.length - chosen} ohne`;
        try { localStorage.setItem("bildauswahl", JSON.stringify({ ...saved, ...choice })); } catch {}
    }

    for (const entry of data) {
        const titles = entry.candidates.map((photo) => photo.title);
        const before = saved[entry.recipe];
        choice[entry.recipe] = before === null || titles.includes(before) ? before : (titles[0] ?? null);
        const block = document.createElement("section");
        block.className = "recipe";
        block.innerHTML = `<h2></h2><div class="options"></div>`;
        block.querySelector("h2").textContent = entry.recipe;
        const options = block.querySelector(".options");

        const buttons = [];
        for (const photo of entry.candidates) {
            const button = document.createElement("button");
            button.className = "option";
            button.innerHTML = `<img loading="lazy" alt=""><span></span>`;
            button.querySelector("img").src = photo.thumb;
            button.querySelector("span").textContent = `${photo.license} · ${photo.author} · ${photo.size}`
                + (photo.via !== entry.recipe ? ` · über „${photo.via}“` : "");
            button.title = photo.title;
            button.onclick = (event) => {
                if (event.ctrlKey || event.metaKey) { window.open(photo.source); return; }
                choice[entry.recipe] = photo.title;
                show();
            };
            buttons.push([button, photo.title]);
            options.append(button);
        }
        const skip = document.createElement("button");
        skip.className = "option skip";
        skip.textContent = "Kein Bild";
        skip.onclick = () => { choice[entry.recipe] = null; show(); };
        buttons.push([skip, null]);
        options.append(skip);

        function show() {
            for (const [button, title] of buttons) button.classList.toggle("chosen", choice[entry.recipe] === title);
            block.classList.toggle("none", !choice[entry.recipe]);
            update();
        }
        show();
        list.append(block);
    }

    document.getElementById("save").onclick = () => {
        const chosen = data.map((entry) => {
            const photo = entry.candidates.find((candidate) => candidate.title === choice[entry.recipe]);
            return { recipe: entry.recipe, file: entry.file, photo: photo || null };
        });
        const blob = new Blob([JSON.stringify(chosen, null, 1)], { type: "application/json" });
        const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "bildauswahl.json" });
        link.click();
        status.textContent = "Gespeichert als bildauswahl.json (in deinem Download-Ordner)";
    };
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
