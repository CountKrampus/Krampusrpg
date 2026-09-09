from __future__ import annotations

import json
import random
import secrets
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


def _as_list(data: Any, keys: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """
    Convert common JSON formats into a list.

    Supports:

        [
            {...},
            {...}
        ]

    and:

        {
            "pokemon": [...]
        }

    and similar structures.
    """
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


# ============================================================
# PLAYER / ACCOUNT FUNCTIONS
# ============================================================

def get_player_by_username(username: str) -> dict[str, Any] | None:
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


def get_player(player_id: int) -> dict[str, Any] | None:
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
    """
    Create a player account and its initial progress.

    Returns:
        New player ID
    """
    if display_name is None:
        display_name = username

    with get_connection() as db:
        cursor = db.execute(
            """
            INSERT INTO players
            (
                username,
                password_hash,
                display_name
            )
            VALUES (?, ?, ?)
            """,
            (
                username,
                password_hash,
                display_name,
            ),
        )

        player_id = cursor.lastrowid

        db.execute(
            """
            INSERT INTO player_progress
            (
                player_id
            )
            VALUES (?)
            """,
            (player_id,),
        )

        db.commit()

        return int(player_id)


# ============================================================
# POKEMON DATA
# ============================================================

def get_all_species() -> list[dict[str, Any]]:
    """Return all Pokémon species."""
    data = load_data("pokemon.json")

    return _as_list(
        data,
        (
            "pokemon",
            "species",
            "items",
        ),
    )


def get_species(species_id: int | str) -> dict[str, Any] | None:
    """Find a Pokémon species by ID."""
    wanted = str(species_id)

    for species in get_all_species():
        current_id = species.get("id")

        if current_id is not None and str(current_id) == wanted:
            return species

        if str(species.get("species_id", "")) == wanted:
            return species

        if str(species.get("slug", "")).lower() == wanted.lower():
            return species

        if str(species.get("name", "")).lower() == wanted.lower():
            return species

    return None


# ============================================================
# MOVE DATA
# ============================================================

def get_all_moves() -> list[dict[str, Any]]:
    """Return all moves."""
    data = load_data("moves.json")

    return _as_list(
        data,
        (
            "moves",
            "items",
        ),
    )


def get_move(move_id: int | str) -> dict[str, Any] | None:
    """Find a move by ID."""
    wanted = str(move_id)

    for move in get_all_moves():
        current_id = move.get("id")

        if current_id is not None and str(current_id) == wanted:
            return move

        if str(move.get("move_id", "")) == wanted:
            return move

        if str(move.get("slug", "")).lower() == wanted.lower():
            return move

        if str(move.get("name", "")).lower() == wanted.lower():
            return move

    return None


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


def get_ability(ability_id: int | str) -> dict[str, Any] | None:
    """Find an ability by ID."""
    wanted = str(ability_id)

    for ability in get_all_abilities():
        if str(ability.get("id")) == wanted:
            return ability

        if str(ability.get("name", "")).lower() == wanted.lower():
            return ability

    return None


# ============================================================
# VARIANTS
# ============================================================

def get_all_variants() -> list[dict[str, Any]]:
    """Return all Pokémon variants."""
    data = load_data("variants.json")

    return _as_list(
        data,
        (
            "variants",
            "items",
        ),
    )


def get_variant(variant_id: str | None) -> dict[str, Any] | None:
    """Find a variant."""
    if not variant_id:
        return None

    wanted = str(variant_id).lower()

    for variant in get_all_variants():
        for key in ("id", "slug", "name"):
            value = variant.get(key)

            if value is not None:
                if str(value).lower() == wanted:
                    return variant

    return None


# ============================================================
# POKEMON GENERATION
# ============================================================

def generate_unique_id() -> str:
    """Generate a unique Pokémon identifier."""
    return secrets.token_hex(12)


def generate_ivs() -> dict[str, int]:
    """Generate six random IVs."""
    return {
        "hp": random.randint(0, 31),
        "attack": random.randint(0, 31),
        "defense": random.randint(0, 31),
        "sp_attack": random.randint(0, 31),
        "sp_defense": random.randint(0, 31),
        "speed": random.randint(0, 31),
    }


def generate_nature() -> str:
    """Generate a random Pokémon nature."""
    natures = [
        "Hardy",
        "Lonely",
        "Brave",
        "Adamant",
        "Naughty",
        "Bold",
        "Docile",
        "Relaxed",
        "Impish",
        "Lax",
        "Timid",
        "Hasty",
        "Serious",
        "Jolly",
        "Naive",
        "Bashful",
        "Mild",
        "Quiet",
        "Quirky",
        "Rash",
        "Calm",
        "Gentle",
        "Sassy",
        "Careful",
    ]

    return random.choice(natures)


def generate_gender(species: dict[str, Any]) -> str:
    """
    Generate gender using common JSON gender formats.
    """
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
        except (TypeError, ValueError):
            pass

    return "male" if random.random() < 0.5 else "female"


# ============================================================
# STATS
# ============================================================

def get_base_hp(species: dict[str, Any]) -> int:
    """Extract base HP from a species record."""
    value = species.get("base_hp")

    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass

    stats = species.get("base_stats")

    if isinstance(stats, dict):
        value = stats.get("hp")

        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass

    stats = species.get("stats")

    if isinstance(stats, dict):
        value = stats.get("hp")

        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass

    return 45


def calculate_hp(
    species: dict[str, Any],
    level: int,
    iv: int = 0,
    ev: int = 0,
) -> int:
    """Calculate basic Pokémon HP."""
    level = max(1, int(level))
    base_hp = get_base_hp(species)

    iv = max(0, min(31, int(iv)))
    ev = max(0, min(252, int(ev)))

    return max(
        1,
        ((2 * base_hp + iv + (ev // 4)) * level // 100)
        + level
        + 10,
    )


# ============================================================
# STARTING MOVES
# ============================================================

def get_species_starting_moves(
    species: dict[str, Any],
) -> list[str]:
    """
    Get starting moves from the species JSON.

    Supports several possible data formats.
    """
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
                move_id = entry.get("move_id")

                if move_id is None:
                    move_id = entry.get("id")

                if move_id is None:
                    move_id = entry.get("move")

                if move_id is not None:
                    result.append(str(move_id))

            elif isinstance(entry, (str, int)):
                result.append(str(entry))

        if result:
            break

    return result[:4]


def add_starting_moves(
    db,
    pokemon_id: int,
    species: dict[str, Any],
) -> None:
    """
    Add up to four starting moves.

    This function uses Python JSON data instead of SQLite readfile().
    """
    move_ids = get_species_starting_moves(species)

    # If species data has no explicit moves, don't invent moves.
    if not move_ids:
        return

    for slot, move_id in enumerate(move_ids, start=1):
        move = get_move(move_id)

        if move is None:
            continue

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
                int(move.get("pp", move.get("max_pp", 0)) or 0),
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
    nature: str | None = None,
    nickname: str | None = None,
) -> dict[str, Any] | None:
    """
    Create a Pokémon belonging to a player.

    Matches the actual database schema in Server/database.py.
    """
    species = get_species(species_id)

    if species is None:
        raise ValueError(
            f"Pokémon species '{species_id}' was not found "
            f"in Data/pokemon.json."
        )

    level = max(1, int(level))

    if not nature:
        nature = generate_nature()

    gender = generate_gender(species)
    ivs = generate_ivs()

    max_hp = calculate_hp(
        species,
        level,
        iv=ivs["hp"],
        ev=0,
    )

    unique_id = generate_unique_id()

    with get_connection() as db:
        cursor = db.execute(
            """
            INSERT INTO pokemon
            (
                unique_id,
                owner_id,
                species_id,
                nickname,
                level,
                experience,
                gender,
                shiny,
                variant,
                nature,
                current_hp,
                max_hp,
                status,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unique_id,
                owner_id,
                str(species_id),
                nickname,
                level,
                0,
                gender,
                int(bool(shiny)),
                variant or "normal",
                nature,
                max_hp,
                max_hp,
                "healthy",
                1,
            ),
        )

        pokemon_id = int(cursor.lastrowid)

        # --------------------------------------------------------
        # IV / EV record
        # --------------------------------------------------------

        db.execute(
            """
            INSERT INTO pokemon_stats
            (
                pokemon_id,
                hp_iv,
                attack_iv,
                defense_iv,
                sp_attack_iv,
                sp_defense_iv,
                speed_iv,
                hp_ev,
                attack_ev,
                defense_ev,
                sp_attack_ev,
                sp_defense_ev,
                speed_ev
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pokemon_id,
                ivs["hp"],
                ivs["attack"],
                ivs["defense"],
                ivs["sp_attack"],
                ivs["sp_defense"],
                ivs["speed"],
                0,
                0,
                0,
                0,
                0,
                0,
            ),
        )

        # --------------------------------------------------------
        # Starting moves
        # --------------------------------------------------------

        add_starting_moves(
            db,
            pokemon_id,
            species,
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
    """
    Get one Pokémon owned by a player.

    Move information is merged from Data/moves.json in Python.
    """
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

        # --------------------------------------------------------
        # Species
        # --------------------------------------------------------

        species = get_species(
            pokemon.get("species_id")
        )

        if species:
            pokemon["species"] = species
            pokemon["species_name"] = species.get(
                "name",
                "Unknown",
            )

        # --------------------------------------------------------
        # Stats
        # --------------------------------------------------------

        stats_row = db.execute(
            """
            SELECT *
            FROM pokemon_stats
            WHERE pokemon_id = ?
            """,
            (pokemon_id,),
        ).fetchone()

        if stats_row:
            pokemon["stats"] = dict(stats_row)
        else:
            pokemon["stats"] = {}

        # --------------------------------------------------------
        # Variant
        # --------------------------------------------------------

        variant = get_variant(
            pokemon.get("variant")
        )

        if variant:
            pokemon["variant_data"] = variant

        # --------------------------------------------------------
        # Moves
        # --------------------------------------------------------

        pokemon["moves"] = []

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
            move_data = dict(move_row)

            move = get_move(
                move_data.get("move_id")
            )

            if move:
                move_data["name"] = move.get(
                    "name",
                    move_data.get("move_id"),
                )

                move_data["type"] = move.get(
                    "type",
                )

                move_data["power"] = move.get(
                    "power",
                )

                move_data["accuracy"] = move.get(
                    "accuracy",
                )

                move_data["pp"] = move.get(
                    "pp",
                    move.get("max_pp"),
                )

                move_data["move_data"] = move

            pokemon["moves"].append(move_data)

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

        result: list[dict[str, Any]] = []

        for row in rows:
            pokemon = dict(row)

            species = get_species(
                pokemon.get("species_id")
            )

            if species:
                pokemon["species"] = species
                pokemon["species_name"] = species.get(
                    "name",
                    "Unknown",
                )

            result.append(pokemon)

        return result


# ============================================================
# PARTY
# ============================================================

def get_party(
    owner_id: int,
) -> list[dict[str, Any]]:
    """
    Return the player's active party.

    The current database does not have a separate party table.
    Party membership is represented by pokemon.is_active.
    """
    with get_connection() as db:
        rows = db.execute(
            """
            SELECT *
            FROM pokemon
            WHERE owner_id = ?
              AND is_active = 1
            ORDER BY id
            LIMIT 6
            """,
            (owner_id,),
        ).fetchall()

        return [dict(row) for row in rows]


def add_to_party(
    owner_id: int,
    pokemon_id: int,
) -> bool:
    """Add a Pokémon to the active party."""
    with get_connection() as db:
        pokemon = db.execute(
            """
            SELECT id
            FROM pokemon
            WHERE id = ?
              AND owner_id = ?
            """,
            (
                pokemon_id,
                owner_id,
            ),
        ).fetchone()

        if pokemon is None:
            return False

        party_count = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pokemon
            WHERE owner_id = ?
              AND is_active = 1
            """,
            (owner_id,),
        ).fetchone()["count"]

        # Already active.
        current = db.execute(
            """
            SELECT is_active
            FROM pokemon
            WHERE id = ?
              AND owner_id = ?
            """,
            (
                pokemon_id,
                owner_id,
            ),
        ).fetchone()

        if current and current["is_active"]:
            return True

        if party_count >= 6:
            return False

        db.execute(
            """
            UPDATE pokemon
            SET is_active = 1
            WHERE id = ?
              AND owner_id = ?
            """,
            (
                pokemon_id,
                owner_id,
            ),
        )

        db.commit()

        return True


def remove_from_party(
    owner_id: int,
    pokemon_id: int,
) -> bool:
    """Remove a Pokémon from the active party."""
    with get_connection() as db:
        cursor = db.execute(
            """
            UPDATE pokemon
            SET is_active = 0
            WHERE id = ?
              AND owner_id = ?
            """,
            (
                pokemon_id,
                owner_id,
            ),
        )

        db.commit()

        return cursor.rowcount > 0


# ============================================================
# STARTER
# ============================================================

def give_starter(
    owner_id: int,
    species_id: int | str,
) -> dict[str, Any] | None:
    """
    Give a player a level-5 starter and make it active.
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

    pokemon_id = pokemon.get("id")

    if pokemon_id is not None:
        add_to_party(
            owner_id,
            int(pokemon_id),
        )

        pokemon = get_pokemon(
            owner_id,
            int(pokemon_id),
        )

    return pokemon


def ensure_player_starter(
    owner_id: int,
    species_id: int | str,
) -> dict[str, Any] | None:
    """
    Give the player a starter only if they do not already own one.
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

        return dict(row) if row else None


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
    data = load_data("areas.json")

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
    wanted = str(area_id)

    for area in get_all_areas():
        if str(area.get("id")) == wanted:
            return area

        if str(area.get("slug", "")).lower() == wanted.lower():
            return area

        if str(area.get("name", "")).lower() == wanted.lower():
            return area

    return None


def get_area_encounters(
    area_id: int | str,
) -> list[dict[str, Any]]:
    """Return encounter entries for an area."""
    area = get_area(area_id)

    if not area:
        return []

    encounters = area.get("encounters")

    if isinstance(encounters, list):
        return encounters

    return []


def generate_encounter(
    area_id: int | str,
) -> dict[str, Any] | None:
    """Choose a random weighted encounter."""
    encounters = get_area_encounters(area_id)

    if not encounters:
        return None

    weighted: list[
        tuple[dict[str, Any], float]
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
        except (TypeError, ValueError):
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
    data = load_data("items.json")

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
    wanted = str(item_id)

    for item in get_all_items():
        if str(item.get("id")) == wanted:
            return item

        if str(item.get("slug", "")).lower() == wanted.lower():
            return item

        if str(item.get("name", "")).lower() == wanted.lower():
            return item

    return None


# ============================================================
# QUESTS
# ============================================================

def get_all_quests() -> list[dict[str, Any]]:
    """Return quests from JSON."""
    data = load_data("quests.json")

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
    wanted = str(quest_id)

    for quest in get_all_quests():
        if str(quest.get("id")) == wanted:
            return quest

        if str(quest.get("slug", "")).lower() == wanted.lower():
            return quest

    return None


# ============================================================
# ITEMS / INVENTORY
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

        return [dict(row) for row in rows]


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
                quantity = quantity + excluded.quantity
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

        current = int(row["quantity"])

        if current < quantity:
            return False

        new_quantity = current - quantity

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
    progress = get_player_progress(player_id)

    if not progress:
        return 0

    return int(progress.get("money", 0))


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

        current = int(row["money"])

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