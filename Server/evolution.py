from __future__ import annotations

from typing import Any

from .database import get_connection
from .services import get_species


def get_evolution_rules(
    from_species: str | None = None,
    to_species: str | None = None,
) -> list[dict[str, Any]]:
    """
    Get evolution rules from the database.

    Args:
        from_species: Filter by source species (optional)
        to_species: Filter by target species (optional)

    Returns:
        List of evolution rule dictionaries
    """
    with get_connection() as db:
        query = "SELECT * FROM evolution_rules WHERE 1=1"
        params = []

        if from_species:
            query += " AND from_species = ?"
            params.append(str(from_species).lower())

        if to_species:
            query += " AND to_species = ?"
            params.append(str(to_species).lower())

        query += " ORDER BY from_species, condition_level"

        rows = db.execute(query, params).fetchall()

        return [dict(row) for row in rows]


def get_evolution_chain(species_id: str) -> list[dict[str, Any]]:
    """
    Get the complete evolution chain for a species.

    Returns a list of evolution rules that apply to this species,
    ordered by the evolution sequence.
    """
    rules = get_evolution_rules(from_species=species_id)

    # Sort by level (if applicable) to maintain proper order
    rules.sort(key=lambda x: (x.get("condition_level") or 999))

    return rules


def can_evolve(
    pokemon: dict[str, Any],
    evolution_rule: dict[str, Any],
) -> tuple[bool, str]:
    """
    Check if a Pokémon can evolve according to a specific evolution rule.

    Returns:
        (can_evolve: bool, reason: str)
    """
    method = evolution_rule.get("method", "level")
    pokemon_level = int(pokemon.get("level", 1))

    if method == "level":
        required_level = evolution_rule.get("condition_level")
        if required_level is not None:
            required_level = int(required_level)
            if pokemon_level >= required_level:
                return True, f"Level {required_level} reached"
            return False, f"Requires level {required_level} (current: {pokemon_level})"

    elif method == "item":
        required_item = evolution_rule.get("condition_item")
        if required_item:
            return False, f"Requires {required_item}"
        return False, "Requires specific item"

    elif method == "friendship":
        required_friendship = evolution_rule.get("condition_friendship")
        if required_friendship is not None:
            return False, f"Requires friendship level {required_friendship}"
        return False, "Requires friendship evolution"

    elif method == "time":
        required_time = evolution_rule.get("condition_time")
        if required_time:
            return False, f"Requires {required_time}"
        return False, "Requires specific time"

    elif method == "location":
        required_location = evolution_rule.get("condition_location")
        if required_location:
            return False, f"Requires location: {required_location}"
        return False, "Requires specific location"

    elif method == "trade":
        held_item = evolution_rule.get("condition_held_item")
        if held_item:
            return False, f"Requires trading while holding {held_item}"
        return True, "Requires trading"

    return False, f"Unknown evolution method: {method}"


def get_evolution_options(pokemon: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Get all available evolution options for a Pokémon.

    Returns a list of evolution rules that the Pokémon currently satisfies.
    """
    species_id = pokemon.get("species_id", "")
    evolution_chain = get_evolution_chain(species_id)

    available = []

    for evo in evolution_chain:
        can_evo, reason = can_evolve(pokemon, evo)
        if can_evo:
            available.append({
                "rule": evo,
                "to_species": evo.get("to_species"),
                "method": evo.get("method"),
                "reason": reason,
            })

    return available


def evolve_pokemon(
    pokemon_id: int,
    to_species: str,
) -> dict[str, Any] | None:
    """
    Evolve a Pokémon to a new species.

    This performs the actual evolution:
    - Updates the species_id
    - Recalculates stats based on new species
    - Preserves level, experience, moves, and other properties
    - Updates shiny status and variant
    """
    with get_connection() as db:
        # Get current Pokémon data
        pokemon_row = db.execute(
            """
            SELECT * FROM pokemon WHERE id = ?
            """,
            (pokemon_id,),
        ).fetchone()

        if not pokemon_row:
            return None

        pokemon = dict(pokemon_row)
        current_level = int(pokemon.get("level", 1))
        current_experience = int(pokemon.get("experience", 0))
        current_shiny = bool(pokemon.get("shiny", 0))
        current_variant = pokemon.get("variant", "normal")

        # Get new species data
        new_species = get_species(to_species)
        if not new_species:
            return None

        # Calculate new stats
        from .services import calculate_pokemon_stats
        new_stats = calculate_pokemon_stats(new_species, current_level)

        # Update Pokémon in database
        db.execute(
            """
            UPDATE pokemon
            SET species_id = ?,
                current_hp = ?,
                max_hp = ?
            WHERE id = ?
            """,
            (
                str(to_species),
                new_stats["hp"],
                new_stats["hp"],
                pokemon_id,
            ),
        )

        # Update stats table
        db.execute(
            """
            UPDATE pokemon_stats
            SET hp = ?,
                attack = ?,
                defense = ?,
                sp_attack = ?,
                sp_defense = ?,
                speed = ?
            WHERE pokemon_id = ?
            """,
            (
                new_stats["hp"],
                new_stats["attack"],
                new_stats["defense"],
                new_stats["sp_attack"],
                new_stats["sp_defense"],
                new_stats["speed"],
                pokemon_id,
            ),
        )

        db.commit()

        # Return updated Pokémon data
        updated_row = db.execute(
            """
            SELECT * FROM pokemon WHERE id = ?
            """,
            (pokemon_id,),
        ).fetchone()

        return dict(updated_row) if updated_row else None


def check_evolution_trigger(
    pokemon: dict[str, Any],
    trigger_type: str = "level_up",
    **trigger_data: Any,
) -> dict[str, Any] | None:
    """
    Check if evolution should trigger after an event.

    Args:
        pokemon: The Pokémon data
        trigger_type: The event that triggered the check (level_up, item_use, trade, etc.)
        trigger_data: Additional data relevant to the trigger

    Returns:
        Evolution data if evolution should occur, None otherwise
    """
    species_id = pokemon.get("species_id", "")
    evolution_chain = get_evolution_chain(species_id)

    for evo in evolution_chain:
        method = evo.get("method", "")

        if trigger_type == "level_up" and method == "level":
            new_level = trigger_data.get("new_level", 0)
            required_level = evo.get("condition_level")

            if required_level is not None and new_level >= int(required_level):
                return {
                    "evolution": evo,
                    "to_species": evo.get("to_species"),
                    "method": method,
                    "trigger": "level_up",
                }

        elif trigger_type == "item_use" and method == "item":
            used_item = trigger_data.get("item", "")
            required_item = evo.get("condition_item")

            if required_item and used_item == required_item:
                return {
                    "evolution": evo,
                    "to_species": evo.get("to_species"),
                    "method": method,
                    "trigger": "item_use",
                }

        elif trigger_type == "trade" and method == "trade":
            held_item = evo.get("condition_held_item")
            pokemon_held_item = trigger_data.get("held_item")

            if not held_item or pokemon_held_item == held_item:
                return {
                    "evolution": evo,
                    "to_species": evo.get("to_species"),
                    "method": method,
                    "trigger": "trade",
                }

    return None


def add_evolution_rule(
    from_species: str,
    to_species: str,
    method: str = "level",
    condition_level: int | None = None,
    condition_item: str | None = None,
    condition_friendship: int | None = None,
    condition_time: str | None = None,
    condition_location: str | None = None,
    condition_held_item: str | None = None,
    description: str = "",
) -> bool:
    """
    Add a new evolution rule to the database.

    Returns True if successful, False otherwise.
    """
    with get_connection() as db:
        try:
            db.execute(
                """
                INSERT INTO evolution_rules
                (
                    from_species, to_species, method,
                    condition_level, condition_item, condition_friendship,
                    condition_time, condition_location, condition_held_item,
                    description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    from_species.lower(),
                    to_species.lower(),
                    method,
                    condition_level,
                    condition_item,
                    condition_friendship,
                    condition_time,
                    condition_location,
                    condition_held_item,
                    description,
                ),
            )
            db.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def remove_evolution_rule(rule_id: int) -> bool:
    """
    Remove an evolution rule from the database.

    Returns True if successful, False otherwise.
    """
    with get_connection() as db:
        cursor = db.execute(
            "DELETE FROM evolution_rules WHERE id = ?",
            (rule_id,),
        )
        db.commit()
        return cursor.rowcount > 0


__all__ = [
    "get_evolution_rules",
    "get_evolution_chain",
    "can_evolve",
    "get_evolution_options",
    "evolve_pokemon",
    "check_evolution_trigger",
    "add_evolution_rule",
    "remove_evolution_rule",
]
