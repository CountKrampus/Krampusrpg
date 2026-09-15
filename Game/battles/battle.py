from __future__ import annotations

import random
from typing import Any

from Server.services import get_move


def calculate_damage(
    attack: int,
    defense: int,
    power: int,
    level: int,
    stab: float = 1.0,
    type_effectiveness: float = 1.0,
    critical: bool = False,
) -> int:
    """
    Calculate damage using the standard Pokémon damage formula.

    Args:
        attack: Attacker's attack stat
        defense: Defender's defense stat
        power: Move power
        level: Attacker's level
        stab: Same-type attack bonus (1.0 or 1.5)
        type_effectiveness: Type effectiveness multiplier
        critical: Whether this is a critical hit

    Returns:
        Calculated damage value
    """
    attack = max(1, attack)
    defense = max(1, defense)
    power = max(1, power)
    level = max(1, level)

    # Base damage calculation
    base_damage = (
        (
            ((2 * level // 5) + 2)
            * power
            * attack
            // defense
        )
        // 50
    ) + 2

    # Apply modifiers
    modifiers = stab * type_effectiveness

    if critical:
        modifiers *= 1.5

    # Random factor (0.85 to 1.0)
    random_factor = random.uniform(0.85, 1.0)
    modifiers *= random_factor

    damage = int(base_damage * modifiers)

    return max(1, damage)


def apply_damage(current_hp: int, damage: int) -> int:
    """Apply damage to current HP, ensuring it doesn't go below 0."""
    return max(0, current_hp - max(0, damage))


def calculate_type_effectiveness(
    move_type: str,
    defender_types: list[str],
) -> float:
    """
    Calculate type effectiveness for a move against defender's types.

    Returns:
        Effectiveness multiplier (0.0, 0.25, 0.5, 1.0, 2.0, 4.0)
    """
    # Simplified type chart - in production this would be a full matrix
    type_chart = {
        "fire": {"grass": 2.0, "water": 0.5, "fire": 0.5, "ice": 2.0, "bug": 2.0},
        "water": {"fire": 2.0, "grass": 0.5, "water": 0.5, "ground": 2.0, "rock": 2.0},
        "grass": {"water": 2.0, "fire": 0.5, "grass": 0.5, "ground": 2.0, "flying": 0.5},
        "electric": {"water": 2.0, "grass": 0.5, "electric": 0.5, "ground": 0.0, "flying": 2.0},
        "ice": {"grass": 2.0, "ground": 2.0, "flying": 2.0, "fire": 0.5, "ice": 0.5},
        "fighting": {"normal": 2.0, "ice": 2.0, "rock": 2.0, "flying": 0.5, "psychic": 0.5},
        "poison": {"grass": 2.0, "poison": 0.5, "ground": 0.5, "rock": 0.5},
        "ground": {"electric": 2.0, "fire": 2.0, "poison": 2.0, "flying": 0.0, "grass": 0.5},
        "flying": {"grass": 2.0, "fighting": 2.0, "bug": 2.0, "electric": 0.5, "rock": 0.5},
        "psychic": {"fighting": 2.0, "poison": 2.0, "psychic": 0.5, "dark": 0.0},
        "bug": {"grass": 2.0, "psychic": 2.0, "fire": 0.5, "fighting": 0.5, "flying": 0.5},
        "rock": {"fire": 2.0, "ice": 2.0, "flying": 2.0, "fighting": 0.5, "ground": 0.5},
        "ghost": {"psychic": 2.0, "ghost": 2.0, "normal": 0.0, "dark": 0.5},
        "dragon": {"dragon": 2.0, "fairy": 0.0},
        "dark": {"psychic": 2.0, "ghost": 2.0, "dark": 0.5, "fighting": 0.5},
        "steel": {"ice": 2.0, "rock": 2.0, "fire": 0.5, "water": 0.5, "electric": 0.5},
        "fairy": {"fighting": 2.0, "dragon": 2.0, "poison": 0.5, "fire": 0.5},
    }

    effectiveness = 1.0

    for defender_type in defender_types:
        defender_type = defender_type.lower()
        if move_type in type_chart:
            effectiveness *= type_chart[move_type].get(defender_type, 1.0)

    return effectiveness


def check_critical_hit(
    speed: int,
    move: dict[str, Any] | None = None,
) -> bool:
    """
    Check if an attack is a critical hit.

    Critical hit chance is based on speed (base 1/16) and can be modified by moves.
    """
    base_chance = 1 / 16

    # Some moves increase critical hit chance
    if move and move.get("high_critical"):
        base_chance = 1 / 8

    return random.random() < base_chance


def calculate_stat_modifier(
    stat_name: str,
    stages: int,
) -> float:
    """
    Calculate stat modifier based on stat stages (-6 to +6).

    Returns:
        Multiplier for the stat
    """
    stage_multipliers = {
        -6: 2/8, -5: 2/7, -4: 2/6, -3: 2/5, -2: 2/4, -1: 2/3,
        0: 1.0,
        1: 3/2, 2: 4/2, 3: 5/2, 4: 6/2, 5: 7/2, 6: 8/2,
    }

    return stage_multipliers.get(stages, 1.0)


def get_speed_priority(pokemon: dict[str, Any]) -> int:
    """
    Determine move priority based on speed and abilities.

    Returns:
        Priority value (higher = moves first)
    """
    base_speed = pokemon.get("stats", {}).get("speed", 50)

    # Quick Claw ability could give priority
    ability = pokemon.get("ability")
    if ability == "quick_claw" and random.random() < 0.2:
        return 1

    # Normal priority based on speed
    return 0


def is_stab(
    move_type: str,
    pokemon_types: list[str],
) -> bool:
    """
    Check if a move gets Same-Type Attack Bonus (STAB).

    Returns:
        True if move type matches one of Pokémon's types
    """
    return move_type.lower() in [t.lower() for t in pokemon_types]


def simulate_turn(
    attacker: dict[str, Any],
    defender: dict[str, Any],
    move_id: str,
) -> dict[str, Any]:
    """
    Simulate a single battle turn.

    Args:
        attacker: Attacking Pokémon data
        defender: Defending Pokémon data
        move_id: Move to use

    Returns:
        Turn result with damage, effectiveness, etc.
    """
    move = get_move(move_id)

    if not move:
        return {
            "success": False,
            "message": "Move not found",
            "damage": 0,
        }

    attacker_stats = attacker.get("stats", {})
    defender_stats = defender.get("stats", {})

    # Get relevant stats
    is_special = move.get("category") == "special"
    attack_stat = attacker_stats.get("sp_attack" if is_special else "attack", 50)
    defense_stat = defender_stats.get("sp_defense" if is_special else "defense", 50)

    # Calculate effectiveness
    move_type = move.get("type", "normal")
    defender_types = attacker.get("types", [move_type])  # Fallback to move type
    effectiveness = calculate_type_effectiveness(move_type, defender_types)

    # Check STAB
    attacker_types = attacker.get("types", ["normal"])
    stab = 1.5 if is_stab(move_type, attacker_types) else 1.0

    # Check critical hit
    speed = attacker_stats.get("speed", 50)
    critical = check_critical_hit(speed, move)

    # Calculate damage
    damage = calculate_damage(
        attack_stat,
        defense_stat,
        move.get("power", 40),
        attacker.get("level", 50),
        stab,
        effectiveness,
        critical,
    )

    # Apply damage
    current_hp = defender.get("current_hp", defender_stats.get("hp", 100))
    new_hp = apply_damage(current_hp, damage)

    # Determine effectiveness message
    if effectiveness >= 2.0:
        effectiveness_msg = "It's super effective!"
    elif effectiveness <= 0.5:
        effectiveness_msg = "It's not very effective..."
    elif effectiveness == 0.0:
        effectiveness_msg = "It doesn't affect the opponent..."
    else:
        effectiveness_msg = ""

    return {
        "success": True,
        "damage": damage,
        "new_hp": new_hp,
        "old_hp": current_hp,
        "effectiveness": effectiveness,
        "effectiveness_msg": effectiveness_msg,
        "critical": critical,
        "stab": stab,
        "move": move,
    }


def calculate_experience_gain(
    defeated_level: int,
    base_exp: int,
    is_wild: bool = True,
    participants: int = 1,
) -> int:
    """
    Calculate experience gained from defeating a Pokémon.

    Formula: (base_exp * level * is_wild) / (7 * participants)
    """
    if is_wild:
        wild_multiplier = 1.0
    else:
        wild_multiplier = 1.5

    exp = int((base_exp * defeated_level * wild_multiplier) / (7 * participants))
    return max(1, exp)


def calculate_level_up(level: int, current_exp: int, species: dict[str, Any]) -> tuple[int, int]:
    """
    Calculate if a Pokémon levels up and returns new level and remaining exp.

    Returns:
        (new_level, remaining_exp)
    """
    # Simplified experience curve - cubic
    exp_needed = int(level ** 3)

    if current_exp >= exp_needed:
        remaining_exp = current_exp - exp_needed
        new_level = level + 1
        return new_level, remaining_exp

    return level, current_exp


def get_available_moves(
    pokemon: dict[str, Any],
    species: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Get all available moves for a Pokémon based on its level and species.

    Returns list of move dictionaries that the Pokémon can learn.
    """
    level = pokemon.get("level", 1)
    level_up_moves = species.get("level_up_moves", [])

    available_moves = []

    for move_entry in level_up_moves:
        learn_level = move_entry.get("level", 1)
        if level >= learn_level:
            move_id = move_entry.get("move_id")
            move = get_move(move_id)
            if move:
                available_moves.append(move)

    return available_moves


__all__ = [
    "calculate_damage",
    "apply_damage",
    "calculate_type_effectiveness",
    "check_critical_hit",
    "calculate_stat_modifier",
    "get_speed_priority",
    "is_stab",
    "simulate_turn",
    "calculate_experience_gain",
    "calculate_level_up",
    "get_available_moves",
]
