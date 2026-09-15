from __future__ import annotations

import sqlite3
from typing import Any


# =============================================================================
# KRAMPUS RPG POKÉMON CATALOG
# =============================================================================
#
# IMPORTANT ARCHITECTURE
#
# Pokémon data is deliberately divided into four separate concepts:
#
#   1. SPECIES
#      Example: charizard
#
#   2. OFFICIAL FORM
#      Example: charizard-mega-x
#
#   3. KRAMPUS VARIANT
#      Example: ruby / sapphire / emerald / undead
#
#   4. SHINY
#      Boolean property of an individual Pokémon
#
# These must never be collapsed into one field.
#
# Example:
#
#   Charizard
#       species = charizard
#       form = mega-x
#       variant = ruby
#       shiny = true
#
# Player-owned Pokémon additionally have:
#
#   owner_id
#   level
#   experience
#   gender
#   nickname
#   HP
#   etc.
#
# IVs, EVs, Nature and permanent Status are intentionally NOT part of this
# architecture.
# =============================================================================


OFFICIAL_NATIONAL_DEX_LIMIT = 1025


# =============================================================================
# DEFAULT KRAMPUS VARIANTS
# =============================================================================

DEFAULT_VARIANTS: list[tuple[str, str, str, str, int]] = [
    (
        "normal",
        "Normal",
        "",
        "The standard Pokémon coloration.",
        1,
    ),
    (
        "ruby",
        "Ruby",
        "-ruby",
        "A custom ruby-colored Krampus RPG variant.",
        1,
    ),
    (
        "sapphire",
        "Sapphire",
        "-sapphire",
        "A custom sapphire-colored Krampus RPG variant.",
        1,
    ),
    (
        "emerald",
        "Emerald",
        "-emerald",
        "A custom emerald-colored Krampus RPG variant.",
        1,
    ),
    (
        "gold",
        "Gold",
        "-gold",
        "A custom gold-colored Krampus RPG variant.",
        1,
    ),
    (
        "silver",
        "Silver",
        "-silver",
        "A custom silver-colored Krampus RPG variant.",
        1,
    ),
    (
        "undead",
        "Undead",
        "-undead",
        "A custom undead Krampus RPG variant.",
        1,
    ),
]


# =============================================================================
# CATALOG SCHEMA
# =============================================================================
#
# The schema is intentionally compatible with the current Krampus RPG
# architecture while incorporating the useful parts of the Claude catalog
# foundation.
#
# The importer is responsible for populating the tables.
# This module is responsible for:
#
#   - schema creation
#   - schema migration
#   - catalog queries
#   - variant queries
#   - form queries
#   - sprite resolution
# =============================================================================

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

    generation INTEGER NOT NULL DEFAULT 0,

    description TEXT NOT NULL DEFAULT '',

    base_hp INTEGER NOT NULL DEFAULT 1,
    base_attack INTEGER NOT NULL DEFAULT 1,
    base_defense INTEGER NOT NULL DEFAULT 1,
    base_sp_attack INTEGER NOT NULL DEFAULT 1,
    base_sp_defense INTEGER NOT NULL DEFAULT 1,
    base_speed INTEGER NOT NULL DEFAULT 1,

    gender_rate INTEGER NOT NULL DEFAULT -1,

    is_fakemon INTEGER NOT NULL DEFAULT 0,

    is_active INTEGER NOT NULL DEFAULT 1,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pokemon_species_national_dex
ON pokemon_species(national_dex);

CREATE INDEX IF NOT EXISTS idx_pokemon_species_name
ON pokemon_species(name);

CREATE INDEX IF NOT EXISTS idx_pokemon_species_fakemon
ON pokemon_species(is_fakemon);


CREATE TABLE IF NOT EXISTS pokemon_species_types (
    species_id TEXT NOT NULL,

    type_id TEXT NOT NULL,

    slot INTEGER NOT NULL DEFAULT 1,

    PRIMARY KEY (species_id, slot),

    FOREIGN KEY (species_id)
        REFERENCES pokemon_species(id)
        ON DELETE CASCADE,

    FOREIGN KEY (type_id)
        REFERENCES pokemon_types(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_species_types_species
ON pokemon_species_types(species_id);

CREATE INDEX IF NOT EXISTS idx_species_types_type
ON pokemon_species_types(type_id);


CREATE TABLE IF NOT EXISTS pokemon_abilities (
    id TEXT PRIMARY KEY,

    name TEXT NOT NULL UNIQUE,

    description TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_pokemon_abilities_name
ON pokemon_abilities(name);


CREATE TABLE IF NOT EXISTS pokemon_species_abilities (
    species_id TEXT NOT NULL,

    ability_id TEXT NOT NULL,

    slot INTEGER NOT NULL DEFAULT 1,

    is_hidden INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (species_id, slot),

    FOREIGN KEY (species_id)
        REFERENCES pokemon_species(id)
        ON DELETE CASCADE,

    FOREIGN KEY (ability_id)
        REFERENCES pokemon_abilities(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_species_abilities_species
ON pokemon_species_abilities(species_id);

CREATE INDEX IF NOT EXISTS idx_species_abilities_ability
ON pokemon_species_abilities(ability_id);


CREATE TABLE IF NOT EXISTS pokemon_forms (
    id TEXT PRIMARY KEY,

    species_id TEXT NOT NULL,

    name TEXT NOT NULL,

    form_name TEXT NOT NULL DEFAULT '',

    display_name TEXT NOT NULL DEFAULT '',

    form_identifier TEXT NOT NULL DEFAULT '',

    is_default INTEGER NOT NULL DEFAULT 0,

    is_battle_only INTEGER NOT NULL DEFAULT 0,

    is_mega INTEGER NOT NULL DEFAULT 0,

    is_gmax INTEGER NOT NULL DEFAULT 0,

    sort_order INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (species_id)
        REFERENCES pokemon_species(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pokemon_forms_species
ON pokemon_forms(species_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_forms_identifier
ON pokemon_forms(form_identifier);

CREATE INDEX IF NOT EXISTS idx_pokemon_forms_default
ON pokemon_forms(species_id, is_default);


CREATE TABLE IF NOT EXISTS pokemon_variants (
    id TEXT PRIMARY KEY,

    name TEXT NOT NULL UNIQUE,

    sprite_suffix TEXT NOT NULL DEFAULT '',

    description TEXT NOT NULL DEFAULT '',

    is_custom INTEGER NOT NULL DEFAULT 1,

    is_active INTEGER NOT NULL DEFAULT 1,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pokemon_variants_active
ON pokemon_variants(is_active);


CREATE TABLE IF NOT EXISTS moves (
    id TEXT PRIMARY KEY,

    name TEXT NOT NULL UNIQUE,

    type_id TEXT,

    category TEXT NOT NULL DEFAULT 'status',

    power INTEGER,

    accuracy INTEGER,

    max_pp INTEGER NOT NULL DEFAULT 0,

    description TEXT NOT NULL DEFAULT '',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (type_id)
        REFERENCES pokemon_types(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_moves_type
ON moves(type_id);

CREATE INDEX IF NOT EXISTS idx_moves_name
ON moves(name);


CREATE TABLE IF NOT EXISTS pokemon_species_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    species_id TEXT NOT NULL,

    move_id TEXT NOT NULL,

    learn_method TEXT NOT NULL DEFAULT 'unknown',

    learn_level INTEGER NOT NULL DEFAULT 0,

    version_group_id INTEGER NOT NULL DEFAULT 0,

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

    known_move_type TEXT,

    location TEXT,

    relative_physical_stats INTEGER,

    trade_species_id TEXT,

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

    relative_path TEXT NOT NULL UNIQUE,

    file_sha256 TEXT NOT NULL,

    git_blob_sha1 TEXT,

    is_duplicate INTEGER NOT NULL DEFAULT 0,

    duplicate_group TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

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

CREATE INDEX IF NOT EXISTS idx_sprite_form
ON pokemon_sprite_inventory(form_id);

CREATE INDEX IF NOT EXISTS idx_sprite_variant
ON pokemon_sprite_inventory(variant_id);

CREATE INDEX IF NOT EXISTS idx_sprite_filename
ON pokemon_sprite_inventory(filename);

CREATE INDEX IF NOT EXISTS idx_sprite_sha256
ON pokemon_sprite_inventory(file_sha256);

CREATE INDEX IF NOT EXISTS idx_sprite_git_sha1
ON pokemon_sprite_inventory(git_blob_sha1);

CREATE INDEX IF NOT EXISTS idx_sprite_duplicate_group
ON pokemon_sprite_inventory(duplicate_group);
"""


# =============================================================================
# SQLITE MIGRATION HELPERS
# =============================================================================

def _table_exists(
    db: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = db.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def _column_exists(
    db: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    if not _table_exists(db, table_name):
        return False

    rows = db.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        str(row["name"]) == column_name
        for row in rows
    )


def _add_column_if_missing(
    db: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    if _column_exists(
        db,
        table_name,
        column_name,
    ):
        return

    db.execute(
        f"""
        ALTER TABLE {table_name}
        ADD COLUMN {column_name} {definition}
        """
    )


# =============================================================================
# CATALOG MIGRATION
# =============================================================================

def migrate_catalog_schema(
    db: sqlite3.Connection,
) -> None:
    """
    Upgrade older catalog databases without deleting catalog data.

    CREATE TABLE IF NOT EXISTS alone is not enough when an existing table
    predates newer catalog columns, so the important columns are reconciled
    here explicitly.
    """

    # -------------------------------------------------------------------------
    # pokemon_species
    # -------------------------------------------------------------------------

    if _table_exists(db, "pokemon_species"):
        _add_column_if_missing(
            db,
            "pokemon_species",
            "category",
            "TEXT NOT NULL DEFAULT 'pokemon'",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "generation",
            "INTEGER NOT NULL DEFAULT 0",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "description",
            "TEXT NOT NULL DEFAULT ''",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "base_hp",
            "INTEGER NOT NULL DEFAULT 1",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "base_attack",
            "INTEGER NOT NULL DEFAULT 1",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "base_defense",
            "INTEGER NOT NULL DEFAULT 1",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "base_sp_attack",
            "INTEGER NOT NULL DEFAULT 1",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "base_sp_defense",
            "INTEGER NOT NULL DEFAULT 1",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "base_speed",
            "INTEGER NOT NULL DEFAULT 1",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "gender_rate",
            "INTEGER NOT NULL DEFAULT -1",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "is_fakemon",
            "INTEGER NOT NULL DEFAULT 0",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "is_active",
            "INTEGER NOT NULL DEFAULT 1",
        )

        _add_column_if_missing(
            db,
            "pokemon_species",
            "created_at",
            "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        )

    # -------------------------------------------------------------------------
    # pokemon_forms
    # -------------------------------------------------------------------------

    if _table_exists(db, "pokemon_forms"):
        _add_column_if_missing(
            db,
            "pokemon_forms",
            "name",
            "TEXT NOT NULL DEFAULT ''",
        )

        _add_column_if_missing(
            db,
            "pokemon_forms",
            "form_name",
            "TEXT NOT NULL DEFAULT ''",
        )

        _add_column_if_missing(
            db,
            "pokemon_forms",
            "display_name",
            "TEXT NOT NULL DEFAULT ''",
        )

        _add_column_if_missing(
            db,
            "pokemon_forms",
            "form_identifier",
            "TEXT NOT NULL DEFAULT ''",
        )

        _add_column_if_missing(
            db,
            "pokemon_forms",
            "is_default",
            "INTEGER NOT NULL DEFAULT 0",
        )

        _add_column_if_missing(
            db,
            "pokemon_forms",
            "is_battle_only",
            "INTEGER NOT NULL DEFAULT 0",
        )

        _add_column_if_missing(
            db,
            "pokemon_forms",
            "is_mega",
            "INTEGER NOT NULL DEFAULT 0",
        )

        _add_column_if_missing(
            db,
            "pokemon_forms",
            "is_gmax",
            "INTEGER NOT NULL DEFAULT 0",
        )

        _add_column_if_missing(
            db,
            "pokemon_forms",
            "sort_order",
            "INTEGER NOT NULL DEFAULT 0",
        )

        _add_column_if_missing(
            db,
            "pokemon_forms",
            "created_at",
            "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        )

    # -------------------------------------------------------------------------
    # pokemon_variants
    # -------------------------------------------------------------------------

    if _table_exists(db, "pokemon_variants"):
        _add_column_if_missing(
            db,
            "pokemon_variants",
            "is_active",
            "INTEGER NOT NULL DEFAULT 1",
        )

        _add_column_if_missing(
            db,
            "pokemon_variants",
            "created_at",
            "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        )

    # -------------------------------------------------------------------------
    # moves
    # -------------------------------------------------------------------------

    if _table_exists(db, "moves"):
        _add_column_if_missing(
            db,
            "moves",
            "description",
            "TEXT NOT NULL DEFAULT ''",
        )

        _add_column_if_missing(
            db,
            "moves",
            "created_at",
            "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        )

    # -------------------------------------------------------------------------
    # pokemon_evolutions
    # -------------------------------------------------------------------------

    if _table_exists(db, "pokemon_evolutions"):
        _add_column_if_missing(
            db,
            "pokemon_evolutions",
            "known_move_type",
            "TEXT",
        )

        _add_column_if_missing(
            db,
            "pokemon_evolutions",
            "relative_physical_stats",
            "INTEGER",
        )

        _add_column_if_missing(
            db,
            "pokemon_evolutions",
            "trade_species_id",
            "TEXT",
        )

    # -------------------------------------------------------------------------
    # sprite inventory
    # -------------------------------------------------------------------------

    if _table_exists(
        db,
        "pokemon_sprite_inventory",
    ):
        _add_column_if_missing(
            db,
            "pokemon_sprite_inventory",
            "created_at",
            "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        )

    # -------------------------------------------------------------------------
    # OWNED POKÉMON
    # -------------------------------------------------------------------------
    #
    # This is the important player-Pokémon migration.
    #
    # Existing owned Pokémon retain their species and all other data.
    # Their form is assigned to the default form later by the catalog
    # synchronization process.
    #
    # SQLite allows adding this column without rebuilding the entire pokemon
    # table. A future full database migration can add the formal FK constraint
    # if desired.
    # -------------------------------------------------------------------------

    if _table_exists(
        db,
        "pokemon",
    ):
        _add_column_if_missing(
            db,
            "pokemon",
            "form_id",
            "TEXT",
        )

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pokemon_form
            ON pokemon(form_id)
            """
        )

    db.commit()


# =============================================================================
# SCHEMA INITIALIZATION
# =============================================================================

def ensure_catalog_schema(
    db: sqlite3.Connection,
) -> None:
    """
    Create or upgrade the complete Pokémon catalog.

    This function is safe to call during application startup.
    """

    db.execute(
        "PRAGMA foreign_keys = ON"
    )

    db.executescript(
        CATALOG_SCHEMA
    )

    migrate_catalog_schema(
        db
    )

    ensure_default_variants(
        db
    )

    ensure_fakemon_category(
        db
    )


# =============================================================================
# DEFAULT VARIANTS
# =============================================================================

def ensure_default_variants(
    db: sqlite3.Connection,
) -> None:
    for (
        variant_id,
        name,
        sprite_suffix,
        description,
        is_custom,
    ) in DEFAULT_VARIANTS:

        db.execute(
            """
            INSERT INTO pokemon_variants (
                id,
                name,
                sprite_suffix,
                description,
                is_custom,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, 1)

            ON CONFLICT(id)
            DO UPDATE SET
                name = excluded.name,
                sprite_suffix = excluded.sprite_suffix,
                description = excluded.description,
                is_custom = excluded.is_custom,
                is_active = 1
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


# =============================================================================
# FAKEMON CATEGORY
# =============================================================================

def ensure_fakemon_category(
    db: sqlite3.Connection,
) -> None:
    """
    Reserve a category marker for future fan-made Pokémon.

    Official species continue to use real National Dex numbers.
    Fakemon are not forced into the official National Dex.
    """

    db.execute(
        """
        INSERT OR IGNORE INTO pokemon_species (
            id,
            national_dex,
            name,
            category,
            generation,
            description,
            is_fakemon,
            is_active
        )
        VALUES (
            'fakemon',
            NULL,
            'Fakemon',
            'fakemon',
            0,
            'Fan-made Pokémon category for future Krampus RPG content.',
            1,
            1
        )
        """
    )

    db.commit()


# =============================================================================
# VARIANTS
# =============================================================================

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
            is_active,
            created_at
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

    return [
        dict(row)
        for row in rows
    ]


def get_variant(
    db: sqlite3.Connection,
    variant_id: str,
) -> dict[str, Any] | None:
    if not variant_id:
        return None

    row = db.execute(
        """
        SELECT *
        FROM pokemon_variants
        WHERE id = ?
          AND is_active = 1
        """,
        (
            variant_id.strip().lower(),
        ),
    ).fetchone()

    return (
        dict(row)
        if row
        else None
    )


# =============================================================================
# SPECIES
# =============================================================================

def get_species(
    db: sqlite3.Connection,
    species_id: str,
) -> dict[str, Any] | None:
    if not species_id:
        return None

    value = species_id.strip().lower()

    row = db.execute(
        """
        SELECT
            s.*,
            GROUP_CONCAT(
                DISTINCT t.name
            ) AS types
        FROM pokemon_species s

        LEFT JOIN pokemon_species_types st
            ON st.species_id = s.id

        LEFT JOIN pokemon_types t
            ON t.id = st.type_id

        WHERE
            s.id = ?
            OR LOWER(s.name) = LOWER(?)

        GROUP BY s.id

        LIMIT 1
        """,
        (
            value,
            value,
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


def get_species_by_dex(
    db: sqlite3.Connection,
    national_dex: int,
) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT
            s.*,
            GROUP_CONCAT(
                DISTINCT t.name
            ) AS types
        FROM pokemon_species s

        LEFT JOIN pokemon_species_types st
            ON st.species_id = s.id

        LEFT JOIN pokemon_types t
            ON t.id = st.type_id

        WHERE s.national_dex = ?

        GROUP BY s.id

        LIMIT 1
        """,
        (
            int(national_dex),
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
    is_fakemon: bool | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    parameters: list[Any] = []

    if name:
        search_value = (
            f"%{name.strip()}%"
        )

        conditions.append(
            """
            (
                LOWER(s.name) LIKE LOWER(?)
                OR LOWER(s.id) LIKE LOWER(?)
                OR CAST(
                    s.national_dex AS TEXT
                ) LIKE ?
            )
            """
        )

        parameters.extend(
            [
                search_value,
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
                WHERE
                    filter_st.species_id = s.id
                    AND LOWER(
                        filter_st.type_id
                    ) = LOWER(?)
            )
            """
        )

        parameters.append(
            type_id.strip()
        )

    if is_fakemon is not None:
        conditions.append(
            "s.is_fakemon = ?"
        )

        parameters.append(
            1 if is_fakemon else 0
        )

    conditions.append(
        "s.is_active = 1"
    )

    where_clause = (
        "WHERE "
        + " AND ".join(conditions)
    )

    safe_limit = max(
        1,
        min(
            int(limit),
            500,
        ),
    )

    parameters.append(
        safe_limit
    )

    rows = db.execute(
        f"""
        SELECT
            s.id,
            s.national_dex,
            s.name,
            s.category,
            s.generation,
            s.description,
            s.base_hp,
            s.base_attack,
            s.base_defense,
            s.base_sp_attack,
            s.base_sp_defense,
            s.base_speed,
            s.gender_rate,
            s.is_fakemon,
            GROUP_CONCAT(
                DISTINCT t.name
            ) AS types

        FROM pokemon_species s

        LEFT JOIN pokemon_species_types st
            ON st.species_id = s.id

        LEFT JOIN pokemon_types t
            ON t.id = st.type_id

        {where_clause}

        GROUP BY s.id

        ORDER BY
            CASE
                WHEN s.national_dex IS NULL
                    THEN 999999
                ELSE s.national_dex
            END,
            s.name

        LIMIT ?
        """,
        parameters,
    ).fetchall()

    result: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)

        item["types"] = (
            item["types"].split(",")
            if item.get("types")
            else []
        )

        result.append(
            item
        )

    return result


def count_species(
    db: sqlite3.Connection,
    official_only: bool = False,
) -> int:
    if official_only:
        row = db.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_species
            WHERE is_fakemon = 0
              AND national_dex BETWEEN 1 AND ?
            """,
            (
                OFFICIAL_NATIONAL_DEX_LIMIT,
            ),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_species
            WHERE is_active = 1
            """
        ).fetchone()

    return int(
        row[0]
        if row
        else 0
    )


# =============================================================================
# TYPES
# =============================================================================

def get_species_types(
    db: sqlite3.Connection,
    species_id: str,
) -> list[str]:
    rows = db.execute(
        """
        SELECT
            t.name
        FROM pokemon_species_types st

        JOIN pokemon_types t
            ON t.id = st.type_id

        WHERE st.species_id = ?

        ORDER BY st.slot
        """,
        (
            species_id,
        ),
    ).fetchall()

    return [
        str(row["name"])
        for row in rows
    ]


# =============================================================================
# ABILITIES
# =============================================================================

def get_species_abilities(
    db: sqlite3.Connection,
    species_id: str,
) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT
            a.id,
            a.name,
            a.description,
            sa.slot,
            sa.is_hidden

        FROM pokemon_species_abilities sa

        JOIN pokemon_abilities a
            ON a.id = sa.ability_id

        WHERE sa.species_id = ?

        ORDER BY
            sa.slot
        """,
        (
            species_id,
        ),
    ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# =============================================================================
# MOVES / LEARNSETS
# =============================================================================

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
            m.description,

            sm.learn_method,
            sm.learn_level,
            sm.version_group_id

        FROM pokemon_species_moves sm

        JOIN moves m
            ON m.id = sm.move_id

        WHERE sm.species_id = ?

        ORDER BY
            CASE
                WHEN sm.learn_method = 'level-up'
                    THEN 0
                WHEN sm.learn_method = 'machine'
                    THEN 1
                WHEN sm.learn_method = 'egg'
                    THEN 2
                WHEN sm.learn_method = 'tutor'
                    THEN 3
                ELSE 4
            END,

            sm.learn_level,

            m.name
        """,
        (
            species_id,
        ),
    ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_level_up_moves(
    db: sqlite3.Connection,
    species_id: str,
    level: int,
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
            m.description,

            sm.learn_level

        FROM pokemon_species_moves sm

        JOIN moves m
            ON m.id = sm.move_id

        WHERE
            sm.species_id = ?
            AND sm.learn_method = 'level-up'
            AND sm.learn_level <= ?

        ORDER BY
            sm.learn_level,
            m.name
        """,
        (
            species_id,
            int(level),
        ),
    ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# =============================================================================
# EVOLUTION
# =============================================================================

def get_species_evolutions(
    db: sqlite3.Connection,
    species_id: str,
) -> dict[str, list[dict[str, Any]]]:
    outgoing = db.execute(
        """
        SELECT
            e.*,

            s.name AS to_species_name

        FROM pokemon_evolutions e

        JOIN pokemon_species s
            ON s.id = e.to_species_id

        WHERE e.from_species_id = ?

        ORDER BY e.id
        """,
        (
            species_id,
        ),
    ).fetchall()

    incoming = db.execute(
        """
        SELECT
            e.*,

            s.name AS from_species_name

        FROM pokemon_evolutions e

        JOIN pokemon_species s
            ON s.id = e.from_species_id

        WHERE e.to_species_id = ?

        ORDER BY e.id
        """,
        (
            species_id,
        ),
    ).fetchall()

    return {
        "previous": [
            dict(row)
            for row in incoming
        ],
        "next": [
            dict(row)
            for row in outgoing
        ],
    }


# =============================================================================
# OFFICIAL FORMS
# =============================================================================

def get_form(
    db: sqlite3.Connection,
    form_id: str,
) -> dict[str, Any] | None:
    if not form_id:
        return None

    row = db.execute(
        """
        SELECT *
        FROM pokemon_forms
        WHERE id = ?
        LIMIT 1
        """,
        (
            form_id.strip().lower(),
        ),
    ).fetchone()

    return (
        dict(row)
        if row
        else None
    )


def get_default_form(
    db: sqlite3.Connection,
    species_id: str,
) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT *
        FROM pokemon_forms

        WHERE
            species_id = ?
            AND is_default = 1

        ORDER BY
            sort_order,
            id

        LIMIT 1
        """,
        (
            species_id,
        ),
    ).fetchone()

    if row:
        return dict(row)

    # Older/imported data may not have marked a form as default.
    row = db.execute(
        """
        SELECT *
        FROM pokemon_forms

        WHERE species_id = ?

        ORDER BY
            sort_order,
            id

        LIMIT 1
        """,
        (
            species_id,
        ),
    ).fetchone()

    return (
        dict(row)
        if row
        else None
    )


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
            name,
            id
        """,
        (
            species_id,
        ),
    ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def set_default_forms_for_owned_pokemon(
    db: sqlite3.Connection,
) -> int:
    """
    Assign the default catalog form to existing owned Pokémon that currently
    have no form_id.

    This does NOT change species, variant, shiny, level, Party or PC location.
    """

    if not _table_exists(
        db,
        "pokemon",
    ):
        return 0

    if not _column_exists(
        db,
        "pokemon",
        "form_id",
    ):
        return 0

    rows = db.execute(
        """
        SELECT
            p.id,
            p.species_id

        FROM pokemon p

        WHERE p.form_id IS NULL
           OR TRIM(p.form_id) = ''
        """
    ).fetchall()

    updated = 0

    for row in rows:
        form = get_default_form(
            db,
            str(row["species_id"]),
        )

        if not form:
            continue

        db.execute(
            """
            UPDATE pokemon
            SET form_id = ?
            WHERE id = ?
            """,
            (
                form["id"],
                row["id"],
            ),
        )

        updated += 1

    db.commit()

    return updated


# =============================================================================
# SPRITE RESOLUTION
# =============================================================================

def find_sprite(
    db: sqlite3.Connection,
    species_id: str,
    form_id: str | None = None,
    variant_id: str = "normal",
    shiny: bool = False,
) -> dict[str, Any] | None:
    """
    Resolve a sprite from:

        species
        + official form
        + Krampus variant
        + shiny

    Shiny is currently matched by filename convention when available.
    The inventory remains flexible enough for future explicit shiny metadata.
    """

    if not species_id:
        return None

    variant = get_variant(
        db,
        variant_id or "normal",
    )

    variant_id_value = (
        variant["id"]
        if variant
        else "normal"
    )

    # -------------------------------------------------------------------------
    # First attempt:
    # exact species + form + variant
    # -------------------------------------------------------------------------

    if form_id:
        row = db.execute(
            """
            SELECT *
            FROM pokemon_sprite_inventory

            WHERE
                species_id = ?
                AND form_id = ?
                AND variant_id = ?

            ORDER BY
                is_duplicate ASC,
                id ASC

            LIMIT 1
            """,
            (
                species_id,
                form_id,
                variant_id_value,
            ),
        ).fetchone()

        if row:
            return dict(row)

    # -------------------------------------------------------------------------
    # Second attempt:
    # species + variant without explicit form
    # -------------------------------------------------------------------------

    row = db.execute(
        """
        SELECT *
        FROM pokemon_sprite_inventory

        WHERE
            species_id = ?
            AND variant_id = ?
            AND form_id IS NULL

        ORDER BY
            is_duplicate ASC,
            id ASC

        LIMIT 1
        """,
        (
            species_id,
            variant_id_value,
        ),
    ).fetchone()

    if row:
        return dict(row)

    # -------------------------------------------------------------------------
    # Third attempt:
    # normal variant as fallback
    # -------------------------------------------------------------------------

    if variant_id_value != "normal":
        row = db.execute(
            """
            SELECT *
            FROM pokemon_sprite_inventory

            WHERE
                species_id = ?
                AND form_id IS NULL
                AND variant_id = 'normal'

            ORDER BY
                is_duplicate ASC,
                id ASC

            LIMIT 1
            """,
            (
                species_id,
            ),
        ).fetchone()

        if row:
            return dict(row)

    # -------------------------------------------------------------------------
    # Fourth attempt:
    # any matching species sprite
    # -------------------------------------------------------------------------

    row = db.execute(
        """
        SELECT *
        FROM pokemon_sprite_inventory

        WHERE species_id = ?

        ORDER BY
            CASE
                WHEN variant_id = 'normal'
                    THEN 0
                ELSE 1
            END,
            is_duplicate ASC,
            id ASC

        LIMIT 1
        """,
        (
            species_id,
        ),
    ).fetchone()

    if row:
        return dict(row)

    return None


# =============================================================================
# COMPLETE SPECIES PROFILE
# =============================================================================

def get_species_profile(
    db: sqlite3.Connection,
    species_id: str,
) -> dict[str, Any] | None:
    """
    Return the complete catalog representation of a species.

    This becomes the main read model for future UI, battles, encounters,
    evolution screens and Pokédex-style pages.
    """

    species = get_species(
        db,
        species_id,
    )

    if not species:
        return None

    actual_species_id = str(
        species["id"]
    )

    default_form = get_default_form(
        db,
        actual_species_id,
    )

    forms = get_species_forms(
        db,
        actual_species_id,
    )

    abilities = get_species_abilities(
        db,
        actual_species_id,
    )

    moves = get_species_moves(
        db,
        actual_species_id,
    )

    evolutions = get_species_evolutions(
        db,
        actual_species_id,
    )

    return {
        "species": species,
        "types": get_species_types(
            db,
            actual_species_id,
        ),
        "abilities": abilities,
        "forms": forms,
        "default_form": default_form,
        "moves": moves,
        "evolutions": evolutions,
    }


# =============================================================================
# CATALOG VALIDATION
# =============================================================================

def validate_catalog(
    db: sqlite3.Connection,
) -> dict[str, Any]:
    """
    Return catalog integrity information.

    This deliberately reports problems instead of silently fixing them.
    The importer can then be tested against these expectations.
    """

    official_species = int(
        db.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_species
            WHERE
                is_fakemon = 0
                AND national_dex BETWEEN 1 AND ?
            """,
            (
                OFFICIAL_NATIONAL_DEX_LIMIT,
            ),
        ).fetchone()[0]
    )

    types = int(
        db.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_types
            """
        ).fetchone()[0]
    )

    abilities = int(
        db.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_abilities
            """
        ).fetchone()[0]
    )

    forms = int(
        db.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_forms
            """
        ).fetchone()[0]
    )

    moves = int(
        db.execute(
            """
            SELECT COUNT(*)
            FROM moves
            """
        ).fetchone()[0]
    )

    learnsets = int(
        db.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_species_moves
            """
        ).fetchone()[0]
    )

    evolutions = int(
        db.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_evolutions
            """
        ).fetchone()[0]
    )

    sprites = int(
        db.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_sprite_inventory
            """
        ).fetchone()[0]
    )

    missing_default_forms = int(
        db.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_species s

            WHERE
                s.is_fakemon = 0
                AND s.national_dex BETWEEN 1 AND ?
                AND NOT EXISTS (
                    SELECT 1
                    FROM pokemon_forms f
                    WHERE
                        f.species_id = s.id
                        AND f.is_default = 1
                )
            """,
            (
                OFFICIAL_NATIONAL_DEX_LIMIT,
            ),
        ).fetchone()[0]
    )

    return {
        "official_species": official_species,
        "expected_official_species": OFFICIAL_NATIONAL_DEX_LIMIT,
        "types": types,
        "abilities": abilities,
        "forms": forms,
        "moves": moves,
        "learnsets": learnsets,
        "evolutions": evolutions,
        "sprites": sprites,
        "missing_default_forms": missing_default_forms,
        "catalog_complete": (
            official_species
            == OFFICIAL_NATIONAL_DEX_LIMIT
        ),
    }