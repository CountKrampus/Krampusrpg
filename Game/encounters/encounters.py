from __future__ import annotations

import random

from Server.database import get_connection
from Server.services import load_data


def get_area(area_id: str):
    for area in load_data("areas.json"):
        if area.get("id") == area_id:
            return area

    return None


def roll_encounter(area_id: str):
    area = get_area(area_id)

    if area is None:
        return None

    encounters = area.get("encounters", [])

    if not encounters:
        return None

    total = sum(
        max(0, int(item.get("weight", 0)))
        for item in encounters
    )

    if total <= 0:
        return None

    roll = random.randint(1, total)

    current = 0

    for encounter in encounters:
        current += max(
            0,
            int(encounter.get("weight", 0)),
        )

        if roll <= current:
            return encounter

    return encounters[-1]
