"""Scale recipe amounts to a different number of servings and format them in German."""

import math
import re

# Placeholders in instructions: {100 g}, {2-3 EL} or {4}
PLACEHOLDER = re.compile(r"\{(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?(?: ([^}]+))?\}")

# Ingredient units are stored in the singular
UNIT_PLURALS = {
    "Prise": "Prisen", "Zweig": "Zweige", "Scheibe": "Scheiben", "Stange": "Stangen",
    "Blatt": "Blätter", "Dolde": "Dolden", "Kugel": "Kugeln", "Kapsel": "Kapseln", "Schale": "Schalen",
}

# How recipes.servings_unit reads for one and for several, e.g. "1 Portion", "2 Springformen (26 cm)"
SERVINGS_UNITS = {
    "Portionen": ("Portion", "Portionen"),
    "Stück": ("Stück", "Stück"),
    "Tassen": ("Tasse", "Tassen"),
    "Gläser": ("Glas", "Gläser"),
    "großes Glas": ("großes Glas", "große Gläser"),
    "Pizzen": ("Pizza", "Pizzen"),
    "Blech": ("Blech", "Bleche"),
    "Bleche": ("Blech", "Bleche"),
    "Flaschen (à 0,5 l)": ("Flasche (à 0,5 l)", "Flaschen (à 0,5 l)"),
    "Springform (26 cm)": ("Springform (26 cm)", "Springformen (26 cm)"),
    "Tarteform (26 cm)": ("Tarteform (26 cm)", "Tarteformen (26 cm)"),
    "Quicheform (28 cm)": ("Quicheform (28 cm)", "Quicheformen (28 cm)"),
    "Kastenform": ("Kastenform", "Kastenformen"),
    "Gugelhupfform": ("Gugelhupfform", "Gugelhupfformen"),
    "Zopf": ("Zopf", "Zöpfe"),
    "Stollen": ("Stollen", "Stollen"),
}

FRACTIONS = {0.25: "¼", 0.5: "½", 0.75: "¾"}


def servings_unit_name(servings, unit):
    """Return unit in the right number for servings, e.g. "Portion" for 1 and "Portionen" for 4."""

    singular, plural = SERVINGS_UNITS.get(unit, (unit, unit))
    return singular if servings == 1 else plural


def round_amount(value, unit):
    """Round value to a sensible kitchen step for unit and return it as a number."""

    if unit in ("g", "ml"):
        step = 5 if value >= 50 else 1
    elif unit in ("kg", "l"):
        step = 0.1
    else:  # EL, TL, pieces, ...: quarters for small amounts, halves above
        step = 0.25 if value < 1 else 0.5

    # Round half up (Python's round() would round 2.5 down to 2), but never down to zero
    return max(step, math.floor(value / step + 0.5) * step)


def format_number(value, unit):
    """Format a rounded amount the German way: "1,2", "½", "1 ½"."""

    if unit not in ("g", "ml", "kg", "l"):
        whole, fraction = divmod(value, 1)
        if fraction in FRACTIONS:
            return f"{int(whole)} {FRACTIONS[fraction]}" if whole else FRACTIONS[fraction]
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def format_amount(value, unit):
    """Return e.g. "1,2 kg" for 1200 g, "2 Prisen" for 2 Prise or "½" without a unit."""

    if unit in ("g", "ml") and value >= 1000:
        value, unit = value / 1000, {"g": "kg", "ml": "l"}[unit]

    value = round_amount(value, unit)
    number = format_number(value, unit)
    if not unit:
        return number
    if value > 1:
        unit = UNIT_PLURALS.get(unit, unit)
    return f"{number} {unit}"


def scale_text(text, factor):
    """Replace every placeholder in text with its amount scaled by factor."""

    def replace(match):
        low, high, unit = match.groups()
        if high is None:
            return format_amount(float(low) * factor, unit)

        low = round_amount(float(low) * factor, unit)
        high = round_amount(float(high) * factor, unit)
        amounts = f"{format_number(low, unit)}–{format_number(high, unit)}"
        if not unit:
            return amounts
        return f"{amounts} {UNIT_PLURALS.get(unit, unit) if high > 1 else unit}"

    return PLACEHOLDER.sub(replace, text)


def format_duration(minutes):
    """Return e.g. "45 Min.", "2 Std. 30 Min." or "3 Tage 3 Std."."""

    days, rest = divmod(minutes, 24 * 60)
    hours, minutes = divmod(rest, 60)

    if days:
        parts = [f"{days} {'Tag' if days == 1 else 'Tage'}"]
        if hours:
            parts.append(f"{hours} Std.")
    else:
        parts = [f"{hours} Std."] if hours else []
        if minutes or not hours:
            parts.append(f"{minutes} Min.")
    return " ".join(parts)
