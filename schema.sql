CREATE TABLE recipes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    preparation_time INTEGER NOT NULL,                     -- Gesamtzeit in Minuten
    servings INTEGER NOT NULL CHECK (servings > 0),        -- Grundmenge, auf die sich alle amounts beziehen
    servings_unit TEXT NOT NULL DEFAULT 'Portionen',       -- z. B. 'Portionen', 'Stück', 'Springform (26 cm)'
    season TEXT NOT NULL CHECK (season IN ('Frühling', 'Sommer', 'Herbst', 'Winter', 'Ganzjährig')),
    instructions TEXT NOT NULL,
    image TEXT
);

CREATE TABLE ingredients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    vegan INTEGER NOT NULL,
    vegetarian INTEGER NOT NULL,
    gluten_free INTEGER NOT NULL,
    category TEXT NOT NULL DEFAULT 'sonstiges'                -- e.g. 'gewürz', 'gemüse', 'geflügel'; see seed.sql
);

CREATE TABLE recipe_ingredients (
    recipe_id INTEGER NOT NULL,
    ingredient_id INTEGER NOT NULL,
    amount REAL CHECK (amount IS NULL OR amount > 0),      -- Menge für recipes.servings; NULL = nach Geschmack
    unit TEXT,                                             -- g, ml, EL, TL, Prise, Bund, Zweig, Scheibe, ...
    FOREIGN KEY (recipe_id) REFERENCES recipes(id),
    FOREIGN KEY (ingredient_id) REFERENCES ingredients(id),
    PRIMARY KEY (recipe_id, ingredient_id)
);
