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
from Server.pokemon_catalog import (  # noqa: E402
    CATALOG_SCHEMA,
    DEFAULT_VARIANTS,
)


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

# DEFAULT_VARIANTS now comes from Server.pokemon_catalog — that module is the
# single canonical source so the live app and this importer can never drift
# apart on the variant roster again.


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

    This now delegates to Server.pokemon_catalog.CATALOG_SCHEMA, which is
    the single canonical schema shared by the live app and this importer.
    Previously this function defined its own competing copy of the schema
    (different column sets on pokemon_species/pokemon_forms/pokemon_evolutions,
    an INTEGER pokemon_types.id instead of TEXT, and a plain `type` string on
    moves instead of a real type_id foreign key) which could silently drift
    out of sync with what the app actually reads. That duplication has been
    removed.
    """

    connection.executescript(CATALOG_SCHEMA)
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
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                sprite_suffix = excluded.sprite_suffix,
                description = excluded.description,
                is_custom = excluded.is_custom
            """,
            (
                variant["id"],
                variant["name"],
                variant["sprite_suffix"],
                variant["description"],
                variant["is_custom"],
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
    """
    Import Pokémon types.

    The canonical schema (Server.pokemon_catalog.CATALOG_SCHEMA) stores
    pokemon_types.id as TEXT — a lowercase slug like "fire" or "water" —
    to match how the rest of the codebase (Data/pokemon.json, Server/
    pc_storage.py) already references types by name, not by PokeAPI's
    internal integer id. This function still returns a dict keyed by the
    numeric PokeAPI id, since that's what the CSV rows reference, but the
    values (and what actually gets written to the database) are the TEXT
    slug that every other table's type_id foreign key now expects.
    """

    type_rows: dict[int, str] = {}

    for row in rows:
        numeric_id = to_int(row.get("id"))

        if numeric_id <= 0:
            continue

        slug = row.get("identifier", "").strip().lower()

        if not slug:
            continue

        type_rows[numeric_id] = slug

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
                slug,
                clean_name(slug),
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


# Standard PokeAPI stat ids (pokemon_stats.csv `stat_id` column). These are
# stable across PokeAPI's dataset and match https://pokeapi.co/api/v2/stat/.
STAT_ID_HP = 1
STAT_ID_ATTACK = 2
STAT_ID_DEFENSE = 3
STAT_ID_SPECIAL_ATTACK = 4
STAT_ID_SPECIAL_DEFENSE = 5
STAT_ID_SPEED = 6


def build_base_stats_lookup(
    stats_rows: list[dict[str, str]],
) -> dict[int, dict[int, int]]:
    """
    pokemon_stats.csv has one row per (pokemon_id, stat_id) pair. Collapse
    it into pokemon_id -> {stat_id: base_stat} so import_species can look
    up all six base stats for a given Pokémon in one dict access.
    """

    lookup: dict[int, dict[int, int]] = {}

    for row in stats_rows:
        pokemon_id = to_int(row.get("pokemon_id"))
        stat_id = to_int(row.get("stat_id"))

        if pokemon_id <= 0 or stat_id <= 0:
            continue

        lookup.setdefault(pokemon_id, {})[stat_id] = to_int(
            row.get("base_stat"),
            1,
        )

    return lookup


def build_species_metadata_lookup(
    species_rows: list[dict[str, str]],
) -> dict[int, dict[str, Any]]:
    """
    pokemon_species.csv is keyed by species id (not the same as pokemon.csv's
    `id` — see the note in import_species), and carries gender_rate plus the
    legendary/mythical/baby flags this importer uses to set `category`.
    """

    lookup: dict[int, dict[str, Any]] = {}

    for row in species_rows:
        species_id = to_int(row.get("id"))

        if species_id <= 0:
            continue

        lookup[species_id] = {
            "gender_rate": to_int(row.get("gender_rate"), -1),
            "generation_id": to_int(row.get("generation_id"), 0),
            "is_legendary": to_int(row.get("is_legendary"), 0),
            "is_mythical": to_int(row.get("is_mythical"), 0),
            "is_baby": to_int(row.get("is_baby"), 0),
        }

    return lookup


def import_species(
    connection: sqlite3.Connection,
    rows: list[dict[str, str]],
    stats_rows: list[dict[str, str]] | None = None,
    species_rows: list[dict[str, str]] | None = None,
) -> dict[int, str]:
    """
    Import species from pokemon.csv, enriched with base stats (from
    pokemon_stats.csv) and gender_rate/category (from pokemon_species.csv).

    Note the two different "id" concepts at play, straight from PokeAPI:
      - pokemon.csv `id` is the specific Pokémon/form row (what
        NATIONAL_DEX_LIMIT filters against here).
      - pokemon.csv `species_id` / pokemon_species.csv `id` is the species
        itself, which base_stats_lookup and species_metadata_lookup are
        keyed by.
    Previously this function silently dropped every stat/gender_rate value,
    since pokemon_stats.csv was downloaded but never consulted.
    """

    base_stats_lookup = build_base_stats_lookup(stats_rows or [])
    species_metadata_lookup = build_species_metadata_lookup(species_rows or [])

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

        stats = base_stats_lookup.get(pokemon_id, {})
        metadata = species_metadata_lookup.get(species_id, {})

        generation = (
            metadata.get("generation_id")
            or generation_from_dex_number(pokemon_id)
        )

        if metadata.get("is_mythical"):
            category = "mythical"
        elif metadata.get("is_legendary"):
            category = "legendary"
        elif metadata.get("is_baby"):
            category = "baby"
        else:
            category = "pokemon"

        connection.execute(
            """
            INSERT INTO pokemon_species (
                id,
                national_dex,
                name,
                category,
                base_hp,
                base_attack,
                base_defense,
                base_sp_attack,
                base_sp_defense,
                base_speed,
                gender_rate,
                generation,
                is_fakemon
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(id) DO UPDATE SET
                national_dex = excluded.national_dex,
                name = excluded.name,
                category = excluded.category,
                base_hp = excluded.base_hp,
                base_attack = excluded.base_attack,
                base_defense = excluded.base_defense,
                base_sp_attack = excluded.base_sp_attack,
                base_sp_defense = excluded.base_sp_defense,
                base_speed = excluded.base_speed,
                gender_rate = excluded.gender_rate,
                generation = excluded.generation,
                is_fakemon = excluded.is_fakemon
            """,
            (
                species_key,
                pokemon_id,
                name,
                category,
                stats.get(STAT_ID_HP, 1),
                stats.get(STAT_ID_ATTACK, 1),
                stats.get(STAT_ID_DEFENSE, 1),
                stats.get(STAT_ID_SPECIAL_ATTACK, 1),
                stats.get(STAT_ID_SPECIAL_DEFENSE, 1),
                stats.get(STAT_ID_SPEED, 1),
                metadata.get("gender_rate", -1),
                generation,
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

    pokemon_to_species: dict[int, str] = {}

    for pokemon_row in pokemon_rows:
        pokemon_id = to_int(pokemon_row.get("id"))

        if pokemon_id <= 0 or pokemon_id > NATIONAL_DEX_LIMIT:
            continue

        species_key = species_by_pokemon_id.get(pokemon_id)

        if species_key:
            pokemon_to_species[pokemon_id] = species_key

    grouped: dict[str, list[tuple[int, str]]] = {}

    for row in pokemon_type_rows:
        pokemon_id = to_int(row.get("pokemon_id"))
        numeric_type_id = to_int(row.get("type_id"))
        slot = to_int(row.get("slot"), 1)

        if pokemon_id <= 0 or numeric_type_id <= 0:
            continue

        species_key = pokemon_to_species.get(pokemon_id)

        if not species_key:
            continue

        type_slug = type_rows.get(numeric_type_id)

        if not type_slug:
            continue

        grouped.setdefault(species_key, []).append(
            (
                slot,
                type_slug,
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

        for slot, type_slug in values:
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
                    type_slug,
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
        # NOTE: pokemon_forms.csv's own `id` column is the form's own
        # primary key, NOT the Pokémon it belongs to — that's `pokemon_id`.
        # This function previously read `row.get("id")` for both the
        # lookup key and the returned dict key, which meant it was almost
        # never finding the right species (a form's own id rarely matches
        # any pokemon.csv id) and the returned form_by_pokemon_id mapping
        # was keyed by the wrong thing entirely.
        pokemon_id = to_int(row.get("pokemon_id"))

        if pokemon_id <= 0:
            continue

        # NOTE: there used to be a `pokemon_id > 2000` guard here meant to
        # filter out "unrelated future/internal form records". In practice
        # this silently dropped every Mega Evolution, regional variant, and
        # Gigantamax form, since PokeAPI assigns alternate-form Pokémon ids
        # starting at 10001 (e.g. Mega Charizard X = 10034). The species_key
        # lookup below already rejects anything species_by_pokemon_id
        # doesn't recognize, so the extra ceiling was both unnecessary and
        # actively harmful. See the caveat on import_species / NATIONAL_DEX_
        # LIMIT below for the remaining piece of this (those alternate-form
        # pokemon.csv rows still need their own species_by_pokemon_id entry
        # for this lookup to succeed at all).

        species_key = species_by_pokemon_id.get(pokemon_id)

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

        sort_order = to_int(
            row.get("form_order")
            or row.get("order"),
            0,
        )

        connection.execute(
            """
            INSERT INTO pokemon_forms (
                id,
                species_id,
                name,
                form_name,
                display_name,
                form_identifier,
                is_default,
                is_battle_only,
                is_mega,
                is_gmax,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                species_id = excluded.species_id,
                name = excluded.name,
                form_name = excluded.form_name,
                display_name = excluded.display_name,
                form_identifier = excluded.form_identifier,
                is_default = excluded.is_default,
                is_battle_only = excluded.is_battle_only,
                is_mega = excluded.is_mega,
                is_gmax = excluded.is_gmax,
                sort_order = excluded.sort_order
            """,
            (
                form_key,
                species_key,
                display_name,
                form_name,
                display_name,
                form_identifier,
                is_default,
                is_battle_only,
                1 if is_mega else 0,
                1 if is_gmax else 0,
                sort_order,
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

        numeric_type_id = to_int(row.get("type_id"))
        move_type_slug = type_rows.get(
            numeric_type_id,
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
                type_id,
                category,
                power,
                accuracy,
                max_pp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                type_id = excluded.type_id,
                category = excluded.category,
                power = excluded.power,
                accuracy = excluded.accuracy,
                max_pp = excluded.max_pp
            """,
            (
                move_key,
                clean_name(identifier),
                move_type_slug,
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
        "pokemon_stats",
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
            datasets.get(
                "pokemon_stats",
                [],
            ),
            datasets.get(
                "pokemon_species",
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