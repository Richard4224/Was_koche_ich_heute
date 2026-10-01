CREATE TABLE recipes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    preparation_time INTEGER NOT NULL,
    instructions TEXT NOT NULL,
    image TEXT
);

CREATE TABLE ingredients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    vegan INTEGER NOT NULL,
    vegetarian INTEGER NOT NULL,
    gluten_free INTEGER NOT NULL
);

CREATE TABLE recipe_ingredients (
    recipe_id INTEGER NOT NULL,
    ingredient_id INTEGER NOT NULL,
    amount TEXT,
    unit TEXT,
    FOREIGN KEY (recipe_id) REFERENCES recipes(id),
    FOREIGN KEY (ingredient_id) REFERENCES ingredients(id),
    PRIMARY KEY (recipe_id, ingredient_id)
);