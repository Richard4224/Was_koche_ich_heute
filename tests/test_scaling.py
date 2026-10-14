"""Tests for scaling.py: amounts scaled to other servings and written the German way."""

import pytest

from scaling import format_amount, format_duration, format_number, round_amount, scale_text, servings_unit_name


@pytest.mark.parametrize("servings, unit, expected", [
    (1, "Portionen", "Portion"),
    (4, "Portionen", "Portionen"),
    (1, "Springform (26 cm)", "Springform (26 cm)"),
    (2, "Springform (26 cm)", "Springformen (26 cm)"),
    (3, "großes Glas", "große Gläser"),
    (1, "Bleche", "Blech"),
    (300, "g", "g"),  # units it doesn't know stay as they are
])
def test_servings_unit_name(servings, unit, expected):
    assert servings_unit_name(servings, unit) == expected


@pytest.mark.parametrize("value, unit, expected", [
    (123, "g", 125),    # steps of 5 from 50 g
    (122, "g", 120),
    (47.4, "g", 47),    # steps of 1 below
    (2.5, "ml", 3),     # half up, unlike Python's round()
    (0.2, "g", 1),      # never down to nothing
    (1.24, "kg", 1.2),
    (0.3, "EL", 0.25),  # quarters below 1
    (0.4, "EL", 0.5),
    (1.3, "EL", 1.5),   # halves above
    (2.2, None, 2),
    (0.05, None, 0.25),
])
def test_round_amount(value, unit, expected):
    assert round_amount(value, unit) == pytest.approx(expected)


@pytest.mark.parametrize("value, unit, expected", [
    (0.5, "EL", "½"),
    (0.25, "TL", "¼"),
    (1.5, None, "1 ½"),
    (2.75, "Zweig", "2 ¾"),
    (2.0, None, "2"),
    (120.0, "g", "120"),
    (1.2, "kg", "1,2"),
    (0.5, "l", "0,5"),  # litres and kilos get decimals, not fractions
])
def test_format_number(value, unit, expected):
    assert format_number(value, unit) == expected


@pytest.mark.parametrize("value, unit, expected", [
    (250, "g", "250 g"),
    (1200, "g", "1,2 kg"),
    (1000, "ml", "1 l"),
    (1, "Prise", "1 Prise"),
    (2, "Prise", "2 Prisen"),
    (1.5, "Blatt", "1 ½ Blätter"),
    (3, "Zweig", "3 Zweige"),
    (2, "EL", "2 EL"),
    (0.5, None, "½"),
    (1 / 3, None, "¼"),
])
def test_format_amount(value, unit, expected):
    assert format_amount(value, unit) == expected


@pytest.mark.parametrize("text, factor, expected", [
    ("{100 g} Mehl", 2, "200 g Mehl"),
    ("{800 ml} Brühe", 2, "1,6 l Brühe"),
    ("{2-3 EL} Öl", 2, "4–6 EL Öl"),
    ("{1-2 Prise} Salz", 1, "1–2 Prisen Salz"),
    ("{0.5-1 Prise} Salz", 1, "½–1 Prise Salz"),
    ("{4} Eier", 0.5, "2 Eier"),
    ("{0.5 TL} Natron", 1, "½ TL Natron"),
    ("{2} Zwiebeln und {1 EL} Butter", 1.5, "3 Zwiebeln und 1 ½ EL Butter"),
    ("Bei 180 °C 25 Minuten backen.", 3, "Bei 180 °C 25 Minuten backen."),
])
def test_scale_text(text, factor, expected):
    assert scale_text(text, factor) == expected


@pytest.mark.parametrize("minutes, expected", [
    (0, "0 Min."),
    (45, "45 Min."),
    (60, "1 Std."),
    (150, "2 Std. 30 Min."),
    (1440, "1 Tag"),
    (1450, "1 Tag"),  # with days, minutes don't matter any more
    (3 * 1440 + 180, "3 Tage 3 Std."),
])
def test_format_duration(minutes, expected):
    assert format_duration(minutes) == expected
