from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


# =============================================================================
# PROJECT PATHS
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from Server.config import DATABASE_PATH  # noqa: E402
from Server.database import get_connection  # noqa: E402
from Server.pokemon_catalog import (  # noqa: E402
    DEFAULT_VARIANTS,
    OFFICIAL_NATIONAL_DEX_LIMIT,
    ensure_catalog_schema,
    migrate_catalog_schema,
    set_default_forms_for_owned_pokemon,
)


# =============================================================================
# POKÉAPI
# =============================================================================

POKEAPI_CSV_BASE = (
    "https://raw.githubusercontent.com/"
    "PokeAPI/pokeapi/master/data/v2/csv"
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
    "pokemon_species_flavor_text": (
        "pokemon_species_flavor_text.csv"
    ),
    "move_flavor_text": (
        "move_flavor_text.csv"
    ),
    "evolution_chains": (
        "evolution_chains.csv"
    ),
    "evolution_triggers": (
        "evolution_triggers.csv"
    ),
}


# =============================================================================
# CONSTANTS
# =============================================================================

NATIONAL_DEX_LIMIT = OFFICIAL_NATIONAL_DEX_LIMIT

REQUEST_TIMEOUT = 120

USER_AGENT = (
    "KrampusRPG-PokemonCatalogImporter/2.0"
)


# =============================================================================
# DEFAULT VARIANTS
# =============================================================================

def import_default_variants(
    connection: sqlite3.Connection,
) -> None:
    """
    Synchronize the canonical Krampus RPG variants.

    Variants are intentionally separate from official Pokémon forms.
    """

    for variant in DEFAULT_VARIANTS:
        if isinstance(variant, dict):
            variant_id = variant["id"]
            name = variant["name"]
            sprite_suffix = variant.get(
                "sprite_suffix",
                "",
            )
            description = variant.get(
                "description",
                "",
            )
            is_custom = int(
                variant.get(
                    "is_custom",
                    1,
                )
            )
        else:
            (
                variant_id,
                name,
                sprite_suffix,
                description,
                is_custom,
            ) = variant

        connection.execute(
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

    connection.commit()


# =============================================================================
# CSV HELPERS
# =============================================================================

def download_csv(
    filename: str,
) -> list[dict[str, str]]:
    """
    Download one PokéAPI CSV dataset.
    """

    url = (
        f"{POKEAPI_CSV_BASE}/{filename}"
    )

    print(
        f"Downloading {filename}..."
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            raw = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Unable to download {filename}: {exc}"
        ) from exc

    text = raw.decode(
        "utf-8-sig"
    )

    return list(
        csv.DictReader(
            text.splitlines()
        )
    )


def download_all_csvs(
    requested: set[str] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """
    Download all required datasets.

    A failed optional dataset does not necessarily abort the complete import.
    Core datasets are validated separately.
    """

    datasets: dict[
        str,
        list[dict[str, str]],
    ] = {}

    for key, filename in CSV_FILES.items():

        if requested and key not in requested:
            continue

        try:
            datasets[key] = download_csv(
                filename
            )
        except Exception as exc:
            print(
                f"WARNING: {exc}"
            )
            datasets[key] = []

    return datasets


# =============================================================================
# VALUE HELPERS
# =============================================================================

def to_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        if value is None:
            return default

        if str(value).strip() == "":
            return default

        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def to_optional_int(
    value: Any,
) -> int | None:
    try:
        if value is None:
            return None

        if str(value).strip() == "":
            return None

        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def clean_identifier(
    value: str | None,
) -> str:
    if not value:
        return ""

    return value.strip().lower()


def slugify(
    value: str,
) -> str:
    """
    Produce stable database identifiers.

    PokéAPI identifiers are already mostly slug-compatible, but this also
    handles unusual future/fakemon names safely.
    """

    value = (
        value
        .strip()
        .lower()
    )

    value = (
        value
        .replace("♀", "-female")
        .replace("♂", "-male")
    )

    value = re.sub(
        r"[^a-z0-9]+",
        "-",
        value,
    )

    value = re.sub(
        r"-+",
        "-",
        value,
    )

    return value.strip("-")


def readable_name(
    value: str | None,
) -> str:
    if not value:
        return ""

    value = (
        value
        .replace("-", " ")
        .replace("_", " ")
    )

    return " ".join(
        word.capitalize()
        for word in value.split()
    )


# =============================================================================
# GENERATION
# =============================================================================

def generation_from_dex(
    national_dex: int,
) -> int:

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


# =============================================================================
# SPECIES LOOKUPS
# =============================================================================

def build_species_lookup(
    species_rows: list[dict[str, str]],
) -> dict[int, str]:
    """
    Map PokéAPI species IDs to stable Krampus species identifiers.
    """

    result: dict[int, str] = {}

    for row in species_rows:
        species_id = to_int(
            row.get("id")
        )

        identifier = clean_identifier(
            row.get("identifier")
        )

        if species_id <= 0:
            continue

        if not identifier:
            continue

        result[species_id] = slugify(
            identifier
        )

    return result


def build_species_dex_lookup(
    species_rows: list[dict[str, str]],
) -> dict[int, int]:
    """
    Map PokéAPI species ID to National Dex number.
    """

    result: dict[int, int] = {}

    for row in species_rows:

        species_id = to_int(
            row.get("id")
        )

        national_dex = to_int(
            row.get("id")
        )

        if (
            species_id > 0
            and 1 <= national_dex <= NATIONAL_DEX_LIMIT
        ):
            result[species_id] = national_dex

    return result


def build_pokemon_species_mapping(
    pokemon_rows: list[dict[str, str]],
    species_rows: list[dict[str, str]],
) -> dict[int, str]:
    """
    CRITICAL FORM MAPPING.

    PokéAPI has:

        pokemon.id
        pokemon.species_id

    Alternate forms have their own pokemon IDs.

    Therefore we must map:

        EVERY pokemon ID
            ->
        its species ID
            ->
        our stable species identifier

    We must NOT assume Pokémon ID == species ID.
    """

    species_by_numeric_id = (
        build_species_lookup(
            species_rows
        )
    )

    result: dict[int, str] = {}

    for row in pokemon_rows:

        pokemon_id = to_int(
            row.get("id")
        )

        species_numeric_id = to_int(
            row.get("species_id")
        )

        if pokemon_id <= 0:
            continue

        species_identifier = (
            species_by_numeric_id.get(
                species_numeric_id
            )
        )

        if not species_identifier:
            continue

        result[pokemon_id] = (
            species_identifier
        )

    return result


# =============================================================================
# TYPES
# =============================================================================

def import_types(
    connection: sqlite3.Connection,
    rows: list[dict[str, str]],
) -> dict[int, str]:

    type_lookup: dict[
        int,
        str,
    ] = {}

    for row in rows:

        numeric_id = to_int(
            row.get("id")
        )

        identifier = clean_identifier(
            row.get("identifier")
        )

        if numeric_id <= 0:
            continue

        if not identifier:
            continue

        type_lookup[
            numeric_id
        ] = str(numeric_id)

        connection.execute(
            """
            INSERT INTO pokemon_types (
                id,
                name
            )
            VALUES (?, ?)

            ON CONFLICT(id)
            DO UPDATE SET
                name = excluded.name
            """,
            (
                numeric_id,
                identifier,
            ),
        )

    connection.commit()

    return type_lookup


# =============================================================================
# SPECIES
# =============================================================================

def import_species(
    connection: sqlite3.Connection,
    species_rows: list[dict[str, str]],
) -> dict[int, str]:
    """
    Import exactly the official species represented by
    pokemon_species.csv.

    National Dex comes from the species identifier itself.
    """

    species_by_numeric_id: dict[
        int,
        str,
    ] = {}

    imported = 0

    for row in species_rows:

        species_numeric_id = to_int(
            row.get("id")
        )

        identifier = clean_identifier(
            row.get("identifier")
        )

        if species_numeric_id <= 0:
            continue

        if not identifier:
            continue

        if (
            species_numeric_id
            > NATIONAL_DEX_LIMIT
        ):
            continue

        species_id = slugify(
            identifier
        )

        name = readable_name(
            identifier
        )

        generation = (
            generation_from_dex(
                species_numeric_id
            )
        )

        gender_rate = to_int(
            row.get("gender_rate"),
            -1,
        )

        connection.execute(
            """
            INSERT INTO pokemon_species (
                id,
                national_dex,
                name,
                generation,
                gender_rate,
                is_fakemon,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, 0, 1)

            ON CONFLICT(id)
            DO UPDATE SET
                national_dex =
                    excluded.national_dex,
                name =
                    excluded.name,
                generation =
                    excluded.generation,
                gender_rate =
                    excluded.gender_rate,
                is_fakemon = 0,
                is_active = 1
            """,
            (
                species_id,
                species_numeric_id,
                name,
                generation,
                gender_rate,
            ),
        )

        species_by_numeric_id[
            species_numeric_id
        ] = species_id

        imported += 1

    connection.commit()

    print(
        f"Imported {imported} species."
    )

    return species_by_numeric_id


# =============================================================================
# SPECIES DESCRIPTIONS
# =============================================================================

def import_species_descriptions(
    connection: sqlite3.Connection,
    flavor_rows: list[dict[str, str]],
    species_lookup: dict[int, str],
) -> int:
    """
    Import species descriptions.

    PokéAPI has descriptions in multiple languages and versions.

    We prefer English and keep one clean description per species.
    """

    descriptions: dict[
        int,
        str,
    ] = {}

    for row in flavor_rows:

        species_id = to_int(
            row.get("species_id")
        )

        language_id = to_int(
            row.get("language_id")
        )

        flavor_text = (
            row.get(
                "flavor_text",
                "",
            )
            .strip()
        )

        if species_id <= 0:
            continue

        if not flavor_text:
            continue

        # PokéAPI language ID 9 is English.
        if language_id != 9:
            continue

        # Keep the first usable description.
        descriptions.setdefault(
            species_id,
            flavor_text,
        )

    updated = 0

    for numeric_species_id, description in descriptions.items():

        species_key = species_lookup.get(
            numeric_species_id
        )

        if not species_key:
            continue

        description = (
            description
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("\f", " ")
        )

        description = re.sub(
            r"\s+",
            " ",
            description,
        ).strip()

        connection.execute(
            """
            UPDATE pokemon_species

            SET description = ?

            WHERE id = ?
            """,
            (
                description,
                species_key,
            ),
        )

        updated += 1

    connection.commit()

    print(
        f"Imported descriptions for {updated} species."
    )

    return updated


# =============================================================================
# BASE STATS
# =============================================================================

def import_base_stats(
    connection: sqlite3.Connection,
    pokemon_rows: list[dict[str, str]],
    stat_rows: list[dict[str, str]],
    species_lookup: dict[int, str],
) -> int:
    """
    Import base stats for the default Pokémon representation of each species.

    pokemon_stats.csv identifies:

        pokemon_id
        stat_id
        base_stat

    We use the default Pokémon record associated with the species.
    """

    pokemon_to_species: dict[
        int,
        int,
    ] = {}

    for row in pokemon_rows:

        pokemon_id = to_int(
            row.get("id")
        )

        species_id = to_int(
            row.get("species_id")
        )

        if (
            pokemon_id > 0
            and species_id > 0
        ):
            pokemon_to_species[
                pokemon_id
            ] = species_id

    stats_by_pokemon: dict[
        int,
        dict[int, int],
    ] = {}

    for row in stat_rows:

        pokemon_id = to_int(
            row.get("pokemon_id")
        )

        stat_id = to_int(
            row.get("stat_id")
        )

        base_stat = to_int(
            row.get("base_stat")
        )

        if (
            pokemon_id <= 0
            or stat_id <= 0
        ):
            continue

        stats_by_pokemon.setdefault(
            pokemon_id,
            {},
        )[stat_id] = base_stat

    # -------------------------------------------------------------------------
    # Find the default Pokémon record for each species.
    # -------------------------------------------------------------------------

    default_pokemon_for_species: dict[
        int,
        int,
    ] = {}

    for row in pokemon_rows:

        pokemon_id = to_int(
            row.get("id")
        )

        species_id = to_int(
            row.get("species_id")
        )

        is_default = to_int(
            row.get("is_default")
        )

        if (
            pokemon_id <= 0
            or species_id <= 0
        ):
            continue

        if is_default == 1:
            default_pokemon_for_species[
                species_id
            ] = pokemon_id

    updated = 0

    for species_numeric_id, species_key in species_lookup.items():

        pokemon_id = (
            default_pokemon_for_species.get(
                species_numeric_id
            )
        )

        if pokemon_id is None:
            continue

        stats = stats_by_pokemon.get(
            pokemon_id
        )

        if not stats:
            continue

        connection.execute(
            """
            UPDATE pokemon_species

            SET
                base_hp = ?,
                base_attack = ?,
                base_defense = ?,
                base_sp_attack = ?,
                base_sp_defense = ?,
                base_speed = ?

            WHERE id = ?
            """,
            (
                stats.get(1, 1),
                stats.get(2, 1),
                stats.get(3, 1),
                stats.get(4, 1),
                stats.get(5, 1),
                stats.get(6, 1),
                species_key,
            ),
        )

        updated += 1

    connection.commit()

    print(
        f"Imported base stats for {updated} species."
    )

    return updated


# =============================================================================
# SPECIES TYPES
# =============================================================================

def import_species_types(
    connection: sqlite3.Connection,
    pokemon_type_rows: list[dict[str, str]],
    pokemon_rows: list[dict[str, str]],
    type_lookup: dict[int, str],
    pokemon_to_species: dict[int, str],
) -> int:
    """
    Import types using every Pokémon's species relationship.

    Default forms are preferred, but alternate forms are allowed to provide
    additional mappings where appropriate.
    """

    inserted: set[
        tuple[str, int]
    ] = set()

    rows_by_species: dict[
        str,
        list[tuple[int, int]],
    ] = {}

    for row in pokemon_type_rows:

        pokemon_id = to_int(
            row.get("pokemon_id")
        )

        type_id = to_int(
            row.get("type_id")
        )

        slot = to_int(
            row.get("slot"),
            1,
        )

        species_key = pokemon_to_species.get(
            pokemon_id
        )

        if not species_key:
            continue

        if type_id not in type_lookup:
            continue

        rows_by_species.setdefault(
            species_key,
            [],
        ).append(
            (
                slot,
                type_id,
            )
        )

    # -------------------------------------------------------------------------
    # Prefer types from the default form.
    # -------------------------------------------------------------------------

    default_pokemon_ids: set[int] = set()

    for row in pokemon_rows:

        pokemon_id = to_int(
            row.get("id")
        )

        if (
            pokemon_id > 0
            and to_int(
                row.get("is_default")
            ) == 1
        ):
            default_pokemon_ids.add(
                pokemon_id
            )

    default_type_rows: dict[
        str,
        list[tuple[int, int]],
    ] = {}

    for row in pokemon_type_rows:

        pokemon_id = to_int(
            row.get("pokemon_id")
        )

        if pokemon_id not in default_pokemon_ids:
            continue

        species_key = pokemon_to_species.get(
            pokemon_id
        )

        type_id = to_int(
            row.get("type_id")
        )

        slot = to_int(
            row.get("slot"),
            1,
        )

        if (
            species_key
            and type_id in type_lookup
        ):
            default_type_rows.setdefault(
                species_key,
                [],
            ).append(
                (
                    slot,
                    type_id,
                )
            )

    # -------------------------------------------------------------------------
    # Insert default-form types first.
    # -------------------------------------------------------------------------

    for species_key, type_rows in default_type_rows.items():

        for slot, type_id in sorted(
            type_rows
        ):

            if (
                species_key,
                slot,
            ) in inserted:
                continue

            connection.execute(
                """
                INSERT INTO pokemon_species_types (
                    species_id,
                    type_id,
                    slot
                )
                VALUES (?, ?, ?)

                ON CONFLICT(
                    species_id,
                    type_id
                )
                DO UPDATE SET
                    slot = excluded.slot
                """,
                (
                    species_key,
                    type_id,
                    slot,
                ),
            )

            inserted.add(
                (
                    species_key,
                    slot,
                )
            )

    # -------------------------------------------------------------------------
    # Fill missing species types from available records.
    # -------------------------------------------------------------------------

    for species_key, type_rows in rows_by_species.items():

        for slot, type_id in sorted(
            type_rows
        ):

            if (
                species_key,
                slot,
            ) in inserted:
                continue

            connection.execute(
                """
                INSERT INTO pokemon_species_types (
                    species_id,
                    type_id,
                    slot
                )
                VALUES (?, ?, ?)

                ON CONFLICT(
                    species_id,
                    type_id
                )
                DO UPDATE SET
                    slot = excluded.slot
                """,
                (
                    species_key,
                    type_id,
                    slot,
                ),
            )

            inserted.add(
                (
                    species_key,
                    slot,
                )
            )

    connection.commit()

    print(
        f"Imported {len(inserted)} species type slots."
    )

    return len(inserted)


# =============================================================================
# ABILITIES
# =============================================================================

def import_abilities(
    connection: sqlite3.Connection,
    ability_rows: list[dict[str, str]],
) -> None:

    for row in ability_rows:

        ability_numeric_id = to_int(
            row.get("id")
        )

        identifier = clean_identifier(
            row.get("identifier")
        )

        if (
            ability_numeric_id <= 0
            or not identifier
        ):
            continue

        ability_id = slugify(
            identifier
        )

        connection.execute(
            """
            INSERT INTO pokemon_abilities (
                id,
                name
            )
            VALUES (?, ?)

            ON CONFLICT(id)
            DO UPDATE SET
                name = excluded.name
            """,
            (
                ability_id,
                readable_name(
                    identifier
                ),
            ),
        )

    connection.commit()


def import_species_abilities(
    connection: sqlite3.Connection,
    pokemon_ability_rows: list[dict[str, str]],
    pokemon_to_species: dict[int, str],
    ability_rows: list[dict[str, str]],
) -> int:

    ability_by_numeric_id: dict[
        int,
        str,
    ] = {}

    for row in ability_rows:

        numeric_id = to_int(
            row.get("id")
        )

        identifier = clean_identifier(
            row.get("identifier")
        )

        if (
            numeric_id > 0
            and identifier
        ):
            ability_by_numeric_id[
                numeric_id
            ] = slugify(
                identifier
            )

    # Remove stale catalog mappings before rebuilding them.
    connection.execute(
        """
        DELETE FROM pokemon_species_abilities
        """
    )

    # -------------------------------------------------------------------------
    # Group abilities by species.
    # -------------------------------------------------------------------------

    grouped: dict[
        str,
        list[tuple[int, str, int]],
    ] = {}

    for row in pokemon_ability_rows:

        pokemon_id = to_int(
            row.get("pokemon_id")
        )

        ability_numeric_id = to_int(
            row.get("ability_id")
        )

        slot = to_int(
            row.get("slot"),
            1,
        )

        is_hidden = to_int(
            row.get("is_hidden")
        )

        species_key = pokemon_to_species.get(
            pokemon_id
        )

        ability_key = ability_by_numeric_id.get(
            ability_numeric_id
        )

        if (
            not species_key
            or not ability_key
        ):
            continue

        grouped.setdefault(
            species_key,
            [],
        ).append(
            (
                slot,
                ability_key,
                is_hidden,
            )
        )

    inserted = 0

    for species_key, abilities in grouped.items():

        seen_slots: set[int] = set()

        for (
            slot,
            ability_key,
            is_hidden,
        ) in sorted(
            abilities,
            key=lambda item: (
                item[0],
                item[1],
            ),
        ):

            if slot in seen_slots:
                continue

            connection.execute(
                """
                INSERT INTO pokemon_species_abilities (
                    species_id,
                    ability_id,
                    slot,
                    is_hidden
                )
                VALUES (?, ?, ?, ?)

                ON CONFLICT(
                    species_id,
                    ability_id
                )
                DO UPDATE SET
                    slot = excluded.slot,
                    is_hidden = excluded.is_hidden
                """,
                (
                    species_key,
                    ability_key,
                    slot,
                    is_hidden,
                ),
            )

            seen_slots.add(
                slot
            )

            inserted += 1

    connection.commit()

    print(
        f"Imported {inserted} species ability slots."
    )

    return inserted


# =============================================================================
# FORMS
# =============================================================================

def import_forms(
    connection: sqlite3.Connection,
    pokemon_form_rows: list[dict[str, str]],
    pokemon_rows: list[dict[str, str]],
    pokemon_to_species: dict[int, str],
) -> int:
    """
    Import official Pokémon forms.

    This is the corrected form architecture.

    We do NOT use:

        pokemon_id <= 1025

    to determine species.

    Instead:

        pokemon_id
            ->
        species_id
            ->
        species key

    This correctly handles alternate Pokémon records such as:

        Mega
        G-Max
        regional
        female
        cosmetic
        battle-only
        other official forms
    """

    # -------------------------------------------------------------------------
    # Form metadata from pokemon_forms.csv
    # -------------------------------------------------------------------------

    form_metadata: dict[
        int,
        dict[str, Any],
    ] = {}

    for row in pokemon_form_rows:

        form_numeric_id = to_int(
            row.get("id")
        )

        pokemon_id = to_int(
            row.get("pokemon_id")
        )

        if (
            form_numeric_id <= 0
            or pokemon_id <= 0
        ):
            continue

        form_metadata[
            pokemon_id
        ] = {
            "form_id": form_numeric_id,
            "form_identifier": clean_identifier(
                row.get("form_identifier")
            ),
            "form_name": clean_identifier(
                row.get("form_name")
            ),
            "is_default": to_int(
                row.get("is_default")
            ),
            "is_battle_only": to_int(
                row.get("is_battle_only")
            ),
            "is_mega": to_int(
                row.get("is_mega")
            ),
            "is_gmax": to_int(
                row.get("is_gmax")
            ),
            "order": to_int(
                row.get("order")
            ),
        }

    # -------------------------------------------------------------------------
    # Pokemon records contain the stable Pokémon identifier.
    # -------------------------------------------------------------------------

    imported = 0

    for row in pokemon_rows:

        pokemon_id = to_int(
            row.get("id")
        )

        identifier = clean_identifier(
            row.get("identifier")
        )

        species_key = pokemon_to_species.get(
            pokemon_id
        )

        if (
            pokemon_id <= 0
            or not identifier
            or not species_key
        ):
            continue

        metadata = form_metadata.get(
            pokemon_id,
            {},
        )

        is_default = int(
            metadata.get(
                "is_default",
                to_int(
                    row.get(
                        "is_default"
                    )
                ),
            )
        )

        form_identifier = clean_identifier(
            metadata.get(
                "form_identifier",
                "",
            )
        )

        form_name = clean_identifier(
            metadata.get(
                "form_name",
                "",
            )
        )

        # Default Pokémon form.
        if not form_identifier:
            form_identifier = (
                "default"
                if is_default
                else slugify(
                    identifier
                )
            )

        # Stable form ID.
        #
        # Use the Pokémon identifier rather than the numeric form ID so
        # database IDs remain readable.
        form_id = slugify(
            identifier
        )

        display_name = readable_name(
            identifier
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

            ON CONFLICT(id)
            DO UPDATE SET
                species_id =
                    excluded.species_id,
                name =
                    excluded.name,
                form_name =
                    excluded.form_name,
                display_name =
                    excluded.display_name,
                form_identifier =
                    excluded.form_identifier,
                is_default =
                    excluded.is_default,
                is_battle_only =
                    excluded.is_battle_only,
                is_mega =
                    excluded.is_mega,
                is_gmax =
                    excluded.is_gmax,
                sort_order =
                    excluded.sort_order
            """,
            (
                form_id,
                species_key,
                identifier,
                form_name,
                display_name,
                form_identifier,
                is_default,
                int(
                    metadata.get(
                        "is_battle_only",
                        0,
                    )
                ),
                int(
                    metadata.get(
                        "is_mega",
                        0,
                    )
                ),
                int(
                    metadata.get(
                        "is_gmax",
                        0,
                    )
                ),
                int(
                    metadata.get(
                        "order",
                        pokemon_id,
                    )
                ),
            ),
        )

        imported += 1

    connection.commit()

    print(
        f"Imported {imported} official forms."
    )

    return imported


# =============================================================================
# MOVES
# =============================================================================

def import_moves(
    connection: sqlite3.Connection,
    move_rows: list[dict[str, str]],
    type_lookup: dict[int, str],
) -> dict[int, str]:

    move_lookup: dict[
        int,
        str,
    ] = {}

    imported = 0

    for row in move_rows:

        numeric_id = to_int(
            row.get("id")
        )

        identifier = clean_identifier(
            row.get("identifier")
        )

        if (
            numeric_id <= 0
            or not identifier
        ):
            continue

        move_id = slugify(
            identifier
        )

        type_numeric_id = to_int(
            row.get("type_id")
        )

        type_identifier = (
            type_lookup.get(
                type_numeric_id,
                "normal",
            )
        )

        category = clean_identifier(
            row.get("damage_class_id")
        )

        # PokéAPI damage class IDs:
        #
        # 1 = status
        # 2 = physical
        # 3 = special
        #
        damage_class_id = to_int(
            row.get("damage_class_id")
        )

        if damage_class_id == 2:
            category = "physical"
        elif damage_class_id == 3:
            category = "special"
        else:
            category = "status"

        power = to_optional_int(
            row.get("power")
        )

        accuracy = to_optional_int(
            row.get("accuracy")
        )

        max_pp = to_int(
            row.get("pp")
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

            ON CONFLICT(id)
            DO UPDATE SET
                name =
                    excluded.name,
                type_id =
                    excluded.type_id,
                category =
                    excluded.category,
                power =
                    excluded.power,
                accuracy =
                    excluded.accuracy,
                max_pp =
                    excluded.max_pp
            """,
            (
                move_id,
                readable_name(
                    identifier
                ),
                type_identifier,
                category,
                power,
                accuracy,
                max_pp,
            ),
        )

        move_lookup[
            numeric_id
        ] = move_id

        imported += 1

    connection.commit()

    print(
        f"Imported {imported} moves."
    )

    return move_lookup


# =============================================================================
# MOVE DESCRIPTIONS
# =============================================================================

def import_move_descriptions(
    connection: sqlite3.Connection,
    flavor_rows: list[dict[str, str]],
    move_lookup: dict[int, str],
) -> int:
    """
    Actually persist move descriptions.

    The earlier Claude foundation downloaded these descriptions but did not
    reliably write them into the moves table.
    """

    descriptions: dict[
        int,
        str,
    ] = {}

    for row in flavor_rows:

        move_numeric_id = to_int(
            row.get("move_id")
        )

        language_id = to_int(
            row.get("language_id")
        )

        text = (
            row.get(
                "flavor_text",
                "",
            )
            .strip()
        )

        if (
            move_numeric_id <= 0
            or not text
        ):
            continue

        if language_id != 9:
            continue

        descriptions.setdefault(
            move_numeric_id,
            text,
        )

    updated = 0

    for numeric_id, description in descriptions.items():

        move_id = move_lookup.get(
            numeric_id
        )

        if not move_id:
            continue

        description = (
            description
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("\f", " ")
        )

        description = re.sub(
            r"\s+",
            " ",
            description,
        ).strip()

        connection.execute(
            """
            UPDATE moves
            SET description = ?
            WHERE id = ?
            """,
            (
                description,
                move_id,
            ),
        )

        updated += 1

    connection.commit()

    print(
        f"Imported descriptions for {updated} moves."
    )

    return updated


# =============================================================================
# LEARNSETS
# =============================================================================

def import_learnsets(
    connection: sqlite3.Connection,
    pokemon_move_rows: list[dict[str, str]],
    pokemon_to_species: dict[int, str],
    move_lookup: dict[int, str],
) -> int:

    connection.execute(
        """
        DELETE FROM pokemon_species_moves
        """
    )

    inserted = 0

    for row in pokemon_move_rows:

        pokemon_id = to_int(
            row.get("pokemon_id")
        )

        move_numeric_id = to_int(
            row.get("move_id")
        )

        species_key = pokemon_to_species.get(
            pokemon_id
        )

        move_id = move_lookup.get(
            move_numeric_id
        )

        if (
            not species_key
            or not move_id
        ):
            continue

        learn_method_id = to_int(
            row.get(
                "pokemon_move_method_id"
            )
        )

        version_group_id = to_int(
            row.get(
                "version_group_id"
            )
        )

        level = to_int(
            row.get(
                "level",
            )
        )

        # PokéAPI move method IDs:
        #
        # 1 = level-up
        # 2 = egg
        # 3 = tutor
        # 4 = machine
        #
        method_map = {
            1: "level-up",
            2: "egg",
            3: "tutor",
            4: "machine",
        }

        learn_method = method_map.get(
            learn_method_id,
            "unknown",
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
                move_id,
                learn_method,
                level,
                version_group_id,
            ),
        )

        inserted += 1

    connection.commit()

    print(
        f"Imported {inserted} learnset entries."
    )

    return inserted


# =============================================================================
# EVOLUTION DATA
# =============================================================================

def import_evolutions(
    connection: sqlite3.Connection,
    pokemon_rows: list[dict[str, str]],
    species_rows: list[dict[str, str]],
    pokemon_to_species: dict[int, str],
    evolution_chains: list[dict[str, str]],
) -> int:
    """
    Import evolution relationships.

    The CSV evolution-chain data identifies chains, but the detailed
    evolution requirements live in the API's evolution-chain JSON.

    This importer therefore uses the PokéAPI chain endpoint for each chain.
    """

    # -------------------------------------------------------------------------
    # species numeric ID -> species key
    # -------------------------------------------------------------------------

    species_lookup = build_species_lookup(
        species_rows
    )

    # -------------------------------------------------------------------------
    # evolution chain IDs
    # -------------------------------------------------------------------------

    chain_ids: set[int] = set()

    for row in species_rows:

        chain_id = to_int(
            row.get("evolution_chain_id")
        )

        species_id = to_int(
            row.get("id")
        )

        if (
            chain_id > 0
            and species_id in species_lookup
        ):
            chain_ids.add(
                chain_id
            )

    if not chain_ids:
        print(
            "No evolution chain IDs were available."
        )

        return 0

    connection.execute(
        """
        DELETE FROM pokemon_evolutions
        """
    )

    inserted = 0

    # -------------------------------------------------------------------------
    # Download each evolution chain.
    # -------------------------------------------------------------------------

    for chain_id in sorted(
        chain_ids
    ):

        url = (
            "https://pokeapi.co/api/v2/"
            f"evolution-chain/{chain_id}/"
        )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                import json

                chain = json.loads(
                    response.read().decode(
                        "utf-8"
                    )
                )

        except Exception as exc:
            print(
                f"WARNING: Could not load evolution chain "
                f"{chain_id}: {exc}"
            )
            continue

        chain_root = chain.get(
            "chain"
        )

        if not chain_root:
            continue

        inserted += import_evolution_node(
            connection,
            chain_root,
            species_lookup,
        )

    connection.commit()

    print(
        f"Imported {inserted} evolution relationships."
    )

    return inserted


def import_evolution_node(
    connection: sqlite3.Connection,
    node: dict[str, Any],
    species_lookup: dict[int, str],
) -> int:

    count = 0

    species_url = (
        node.get(
            "species",
            {},
        )
        .get(
            "url",
            "",
        )
    )

    from_species_numeric_id = extract_api_id(
        species_url
    )

    from_species_id = species_lookup.get(
        from_species_numeric_id
    )

    if from_species_id:

        for evolution in node.get(
            "evolution_details",
            [],
        ):

            target_url = (
                evolution.get(
                    "target_species_id"
                )
            )

            if target_url is None:
                continue

            to_species_id = species_lookup.get(
                to_int(
                    target_url
                )
            )

            if not to_species_id:
                continue

            trigger = clean_identifier(
                evolution.get(
                    "trigger_name",
                    ""
                )
            )

            minimum_level = to_optional_int(
                evolution.get(
                    "min_level"
                )
            )

            item_id = (
                evolution.get(
                    "item_name"
                )
                or None
            )

            gender = (
                evolution.get(
                    "gender"
                )
            )

            time_of_day = (
                evolution.get(
                    "time_of_day"
                )
                or None
            )

            minimum_happiness = (
                to_optional_int(
                    evolution.get(
                        "min_happiness"
                    )
                )
            )

            minimum_beauty = (
                to_optional_int(
                    evolution.get(
                        "min_beauty"
                    )
                )
            )

            minimum_affection = (
                to_optional_int(
                    evolution.get(
                        "min_affection"
                    )
                )
            )

            known_move_id = (
                evolution.get(
                    "known_move_name"
                )
                or None
            )

            known_move_type = (
                evolution.get(
                    "known_move_type"
                )
                or None
            )

            location = (
                evolution.get(
                    "location_name"
                )
                or None
            )

            relative_physical_stats = (
                to_optional_int(
                    evolution.get(
                        "relative_physical_stats"
                    )
                )
            )

            trade_species_id = (
                evolution.get(
                    "trade_species_id"
                )
                or None
            )

            raw_condition = (
                str(evolution)
            )

            connection.execute(
                """
                INSERT INTO pokemon_evolutions (
                    from_species_id,
                    to_species_id,
                    trigger,
                    minimum_level,
                    item_id,
                    gender,
                    time_of_day,
                    minimum_happiness,
                    minimum_beauty,
                    minimum_affection,
                    known_move_id,
                    known_move_type,
                    location,
                    relative_physical_stats,
                    trade_species_id,
                    raw_condition
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    from_species_id,
                    to_species_id,
                    trigger,
                    minimum_level,
                    item_id,
                    gender,
                    time_of_day,
                    minimum_happiness,
                    minimum_beauty,
                    minimum_affection,
                    known_move_id,
                    known_move_type,
                    location,
                    relative_physical_stats,
                    trade_species_id,
                    raw_condition,
                ),
            )

            count += 1

    for child in node.get(
        "evolves_to",
        [],
    ):

        count += import_evolution_node(
            connection,
            child,
            species_lookup,
        )

    return count


def extract_api_id(
    url: str | None,
) -> int:
    if not url:
        return 0

    match = re.search(
        r"/(\d+)/?$",
        url,
    )

    if not match:
        return 0

    return to_int(
        match.group(1)
    )


# =============================================================================
# SPRITE INVENTORY
# =============================================================================

def file_sha256(
    path: Path,
) -> str:

    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:

        while True:
            chunk = handle.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()


def git_blob_sha1(
    path: Path,
) -> str:

    data = path.read_bytes()

    header = (
        f"blob {len(data)}\0"
        .encode(
            "utf-8"
        )
    )

    return hashlib.sha1(
        header + data
    ).hexdigest()


# =============================================================================
# SPRITE NAME RESOLUTION
# =============================================================================

def build_species_name_lookup(
    connection: sqlite3.Connection,
) -> dict[str, str]:

    rows = connection.execute(
        """
        SELECT
            id,
            name
        FROM pokemon_species
        """
    ).fetchall()

    result: dict[
        str,
        str,
    ] = {}

    for row in rows:

        result[
            clean_identifier(
                row["name"]
            )
        ] = row["id"]

        result[
            clean_identifier(
                row["id"]
            )
        ] = row["id"]

    return result


def resolve_sprite_components(
    filename: str,
    species_lookup: dict[str, str],
    form_ids: set[str],
    variant_ids: set[str],
) -> tuple[
    str | None,
    str | None,
    str | None,
]:

    stem = Path(
        filename
    ).stem.lower()

    # -------------------------------------------------------------------------
    # Determine variant from suffix.
    # -------------------------------------------------------------------------

    variant_id: str | None = None

    for candidate in sorted(
        variant_ids,
        key=len,
        reverse=True,
    ):

        suffix = (
            "-"
            + candidate
        )

        if (
            candidate != "normal"
            and stem.endswith(
                suffix
            )
        ):
            variant_id = candidate

            stem = stem[
                : -len(suffix)
            ]

            break

    if variant_id is None:
        variant_id = "normal"

    # -------------------------------------------------------------------------
    # Exact form match.
    # -------------------------------------------------------------------------

    form_id: str | None = None

    if stem in form_ids:
        form_id = stem

        species_id = None

        # Form IDs are based on Pokémon identifiers. Find their species.
        row = None

        # This is intentionally resolved later by the database query.
        return (
            None,
            form_id,
            variant_id,
        )

    # -------------------------------------------------------------------------
    # Species match.
    # -------------------------------------------------------------------------

    species_id = species_lookup.get(
        stem
    )

    if species_id:
        return (
            species_id,
            None,
            variant_id,
        )

    # -------------------------------------------------------------------------
    # Attempt to identify species from form naming.
    #
    # Examples:
    #
    #   charizard-mega-x
    #   meowth-galar
    #   growlithe-hisui
    #
    # Longest known species prefix wins.
    # -------------------------------------------------------------------------

    matching_species = sorted(
        (
            key
            for key in species_lookup
            if stem == key
            or stem.startswith(
                key + "-"
            )
        ),
        key=len,
        reverse=True,
    )

    if matching_species:
        species_key = matching_species[0]

        possible_form = stem

        if possible_form in form_ids:
            form_id = possible_form

        return (
            species_lookup[
                species_key
            ],
            form_id,
            variant_id,
        )

    return (
        None,
        None,
        variant_id,
    )


def import_sprite_inventory(
    connection: sqlite3.Connection,
    sprite_root: Path,
) -> int:

    if not sprite_root.exists():
        print(
            f"Sprite directory does not exist: {sprite_root}"
        )

        return 0

    if not sprite_root.is_dir():
        print(
            f"Sprite path is not a directory: {sprite_root}"
        )

        return 0

    species_rows = connection.execute(
        """
        SELECT
            id,
            name
        FROM pokemon_species
        """
    ).fetchall()

    species_lookup: dict[
        str,
        str,
    ] = {}

    for row in species_rows:

        species_id = row["id"]

        species_lookup[
            clean_identifier(
                species_id
            )
        ] = species_id

        species_lookup[
            clean_identifier(
                row["name"]
            )
        ] = species_id

    form_rows = connection.execute(
        """
        SELECT
            id,
            species_id
        FROM pokemon_forms
        """
    ).fetchall()

    form_to_species: dict[
        str,
        str,
    ] = {}

    form_ids: set[str] = set()

    for row in form_rows:

        form_id = clean_identifier(
            row["id"]
        )

        form_ids.add(
            form_id
        )

        form_to_species[
            form_id
        ] = row["species_id"]

    variant_rows = connection.execute(
        """
        SELECT id
        FROM pokemon_variants
        WHERE is_active = 1
        """
    ).fetchall()

    variant_ids = {
        clean_identifier(
            row["id"]
        )
        for row in variant_rows
    }

    # -------------------------------------------------------------------------
    # Existing inventory is rebuilt from the actual sprite directory.
    # -------------------------------------------------------------------------

    connection.execute(
        """
        DELETE FROM pokemon_sprite_inventory
        """
    )

    all_files = sorted(
        path
        for path in sprite_root.rglob("*")
        if path.is_file()
        and path.suffix.lower()
        in {
            ".png",
            ".gif",
            ".webp",
        }
    )

    # -------------------------------------------------------------------------
    # Detect exact duplicates by Git blob hash.
    # -------------------------------------------------------------------------

    hash_groups: dict[
        str,
        list[Path],
    ] = {}

    for path in all_files:

        try:
            blob_hash = git_blob_sha1(
                path
            )
        except OSError:
            continue

        hash_groups.setdefault(
            blob_hash,
            [],
        ).append(
            path
        )

    imported = 0

    for path in all_files:

        try:
            relative_path = path.relative_to(
                sprite_root
            )

            relative_path_string = (
                relative_path
                .as_posix()
            )

            filename = path.name

            sha256 = file_sha256(
                path
            )

            blob_sha1 = git_blob_sha1(
                path
            )

        except OSError:
            continue

        species_id, form_id, variant_id = (
            resolve_sprite_components(
                filename,
                species_lookup,
                form_ids,
                variant_ids,
            )
        )

        # If a form was recognized, resolve its species.
        if form_id:
            species_id = (
                form_to_species.get(
                    form_id
                )
            )

        duplicate_files = (
            hash_groups.get(
                blob_sha1,
                [],
            )
        )

        is_duplicate = (
            1
            if len(
                duplicate_files
            ) > 1
            else 0
        )

        duplicate_group = (
            blob_sha1
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

            ON CONFLICT(relative_path)
            DO UPDATE SET
                species_id =
                    excluded.species_id,
                form_id =
                    excluded.form_id,
                variant_id =
                    excluded.variant_id,
                filename =
                    excluded.filename,
                file_sha256 =
                    excluded.file_sha256,
                git_blob_sha1 =
                    excluded.git_blob_sha1,
                is_duplicate =
                    excluded.is_duplicate,
                duplicate_group =
                    excluded.duplicate_group
            """,
            (
                species_id,
                form_id,
                variant_id,
                filename,
                relative_path_string,
                sha256,
                blob_sha1,
                is_duplicate,
                duplicate_group,
            ),
        )

        imported += 1

    connection.commit()

    print(
        f"Indexed {imported} sprite files."
    )

    return imported


# =============================================================================
# VALIDATION
# =============================================================================

def validate_catalog(
    connection: sqlite3.Connection,
) -> dict[str, Any]:

    def count(
        table: str,
    ) -> int:

        row = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {table}
            """
        ).fetchone()

        return int(
            row[0]
        )

    official_species = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_species
            WHERE
                is_fakemon = 0
                AND national_dex BETWEEN 1 AND ?
            """,
            (
                NATIONAL_DEX_LIMIT,
            ),
        ).fetchone()[0]
    )

    missing_forms = int(
        connection.execute(
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
                NATIONAL_DEX_LIMIT,
            ),
        ).fetchone()[0]
    )

    missing_types = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM pokemon_species s

            WHERE
                s.is_fakemon = 0
                AND s.national_dex BETWEEN 1 AND ?

                AND NOT EXISTS (
                    SELECT 1
                    FROM pokemon_species_types st
                    WHERE st.species_id = s.id
                )
            """,
            (
                NATIONAL_DEX_LIMIT,
            ),
        ).fetchone()[0]
    )

    result = {
        "species": official_species,
        "expected_species": NATIONAL_DEX_LIMIT,
        "types": count(
            "pokemon_types"
        ),
        "abilities": count(
            "pokemon_abilities"
        ),
        "forms": count(
            "pokemon_forms"
        ),
        "variants": count(
            "pokemon_variants"
        ),
        "moves": count(
            "moves"
        ),
        "learnsets": count(
            "pokemon_species_moves"
        ),
        "evolutions": count(
            "pokemon_evolutions"
        ),
        "sprites": count(
            "pokemon_sprite_inventory"
        ),
        "missing_default_forms": missing_forms,
        "missing_types": missing_types,
    }

    result["complete"] = (
        official_species
        == NATIONAL_DEX_LIMIT
        and missing_forms == 0
        and missing_types == 0
    )

    print()
    print(
        "========================================"
    )
    print(
        "KRAMPUS RPG POKÉMON CATALOG VALIDATION"
    )
    print(
        "========================================"
    )

    for key, value in result.items():
        print(
            f"{key}: {value}"
        )

    print(
        "========================================"
    )

    return result


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def open_database() -> sqlite3.Connection:
    connection = get_connection()

    connection.row_factory = sqlite3.Row

    return connection


# =============================================================================
# CORE IMPORT
# =============================================================================

def run_import(
    connection: sqlite3.Connection,
    datasets: dict[str, list[dict[str, str]]],
    sprite_root: Path | None,
    skip_sprites: bool,
    skip_evolutions: bool,
) -> dict[str, Any]:

    # -------------------------------------------------------------------------
    # Validate required data.
    # -------------------------------------------------------------------------

    required = [
        "types",
        "pokemon",
        "pokemon_species",
        "pokemon_types",
        "abilities",
        "pokemon_abilities",
        "pokemon_forms",
        "moves",
        "pokemon_moves",
        "pokemon_stats",
        "pokemon_species_flavor_text",
        "move_flavor_text",
    ]

    missing = [
        key
        for key in required
        if not datasets.get(key)
    ]

    if missing:
        raise RuntimeError(
            "Missing required PokéAPI datasets: "
            + ", ".join(missing)
        )

    # -------------------------------------------------------------------------
    # Schema.
    # -------------------------------------------------------------------------

    print()
    print(
        "Preparing catalog database..."
    )

    ensure_catalog_schema(
        connection
    )

    migrate_catalog_schema(
        connection
    )

    import_default_variants(
        connection
    )

    # -------------------------------------------------------------------------
    # Types.
    # -------------------------------------------------------------------------

    print()
    print(
        "Importing Pokémon types..."
    )

    type_lookup = import_types(
        connection,
        datasets["types"],
    )

    # -------------------------------------------------------------------------
    # Species.
    # -------------------------------------------------------------------------

    print()
    print(
        "Importing Pokémon species..."
    )

    species_lookup = import_species(
        connection,
        datasets["pokemon_species"],
    )

    # -------------------------------------------------------------------------
    # CRITICAL mapping.
    # -------------------------------------------------------------------------

    print()
    print(
        "Building Pokemon to species mapping..."
    )

    pokemon_to_species = (
        build_pokemon_species_mapping(
            datasets["pokemon"],
            datasets["pokemon_species"],
        )
    )

    print(
        f"Mapped {len(pokemon_to_species)} Pokémon records "
        "to species."
    )

    # -------------------------------------------------------------------------
    # Descriptions.
    # -------------------------------------------------------------------------

    print()
    print(
        "Importing species descriptions..."
    )

    import_species_descriptions(
        connection,
        datasets[
            "pokemon_species_flavor_text"
        ],
        species_lookup,
    )

    # -------------------------------------------------------------------------
    # Stats.
    # -------------------------------------------------------------------------

    print()
    print(
        "Importing base stats..."
    )

    import_base_stats(
        connection,
        datasets["pokemon"],
        datasets["pokemon_stats"],
        species_lookup,
    )

    # -------------------------------------------------------------------------
    # Types.
    # -------------------------------------------------------------------------

    print()
    print(
        "Importing species types..."
    )

    import_species_types(
        connection,
        datasets["pokemon_types"],
        datasets["pokemon"],
        type_lookup,
        pokemon_to_species,
    )

    # -------------------------------------------------------------------------
    # Abilities.
    # -------------------------------------------------------------------------

    print()
    print(
        "Importing abilities..."
    )

    import_abilities(
        connection,
        datasets["abilities"],
    )

    print(
        "Importing species abilities..."
    )

    import_species_abilities(
        connection,
        datasets["pokemon_abilities"],
        pokemon_to_species,
        datasets["abilities"],
    )

    # -------------------------------------------------------------------------
    # Forms.
    # -------------------------------------------------------------------------

    print()
    print(
        "Importing official Pokémon forms..."
    )

    import_forms(
        connection,
        datasets["pokemon_forms"],
        datasets["pokemon"],
        pokemon_to_species,
    )

    # -------------------------------------------------------------------------
    # Moves.
    # -------------------------------------------------------------------------

    print()
    print(
        "Importing moves..."
    )

    move_lookup = import_moves(
        connection,
        datasets["moves"],
        type_lookup,
    )

    # -------------------------------------------------------------------------
    # Move descriptions.
    # -------------------------------------------------------------------------

    print()
    print(
        "Importing move descriptions..."
    )

    import_move_descriptions(
        connection,
        datasets["move_flavor_text"],
        move_lookup,
    )

    # -------------------------------------------------------------------------
    # Learnsets.
    # -------------------------------------------------------------------------

    print()
    print(
        "Importing complete learnsets..."
    )

    import_learnsets(
        connection,
        datasets["pokemon_moves"],
        pokemon_to_species,
        move_lookup,
    )

    # -------------------------------------------------------------------------
    # Evolutions.
    # -------------------------------------------------------------------------

    if not skip_evolutions:

        print()
        print(
            "Importing evolution chains..."
        )

        import_evolutions(
            connection,
            datasets["pokemon"],
            datasets["pokemon_species"],
            pokemon_to_species,
            datasets.get(
                "evolution_chains",
                [],
            ),
        )

    else:
        print()
        print(
            "Skipping evolution import."
        )

    # -------------------------------------------------------------------------
    # Existing owned Pokémon.
    # -------------------------------------------------------------------------

    print()
    print(
        "Assigning default forms to existing Pokémon..."
    )

    updated_owned = (
        set_default_forms_for_owned_pokemon(
            connection
        )
    )

    print(
        f"Updated {updated_owned} owned Pokémon."
    )

    # -------------------------------------------------------------------------
    # Sprites.
    # -------------------------------------------------------------------------

    if (
        not skip_sprites
        and sprite_root is not None
    ):

        print()
        print(
            "Indexing Pokémon sprites..."
        )

        import_sprite_inventory(
            connection,
            sprite_root,
        )

    elif not skip_sprites:
        print()
        print(
            "No sprite directory supplied; "
            "sprite indexing skipped."
        )

    # -------------------------------------------------------------------------
    # Final validation.
    # -------------------------------------------------------------------------

    return validate_catalog(
        connection
    )


# =============================================================================
# COMMAND LINE
# =============================================================================

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Import the complete Pokémon catalog "
            "for Krampus RPG."
        )
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=Path(
            DATABASE_PATH
        ),
        help=(
            "SQLite database path."
        ),
    )

    parser.add_argument(
        "--sprites",
        type=Path,
        default=None,
        help=(
            "Pokémon sprite directory."
        ),
    )

    parser.add_argument(
        "--skip-sprites",
        action="store_true",
        help=(
            "Do not index sprite files."
        ),
    )

    parser.add_argument(
        "--skip-evolutions",
        action="store_true",
        help=(
            "Do not import evolution chains."
        ),
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help=(
            "Only validate the current catalog."
        ),
    )

    return parser.parse_args()


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:

    args = parse_args()

    print()
    print(
        "=========================================="
    )
    print(
        " KRAMPUS RPG - POKÉMON CATALOG IMPORTER"
    )
    print(
        "=========================================="
    )

    print(
        f"Database: {args.database}"
    )

    if args.sprites:
        print(
            f"Sprites:  {args.sprites}"
        )

    connection = open_database()

    try:

        ensure_catalog_schema(
            connection
        )

        migrate_catalog_schema(
            connection
        )

        if args.validate_only:

            validate_catalog(
                connection
            )

            return 0

        datasets = download_all_csvs()

        results = run_import(
            connection,
            datasets,
            args.sprites,
            args.skip_sprites,
            args.skip_evolutions,
        )

        print()
        print(
            "Pokémon catalog import finished."
        )

        if results.get(
            "complete"
        ):
            print(
                "CATALOG STATUS: COMPLETE"
            )
            return 0

        print(
            "CATALOG STATUS: REVIEW REQUIRED"
        )

        return 1

    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )