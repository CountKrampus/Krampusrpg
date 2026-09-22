from __future__ import annotations

import json
import random
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from .config import DATA_DIR
from .database import get_connection


# ============================================================
# PATHS / DATA
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

_DATA_CACHE: dict[str, Any] = {}


def load_data(filename: str) -> Any:
    """Load and cache a JSON file from the Data directory."""
    if filename in _DATA_CACHE:
        return _DATA_CACHE[filename]

    path = DATA_DIR / filename

    if not path.exists():
        _DATA_CACHE[filename] = {}
        return {}

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    _DATA_CACHE[filename] = data
    return data


def clear_data_cache() -> None:
    """Clear cached JSON data."""
    _DATA_CACHE.clear()


def _as_list(
    data: Any,
    keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Convert common JSON structures into a list."""
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)

            if isinstance(value, list):
                return value

    return []


# ============================================================
# DATABASE HELPERS
# ============================================================

def _table_exists(db, table_name: str) -> bool:
    row = db.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def _column_exists(
    db,
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


def _table_columns(
    db,
    table_name: str,
) -> set[str]:
    if not _table_exists(db, table_name):
        return set()

    rows = db.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        str(row["name"])
        for row in rows
    }


# ============================================================
# PLAYER / ACCOUNT FUNCTIONS
# ============================================================

def get_player_by_username(
    username: str,
) -> dict[str, Any] | None:
    """Find a player by username."""
    with get_connection() as db:
        row = db.execute(
            """
            SELECT *
            FROM players
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

        return dict(row) if row else None


def get_player(
    player_id: int,
) -> dict[str, Any] | None:
    """Find a player by ID."""
    with get_connection() as db:
        row = db.execute(
            """
            SELECT *
            FROM players
            WHERE id = ?
            """,
            (player_id,),
        ).fetchone()

        return dict(row) if row else None


def create_player(
    username: str,
    password_hash: str,
    display_name: str | None = None,
) -> int:
    """Create a player account and initial progress."""
    if display_name is None:
        display_name = username

    with get_connection() as db:
        columns = _table_columns(db, "players")

        fields = [
            "username",
            "password_hash",
            "display_name",
        ]

        values: list[Any] = [
            username,
            password_hash,
            display_name,
        ]

        if "role_id" in columns:
            fields.append("role_id")

            role = db.execute(
                """
                SELECT id
                FROM roles
                WHERE name = 'player'
                LIMIT 1
                """
            ).fetchone()

            values.append(
                int(role["id"])
                if role
                else 1
            )

        placeholders = ", ".join(
            "?"
            for _ in fields
        )

        cursor = db.execute(
            f"""
            INSERT INTO players
            ({", ".join(fields)})
            VALUES ({placeholders})
            """,
            tuple(values),
        )

        player_id = int(cursor.lastrowid)

        if _table_exists(db, "player_progress"):
            existing_progress = db.execute(
                """
                SELECT player_id
                FROM player_progress
                WHERE player_id = ?
                """,
                (player_id,),
            ).fetchone()

            if not existing_progress:
                db.execute(
                    """
                    INSERT INTO player_progress
                    (player_id)
                    VALUES (?)
                    """,
                    (player_id,),
                )

        db.commit()

        return player_id


# ============================================================
# POKEMON DATA
# ============================================================

def get_all_species() -> list[dict[str, Any]]:
    """Return all Pokémon species from database."""
    from .database import get_connection

    with get_connection() as db:
        species = db.execute(
            """
            SELECT
                id,
                national_dex,
                name,
                category,
                generation,
                description,
                base_hp,
                base_attack,
                base_defense,
                base_sp_attack,
                base_sp_defense,
                base_speed,
                gender_rate,
                is_fakemon,
                is_active
            FROM pokemon_species
            WHERE is_active = 1
            ORDER BY national_dex
            """
        ).fetchall()

        result = []
        for row in species:
            species_dict = dict(row)
            # Get types
            types = db.execute(
                """
                SELECT t.name FROM pokemon_types t
                JOIN pokemon_species_types pst ON pst.type_id = t.id
                WHERE pst.species_id = ?
                ORDER BY pst.slot
                """,
                (row["id"],),
            ).fetchall()

            species_dict["type"] = [t[0] for t in types]
            species_dict["base_stats"] = {
                "hp": row["base_hp"],
                "attack": row["base_attack"],
                "defense": row["base_defense"],
                "sp_attack": row["base_sp_attack"],
                "sp_defense": row["base_sp_defense"],
                "speed": row["base_speed"],
            }

            result.append(species_dict)

        return result


def get_species(
    species_id: int | str,
) -> dict[str, Any] | None:
    """Find a Pokémon species by ID, slug, or name from database."""
    from .database import get_connection

    wanted = str(species_id).lower()

    try:
        with get_connection() as db:
            # Try exact ID match first
            species = db.execute(
                """
                SELECT
                    id,
                    national_dex,
                    name,
                    category,
                    generation,
                    description,
                    base_hp,
                    base_attack,
                    base_defense,
                    base_sp_attack,
                    base_sp_defense,
                    base_speed,
                    gender_rate,
                    is_fakemon,
                    is_active
                FROM pokemon_species
                WHERE id = ? AND is_active = 1
                """,
                (wanted,),
            ).fetchone()

            if not species:
                # Try name match
                species = db.execute(
                    """
                    SELECT
                        id,
                        national_dex,
                        name,
                        category,
                        generation,
                        description,
                        base_hp,
                        base_attack,
                        base_defense,
                        base_sp_attack,
                        base_sp_defense,
                        base_speed,
                        gender_rate,
                        is_fakemon,
                        is_active
                    FROM pokemon_species
                    WHERE LOWER(name) = ? AND is_active = 1
                    """,
                    (wanted,),
                ).fetchone()

            if species:
                species_dict = dict(species)

                # Get types
                types = db.execute(
                    """
                    SELECT t.name FROM pokemon_types t
                    JOIN pokemon_species_types pst ON pst.type_id = t.id
                    WHERE pst.species_id = ?
                    ORDER BY pst.slot
                    """,
                    (species_dict["id"],),
                ).fetchall()

                species_dict["type"] = [t[0] for t in types]
                species_dict["base_stats"] = {
                    "hp": species_dict["base_hp"],
                    "attack": species_dict["base_attack"],
                    "defense": species_dict["base_defense"],
                    "sp_attack": species_dict["base_sp_attack"],
                    "sp_defense": species_dict["base_sp_defense"],
                    "speed": species_dict["base_speed"],
                }

                return species_dict
    except sqlite3.OperationalError:
        pass

    # JSON catalog fallback
    import json
    from pathlib import Path
    json_path = Path(__file__).resolve().parent.parent / "Data" / "pokemon.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                all_pokemon = json.load(f)
            for p in all_pokemon:
                if str(p.get("id")).lower() == wanted or str(p.get("name", "")).lower() == wanted:
                    base_stats = p.get("base_stats", {})
                    return {
                        "id": str(p["id"]),
                        "national_dex": p.get("national_dex", 0),
                        "name": p.get("name", str(p["id"]).title()),
                        "category": "pokemon",
                        "generation": p.get("generation", 1),
                        "description": p.get("description", ""),
                        "base_hp": base_stats.get("hp", 45),
                        "base_attack": base_stats.get("attack", 49),
                        "base_defense": base_stats.get("defense", 49),
                        "base_sp_attack": base_stats.get("sp_attack", 65),
                        "base_sp_defense": base_stats.get("sp_defense", 65),
                        "base_speed": base_stats.get("speed", 45),
                        "gender_rate": p.get("gender_rate", -1),
                        "is_fakemon": 0,
                        "is_active": 1,
                        "type": p.get("type", ["normal"]),
                        "base_stats": base_stats,
                        "starting_moves": p.get("starting_moves", ["tackle"]),
                    }
        except Exception:
            pass

    return None


# ============================================================
# MOVE DATA
# ============================================================

def get_all_moves() -> list[dict[str, Any]]:
    """Return all moves from the database."""
    from .database import get_connection

    with get_connection() as db:
        moves = db.execute(
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
                t.name as type_name
            FROM moves m
            LEFT JOIN pokemon_types t ON t.id = m.type_id
            ORDER BY m.name
            """
        ).fetchall()

        return [dict(row) for row in moves]


def get_move(
    move_id: int | str,
) -> dict[str, Any] | None:
    """Find a move by ID, slug, or name."""
    from .database import get_connection

    wanted = str(move_id).lower()

    try:
        with get_connection() as db:
            # Try to find by exact ID match first
            move = db.execute(
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
                    t.name as type_name
                FROM moves m
                LEFT JOIN pokemon_types t ON t.id = m.type_id
                WHERE m.id = ?
                """,
                (wanted,),
            ).fetchone()

            if move:
                return dict(move)

            # Try to find by name
            move = db.execute(
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
                    t.name as type_name
                FROM moves m
                LEFT JOIN pokemon_types t ON t.id = m.type_id
                WHERE LOWER(m.name) = ?
                """,
                (wanted,),
            ).fetchone()

            if move:
                return dict(move)

    except sqlite3.OperationalError:
        pass

    # Fallback to Data/moves.json
    import json
    from pathlib import Path
    json_path = Path(__file__).resolve().parent.parent / "Data" / "moves.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                all_moves = json.load(f)
            for m in all_moves:
                if str(m.get("id")).lower() == wanted or str(m.get("name", "")).lower() == wanted:
                    return {
                        "id": str(m["id"]),
                        "name": m.get("name", str(m["id"]).title()),
                        "type_id": m.get("type", "normal"),
                        "category": m.get("category", "physical"),
                        "power": m.get("power", 40),
                        "accuracy": m.get("accuracy", 100),
                        "max_pp": m.get("pp", 35),
                        "pp": m.get("pp", 35),
                        "description": m.get("description", ""),
                    }
        except Exception:
            pass

    return {
        "id": wanted,
        "name": wanted.title(),
        "type_id": "normal",
        "category": "physical",
        "power": 40,
        "accuracy": 100,
        "max_pp": 35,
        "pp": 35,
        "description": "",
    }


# ============================================================
# ABILITIES
# ============================================================

def get_all_abilities() -> list[dict[str, Any]]:
    """Return all abilities."""
    data = load_data("abilities.json")

    return _as_list(
        data,
        (
            "abilities",
            "items",
        ),
    )


def get_ability(
    ability_id: int | str,
) -> dict[str, Any] | None:
    """Find an ability by ID or name."""
    wanted = str(ability_id)

    for ability in get_all_abilities():
        if str(
            ability.get("id", "")
        ) == wanted:
            return ability

        if str(
            ability.get("name", "")
        ).lower() == wanted.lower():
            return ability

    return None


# ============================================================
# VARIANTS
# ============================================================

def get_all_variants() -> list[dict[str, Any]]:
    """Return all custom Krampus Pokémon variants from database."""
    from .database import get_connection

    with get_connection() as db:
        variants = db.execute(
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
            ORDER BY name
            """
        ).fetchall()

        return [dict(row) for row in variants]


def get_variant(
    variant_id: str | None,
) -> dict[str, Any] | None:
    """Find a custom Krampus variant from database."""
    from .database import get_connection

    if not variant_id:
        return None

    wanted = str(variant_id).lower()

    with get_connection() as db:
        variant = db.execute(
            """
            SELECT
                id,
                name,
                sprite_suffix,
                description,
                is_custom,
                is_active
            FROM pokemon_variants
            WHERE id = ? OR LOWER(name) = ?
            LIMIT 1
            """,
            (wanted, wanted),
        ).fetchone()

        return dict(variant) if variant else None


# ============================================================
# POKEMON GENERATION
# ============================================================

def generate_unique_id() -> str:
    """Generate a unique Pokémon identifier."""
    return secrets.token_hex(12)


def generate_gender(
    species: dict[str, Any],
) -> str:
    """Generate a Pokémon's gender."""
    gender = species.get("gender")

    if isinstance(gender, str):
        value = gender.lower()

        if value in {
            "male",
            "female",
            "genderless",
        }:
            return value

    if species.get("genderless") is True:
        return "genderless"

    ratio = species.get("gender_ratio")

    if isinstance(ratio, dict):
        male = ratio.get("male")
        female = ratio.get("female")

        try:
            male = float(male)
            female = float(female)

            total = male + female

            if total > 0:
                return (
                    "male"
                    if random.random() * total < male
                    else "female"
                )
        except (
            TypeError,
            ValueError,
        ):
            pass

    return (
        "male"
        if random.random() < 0.5
        else "female"
    )


# ============================================================
# BASE STATS
# ============================================================

STAT_NAMES = (
    "hp",
    "attack",
    "defense",
    "sp_attack",
    "sp_defense",
    "speed",
)


def get_species_base_stats(
    species: dict[str, Any],
) -> dict[str, int]:
    """
    Read the species base stats.

    No IVs, EVs, or Nature modifiers are used.
    """
    result = {
        stat: 50
        for stat in STAT_NAMES
    }

    possible = species.get("base_stats")

    if not isinstance(possible, dict):
        possible = species.get("stats")

    if isinstance(possible, dict):
        aliases = {
            "hp": ("hp", "HP"),
            "attack": (
                "attack",
                "Attack",
                "atk",
            ),
            "defense": (
                "defense",
                "Defense",
                "def",
            ),
            "sp_attack": (
                "sp_attack",
                "special_attack",
                "Special Attack",
                "sp_atk",
            ),
            "sp_defense": (
                "sp_defense",
                "special_defense",
                "Special Defense",
                "sp_def",
            ),
            "speed": (
                "speed",
                "Speed",
            ),
        }

        for stat, keys in aliases.items():
            for key in keys:
                if key not in possible:
                    continue

                try:
                    result[stat] = max(
                        1,
                        int(possible[key]),
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    pass

                break

    return result


def calculate_stat(
    base_stat: int,
    level: int,
) -> int:
    """
    Calculate a player Pokémon stat.

    This deliberately does not use IVs, EVs,
    Nature, or permanent modifiers.
    """
    base_stat = max(
        1,
        int(base_stat),
    )

    level = max(
        1,
        int(level),
    )

    return max(
        1,
        ((2 * base_stat * level) // 100)
        + 5,
    )


def calculate_hp(
    species: dict[str, Any],
    level: int,
) -> int:
    """Calculate Pokémon HP without IV/EV/Nature."""
    level = max(
        1,
        int(level),
    )

    base_hp = get_species_base_stats(
        species
    )["hp"]

    return max(
        1,
        ((2 * base_hp * level) // 100)
        + level
        + 10,
    )


def calculate_pokemon_stats(
    species: dict[str, Any],
    level: int,
) -> dict[str, int]:
    """Calculate all permanent Pokémon stats."""
    base = get_species_base_stats(
        species
    )

    stats = {
        stat: calculate_stat(
            base[stat],
            level,
        )
        for stat in STAT_NAMES
    }

    stats["hp"] = calculate_hp(
        species,
        level,
    )

    return stats


# ============================================================
# STARTING MOVES
# ============================================================

def get_species_starting_moves(
    species: dict[str, Any],
) -> list[str]:
    """Get starting moves from species data."""
    result: list[str] = []

    possible_keys = (
        "starting_moves",
        "moves",
        "level_up_moves",
    )

    for key in possible_keys:
        value = species.get(key)

        if not isinstance(value, list):
            continue

        for entry in value:
            if isinstance(entry, dict):
                move_id = entry.get(
                    "move_id"
                )

                if move_id is None:
                    move_id = entry.get(
                        "id"
                    )

                if move_id is None:
                    move_id = entry.get(
                        "move"
                    )

                if move_id is not None:
                    result.append(
                        str(move_id)
                    )

            elif isinstance(
                entry,
                (str, int),
            ):
                result.append(
                    str(entry)
                )

        if result:
            break

    return result[:4]


def add_starting_moves(
    db,
    pokemon_id: int,
    species: dict[str, Any],
) -> None:
    """Add up to four starting moves."""
    move_ids = get_species_starting_moves(
        species
    )

    if not move_ids:
        return

    if not _table_exists(
        db,
        "pokemon_moves",
    ):
        return

    columns = _table_columns(
        db,
        "pokemon_moves",
    )

    required = {
        "pokemon_id",
        "move_id",
        "slot",
    }

    if not required.issubset(columns):
        return

    has_pp = "current_pp" in columns

    for slot, move_id in enumerate(
        move_ids,
        start=1,
    ):
        move = get_move(move_id)

        if move is None:
            continue

        if has_pp:
            pp = int(
                move.get(
                    "pp",
                    move.get(
                        "max_pp",
                        0,
                    ),
                )
                or 0
            )

            db.execute(
                """
                INSERT OR IGNORE INTO pokemon_moves
                (
                    pokemon_id,
                    move_id,
                    slot,
                    current_pp
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    pokemon_id,
                    str(move_id),
                    slot,
                    pp,
                ),
            )
        else:
            db.execute(
                """
                INSERT OR IGNORE INTO pokemon_moves
                (
                    pokemon_id,
                    move_id,
                    slot
                )
                VALUES (?, ?, ?)
                """,
                (
                    pokemon_id,
                    str(move_id),
                    slot,
                ),
            )


# ============================================================
# CREATE POKEMON
# ============================================================

def create_pokemon(
    owner_id: int,
    species_id: int | str,
    level: int = 5,
    shiny: bool = False,
    variant: str = "normal",
    nickname: str | None = None,
    auto_store: bool = True,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """
    Create a Pokémon.

    - Nature, IVs, EVs, and status are not used in Krampus RPG.
    - If auto_store is True (default), the Pokémon is automatically
      placed into the player's Party (if under 6) or PC storage,
      guaranteeing storage ownership integrity.
    """
    species = get_species(
        species_id
    )

    if species is None:
        raise ValueError(
            f"Pokémon species '{species_id}' "
            f"was not found in "
            f"Data/pokemon.json."
        )

    # Resolve the requested variant against the database instead of
    # storing whatever string was passed. Previously this function
    # stored `variant or "normal"` directly with no validation at all —
    # reachable not just from admin tooling but from any authenticated
    # player via POST /api/pokemon/create, which forwards a client-
    # supplied "variant" field straight through. An invalid value would
    # silently persist as an unresolvable Pokémon that get_variant()
    # could never look back up. Resolved here the same way
    # add_pokemon.py's find_variant() resolves it: by id or
    # case-insensitive name, active only.
    resolved_variant = get_variant(
        variant or "normal"
    )

    if resolved_variant is None:
        valid_ids = ", ".join(
            sorted(
                v["id"]
                for v in get_all_variants()
            )
        )

        raise ValueError(
            f"Unknown variant '{variant}'. "
            f"Valid variants: {valid_ids}"
        )

    variant = resolved_variant["id"]

    level = max(
        1,
        min(100, int(level)),
    )

    gender = generate_gender(
        species
    )

    stats = calculate_pokemon_stats(
        species,
        level,
    )

    unique_id = generate_unique_id()

    with get_connection() as db:
        columns = _table_columns(
            db,
            "pokemon",
        )

        fields: list[str] = []
        values: list[Any] = []

        def add_field(
            name: str,
            value: Any,
        ) -> None:
            if name in columns:
                fields.append(name)
                values.append(value)

        add_field(
            "unique_id",
            unique_id,
        )
        add_field(
            "owner_id",
            owner_id,
        )
        add_field(
            "species_id",
            str(species_id),
        )
        add_field(
            "nickname",
            nickname,
        )
        add_field(
            "level",
            level,
        )
        add_field(
            "experience",
            0,
        )
        add_field(
            "gender",
            gender,
        )
        add_field(
            "shiny",
            int(bool(shiny)),
        )
        add_field(
            "variant",
            variant or "normal",
        )

        if "current_hp" in columns:
            add_field(
                "current_hp",
                stats["hp"],
            )

        if "max_hp" in columns:
            add_field(
                "max_hp",
                stats["hp"],
            )

        placeholders = ", ".join(
            "?"
            for _ in fields
        )

        cursor = db.execute(
            f"""
            INSERT INTO pokemon
            ({", ".join(fields)})
            VALUES ({placeholders})
            """,
            tuple(values),
        )

        pokemon_id = int(
            cursor.lastrowid
        )

        # ----------------------------------------------------
        # Save calculated stats.
        #
        # New schema:
        #   normal stat columns
        #
        # Legacy schema:
        #   IV/EV columns
        #
        # We intentionally do NOT write IV/EV data.
        # ----------------------------------------------------

        if _table_exists(
            db,
            "pokemon_stats",
        ):
            stat_columns = _table_columns(
                db,
                "pokemon_stats",
            )

            if "pokemon_id" in stat_columns:
                stat_fields = [
                    "pokemon_id"
                ]

                stat_values: list[Any] = [
                    pokemon_id
                ]

                stat_mapping = {
                    "hp": stats["hp"],
                    "attack": stats["attack"],
                    "defense": stats["defense"],
                    "sp_attack": stats[
                        "sp_attack"
                    ],
                    "sp_defense": stats[
                        "sp_defense"
                    ],
                    "speed": stats[
                        "speed"
                    ],
                }

                for stat, value in (
                    stat_mapping.items()
                ):
                    if stat in stat_columns:
                        stat_fields.append(
                            stat
                        )
                        stat_values.append(
                            value
                        )

                # If the current database still has
                # the old IV/EV-only schema, don't create
                # fake IV/EV values. The migration is
                # responsible for replacing that schema.
                if len(stat_fields) > 1:
                    placeholders = ", ".join(
                        "?"
                        for _ in stat_fields
                    )

                    db.execute(
                        f"""
                        INSERT INTO pokemon_stats
                        ({", ".join(stat_fields)})
                        VALUES ({placeholders})
                        """,
                        tuple(
                            stat_values
                        ),
                    )
                else:
                    db.execute(
                        """
                        INSERT OR IGNORE INTO
                        pokemon_stats
                        (pokemon_id)
                        VALUES (?)
                        """,
                        (pokemon_id,),
                    )

        add_starting_moves(
            db,
            pokemon_id,
            species,
        )

        if auto_store:
            if _table_exists(db, "party") and _table_exists(db, "pc_storage"):
                party_rows = db.execute(
                    """
                    SELECT slot
                    FROM party
                    WHERE player_id = ?
                    ORDER BY slot
                    """,
                    (owner_id,),
                ).fetchall()

                occupied_party = {int(r["slot"]) for r in party_rows}
                if len(occupied_party) < 6:
                    assigned_slot = None
                    for s in range(1, 7):
                        if s not in occupied_party:
                            assigned_slot = s
                            break
                    if assigned_slot is not None:
                        db.execute(
                            """
                            INSERT INTO party (player_id, pokemon_id, slot)
                            VALUES (?, ?, ?)
                            """,
                            (owner_id, pokemon_id, assigned_slot),
                        )
                else:
                    pc_rows = db.execute(
                        """
                        SELECT page, slot
                        FROM pc_storage
                        WHERE player_id = ?
                        ORDER BY page, slot
                        """,
                        (owner_id,),
                    ).fetchall()
                    occupied_pc = {
                        (int(r["page"]), int(r["slot"]))
                        for r in pc_rows
                    }
                    assigned_page = 1
                    assigned_pc_slot = 1
                    found = False
                    while not found:
                        for s in range(1, 31):
                            if (assigned_page, s) not in occupied_pc:
                                assigned_pc_slot = s
                                found = True
                                break
                        if not found:
                            assigned_page += 1

                    db.execute(
                        """
                        INSERT INTO pc_storage (player_id, pokemon_id, page, slot)
                        VALUES (?, ?, ?, ?)
                        """,
                        (owner_id, pokemon_id, assigned_page, assigned_pc_slot),
                    )

        db.commit()

    return get_pokemon(
        owner_id,
        pokemon_id,
    )


# ============================================================
# GET POKEMON
# ============================================================

def get_pokemon(
    owner_id: int,
    pokemon_id: int,
) -> dict[str, Any] | None:
    """Get one Pokémon owned by a player."""
    with get_connection() as db:
        row = db.execute(
            """
            SELECT *
            FROM pokemon
            WHERE id = ?
              AND owner_id = ?
            """,
            (
                pokemon_id,
                owner_id,
            ),
        ).fetchone()

        if row is None:
            return None

        pokemon = dict(row)

        # ----------------------------------------------------
        # Never expose the removed party mechanic.
        # ----------------------------------------------------

        pokemon.pop(
            "is_active",
            None,
        )

        # Legacy columns are ignored by the game logic.
        pokemon.pop(
            "nature",
            None,
        )
        pokemon.pop(
            "status",
            None,
        )

        species = get_species(
            pokemon.get(
                "species_id"
            )
        )

        if species:
            pokemon["species"] = species
            pokemon["species_name"] = (
                species.get(
                    "name",
                    "Unknown",
                )
            )

            pokemon["base_stats"] = (
                get_species_base_stats(
                    species
                )
            )

        # ----------------------------------------------------
        # Stats
        # ----------------------------------------------------

        pokemon["stats"] = {}

        if _table_exists(
            db,
            "pokemon_stats",
        ):
            stats_row = db.execute(
                """
                SELECT *
                FROM pokemon_stats
                WHERE pokemon_id = ?
                """,
                (pokemon_id,),
            ).fetchone()

            if stats_row:
                raw_stats = dict(
                    stats_row
                )

                for stat in STAT_NAMES:
                    if stat in raw_stats:
                        pokemon[
                            "stats"
                        ][stat] = raw_stats[
                            stat
                        ]

        # If no calculated stats are stored,
        # calculate them from species + level.
        if species:
            calculated = (
                calculate_pokemon_stats(
                    species,
                    int(
                        pokemon.get(
                            "level",
                            1,
                        )
                    ),
                )
            )

            for stat in STAT_NAMES:
                pokemon[
                    "stats"
                ].setdefault(
                    stat,
                    calculated[stat],
                )

        variant = get_variant(
            pokemon.get(
                "variant"
            )
        )

        if variant:
            pokemon[
                "variant_data"
            ] = variant

        # ----------------------------------------------------
        # Moves
        # ----------------------------------------------------

        pokemon["moves"] = []

        if _table_exists(
            db,
            "pokemon_moves",
        ):
            move_rows = db.execute(
                """
                SELECT *
                FROM pokemon_moves
                WHERE pokemon_id = ?
                ORDER BY slot
                """,
                (pokemon_id,),
            ).fetchall()

            for move_row in move_rows:
                move_data = dict(
                    move_row
                )

                move = get_move(
                    move_data.get(
                        "move_id"
                    )
                )

                if move:
                    move_data["name"] = (
                        move.get(
                            "name",
                            move_data.get(
                                "move_id"
                            ),
                        )
                    )

                    move_data["type"] = (
                        move.get(
                            "type"
                        )
                    )

                    move_data["power"] = (
                        move.get(
                            "power"
                        )
                    )

                    move_data["accuracy"] = (
                        move.get(
                            "accuracy"
                        )
                    )

                    move_data["pp"] = (
                        move.get(
                            "pp",
                            move.get(
                                "max_pp"
                            ),
                        )
                    )

                    move_data[
                        "move_data"
                    ] = move

                pokemon[
                    "moves"
                ].append(
                    move_data
                )

        return pokemon


# ============================================================
# PLAYER POKEMON
# ============================================================

def get_player_pokemon(
    owner_id: int,
) -> list[dict[str, Any]]:
    """Return all Pokémon belonging to a player."""
    with get_connection() as db:
        rows = db.execute(
            """
            SELECT *
            FROM pokemon
            WHERE owner_id = ?
            ORDER BY id
            """,
            (owner_id,),
        ).fetchall()

    result: list[
        dict[str, Any]
    ] = []

    for row in rows:
        pokemon_id = int(
            row["id"]
        )

        pokemon = get_pokemon(
            owner_id,
            pokemon_id,
        )

        if pokemon:
            result.append(
                pokemon
            )

    return result


# ============================================================
# PARTY
# ============================================================

def get_party(
    owner_id: int,
) -> list[dict[str, Any]]:
    """Return the player's database-backed party."""
    from .party_storage import (
        get_party as get_storage_party,
    )

    return get_storage_party(
        owner_id
    )


def add_to_party(
    owner_id: int,
    pokemon_id: int,
) -> bool:
    """Add a Pokémon to the database-backed party."""
    from .party_storage import (
        add_to_party as add_storage_party,
    )

    return bool(
        add_storage_party(
            owner_id,
            pokemon_id,
        )
    )


def remove_from_party(
    owner_id: int,
    pokemon_id: int,
) -> bool:
    """
    Remove a Pokémon from Party.

    The storage layer ALWAYS moves it into PC.
    It must never simply disappear from ownership.
    """
    from .party_storage import (
        remove_from_party as
        remove_storage_party,
    )

    result = remove_storage_party(
        owner_id,
        pokemon_id,
    )

    if isinstance(result, dict):
        return bool(
            result.get(
                "success",
                True,
            )
        )

    return bool(result)


# ============================================================
# STARTER
# ============================================================

def give_starter(
    owner_id: int,
    species_id: int | str,
) -> dict[str, Any] | None:
    """
    Create a level-5 starter and place it into Party.

    If Party is full, the storage system places it into PC.
    """
    pokemon = create_pokemon(
        owner_id=owner_id,
        species_id=species_id,
        level=5,
        shiny=False,
        variant="normal",
    )

    if pokemon is None:
        return None

    pokemon_id = pokemon.get(
        "id"
    )

    if pokemon_id is None:
        return pokemon

    pokemon_id = int(
        pokemon_id
    )

    added = add_to_party(
        owner_id,
        pokemon_id,
    )

    if not added:
        # Party may be full.
        # Do not leave the Pokémon unassigned.
        try:
            from .pc_storage import (
                deposit_pokemon,
            )

            deposit_pokemon(
                owner_id,
                pokemon_id,
            )
        except Exception:
            pass

    return get_pokemon(
        owner_id,
        pokemon_id,
    )


def ensure_player_starter(
    owner_id: int,
    species_id: int | str,
) -> dict[str, Any] | None:
    """
    Give a player a starter only if they own no Pokémon.
    """
    with get_connection() as db:
        existing = db.execute(
            """
            SELECT id
            FROM pokemon
            WHERE owner_id = ?
            ORDER BY id
            LIMIT 1
            """,
            (owner_id,),
        ).fetchone()

    if existing:
        return get_pokemon(
            owner_id,
            int(existing["id"]),
        )

    return give_starter(
        owner_id,
        species_id,
    )


# ============================================================
# PLAYER PROGRESS
# ============================================================

def get_player_progress(
    player_id: int,
) -> dict[str, Any] | None:
    """Get a player's progression record."""
    with get_connection() as db:
        row = db.execute(
            """
            SELECT *
            FROM player_progress
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        return (
            dict(row)
            if row
            else None
        )


def update_player_progress(
    player_id: int,
    **updates: Any,
) -> bool:
    """Update allowed player progression fields."""
    allowed = {
        "current_region",
        "current_area",
        "money",
        "badges",
    }

    values = {
        key: value
        for key, value in updates.items()
        if key in allowed
    }

    if not values:
        return False

    assignments = ", ".join(
        f"{key} = ?"
        for key in values
    )

    with get_connection() as db:
        cursor = db.execute(
            f"""
            UPDATE player_progress
            SET {assignments}
            WHERE player_id = ?
            """,
            (
                *values.values(),
                player_id,
            ),
        )

        db.commit()

        return cursor.rowcount > 0


# ============================================================
# AREAS / ENCOUNTERS
# ============================================================

def get_all_areas() -> list[dict[str, Any]]:
    """Return all areas."""
    data = load_data(
        "areas.json"
    )

    return _as_list(
        data,
        (
            "areas",
            "locations",
            "items",
        ),
    )


def get_area(
    area_id: int | str,
) -> dict[str, Any] | None:
    """Find an area by ID, slug, or name."""
    wanted = str(
        area_id
    )

    for area in get_all_areas():
        if str(
            area.get("id")
        ) == wanted:
            return area

        if str(
            area.get("slug", "")
        ).lower() == wanted.lower():
            return area

        if str(
            area.get("name", "")
        ).lower() == wanted.lower():
            return area

    return None


def get_area_encounters(
    area_id: int | str,
) -> list[dict[str, Any]]:
    """Return encounter entries for an area."""
    area = get_area(
        area_id
    )

    if not area:
        return []

    encounters = area.get(
        "encounters"
    )

    if isinstance(
        encounters,
        list,
    ):
        return encounters

    return []


def generate_encounter(
    area_id: int | str,
) -> dict[str, Any] | None:
    """Choose a random weighted encounter."""
    encounters = get_area_encounters(
        area_id
    )

    if not encounters:
        return None

    weighted: list[
        tuple[
            dict[str, Any],
            float,
        ]
    ] = []

    for encounter in encounters:
        try:
            weight = float(
                encounter.get(
                    "weight",
                    encounter.get(
                        "chance",
                        1,
                    ),
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            weight = 1.0

        if weight > 0:
            weighted.append(
                (
                    encounter,
                    weight,
                )
            )

    if not weighted:
        return None

    total = sum(
        weight
        for _, weight in weighted
    )

    roll = random.uniform(
        0,
        total,
    )

    current = 0.0

    for encounter, weight in weighted:
        current += weight

        if roll <= current:
            return encounter

    return weighted[-1][0]


# ============================================================
# ITEMS
# ============================================================

def get_all_items() -> list[dict[str, Any]]:
    """Return all items."""
    data = load_data(
        "items.json"
    )

    return _as_list(
        data,
        (
            "items",
            "inventory",
        ),
    )


def get_item(
    item_id: int | str,
) -> dict[str, Any] | None:
    """Find an item."""
    wanted = str(
        item_id
    )

    for item in get_all_items():
        if str(
            item.get("id")
        ) == wanted:
            return item

        if str(
            item.get("slug", "")
        ).lower() == wanted.lower():
            return item

        if str(
            item.get("name", "")
        ).lower() == wanted.lower():
            return item

    return None


# ============================================================
# QUESTS
# ============================================================

def get_all_quests() -> list[dict[str, Any]]:
    """Return quests from JSON."""
    data = load_data(
        "quests.json"
    )

    return _as_list(
        data,
        (
            "quests",
            "items",
        ),
    )


def get_quest(
    quest_id: int | str,
) -> dict[str, Any] | None:
    """Find a quest."""
    wanted = str(
        quest_id
    )

    for quest in get_all_quests():
        if str(
            quest.get("id")
        ) == wanted:
            return quest

        if str(
            quest.get("slug", "")
        ).lower() == wanted.lower():
            return quest

    return None


# ============================================================
# INVENTORY
# ============================================================

def get_player_items(
    player_id: int,
) -> list[dict[str, Any]]:
    """Get a player's inventory."""
    with get_connection() as db:
        rows = db.execute(
            """
            SELECT *
            FROM player_items
            WHERE player_id = ?
            ORDER BY item_id
            """,
            (player_id,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def add_item(
    player_id: int,
    item_id: int | str,
    quantity: int = 1,
) -> None:
    """Add items to a player's inventory."""
    if quantity <= 0:
        return

    with get_connection() as db:
        db.execute(
            """
            INSERT INTO player_items
            (
                player_id,
                item_id,
                quantity
            )
            VALUES (?, ?, ?)
            ON CONFLICT(player_id, item_id)
            DO UPDATE SET
                quantity =
                    quantity
                    + excluded.quantity
            """,
            (
                player_id,
                str(item_id),
                quantity,
            ),
        )

        db.commit()


def remove_item(
    player_id: int,
    item_id: int | str,
    quantity: int = 1,
) -> bool:
    """Remove items from inventory."""
    if quantity <= 0:
        return False

    with get_connection() as db:
        row = db.execute(
            """
            SELECT quantity
            FROM player_items
            WHERE player_id = ?
              AND item_id = ?
            """,
            (
                player_id,
                str(item_id),
            ),
        ).fetchone()

        if row is None:
            return False

        current = int(
            row["quantity"]
        )

        if current < quantity:
            return False

        new_quantity = (
            current - quantity
        )

        if new_quantity <= 0:
            db.execute(
                """
                DELETE FROM player_items
                WHERE player_id = ?
                  AND item_id = ?
                """,
                (
                    player_id,
                    str(item_id),
                ),
            )
        else:
            db.execute(
                """
                UPDATE player_items
                SET quantity = ?
                WHERE player_id = ?
                  AND item_id = ?
                """,
                (
                    new_quantity,
                    player_id,
                    str(item_id),
                ),
            )

        db.commit()

        return True


# ============================================================
# MONEY
# ============================================================

def get_player_money(
    player_id: int,
) -> int:
    """Get player's current money."""
    progress = get_player_progress(
        player_id
    )

    if not progress:
        return 0

    return int(
        progress.get(
            "money",
            0,
        )
    )


def add_money(
    player_id: int,
    amount: int,
    transaction_type: str = "money_change",
    details: str | None = None,
) -> int:
    """Add or remove money and log the transaction."""
    with get_connection() as db:
        row = db.execute(
            """
            SELECT money
            FROM player_progress
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        if row is None:
            return 0

        current = int(
            row["money"]
        )

        new_amount = max(
            0,
            current + int(amount),
        )

        db.execute(
            """
            UPDATE player_progress
            SET money = ?
            WHERE player_id = ?
            """,
            (
                new_amount,
                player_id,
            ),
        )

        if _table_exists(
            db,
            "transaction_log",
        ):
            db.execute(
                """
                INSERT INTO transaction_log
                (
                    player_id,
                    transaction_type,
                    amount,
                    details
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    player_id,
                    transaction_type,
                    int(amount),
                    details,
                ),
            )

        db.commit()

        return new_amount