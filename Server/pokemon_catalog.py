from __future__ import annotations

import sqlite3
from typing import Any


CATALOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS pokemon_types (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS pokemon_species (
    id TEXT PRIMARY KEY,
    national_dex INTEGER UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'pokemon',
    base_hp INTEGER NOT NULL DEFAULT 1,
    base_attack INTEGER NOT NULL DEFAULT 1,
    base_defense INTEGER NOT NULL DEFAULT 1,
    base_sp_attack INTEGER NOT NULL DEFAULT 1,
    base_sp_defense INTEGER NOT NULL DEFAULT 1,
    base_speed INTEGER NOT NULL DEFAULT 1,
    gender_rate INTEGER NOT NULL DEFAULT -1,
    is_fakemon INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pokemon_species_types (
    species_id TEXT NOT NULL,
    type_id TEXT NOT NULL,
    slot INTEGER NOT NULL DEFAULT 1,

    PRIMARY KEY (species_id, type_id),

    FOREIGN KEY (species_id)
        REFERENCES pokemon_species(id)
        ON DELETE CASCADE,

    FOREIGN KEY (type_id)
        REFERENCES pokemon_types(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pokemon_abilities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pokemon_species_abilities (
    species_id TEXT NOT NULL,
    ability_id TEXT NOT NULL,
    slot INTEGER NOT NULL DEFAULT 1,
    is_hidden INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (species_id, ability_id),

    FOREIGN KEY (species_id)
        REFERENCES pokemon_species(id)
        ON DELETE CASCADE,

    FOREIGN KEY (ability_id)
        REFERENCES pokemon_abilities(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pokemon_forms (
    id TEXT PRIMARY KEY,
    species_id TEXT NOT NULL,
    name TEXT NOT NULL,
    form_name TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    is_battle_only INTEGER NOT NULL DEFAULT 0,
    is_mega INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (species_id)
        REFERENCES pokemon_species(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pokemon_forms_species
ON pokemon_forms(species_id);

CREATE TABLE IF NOT EXISTS pokemon_variants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    sprite_suffix TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    is_custom INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS moves (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type_id TEXT,
    category TEXT NOT NULL DEFAULT 'status',
    power INTEGER,
    accuracy INTEGER,
    max_pp INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',

    FOREIGN KEY (type_id)
        REFERENCES pokemon_types(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_moves_type
ON moves(type_id);

CREATE TABLE IF NOT EXISTS pokemon_species_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    species_id TEXT NOT NULL,
    move_id TEXT NOT NULL,
    learn_method TEXT NOT NULL DEFAULT 'level-up',
    learn_level INTEGER NOT NULL DEFAULT 0,
    version_group_id INTEGER,

    FOREIGN KEY (species_id)
        REFERENCES pokemon_species(id)
        ON DELETE CASCADE,

    FOREIGN KEY (move_id)
        REFERENCES moves(id)
        ON DELETE CASCADE,

    UNIQUE (
        species_id,
        move_id,
        learn_method,
        learn_level,
        version_group_id
    )
);

CREATE INDEX IF NOT EXISTS idx_species_moves_species
ON pokemon_species_moves(species_id);

CREATE INDEX IF NOT EXISTS idx_species_moves_move
ON pokemon_species_moves(move_id);

CREATE TABLE IF NOT EXISTS pokemon_evolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_species_id TEXT NOT NULL,
    to_species_id TEXT NOT NULL,
    trigger TEXT NOT NULL DEFAULT '',
    minimum_level INTEGER,
    item_id TEXT,
    gender TEXT,
    time_of_day TEXT,
    minimum_happiness INTEGER,
    minimum_beauty INTEGER,
    minimum_affection INTEGER,
    known_move_id TEXT,
    location TEXT,
    raw_condition TEXT NOT NULL DEFAULT '',

    FOREIGN KEY (from_species_id)
        REFERENCES pokemon_species(id)
        ON DELETE CASCADE,

    FOREIGN KEY (to_species_id)
        REFERENCES pokemon_species(id)
        ON DELETE CASCADE,

    FOREIGN KEY (known_move_id)
        REFERENCES moves(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_pokemon_evolutions_from
ON pokemon_evolutions(from_species_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_evolutions_to
ON pokemon_evolutions(to_species_id);

CREATE TABLE IF NOT EXISTS pokemon_sprite_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    species_id TEXT,
    form_id TEXT,
    variant_id TEXT,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    git_blob_sha1 TEXT,
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    duplicate_group TEXT,

    FOREIGN KEY (species_id)
        REFERENCES pokemon_species(id)
        ON DELETE SET NULL,

    FOREIGN KEY (form_id)
        REFERENCES pokemon_forms(id)
        ON DELETE SET NULL,

    FOREIGN KEY (variant_id)
        REFERENCES pokemon_variants(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sprite_species
ON pokemon_sprite_inventory(species_id);

CREATE INDEX IF NOT EXISTS idx_sprite_filename
ON pokemon_sprite_inventory(filename);

CREATE INDEX IF NOT EXISTS idx_sprite_sha256
ON pokemon_sprite_inventory(file_sha256);

CREATE INDEX IF NOT EXISTS idx_sprite_duplicate_group
ON pokemon_sprite_inventory(duplicate_group);
"""


DEFAULT_VARIANTS = [
    (
        "normal",
        "Normal",
        "",
        "Standard Pokémon coloration.",
        1,
    ),
    (
        "ruby",
        "Ruby",
        "-ruby",
        "Ruby custom coloration.",
        1,
    ),
    (
        "sapphire",
        "Sapphire",
        "-sapphire",
        "Sapphire custom coloration.",
        1,
    ),
    (
        "emerald",
        "Emerald",
        "-emerald",
        "Emerald custom coloration.",
        1,
    ),
    (
        "gold",
        "Gold",
        "-gold",
        "Gold custom coloration.",
        1,
    ),
    (
        "silver",
        "Silver",
        "-silver",
        "Silver custom coloration.",
        1,
    ),
    (
        "undead",
        "Undead",
        "-undead",
        "Undead custom coloration.",
        1,
    ),
]


def ensure_catalog_schema(db: sqlite3.Connection) -> None:
    db.executescript(CATALOG_SCHEMA)

    for (
        variant_id,
        name,
        sprite_suffix,
        description,
        is_custom,
    ) in DEFAULT_VARIANTS:
        db.execute(
            """
            INSERT INTO pokemon_variants
            (
                id,
                name,
                sprite_suffix,
                description,
                is_custom
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET
                name = excluded.name,
                sprite_suffix = excluded.sprite_suffix,
                description = excluded.description,
                is_custom = excluded.is_custom
            """,
            (
                variant_id,
                name,
                sprite_suffix,
                description,
                is_custom,
            ),
        )

    db.commit()


def get_all_variants(
    db: sqlite3.Connection,
) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT
            id,
            name,
            sprite_suffix,
            description,
            is_custom,
            is_active
        FROM pokemon_variants
        WHERE is_active = 1
        ORDER BY
            CASE
                WHEN id = 'normal' THEN 0
                ELSE 1
            END,
            name
        """
    ).fetchall()

    return [dict(row) for row in rows]


def get_variant(
    db: sqlite3.Connection,
    variant_id: str,
) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT *
        FROM pokemon_variants
        WHERE id = ?
        """,
        (variant_id,),
    ).fetchone()

    return dict(row) if row else None


def get_species(
    db: sqlite3.Connection,
    species_id: str,
) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT
            s.*,
            GROUP_CONCAT(DISTINCT t.name) AS types
        FROM pokemon_species s
        LEFT JOIN pokemon_species_types st
            ON st.species_id = s.id
        LEFT JOIN pokemon_types t
            ON t.id = st.type_id
        WHERE
            s.id = ?
            OR LOWER(s.name) = LOWER(?)
        GROUP BY s.id
        """,
        (
            species_id,
            species_id,
        ),
    ).fetchone()

    if row is None:
        return None

    result = dict(row)

    result["types"] = (
        result.get("types", "").split(",")
        if result.get("types")
        else []
    )

    return result


def search_species(
    db: sqlite3.Connection,
    name: str | None = None,
    type_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    parameters: list[Any] = []

    if name:
        conditions.append(
            """
            (
                LOWER(s.name) LIKE LOWER(?)
                OR LOWER(s.id) LIKE LOWER(?)
            )
            """
        )

        search_value = f"%{name.strip()}%"

        parameters.extend(
            [
                search_value,
                search_value,
            ]
        )

    if type_id:
        conditions.append(
            """
            EXISTS (
                SELECT 1
                FROM pokemon_species_types filter_st
                WHERE filter_st.species_id = s.id
                  AND filter_st.type_id = ?
            )
            """
        )

        parameters.append(type_id.lower())

    where_clause = ""

    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    parameters.append(max(1, min(int(limit), 500)))

    rows = db.execute(
        f"""
        SELECT
            s.id,
            s.national_dex,
            s.name,
            s.category,
            s.base_hp,
            s.base_attack,
            s.base_defense,
            s.base_sp_attack,
            s.base_sp_defense,
            s.base_speed,
            GROUP_CONCAT(DISTINCT t.name) AS types
        FROM pokemon_species s
        LEFT JOIN pokemon_species_types st
            ON st.species_id = s.id
        LEFT JOIN pokemon_types t
            ON t.id = st.type_id
        {where_clause}
        GROUP BY s.id
        ORDER BY
            CASE
                WHEN s.national_dex IS NULL THEN 999999
                ELSE s.national_dex
            END,
            s.name
        LIMIT ?
        """,
        parameters,
    ).fetchall()

    result = []

    for row in rows:
        item = dict(row)

        item["types"] = (
            item["types"].split(",")
            if item.get("types")
            else []
        )

        result.append(item)

    return result


def get_species_types(
    db: sqlite3.Connection,
    species_id: str,
) -> list[str]:
    rows = db.execute(
        """
        SELECT t.name
        FROM pokemon_species_types st
        JOIN pokemon_types t
            ON t.id = st.type_id
        WHERE st.species_id = ?
        ORDER BY st.slot
        """,
        (species_id,),
    ).fetchall()

    return [
        str(row["name"])
        for row in rows
    ]


def get_species_moves(
    db: sqlite3.Connection,
    species_id: str,
) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT
            m.id,
            m.name,
            m.type_id,
            m.category,
            m.power,
            m.accuracy,
            m.max_pp,
            sm.learn_method,
            sm.learn_level,
            sm.version_group_id
        FROM pokemon_species_moves sm
        JOIN moves m
            ON m.id = sm.move_id
        WHERE sm.species_id = ?
        ORDER BY
            CASE sm.learn_method
                WHEN 'level-up' THEN 0
                WHEN 'machine' THEN 1
                WHEN 'egg' THEN 2
                WHEN 'tutor' THEN 3
                ELSE 4
            END,
            sm.learn_level,
            m.name
        """,
        (species_id,),
    ).fetchall()

    return [dict(row) for row in rows]


def get_species_evolutions(
    db: sqlite3.Connection,
    species_id: str,
) -> dict[str, list[dict[str, Any]]]:
    outgoing = db.execute(
        """
        SELECT *
        FROM pokemon_evolutions
        WHERE from_species_id = ?
        ORDER BY id
        """,
        (species_id,),
    ).fetchall()

    incoming = db.execute(
        """
        SELECT *
        FROM pokemon_evolutions
        WHERE to_species_id = ?
        ORDER BY id
        """,
        (species_id,),
    ).fetchall()

    return {
        "previous": [dict(row) for row in incoming],
        "next": [dict(row) for row in outgoing],
    }


def get_form(
    db: sqlite3.Connection,
    form_id: str,
) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT *
        FROM pokemon_forms
        WHERE id = ?
        """,
        (form_id,),
    ).fetchone()

    return dict(row) if row else None


def get_species_forms(
    db: sqlite3.Connection,
    species_id: str,
) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT *
        FROM pokemon_forms
        WHERE species_id = ?
        ORDER BY
            is_default DESC,
            sort_order,
            name
        """,
        (species_id,),
    ).fetchall()

    return [dict(row) for row in rows]