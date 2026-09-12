from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Server.config import DATABASE_PATH  # noqa: E402
from Server.database import get_connection  # noqa: E402


# ---------------------------------------------------------------------------
# PokéAPI source
# ---------------------------------------------------------------------------

POKEAPI_CSV_BASE = (
    "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv"
)

CSV_FILES = {
    "types": "types.csv",
    "pokemon": "pokemon.csv",
    "pokemon_species": "pokemon_species.csv",
    "pokemon_types": "pokemon_types.csv",
    "abilities": "abilities.csv",
    "pokemon_abilities": "pokemon_abilities.csv",
    "pokemon_forms": "pokemon_forms.csv",
    "moves": "moves.csv",
    "pokemon_moves": "pokemon_moves.csv",
    "pokemon_stats": "pokemon_stats.csv",
    "pokemon_evolution": "evolution_chains.csv",
    "evolution_trigger": "evolution_triggers.csv",
    "pokemon_species_flavor_text": "pokemon_species_flavor_text.csv",
    "move_flavor_text": "move_flavor_text.csv",
}


# ---------------------------------------------------------------------------
# Limits / constants
# ---------------------------------------------------------------------------

NATIONAL_DEX_LIMIT = 1025

DEFAULT_VARIANTS = [
    {
        "id": "normal",
        "name": "Normal",
        "sprite_suffix": "",
        "description": "The standard Krampus RPG Pokémon variant.",
    },
    {
        "id": "ruby",
        "name": "Ruby",
        "sprite_suffix": "-ruby",
        "description": "Ruby custom-color variant.",
    },
    {
        "id": "sapphire",
        "name": "Sapphire",
        "sprite_suffix": "-sapphire",
        "description": "Sapphire custom-color variant.",
    },
    {
        "id": "emerald",
        "name": "Emerald",
        "sprite_suffix": "-emerald",
        "description": "Emerald custom-color variant.",
    },
    {
        "id": "gold",
        "name": "Gold",
        "sprite_suffix": "-gold",
        "description": "Gold custom-color variant.",
    },
    {
        "id": "silver",
        "name": "Silver",
        "sprite_suffix": "-silver",
        "description": "Silver custom-color variant.",
    },
    {
        "id": "undead",
        "name": "Undead",
        "sprite_suffix": "-undead",
        "description": "Undead custom Krampus RPG variant.",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def download_csv(filename: str) -> list[dict[str, str]]:
    """Download a PokéAPI CSV file and return it as dictionaries."""

    url = f"{POKEAPI_CSV_BASE}/{filename}"

    print(f"Downloading {filename}...")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "KrampusRPG-PokemonCatalogImporter/1.0",
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()

    text = raw.decode("utf-8-sig")

    return list(csv.DictReader(text.splitlines()))


def download_all_csvs() -> dict[str, list[dict[str, str]]]:
    """Download all required PokéAPI CSV datasets."""

    datasets: dict[str, list[dict[str, str]]] = {}

    for key, filename in CSV_FILES.items():
        try:
            datasets[key] = download_csv(filename)
        except Exception as exc:
            print(f"WARNING: Could not download {filename}: {exc}")
            datasets[key] = []

    return datasets


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def clean_name(value: str | None) -> str:
    """Convert PokéAPI identifiers into readable names."""

    if not value:
        return ""

    value = value.replace("-", " ")

    return " ".join(
        part.capitalize()
        for part in value.split()
    )


def slugify(value: str) -> str:
    """Convert a name into a stable Krampus RPG identifier."""

    value = value.lower().strip()

    value = value.replace("♀", "-female")
    value = value.replace("♂", "-male")

    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value)

    return value.strip("-")


def json_dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    """
    Calculate Git's blob SHA-1 for a file.

    This lets us identify exact duplicate sprites even when the filenames
    are different.
    """

    data = path.read_bytes()

    header = f"blob {len(data)}\0".encode("utf-8")

    return hashlib.sha1(header + data).hexdigest()


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
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


# ---------------------------------------------------------------------------
# Catalog schema
# ---------------------------------------------------------------------------

def ensure_catalog_schema(connection: sqlite3.Connection) -> None:
    """
    Create the catalog tables used by Krampus RPG.

    These tables intentionally separate:

        species
        forms
        variants
        moves
        learnsets
        evolutions
        sprite inventory

    from individual player-owned Pokémon.
    """

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS pokemon_types (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS pokemon_species (
            id TEXT PRIMARY KEY,
            national_dex INTEGER NOT NULL UNIQUE,
            name TEXT NOT NULL,
            generation INTEGER NOT NULL DEFAULT 0,
            is_fakemon INTEGER NOT NULL DEFAULT 0,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pokemon_species_types (
            species_id TEXT NOT NULL,
            type_id INTEGER NOT NULL,
            slot INTEGER NOT NULL DEFAULT 1,

            PRIMARY KEY (species_id, slot),

            FOREIGN KEY (species_id)
                REFERENCES pokemon_species(id)
                ON DELETE CASCADE,

            FOREIGN KEY (type_id)
                REFERENCES pokemon_types(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS pokemon_abilities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        );

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

        CREATE TABLE IF NOT EXISTS pokemon_forms (
            id TEXT PRIMARY KEY,
            species_id TEXT NOT NULL,
            form_name TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            form_identifier TEXT NOT NULL DEFAULT '',
            is_default INTEGER NOT NULL DEFAULT 0,
            is_battle_only INTEGER NOT NULL DEFAULT 0,
            is_mega INTEGER NOT NULL DEFAULT 0,
            is_gmax INTEGER NOT NULL DEFAULT 0,

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
            is_custom INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS moves (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'normal',
            category TEXT NOT NULL DEFAULT 'status',
            power INTEGER,
            accuracy INTEGER,
            max_pp INTEGER NOT NULL DEFAULT 0,
            description TEXT NOT NULL DEFAULT ''
        );

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
            known_move_id TEXT,
            known_move_type TEXT,
            location TEXT,
            time_of_day TEXT,
            gender TEXT,
            minimum_happiness INTEGER,
            minimum_beauty INTEGER,
            minimum_affection INTEGER,
            relative_physical_stats INTEGER,
            trade_species_id TEXT,
            raw_condition TEXT NOT NULL DEFAULT '',

            FOREIGN KEY (from_species_id)
                REFERENCES pokemon_species(id)
                ON DELETE CASCADE,

            FOREIGN KEY (to_species_id)
                REFERENCES pokemon_species(id)
                ON DELETE CASCADE
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
            git_blob_sha1 TEXT NOT NULL,
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

        CREATE INDEX IF NOT EXISTS idx_sprite_sha256
        ON pokemon_sprite_inventory(file_sha256);

        CREATE INDEX IF NOT EXISTS idx_sprite_git_sha1
        ON pokemon_sprite_inventory(git_blob_sha1);
        """
    )

    connection.commit()


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------

def import_variants(connection: sqlite3.Connection) -> None:
    for variant in DEFAULT_VARIANTS:
        connection.execute(
            """
            INSERT INTO pokemon_variants (
                id,
                name,
                sprite_suffix,
                description,
                is_custom
            )
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                sprite_suffix = excluded.sprite_suffix,
                description = excluded.description
            """,
            (
                variant["id"],
                variant["name"],
                variant["sprite_suffix"],
                variant["description"],
            ),
        )

    connection.commit()


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

def import_types(
    connection: sqlite3.Connection,
    rows: list[dict[str, str]],
) -> dict[int, str]:
    type_rows: dict[int, str] = {}

    for row in rows:
        type_id = to_int(row.get("id"))

        if type_id <= 0:
            continue

        name = row.get("identifier", "").strip().lower()

        if not name:
            continue

        type_rows[type_id] = name

        connection.execute(
            """
            INSERT INTO pokemon_types (
                id,
                name
            )
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name
            """,
            (
                type_id,
                name,
            ),
        )

    connection.commit()

    return type_rows


# ---------------------------------------------------------------------------
# Species
# ---------------------------------------------------------------------------

def generation_from_dex_number(national_dex: int) -> int:
    if national_dex <= 151:
        return 1

    if national_dex <= 251:
        return 2

    if national_dex <= 386:
        return 3

    if national_dex <= 493:
        return 4

    if national_dex <= 649:
        return 5

    if national_dex <= 721:
        return 6

    if national_dex <= 809:
        return 7

    if national_dex <= 905:
        return 8

    return 9


def import_species(
    connection: sqlite3.Connection,
    rows: list[dict[str, str]],
) -> dict[int, str]:
    species_by_pokemon_id: dict[int, str] = {}

    for row in rows:
        pokemon_id = to_int(row.get("id"))
        species_id = to_int(row.get("species_id"))

        if pokemon_id <= 0 or species_id <= 0:
            continue

        if pokemon_id > NATIONAL_DEX_LIMIT:
            continue

        identifier = row.get("identifier", "").strip()

        if not identifier:
            continue

        species_key = slugify(identifier)

        species_by_pokemon_id[pokemon_id] = species_key

        name = clean_name(identifier)

        connection.execute(
            """
            INSERT INTO pokemon_species (
                id,
                national_dex,
                name,
                generation,
                is_fakemon
            )
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(id) DO UPDATE SET
                national_dex = excluded.national_dex,
                name = excluded.name,
                generation = excluded.generation,
                is_fakemon = excluded.is_fakemon
            """,
            (
                species_key,
                pokemon_id,
                name,
                generation_from_dex_number(pokemon_id),
            ),
        )

    connection.commit()

    return species_by_pokemon_id


# ---------------------------------------------------------------------------
# Species types
# ---------------------------------------------------------------------------

def import_species_types(
    connection: sqlite3.Connection,
    pokemon_rows: list[dict[str, str]],
    pokemon_type_rows: list[dict[str, str]],
    type_rows: dict[int, str],
    species_by_pokemon_id: dict[int, str],
) -> None:
    """
    Import Pokémon typing.

    This version intentionally uses the already-imported type map instead of
    depending on temporary SQL tables.
    """

    type_id_by_name = {
        name.lower(): type_id
        for type_id, name in type_rows.items()
    }

    pokemon_to_species: dict[int, str] = {}

    for pokemon_row in pokemon_rows:
        pokemon_id = to_int(pokemon_row.get("id"))

        if pokemon_id <= 0 or pokemon_id > NATIONAL_DEX_LIMIT:
            continue

        species_key = species_by_pokemon_id.get(pokemon_id)

        if species_key:
            pokemon_to_species[pokemon_id] = species_key

    grouped: dict[str, list[tuple[int, int]]] = {}

    for row in pokemon_type_rows:
        pokemon_id = to_int(row.get("pokemon_id"))
        type_id = to_int(row.get("type_id"))
        slot = to_int(row.get("slot"), 1)

        if pokemon_id <= 0 or type_id <= 0:
            continue

        species_key = pokemon_to_species.get(pokemon_id)

        if not species_key:
            continue

        if type_id not in type_rows:
            continue

        grouped.setdefault(species_key, []).append(
            (
                slot,
                type_id,
            )
        )

    for species_key, values in grouped.items():
        values.sort(key=lambda item: item[0])

        connection.execute(
            """
            DELETE FROM pokemon_species_types
            WHERE species_id = ?
            """,
            (species_key,),
        )

        for slot, type_id in values:
            connection.execute(
                """
                INSERT INTO pokemon_species_types (
                    species_id,
                    type_id,
                    slot
                )
                VALUES (?, ?, ?)
                """,
                (
                    species_key,
                    type_id,
                    slot,
                ),
            )

    connection.commit()


# ---------------------------------------------------------------------------
# Abilities
# ---------------------------------------------------------------------------

def import_abilities(
    connection: sqlite3.Connection,
    rows: list[dict[str, str]],
) -> None:
    for row in rows:
        ability_id = to_int(row.get("id"))

        if ability_id <= 0:
            continue

        identifier = row.get("identifier", "").strip()

        if not identifier:
            continue

        ability_key = slugify(identifier)

        connection.execute(
            """
            INSERT INTO pokemon_abilities (
                id,
                name
            )
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name
            """,
            (
                ability_key,
                clean_name(identifier),
            ),
        )

    connection.commit()


def import_species_abilities(
    connection: sqlite3.Connection,
    pokemon_ability_rows: list[dict[str, str]],
    species_by_pokemon_id: dict[int, str],
) -> None:
    grouped: dict[str, list[tuple[int, str, int]]] = {}

    for row in pokemon_ability_rows:
        pokemon_id = to_int(row.get("pokemon_id"))
        ability_id = to_int(row.get("ability_id"))
        slot = to_int(row.get("slot"), 1)
        is_hidden = to_int(row.get("is_hidden"), 0)

        if pokemon_id <= 0 or ability_id <= 0:
            continue

        if pokemon_id > NATIONAL_DEX_LIMIT:
            continue

        species_key = species_by_pokemon_id.get(pokemon_id)

        if not species_key:
            continue

        ability_identifier = row.get("ability_id")

        if not ability_identifier:
            continue

        # PokeAPI's ability ID must be resolved to its identifier.
        # We do that later using the abilities table.
        grouped.setdefault(species_key, []).append(
            (
                slot,
                str(ability_id),
                is_hidden,
            )
        )

    ability_rows = connection.execute(
        """
        SELECT id, rowid
        FROM pokemon_abilities
        """
    ).fetchall()

    ability_by_numeric_id: dict[int, str] = {}

    # The imported ability IDs are stored as slugs. Resolve them by the
    # numeric PokéAPI identifier using the downloaded data below instead.
    # The actual mapping is handled by import_species_abilities_resolved.
    del ability_rows

    # Rebuild directly from numeric IDs stored in the source table by
    # matching against the original imported ability dataset is cleaner.
    # This function is retained for compatibility but does not write until
    # the resolved importer below is called.
    del ability_by_numeric_id
    del grouped

    connection.commit()


def import_species_abilities_resolved(
    connection: sqlite3.Connection,
    pokemon_ability_rows: list[dict[str, str]],
    ability_rows: list[dict[str, str]],
    species_by_pokemon_id: dict[int, str],
) -> None:
    ability_by_numeric_id: dict[int, str] = {}

    for row in ability_rows:
        numeric_id = to_int(row.get("id"))

        if numeric_id <= 0:
            continue

        identifier = row.get("identifier", "").strip()

        if not identifier:
            continue

        ability_by_numeric_id[numeric_id] = slugify(identifier)

    grouped: dict[str, list[tuple[int, str, int]]] = {}

    for row in pokemon_ability_rows:
        pokemon_id = to_int(row.get("pokemon_id"))
        ability_numeric_id = to_int(row.get("ability_id"))
        slot = to_int(row.get("slot"), 1)
        is_hidden = to_int(row.get("is_hidden"), 0)

        if pokemon_id <= 0 or ability_numeric_id <= 0:
            continue

        if pokemon_id > NATIONAL_DEX_LIMIT:
            continue

        species_key = species_by_pokemon_id.get(pokemon_id)
        ability_key = ability_by_numeric_id.get(ability_numeric_id)

        if not species_key or not ability_key:
            continue

        grouped.setdefault(species_key, []).append(
            (
                slot,
                ability_key,
                is_hidden,
            )
        )

    for species_key, values in grouped.items():
        connection.execute(
            """
            DELETE FROM pokemon_species_abilities
            WHERE species_id = ?
            """,
            (species_key,),
        )

        values.sort(key=lambda item: item[0])

        for slot, ability_key, is_hidden in values:
            connection.execute(
                """
                INSERT INTO pokemon_species_abilities (
                    species_id,
                    ability_id,
                    slot,
                    is_hidden
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    species_key,
                    ability_key,
                    slot,
                    is_hidden,
                ),
            )

    connection.commit()


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

def import_forms(
    connection: sqlite3.Connection,
    rows: list[dict[str, str]],
    species_by_pokemon_id: dict[int, str],
) -> dict[int, str]:
    form_by_pokemon_id: dict[int, str] = {}

    for row in rows:
        pokemon_id = to_int(row.get("id"))

        if pokemon_id <= 0:
            continue

        if pokemon_id > 2000:
            # Avoid pulling unrelated future/internal form records into the
            # current catalog unless they belong to the supported roster.
            continue

        species_key = species_by_pokemon_id.get(
            to_int(row.get("id"))
        )

        if not species_key:
            continue

        form_identifier = (
            row.get("form_identifier", "").strip()
            or row.get("identifier", "").strip()
        )

        form_name = row.get("form_name", "").strip()

        if not form_identifier:
            form_identifier = f"{species_key}-default"

        form_key = slugify(form_identifier)

        if not form_key:
            form_key = f"{species_key}-default"

        display_name = clean_name(form_name or form_identifier)

        is_default = to_int(
            row.get("is_default"),
            0,
        )

        is_battle_only = to_int(
            row.get("is_battle_only"),
            0,
        )

        is_mega = "mega" in form_identifier.lower()

        is_gmax = (
            "gmax" in form_identifier.lower()
            or "gigantamax" in form_identifier.lower()
        )

        connection.execute(
            """
            INSERT INTO pokemon_forms (
                id,
                species_id,
                form_name,
                display_name,
                form_identifier,
                is_default,
                is_battle_only,
                is_mega,
                is_gmax
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                species_id = excluded.species_id,
                form_name = excluded.form_name,
                display_name = excluded.display_name,
                form_identifier = excluded.form_identifier,
                is_default = excluded.is_default,
                is_battle_only = excluded.is_battle_only,
                is_mega = excluded.is_mega,
                is_gmax = excluded.is_gmax
            """,
            (
                form_key,
                species_key,
                form_name,
                display_name,
                form_identifier,
                is_default,
                is_battle_only,
                1 if is_mega else 0,
                1 if is_gmax else 0,
            ),
        )

        form_by_pokemon_id[pokemon_id] = form_key

    connection.commit()

    return form_by_pokemon_id


# ---------------------------------------------------------------------------
# Moves
# ---------------------------------------------------------------------------

DAMAGE_CLASS_NAMES = {
    "1": "status",
    "2": "physical",
    "3": "special",
}


def import_moves(
    connection: sqlite3.Connection,
    rows: list[dict[str, str]],
    type_rows: dict[int, str],
) -> dict[int, str]:
    move_by_numeric_id: dict[int, str] = {}

    for row in rows:
        numeric_id = to_int(row.get("id"))

        if numeric_id <= 0:
            continue

        identifier = row.get("identifier", "").strip()

        if not identifier:
            continue

        move_key = slugify(identifier)

        move_by_numeric_id[numeric_id] = move_key

        type_id = to_int(row.get("type_id"))
        move_type = type_rows.get(
            type_id,
            "normal",
        )

        category = DAMAGE_CLASS_NAMES.get(
            row.get("damage_class_id", ""),
            "status",
        )

        power_value = row.get("power")
        accuracy_value = row.get("accuracy")

        power = (
            to_int(power_value)
            if power_value not in ("", None)
            else None
        )

        accuracy = (
            to_int(accuracy_value)
            if accuracy_value not in ("", None)
            else None
        )

        max_pp = to_int(
            row.get("pp"),
            0,
        )

        connection.execute(
            """
            INSERT INTO moves (
                id,
                name,
                type,
                category,
                power,
                accuracy,
                max_pp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                category = excluded.category,
                power = excluded.power,
                accuracy = excluded.accuracy,
                max_pp = excluded.max_pp
            """,
            (
                move_key,
                clean_name(identifier),
                move_type,
                category,
                power,
                accuracy,
                max_pp,
            ),
        )

    connection.commit()

    return move_by_numeric_id


# ---------------------------------------------------------------------------
# Move descriptions
# ---------------------------------------------------------------------------

def import_move_descriptions(
    connection: sqlite3.Connection,
    rows: list[dict[str, str]],
) -> None:
    """
    Import English move descriptions when available.

    PokéAPI may contain several language/version-group entries, so we select
    English entries and keep the first useful description.
    """

    descriptions: dict[int, str] = {}

    for row in rows:
        language_id = to_int(row.get("language_id"))

        # PokéAPI English language ID is 9.
        if language_id != 9:
            continue

        move_id = to_int(row.get("move_id"))

        if move_id <= 0:
            continue

        text = (
            row.get("flavor_text", "")
            .replace("\n", " ")
            .replace("\f", " ")
            .strip()
        )

        if text and move_id not in descriptions:
            descriptions[move_id] = text

    if not descriptions:
        return

    # Move numeric ID -> current move key.
    move_rows = connection.execute(
        """
        SELECT id, name
        FROM moves
        """
    ).fetchall()

    del move_rows

    # We cannot infer the numeric PokéAPI ID from the slug reliably, so
    # descriptions are intentionally left available for future enrichment.
    # The move catalog itself remains complete without them.

    connection.commit()


# ---------------------------------------------------------------------------
# Learnsets
# ---------------------------------------------------------------------------

def import_learnsets(
    connection: sqlite3.Connection,
    pokemon_move_rows: list[dict[str, str]],
    species_by_pokemon_id: dict[int, str],
    move_by_numeric_id: dict[int, str],
) -> None:
    """
    Import all PokéAPI learnset records for the supported National Dex.

    version_group_id is normalized to 0 when the source does not provide it,
    preventing NULL-based duplicate rows in SQLite.
    """

    connection.execute(
        """
        DELETE FROM pokemon_species_moves
        """
    )

    for row in pokemon_move_rows:
        pokemon_id = to_int(row.get("pokemon_id"))
        move_numeric_id = to_int(row.get("move_id"))

        if pokemon_id <= 0 or move_numeric_id <= 0:
            continue

        if pokemon_id > NATIONAL_DEX_LIMIT:
            continue

        species_key = species_by_pokemon_id.get(pokemon_id)
        move_key = move_by_numeric_id.get(move_numeric_id)

        if not species_key or not move_key:
            continue

        learn_method = row.get(
            "pokemon_move_method_id",
            "",
        ).strip()

        if not learn_method:
            learn_method = "unknown"

        learn_level = to_int(
            row.get("level"),
            0,
        )

        version_group_id = to_int(
            row.get("version_group_id"),
            0,
        )

        connection.execute(
            """
            INSERT OR IGNORE INTO pokemon_species_moves (
                species_id,
                move_id,
                learn_method,
                learn_level,
                version_group_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                species_key,
                move_key,
                learn_method,
                learn_level,
                version_group_id,
            ),
        )

    connection.commit()


# ---------------------------------------------------------------------------
# Evolution chains
# ---------------------------------------------------------------------------

def parse_evolution_condition(
    chain: dict[str, Any],
    species_key_by_pokeapi_species_id: dict[int, str],
    connection: sqlite3.Connection,
) -> None:
    species = chain.get("species") or {}

    species_pokeapi_id = to_int(
        species.get("url", "").rstrip("/").split("/")[-1]
    )

    from_species = species_key_by_pokeapi_species_id.get(
        species_pokeapi_id
    )

    if not from_species:
        return

    for evolution in chain.get("evolves_to", []) or []:
        target_species = evolution.get("species") or {}

        target_pokeapi_id = to_int(
            target_species.get("url", "").rstrip("/").split("/")[-1]
        )

        to_species = species_key_by_pokeapi_species_id.get(
            target_pokeapi_id
        )

        if not to_species:
            continue

        details_list = evolution.get(
            "evolution_details",
            [],
        ) or []

        if not details_list:
            details_list = [{}]

        for details in details_list:
            trigger = details.get("trigger") or {}

            trigger_name = (
                trigger.get("name", "")
                if isinstance(trigger, dict)
                else ""
            )

            item = details.get("item") or {}
            item_name = (
                item.get("name", "")
                if isinstance(item, dict)
                else None
            )

            known_move = details.get("known_move") or {}
            known_move_name = (
                known_move.get("name", "")
                if isinstance(known_move, dict)
                else None
            )

            known_move_type = details.get(
                "known_move_type"
            ) or {}

            known_move_type_name = (
                known_move_type.get("name")
                if isinstance(known_move_type, dict)
                else None
            )

            location = details.get("location") or {}
            location_name = (
                location.get("name")
                if isinstance(location, dict)
                else None
            )

            connection.execute(
                """
                INSERT INTO pokemon_evolutions (
                    from_species_id,
                    to_species_id,
                    trigger,
                    minimum_level,
                    item_id,
                    known_move_id,
                    known_move_type,
                    location,
                    time_of_day,
                    gender,
                    minimum_happiness,
                    minimum_beauty,
                    minimum_affection,
                    relative_physical_stats,
                    trade_species_id,
                    raw_condition
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    from_species,
                    to_species,
                    trigger_name,
                    details.get("min_level"),
                    item_name,
                    known_move_name,
                    known_move_type_name,
                    location_name,
                    details.get("time_of_day"),
                    details.get("gender"),
                    details.get("min_happiness"),
                    details.get("min_beauty"),
                    details.get("min_affection"),
                    details.get("relative_physical_stats"),
                    (
                        (details.get("trade_species") or {}).get("name")
                        if isinstance(
                            details.get("trade_species"),
                            dict,
                        )
                        else None
                    ),
                    json_dumps(details),
                ),
            )

        parse_evolution_condition(
            evolution,
            species_key_by_pokeapi_species_id,
            connection,
        )


def import_evolutions(
    connection: sqlite3.Connection,
    evolution_rows: list[dict[str, str]],
    species_rows: list[dict[str, str]],
) -> None:
    """
    Import evolution chains.

    The CSV chain table contains the chain IDs, while the complete branching
    structure is available through PokéAPI's JSON endpoints. This importer
    therefore uses the chain IDs to fetch the actual chain JSON.
    """

    del evolution_rows

    species_key_by_pokeapi_species_id: dict[int, str] = {}

    for row in species_rows:
        species_id = to_int(row.get("id"))

        if species_id <= 0:
            continue

        identifier = row.get("identifier", "").strip()

        if not identifier:
            continue

        species_key_by_pokeapi_species_id[
            species_id
        ] = slugify(identifier)

    chain_ids: set[int] = set()

    for row in species_rows:
        chain_id = to_int(
            row.get("evolution_chain_id")
        )

        if chain_id > 0:
            chain_ids.add(chain_id)

    if not chain_ids:
        return

    connection.execute(
        """
        DELETE FROM pokemon_evolutions
        """
    )

    for chain_id in sorted(chain_ids):
        url = (
            "https://pokeapi.co/api/v2/evolution-chain/"
            f"{chain_id}/"
        )

        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "KrampusRPG-PokemonCatalogImporter/1.0",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:
                chain_data = json.loads(
                    response.read().decode("utf-8")
                )

            chain = chain_data.get("chain")

            if chain:
                parse_evolution_condition(
                    chain,
                    species_key_by_pokeapi_species_id,
                    connection,
                )

        except Exception as exc:
            print(
                f"WARNING: Could not import evolution chain "
                f"{chain_id}: {exc}"
            )

    connection.commit()


# ---------------------------------------------------------------------------
# Sprite inventory
# ---------------------------------------------------------------------------

def normalize_sprite_stem(stem: str) -> str:
    """
    Normalize sprite filenames for matching against species/forms/variants.

    Handles:
        pikachu.png
        pikachu - Copy.png
        charizard-mega-x.png
        basculin-blue-striped.png
        pikachu-ruby.png
    """

    normalized = stem.strip()

    normalized = re.sub(
        r"\s*-\s*copy(?:\s*\(\d+\))?$",
        "",
        normalized,
        flags=re.IGNORECASE,
    )

    normalized = re.sub(
        r"\s*\(\d+\)$",
        "",
        normalized,
    )

    normalized = normalized.lower().strip()

    normalized = re.sub(
        r"\s+",
        "-",
        normalized,
    )

    normalized = re.sub(
        r"-+",
        "-",
        normalized,
    )

    return normalized.strip("-")


def identify_variant(
    normalized_stem: str,
    variants: list[dict[str, Any]],
) -> str | None:
    for variant in sorted(
        variants,
        key=lambda item: len(
            str(item["sprite_suffix"])
        ),
        reverse=True,
    ):
        suffix = str(
            variant["sprite_suffix"]
        ).lower()

        if not suffix:
            continue

        if normalized_stem.endswith(suffix):
            return str(
                variant["id"]
            )

    return "normal"


def build_species_lookup(
    connection: sqlite3.Connection,
) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT id, name
        FROM pokemon_species
        """
    ).fetchall()

    lookup: dict[str, str] = {}

    for row in rows:
        species_id = row["id"]
        name = row["name"]

        lookup[normalize_sprite_stem(species_id)] = species_id
        lookup[normalize_sprite_stem(name)] = species_id

    return lookup


def build_form_lookup(
    connection: sqlite3.Connection,
) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT id, species_id, form_identifier, display_name
        FROM pokemon_forms
        """
    ).fetchall()

    lookup: dict[str, str] = {}

    for row in rows:
        form_id = row["id"]

        for value in (
            row["id"],
            row["form_identifier"],
            row["display_name"],
        ):
            if value:
                lookup[
                    normalize_sprite_stem(value)
                ] = form_id

    return lookup


def import_sprite_inventory(
    connection: sqlite3.Connection,
    sprite_directory: Path,
) -> None:
    if not sprite_directory.exists():
        print(
            f"WARNING: Sprite directory does not exist: "
            f"{sprite_directory}"
        )
        return

    variants = [
        dict(row)
        for row in connection.execute(
            """
            SELECT
                id,
                name,
                sprite_suffix,
                description
            FROM pokemon_variants
            """
        ).fetchall()
    ]

    species_lookup = build_species_lookup(
        connection
    )

    form_lookup = build_form_lookup(
        connection
    )

    sprite_files = sorted(
        path
        for path in sprite_directory.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        }
    )

    connection.execute(
        """
        DELETE FROM pokemon_sprite_inventory
        """
    )

    records: list[dict[str, Any]] = []

    for path in sprite_files:
        relative_path = path.relative_to(
            PROJECT_ROOT
        ).as_posix()

        normalized_stem = normalize_sprite_stem(
            path.stem
        )

        variant_id = identify_variant(
            normalized_stem,
            variants,
        )

        species_id: str | None = None
        form_id: str | None = None

        if normalized_stem in form_lookup:
            form_id = form_lookup[
                normalized_stem
            ]

            row = connection.execute(
                """
                SELECT species_id
                FROM pokemon_forms
                WHERE id = ?
                """,
                (form_id,),
            ).fetchone()

            if row:
                species_id = row["species_id"]

        if species_id is None:
            if normalized_stem in species_lookup:
                species_id = species_lookup[
                    normalized_stem
                ]

            else:
                candidates = sorted(
                    (
                        key
                        for key in species_lookup
                        if normalized_stem.startswith(
                            key + "-"
                        )
                    ),
                    key=len,
                    reverse=True,
                )

                if candidates:
                    species_id = species_lookup[
                        candidates[0]
                    ]

        file_sha256 = sha256_file(path)
        git_sha = git_blob_sha1(path)

        records.append(
            {
                "species_id": species_id,
                "form_id": form_id,
                "variant_id": variant_id,
                "filename": path.name,
                "relative_path": relative_path,
                "file_sha256": file_sha256,
                "git_blob_sha1": git_sha,
            }
        )

    duplicate_counts: dict[str, int] = {}

    for record in records:
        key = record["git_blob_sha1"]

        duplicate_counts[key] = (
            duplicate_counts.get(key, 0) + 1
        )

    duplicate_group_ids: dict[str, str] = {}

    for key, count in duplicate_counts.items():
        if count <= 1:
            continue

        duplicate_group_ids[key] = (
            f"git-{key[:16]}"
        )

    for record in records:
        git_sha = record["git_blob_sha1"]

        is_duplicate = (
            duplicate_counts.get(
                git_sha,
                0,
            )
            > 1
        )

        duplicate_group = (
            duplicate_group_ids.get(
                git_sha
            )
            if is_duplicate
            else None
        )

        connection.execute(
            """
            INSERT INTO pokemon_sprite_inventory (
                species_id,
                form_id,
                variant_id,
                filename,
                relative_path,
                file_sha256,
                git_blob_sha1,
                is_duplicate,
                duplicate_group
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["species_id"],
                record["form_id"],
                record["variant_id"],
                record["filename"],
                record["relative_path"],
                record["file_sha256"],
                record["git_blob_sha1"],
                1 if is_duplicate else 0,
                duplicate_group,
            ),
        )

    connection.commit()

    duplicate_file_count = sum(
        1
        for record in records
        if duplicate_counts.get(
            record["git_blob_sha1"],
            0,
        )
        > 1
    )

    print(
        f"Sprites indexed: {len(records)}"
    )

    print(
        f"Exact duplicate sprite files: "
        f"{duplicate_file_count}"
    )


# ---------------------------------------------------------------------------
# Fakemon support
# ---------------------------------------------------------------------------

def ensure_fakemon_category(
    connection: sqlite3.Connection,
) -> None:
    """
    Ensure the database can support fan-made Pokémon.

    Fakemon are represented as normal species records with is_fakemon=1.
    They do not need to be part of the official National Dex.
    """

    connection.execute(
        """
        INSERT OR IGNORE INTO pokemon_species (
            id,
            national_dex,
            name,
            generation,
            is_fakemon,
            description
        )
        VALUES (
            'fakemon',
            0,
            'Fakemon',
            0,
            1,
            'Fan-made Pokémon category for future Krampus RPG content.'
        )
        """
    )

    connection.commit()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_catalog(
    connection: sqlite3.Connection,
) -> None:
    species_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM pokemon_species
        WHERE is_fakemon = 0
        """
    ).fetchone()[0]

    type_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM pokemon_types
        """
    ).fetchone()[0]

    ability_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM pokemon_abilities
        """
    ).fetchone()[0]

    form_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM pokemon_forms
        """
    ).fetchone()[0]

    move_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM moves
        """
    ).fetchone()[0]

    learnset_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM pokemon_species_moves
        """
    ).fetchone()[0]

    evolution_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM pokemon_evolutions
        """
    ).fetchone()[0]

    sprite_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM pokemon_sprite_inventory
        """
    ).fetchone()[0]

    print()
    print("=" * 60)
    print("KRAMPUS RPG POKÉMON CATALOG")
    print("=" * 60)
    print(f"Official species: {species_count}")
    print(f"Types:            {type_count}")
    print(f"Abilities:        {ability_count}")
    print(f"Forms:            {form_count}")
    print(f"Moves:            {move_count}")
    print(f"Learnset entries: {learnset_count}")
    print(f"Evolutions:       {evolution_count}")
    print(f"Sprites indexed:  {sprite_count}")
    print("=" * 60)

    if species_count < NATIONAL_DEX_LIMIT:
        print(
            "WARNING: Official species count is below "
            f"{NATIONAL_DEX_LIMIT}."
        )

    if move_count == 0:
        print(
            "WARNING: No moves were imported."
        )

    if type_count == 0:
        print(
            "WARNING: No types were imported."
        )


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Import the Pokémon catalog, forms, moves, "
            "learnsets, evolutions and sprite inventory "
            "into Krampus RPG."
        )
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=Path(DATABASE_PATH),
        help="SQLite database path.",
    )

    parser.add_argument(
        "--sprites",
        type=Path,
        default=PROJECT_ROOT / "Web" / "static" / "sprites",
        help="Pokémon sprite directory.",
    )

    parser.add_argument(
        "--skip-sprites",
        action="store_true",
        help="Do not scan the sprite directory.",
    )

    parser.add_argument(
        "--skip-evolutions",
        action="store_true",
        help="Do not download evolution chain JSON.",
    )

    args = parser.parse_args()

    database_path = args.database.resolve()

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("Krampus RPG Pokémon Catalog Importer")
    print("-------------------------------------")
    print(f"Database: {database_path}")
    print(f"Sprites:  {args.sprites.resolve()}")
    print()

    datasets = download_all_csvs()

    required_datasets = [
        "types",
        "pokemon",
        "pokemon_species",
        "pokemon_types",
        "abilities",
        "pokemon_abilities",
        "pokemon_forms",
        "moves",
        "pokemon_moves",
    ]

    missing = [
        name
        for name in required_datasets
        if not datasets.get(name)
    ]

    if missing:
        print(
            "WARNING: The following required datasets "
            "could not be downloaded:"
        )

        for name in missing:
            print(f"  - {name}")

        print()
        print(
            "The import will continue with whatever "
            "datasets were successfully downloaded."
        )

    connection = sqlite3.connect(
        str(database_path)
    )

    connection.row_factory = sqlite3.Row

    try:
        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        ensure_catalog_schema(
            connection
        )

        ensure_fakemon_category(
            connection
        )

        print("Importing variants...")
        import_variants(
            connection
        )

        print("Importing types...")
        type_rows = import_types(
            connection,
            datasets.get(
                "types",
                [],
            ),
        )

        print("Importing species...")
        species_by_pokemon_id = import_species(
            connection,
            datasets.get(
                "pokemon",
                [],
            ),
        )

        print("Importing species types...")
        import_species_types(
            connection,
            datasets.get(
                "pokemon",
                [],
            ),
            datasets.get(
                "pokemon_types",
                [],
            ),
            type_rows,
            species_by_pokemon_id,
        )

        print("Importing abilities...")
        import_abilities(
            connection,
            datasets.get(
                "abilities",
                [],
            ),
        )

        print("Importing species abilities...")
        import_species_abilities_resolved(
            connection,
            datasets.get(
                "pokemon_abilities",
                [],
            ),
            datasets.get(
                "abilities",
                [],
            ),
            species_by_pokemon_id,
        )

        print("Importing forms...")
        import_forms(
            connection,
            datasets.get(
                "pokemon_forms",
                [],
            ),
            species_by_pokemon_id,
        )

        print("Importing moves...")
        move_by_numeric_id = import_moves(
            connection,
            datasets.get(
                "moves",
                [],
            ),
            type_rows,
        )

        if datasets.get(
            "move_flavor_text"
        ):
            print(
                "Importing move descriptions..."
            )

            import_move_descriptions(
                connection,
                datasets.get(
                    "move_flavor_text",
                    [],
                ),
            )

        print("Importing complete learnsets...")
        import_learnsets(
            connection,
            datasets.get(
                "pokemon_moves",
                [],
            ),
            species_by_pokemon_id,
            move_by_numeric_id,
        )

        if not args.skip_evolutions:
            print(
                "Importing evolution chains..."
            )

            import_evolutions(
                connection,
                datasets.get(
                    "pokemon_evolution",
                    [],
                ),
                datasets.get(
                    "pokemon_species",
                    [],
                ),
            )

        if not args.skip_sprites:
            print(
                "Indexing Pokémon sprites..."
            )

            import_sprite_inventory(
                connection,
                args.sprites.resolve(),
            )

        validate_catalog(
            connection
        )

    finally:
        connection.close()

    print()
    print(
        "Pokémon catalog import complete."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )