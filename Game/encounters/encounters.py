from __future__ import annotations

import random
from typing import Any

from Server.database import get_connection
from Server.services import get_area, get_species


def roll_encounter(
    area_id: str,
    time_of_day: str = "day",
    weather: str = "clear",
    player_level: int | None = None,
) -> dict[str, Any] | None:
    """
    Roll for a random encounter in an area with advanced conditions.

    Args:
        area_id: The area identifier
        time_of_day: Time of day (day, night, dawn, dusk)
        weather: Current weather (clear, rain, snow, etc.)
        player_level: Player's average level for level scaling

    Returns:
        Encounter data dict or None if no encounter
    """
    area = get_area(area_id)

    if area is None:
        return None

    encounters = area.get("encounters", [])

    if not encounters:
        return None

    # Filter encounters based on conditions
    valid_encounters = []

    for encounter in encounters:
        # Check time conditions
        required_time = encounter.get("time")
        if required_time and required_time != time_of_day:
            continue

        # Check weather conditions
        required_weather = encounter.get("weather")
        if required_weather and required_weather != weather:
            continue

        # Check level requirements
        min_level = encounter.get("min_level", 1)
        max_level = encounter.get("max_level", 100)

        if player_level:
            # Scale encounters to player level
            if player_level < min_level - 5 or player_level > max_level + 10:
                continue

        valid_encounters.append(encounter)

    if not valid_encounters:
        return None

    # Calculate weighted random selection
    total_weight = sum(
        max(0, int(item.get("weight", 1)))
        for item in valid_encounters
    )

    if total_weight <= 0:
        return None

    roll = random.randint(1, total_weight)

    current = 0

    for encounter in valid_encounters:
        current += max(0, int(encounter.get("weight", 1)))

        if roll <= current:
            return _enrich_encounter(encounter, player_level)

    return _enrich_encounter(valid_encounters[-1], player_level)


def _enrich_encounter(
    encounter: dict[str, Any],
    player_level: int | None = None,
) -> dict[str, Any]:
    """
    Enrich encounter data with species information and level generation.
    """
    species_id = encounter.get("species_id")

    if not species_id:
        return encounter

    species = get_species(species_id)

    if species:
        encounter["species"] = species
        encounter["species_name"] = species.get("name", species_id)

    # Generate level for the encounter
    min_level = encounter.get("min_level", 1)
    max_level = encounter.get("max_level", 100)

    if player_level:
        # Scale to player level +/- 5 levels
        scaled_min = max(min_level, player_level - 5)
        scaled_max = min(max_level, player_level + 5)
        encounter_level = random.randint(scaled_min, scaled_max)
    else:
        encounter_level = random.randint(min_level, max_level)

    encounter["level"] = encounter_level

    # Generate other properties
    encounter["shiny_chance"] = encounter.get("shiny_chance", 1/4096)
    encounter["is_shiny"] = random.random() < encounter["shiny_chance"]

    return encounter


def get_encounter_rate(
    area_id: str,
    terrain: str = "grass",
) -> float:
    """
    Get the encounter rate for an area based on terrain.

    Returns a probability (0.0 to 1.0) of encountering Pokémon per step.
    """
    area = get_area(area_id)

    if area is None:
        return 0.0

    terrain_rates = area.get("encounter_rates", {})

    # Default rates
    default_rates = {
        "grass": 0.15,
        "water": 0.10,
        "cave": 0.12,
        "building": 0.05,
        "urban": 0.08,
    }

    return terrain_rates.get(terrain, default_rates.get(terrain, 0.1))


def get_area_encounters(
    area_id: str,
    time_of_day: str = "day",
    weather: str = "clear",
) -> list[dict[str, Any]]:
    """
    Get all possible encounters for an area with current conditions.

    Useful for displaying encounter tables or Pokédex data.
    """
    area = get_area(area_id)

    if area is None:
        return []

    encounters = area.get("encounters", [])

    # Filter by conditions
    valid_encounters = []

    for encounter in encounters:
        required_time = encounter.get("time")
        if required_time and required_time != time_of_day:
            continue

        required_weather = encounter.get("weather")
        if required_weather and required_weather != weather:
            continue

        valid_encounters.append(_enrich_encounter(encounter))

    return valid_encounters


def can_encounter(
    area_id: str,
    terrain: str = "grass",
) -> bool:
    """
    Quick check if an encounter can happen in current conditions.

    Returns True if an encounter should occur.
    """
    encounter_rate = get_encounter_rate(area_id, terrain)
    return random.random() < encounter_rate


def get_encounter_by_species(
    area_id: str,
    species_id: str,
) -> dict[str, Any] | None:
    """
    Get specific encounter data for a species in an area.

    Useful for forced encounters or special events.
    """
    area = get_area(area_id)

    if area is None:
        return None

    encounters = area.get("encounters", [])

    for encounter in encounters:
        if encounter.get("species_id") == species_id:
            return _enrich_encounter(encounter)

    return None


__all__ = [
    "roll_encounter",
    "get_encounter_rate",
    "get_area_encounters",
    "can_encounter",
    "get_encounter_by_species",
]
