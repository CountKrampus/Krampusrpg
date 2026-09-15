from __future__ import annotations

import random
from typing import Any

from Server.database import get_connection
from Server.services import get_species, calculate_pokemon_stats


def can_breed(
    pokemon1_id: int,
    pokemon2_id: int,
) -> tuple[bool, str]:
    """
    Check if two Pokémon can breed.

    Returns:
        (can_breed: bool, reason: str)
    """
    with get_connection() as db:
        # Get both Pokémon
        pokemon1 = db.execute(
            "SELECT * FROM pokemon WHERE id = ?",
            (pokemon1_id,),
        ).fetchone()

        pokemon2 = db.execute(
            "SELECT * FROM pokemon WHERE id = ?",
            (pokemon2_id,),
        ).fetchone()

        if not pokemon1 or not pokemon2:
            return False, "One or both Pokémon not found"

        # Check they belong to the same owner
        if pokemon1["owner_id"] != pokemon2["owner_id"]:
            return False, "Pokémon must belong to the same owner"

        # Check they're different Pokémon
        if pokemon1["id"] == pokemon2["id"]:
            return False, "Cannot breed a Pokémon with itself"

        # Check species compatibility (simplified)
        # In full implementation, this would use egg groups
        species1 = get_species(pokemon1["species_id"])
        species2 = get_species(pokemon2["species_id"])

        if not species1 or not species2:
            return False, "Species data not found"

        # Same species can breed
        if pokemon1["species_id"] == pokemon2["species_id"]:
            return True, "Same species breeding allowed"

        # Different species breeding (simplified - would use egg groups)
        return True, "Different species breeding allowed"


def calculate_egg_species(
    pokemon1_id: int,
    pokemon2_id: int,
) -> str:
    """
    Calculate the species of an egg from two parents.

    Simplified logic: the egg will be the species of the mother (or first parent).
    """
    with get_connection() as db:
        pokemon1 = db.execute(
            "SELECT * FROM pokemon WHERE id = ?",
            (pokemon1_id,),
        ).fetchone()

        # Simplified: use first parent's species
        return pokemon1["species_id"]


def create_egg(
    owner_id: int,
    pokemon1_id: int,
    pokemon2_id: int,
) -> dict[str, Any] | None:
    """
    Create an egg from two parent Pokémon.

    Returns:
        Egg data or None if breeding failed
    """
    can_breed, reason = can_breed(pokemon1_id, pokemon2_id)

    if not can_breed:
        return None

    egg_species = calculate_egg_species(pokemon1_id, pokemon2_id)

    # Mark as egg and create basic database entry
    # In full implementation, this would use create_pokemon
    with get_connection() as db:
        # Generate unique ID for the egg
        import secrets
        unique_id = secrets.token_hex(12)

        # Insert egg as a level 1 Pokémon
        cursor = db.execute(
            """
            INSERT INTO pokemon
            (unique_id, owner_id, species_id, level, experience, gender, shiny, variant, current_hp, max_hp, nickname)
            VALUES (?, ?, ?, 1, 0, 'unknown', 0, 'normal', 1, 1, 'Egg')
            """,
            (unique_id, owner_id, egg_species, ),
        )

        egg_id = cursor.lastrowid

        # Create stats entry
        species = get_species(egg_species)
        if species:
            stats = calculate_pokemon_stats(species, 1)

            db.execute(
                """
                INSERT INTO pokemon_stats
                (pokemon_id, hp, attack, defense, sp_attack, sp_defense, speed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (egg_id, stats["hp"], stats["attack"], stats["defense"],
                 stats["sp_attack"], stats["sp_defense"], stats["speed"]),
            )

        db.commit()

        # Return egg data
        egg = db.execute(
            "SELECT * FROM pokemon WHERE id = ?",
            (egg_id,),
        ).fetchone()

        return dict(egg) if egg else None


def get_egg_hatch_steps(
    species_id: str,
) -> int:
    """
    Get the number of steps required for an egg to hatch.

    Simplified: most species hatch in around 5000 steps.
    """
    # Different species have different hatch rates
    # This would be species-specific data
    base_steps = 5000

    # Adjust for species (simplified)
    fast_hatch_species = ["pikachu", "cleffa", "igglybuff", "jigglypuff"]
    if species_id.lower() in fast_hatch_species:
        return base_steps // 2

    slow_hatch_species = ["larvitar", "bagon", "trapinch", "snorunt"]
    if species_id.lower() in slow_hatch_species:
        return base_steps * 2

    return base_steps


def hatch_egg(
    pokemon_id: int,
    steps_walked: int,
) -> dict[str, Any] | None:
    """
    Attempt to hatch an egg based on steps walked.

    Returns:
        Hatched Pokémon data or None if not ready to hatch
    """
    with get_connection() as db:
        pokemon = db.execute(
            "SELECT * FROM pokemon WHERE id = ?",
            (pokemon_id,),
        ).fetchone()

        if not pokemon:
            return None

        if pokemon.get("nickname") != "Egg":
            return None

        species_id = pokemon["species_id"]
        required_steps = get_egg_hatch_steps(species_id)

        if steps_walked < required_steps:
            return {
                "success": False,
                "ready": False,
                "steps_remaining": required_steps - steps_walked,
            }

        # Hatch the egg
        db.execute(
            """
            UPDATE pokemon
            SET nickname = NULL,
                current_hp = (SELECT hp FROM pokemon_stats WHERE pokemon_id = ?),
                max_hp = (SELECT hp FROM pokemon_stats WHERE pokemon_id = ?)
            WHERE id = ?
            """,
            (pokemon_id, pokemon_id, pokemon_id),
        )

        db.commit()

        hatched = db.execute(
            "SELECT * FROM pokemon WHERE id = ?",
            (pokemon_id,),
        ).fetchone()

        return {
            "success": True,
            "pokemon": dict(hatched) if hatched else None,
        }


def get_breeding_compatibility(
    pokemon1_id: int,
    pokemon2_id: int,
) -> dict[str, Any]:
    """
    Get detailed breeding compatibility information.

    Returns:
        Compatibility data with chances and egg information
    """
    can_breed_result, reason = can_breed(pokemon1_id, pokemon2_id)

    if not can_breed_result:
        return {
            "can_breed": False,
            "reason": reason,
        }

    with get_connection() as db:
        pokemon1 = db.execute(
            "SELECT * FROM pokemon WHERE id = ?",
            (pokemon1_id,),
        ).fetchone()

        pokemon2 = db.execute(
            "SELECT * FROM pokemon WHERE id = ?",
            (pokemon2_id,),
        ).fetchone()

        species1 = get_species(pokemon1["species_id"])
        species2 = get_species(pokemon2["species_id"])

        egg_species = calculate_egg_species(pokemon1_id, pokemon2_id)
        hatch_steps = get_egg_hatch_steps(egg_species)

        return {
            "can_breed": True,
            "egg_species": egg_species,
            "hatch_steps": hatch_steps,
            "parent1": dict(pokemon1),
            "parent2": dict(pokemon2),
            "species1": species1,
            "species2": species2,
        }


def get_day_care_center_capacity(player_id: int) -> dict[str, Any]:
    """
    Get information about a player's Day Care center usage.

    Returns:
        Capacity information with current usage
    """
    # This would be implemented with a day_care table
    # For now, return default capacity
    return {
        "max_eggs": 10,
        "current_eggs": 0,
        "available_slots": 10,
    }


__all__ = [
    "can_breed",
    "calculate_egg_species",
    "create_egg",
    "get_egg_hatch_steps",
    "hatch_egg",
    "get_breeding_compatibility",
    "get_day_care_center_capacity",
]
