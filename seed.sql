PRAGMA foreign_keys = ON;

INSERT INTO recipes (name, preparation_time, instructions, image)
VALUES ('Kürbissuppe', 30, '**Kürbissuppe (4 Portionen)**
1. Kürbis waschen, halbieren, entkernen und in Würfel schneiden. Hokkaido muss nicht geschält werden.
2. Zwiebel, Knoblauch und Ingwer schälen und fein hacken.
3. Olivenöl in einem Topf erhitzen und Zwiebel, Knoblauch und Ingwer darin 3 Minuten andünsten.
4. Kürbiswürfel dazugeben und 2 Minuten mitbraten.
5. Mit der Gemüsebrühe ablöschen und ca. 20 Minuten köcheln lassen, bis der Kürbis weich ist.
6. Kokosmilch hinzufügen und alles fein pürieren.
7. Mit Salz, Pfeffer und Muskatnuss abschmecken.
8. In Schüsseln füllen und mit gerösteten Kürbiskernen garnieren.

Guten Appetit!', 'kuerbissuppe.jpg');

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Zwiebel', 1, 1, 1);

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Hokkaido-Kürbis', 1, 1, 1);

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Knoblauchzehe', 1, 1, 1);

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Ingwer', 1, 1, 1);

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Pfeffer', 1, 1, 1);

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Salz', 1, 1, 1);

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Olivenöl', 1, 1, 1);

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Kokosmilch', 1, 1, 1);

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Muskatnuss', 1, 1, 1);

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Gemüsebrühe', 1, 1, 1);

INSERT INTO ingredients (name, vegan, vegetarian, gluten_free)
VALUES ('Kürbiskerne', 1, 1, 1);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Zwiebel'),
    '1',
    NULL
);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Hokkaido-Kürbis'),
    '1',
    NULL
);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Knoblauchzehe'),
    '2',
    NULL
);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Ingwer'),
    '1',
    'Stück'
);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Olivenöl'),
    '2',
    'EL'
);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Gemüsebrühe'),
    '800',
    'ml'
);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Kokosmilch'),
    '200',
    'ml'
);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Salz'),
    NULL,
    NULL
);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Pfeffer'),
    NULL,
    NULL
);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Muskatnuss'),
    NULL,
    NULL
);

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit)
VALUES (
    (SELECT id FROM recipes WHERE name = 'Kürbissuppe'),
    (SELECT id FROM ingredients WHERE name = 'Kürbiskerne'),
    NULL,
    NULL
);

