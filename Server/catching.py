"""
Krampus RPG Catching System

Powers wild encounters and ball throwing:

- Server/catching.py (this file): encounter generation with levels and
  shiny rolls, plus the catch-rate formula and attempt_catch() which
  consumes a ball from the player's bag and creates the Pokémon on
  success.
- The /world-exploration page and its API endpoints (registered in
  Server/app.py): area selection, "Search for Pokémon", and the ball
  throwing UI.

Ball data comes from Data/items.json entries whose "type" is
"pokeball" (poke_ball, great_ball, ultra_ball). Each ball may carry a
"catch_multiplier" — poke 1.0, great 1.5, ultra 2.0 by default.

The catch formula is a simplified Gen-1-style roll:

    catch_rate = base_rate * ball_multiplier * level_factor

- base_rate: per-species "catch_rate" from Data/pokemon.json
  (defaults to 45 when absent, the classic mid-tier value).
- level_factor: higher-level wild Pokémon are harder to catch.
- The result is clamped into [3%, 95%] so no catch is ever
  guaranteed or impossible.
"""

from __future__ import annotations

import random
from typing import Any

from .services import (
    create_pokemon,
    generate_encounter,
    get_item,
    get_player_items,
    get_species,
    remove_item,
)

# Per-species default when Data/pokemon.json has no catch_rate.
DEFAULT_CATCH_RATE = 45.0

# Clamps on the final catch chance (percent).
MIN_CATCH_CHANCE = 3.0
MAX_CATCH_CHANCE = 95.0

# Wild shiny odds (1 in N).
SHINY_ODDS = 512

# Ball type id -> default catch multiplier when the item record
# doesn't carry one.
BALL_TYPE_FALLBACK = {
    "poke_ball": 1.0,
    "great_ball": 1.5,
    "ultra_ball": 2.0,
}

# Fallback order: which balls the throw endpoint uses when no
# specific ball id is given.
DEFAULT_THROW_ORDER = ("poke_ball", "great_ball", "ultra_ball")


# ============================================================
# ENCOUNTERS
# ============================================================

def _roll_level(entry: dict[str, Any]) -> int:
    """Roll a level in the encounter entry's min..max range."""

    try:
        min_level = max(1, int(entry.get("min_level", 1)))
    except (TypeError, ValueError):
        min_level = 1

    try:
        max_level = max(min_level, int(entry.get("max_level", min_level)))
    except (TypeError, ValueError):
        max_level = min_level

    return random.randint(min_level, max_level)


def start_encounter(area_id: str | int) -> dict[str, Any] | None:
    """
    Generate a wild Pokémon encounter for an area.

    Returns None when the area has no encounters. Otherwise returns:

        {
            "species_id", "species_name", "types", "level",
            "shiny", "base_stats", "catch_rate", "sprite_url"
        }

    This is a transient description of the wild Pokémon (nothing is
    persisted until it's actually caught) so the client can't ask the
    server to "catch" a species that wasn't really encountered.
    """

    entry = generate_encounter(area_id)

    if entry is None:
        return None

    species_id = str(entry.get("species_id", "")).strip().lower()
    species = get_species(species_id)

    if species is None:
        return None

    level = _roll_level(entry)
    shiny = random.randint(1, SHINY_ODDS) == 1

    from .sprite_resolver import resolve_sprite

    return {
        "species_id": species["id"],
        "species_name": species.get("name", species["id"].title()),
        "types": species.get("type", []),
        "level": level,
        "shiny": shiny,
        "base_stats": species.get("base_stats", {}),
        "catch_rate": get_species_catch_rate(species),
        "sprite_url": resolve_sprite(
            species["id"],
            shiny=shiny,
        ),
    }


# ============================================================
# CATCH RATE
# ============================================================

def get_species_catch_rate(species: dict[str, Any] | None) -> float:
    """Species catch rate from its record, or the default."""

    if not species:
        return DEFAULT_CATCH_RATE

    try:
        rate = float(species.get("catch_rate", DEFAULT_CATCH_RATE))
    except (TypeError, ValueError):
        rate = DEFAULT_CATCH_RATE

    if rate <= 0:
        return DEFAULT_CATCH_RATE

    return rate


def get_ball_multiplier(item_id: str) -> float:
    """Catch multiplier for a ball item, from its record or fallbacks."""

    ball = get_item(item_id)

    if ball is None or str(ball.get("type", "")).lower() != "pokeball":
        return 0.0

    try:
        multiplier = float(ball.get("catch_multiplier", 0))
    except (TypeError, ValueError):
        multiplier = 0.0

    if multiplier <= 0:
        multiplier = BALL_TYPE_FALLBACK.get(
            str(ball.get("id", "")).lower(),
            1.0,
        )

    return multiplier


def calculate_catch_chance(
    encounter: dict[str, Any],
    ball_item_id: str,
) -> float:
    """
    Catch chance (percent) for a wild encounter with a given ball.

    Level penalty: a soft curve that barely matters for low-level wild
    Pokémon and caps around -30% for very high levels.
    """

    multiplier = get_ball_multiplier(ball_item_id)

    if multiplier <= 0:
        return 0.0

    base_rate = get_species_catch_rate(
        get_species(encounter.get("species_id"))
    )

    level = max(1, int(encounter.get("level", 1)))
    level_factor = 1.0 - min(level, 50) * 0.006

    chance = base_rate * multiplier * level_factor

    return round(min(MAX_CATCH_CHANCE, max(MIN_CATCH_CHANCE, chance)), 2)


# ============================================================
# BALL INVENTORY
# ============================================================

def get_player_balls(player_id: int) -> list[dict[str, Any]]:
    """
    The player's Poké Balls with catalog data and catch chances kept
    out (those depend on the encounter) — sorted by strength.
    """

    balls: list[dict[str, Any]] = []

    owned = {
        str(entry.get("item_id", "")).lower(): int(entry.get("quantity", 0))
        for entry in get_player_items(player_id)
    }

    for item in get_player_items(player_id):
        item_id = str(item.get("item_id", "")).lower()

        if int(item.get("quantity", 0)) <= 0:
            continue

        ball = get_item(item_id)

        if ball is None or str(ball.get("type", "")).lower() != "pokeball":
            continue

        balls.append(
            {
                "item_id": item_id,
                "name": ball.get("name", item_id.title()),
                "quantity": int(item.get("quantity", 0)),
                "catch_multiplier": get_ball_multiplier(item_id),
                "description": ball.get("description", ""),
            }
        )

    # Also surface balls the catalog knows about that the player owns
    # but get_all_items() ordering may have skipped (defensive; cheap).
    for item_id, quantity in owned.items():
        if quantity <= 0 or any(b["item_id"] == item_id for b in balls):
            continue

        ball = get_item(item_id)

        if ball is None or str(ball.get("type", "")).lower() != "pokeball":
            continue

        balls.append(
            {
                "item_id": item_id,
                "name": ball.get("name", item_id.title()),
                "quantity": quantity,
                "catch_multiplier": get_ball_multiplier(item_id),
                "description": ball.get("description", ""),
            }
        )

    balls.sort(key=lambda b: b["catch_multiplier"])

    return balls


def _consume_ball(player_id: int, ball_item_id: str) -> str:
    """
    Pick the ball to spend and remove it from the bag.

    With an explicit ball_item_id: verifies the player owns it.
    Otherwise: uses the strongest ball the player owns (players would
    rather save their Ultra Balls; strongest-first also matches player
    expectation that a manual choice was saved).

    Returns the consumed ball's item id.
    Raises ValueError when the player has no usable ball.
    """

    if ball_item_id:
        ball_id = str(ball_item_id).strip().lower()

        if get_ball_multiplier(ball_id) <= 0:
            raise ValueError(f"{ball_id.replace('_', ' ')} is not a Poké Ball.")

        owned = any(
            str(entry.get("item_id", "")).lower() == ball_id
            and int(entry.get("quantity", 0)) > 0
            for entry in get_player_items(player_id)
        )

        if not owned:
            raise ValueError("You don't have that Poké Ball.")

    else:
        balls = [
            ball for ball in get_player_balls(player_id)
            if ball["quantity"] > 0
        ]

        if not balls:
            raise ValueError("You have no Poké Balls.")

        # Strongest first for auto-throw.
        balls.sort(key=lambda b: b["catch_multiplier"], reverse=True)

        ball_id = balls[0]["item_id"]

    # Actually spend the ball — this is the only place inventory is
    # touched, and it happens before the roll so a catch can never be
    # free.
    if not remove_item(player_id, ball_id, 1):
        raise ValueError("You have no Poké Balls left.")

    return ball_id


# ============================================================
# THE CATCH
# ============================================================

def attempt_catch(
    player_id: int,
    encounter: dict[str, Any],
    ball_item_id: str = "",
) -> dict[str, Any]:
    """
    Attempt to catch a wild encounter.

    - Consumes exactly one ball (the given one, or the player's
      strongest).
    - Rolls against the catch chance.
    - On success, creates the Pokémon (with its rolled shiny status)
      into the player's Party/PC via create_pokemon().

    Raises ValueError on invalid input (no ball, malformed encounter).

    Returns:

        {
            "success", "caught", "ball", "catch_chance",
            "roll", "pokemon" (when caught: full record)
        }
    """

    species_id = str(encounter.get("species_id", "")).strip().lower()

    if not species_id or get_species(species_id) is None:
        raise ValueError("Invalid encounter.")

    try:
        level = int(encounter.get("level", 1))
    except (TypeError, ValueError):
        level = 1

    if not 1 <= level <= 100:
        raise ValueError("Invalid encounter level.")

    shiny = bool(encounter.get("shiny", False))

    ball_id = _consume_ball(player_id, ball_item_id)
    catch_chance = calculate_catch_chance(encounter, ball_id)

    roll = random.uniform(0, 100)
    caught = roll <= catch_chance

    result: dict[str, Any] = {
        "ball": ball_id,
        "ball_name": (get_item(ball_id) or {}).get("name", ball_id.title()),
        "catch_chance": catch_chance,
        "roll": round(roll, 2),
        "caught": False,
    }

    if not caught:
        return result

    pokemon = create_pokemon(
        owner_id=player_id,
        species_id=species_id,
        level=level,
        shiny=shiny,
    )

    if pokemon is None:
        raise ValueError("Failed to create the caught Pokémon.")

    result["caught"] = True
    result["pokemon"] = {
        "id": pokemon["id"],
        "species_id": pokemon["species_id"],
        "species_name": pokemon.get("species_name", species_id.title()),
        "level": pokemon["level"],
        "shiny": bool(pokemon.get("shiny", 0)),
        "nickname": pokemon.get("nickname"),
    }

    return result
