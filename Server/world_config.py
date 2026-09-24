"""
Krampus RPG World Configuration

Admin-facing read/write access to the world data files:

- Data/areas.json: areas and their wild encounter tables
  (species, level range, weight).
- Global catch tuning values (shiny odds, catch clamps) stored in the
  admin "settings" table and consumed by Server/catching.py.

Writes are atomic (temp file + os.replace) and always re-dump the whole
areas list, keeping any extra per-area fields the editor doesn't know
about. Every mutation clears the services data cache so the running
app immediately serves the new tables without a restart.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .config import DATA_DIR
from .services import clear_data_cache

AREAS_FILE = DATA_DIR / "areas.json"

# Region id -> display label. The canonical region list for the
# Hollyhollow/Frostpine world; used by the Story Adventure map strip
# and the admin world editor's region picker.
REGION_LABELS = {
    "hollyhollow": "Hollyhollow",
    "frostpine": "Frostpine",
}

# Settings-table keys for catch tuning (see Server/catching.py).
SETTING_SHINY_ODDS = "world_shiny_odds"
SETTING_MIN_CATCH = "world_min_catch_chance"
SETTING_MAX_CATCH = "world_max_catch_chance"
SETTING_DEFAULT_RATE = "world_default_catch_rate"

# Validation bounds for the editable catch settings.
SHINY_ODDS_MIN = 2
SHINY_ODDS_MAX = 100_000
CATCH_CHANCE_MIN = 1.0
CATCH_CHANCE_MAX = 100.0
DEFAULT_RATE_MIN = 1.0
DEFAULT_RATE_MAX = 255.0

_AREA_TYPES = (
    "town",
    "route",
    "cave",
    "forest",
    "water",
    "mountain",
)


# ============================================================
# AREAS
# ============================================================

def load_areas_document() -> dict[str, Any]:
    """
    Load the raw areas.json document.

    areas.json is normally a bare list; a {"areas": [...]} wrapper is
    also accepted and preserved on write.
    """

    if not AREAS_FILE.exists():
        return {"areas": []}

    try:
        with AREAS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {"areas": []}

    if isinstance(data, list):
        return {"areas": data}

    if isinstance(data, dict) and isinstance(data.get("areas"), list):
        return data

    return {"areas": []}


def save_areas_document(document: dict[str, Any]) -> None:
    """
    Atomically write the areas document back to Data/areas.json and
    clear the services data cache so changes are live immediately.
    """

    AREAS_FILE.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        dir=str(AREAS_FILE.parent),
        suffix=".tmp",
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(document, file, indent=2, ensure_ascii=False)
            file.write("\n")

        os.replace(temp_path, AREAS_FILE)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

        raise

    clear_data_cache()


def get_area_by_id(area_id: str) -> dict[str, Any] | None:
    """Find an area in the raw document by exact id (case-insensitive)."""

    wanted = str(area_id).strip().lower()

    for area in load_areas_document()["areas"]:
        if str(area.get("id", "")).lower() == wanted:
            return area

    return None


def slugify_area_id(name: str) -> str:
    """Turn an area name into a URL-safe snake_case id."""

    slug = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(name).strip().lower(),
    ).strip("_")

    return slug or "area"


def create_area(
    name: str,
    area_type: str = "route",
    description: str = "",
    region: str = "hollyhollow",
) -> dict[str, Any]:
    """
    Create a new (empty) area. Raises ValueError on bad input or a
    duplicate id.
    """

    name = str(name).strip()

    if not name:
        raise ValueError("Area name is required.")

    document = load_areas_document()
    areas = document["areas"]

    area_id = slugify_area_id(name)

    if get_area_by_id(area_id) is not None:
        raise ValueError(f"An area with id '{area_id}' already exists.")

    if area_type not in _AREA_TYPES:
        area_type = "route"

    area = {
        "id": area_id,
        "name": name,
        "region": str(region).strip() or "hollyhollow",
        "type": area_type,
        "description": str(description).strip(),
        "encounters": [],
    }

    areas.append(area)
    save_areas_document(document)

    return area


def update_area(
    area_id: str,
    name: str | None = None,
    area_type: str | None = None,
    description: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """
    Update an area's display fields (id is immutable — encounters
    reference it). Returns the updated area.
    """

    area = get_area_by_id(area_id)

    if area is None:
        raise ValueError("Area not found.")

    document = load_areas_document()

    if name is not None:
        name = str(name).strip()

        if not name:
            raise ValueError("Area name cannot be empty.")

        area["name"] = name

    if area_type is not None and area_type in _AREA_TYPES:
        area["type"] = area_type

    if description is not None:
        area["description"] = str(description).strip()

    if region is not None:
        region = str(region).strip()

        if region:
            area["region"] = region

    save_areas_document(document)

    return area


def delete_area(area_id: str) -> None:
    """Remove an area and all of its encounters."""

    document = load_areas_document()
    wanted = str(area_id).strip().lower()

    remaining = [
        area
        for area in document["areas"]
        if str(area.get("id", "")).lower() != wanted
    ]

    if len(remaining) == len(document["areas"]):
        raise ValueError("Area not found.")

    document["areas"] = remaining
    save_areas_document(document)


# ============================================================
# ENCOUNTERS
# ============================================================

def _parse_level(value: Any, default: int) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return default

    return max(1, min(100, level))


def _parse_weight(value: Any) -> float:
    try:
        weight = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(1000.0, weight))


def set_area_encounters(
    area_id: str,
    encounters: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Replace an area's full encounter table with a validated list.

    Each entry: {"species_id", "min_level", "max_level", "weight"}.
    Unknown species ids are rejected so a typo can't silently create
    an encounter that can never generate. Raises ValueError on any
    invalid entry (nothing is written).
    """

    area = get_area_by_id(area_id)

    if area is None:
        raise ValueError("Area not found.")

    # Imported late to avoid a circular import at module load:
    # services imports nothing from this module, but get_species is
    # heavy and the catalog check belongs to the validation step.
    from .services import get_species

    cleaned: list[dict[str, Any]] = []

    for index, entry in enumerate(encounters, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Encounter #{index} is malformed.")

        species_id = str(entry.get("species_id", "")).strip().lower()

        if not species_id:
            raise ValueError(
                f"Encounter #{index} is missing a species."
            )

        if get_species(species_id) is None:
            raise ValueError(
                f"Encounter #{index}: unknown species "
                f"'{species_id}'."
            )

        min_level = _parse_level(entry.get("min_level"), 1)
        max_level = _parse_level(entry.get("max_level"), min_level)
        max_level = max(min_level, max_level)

        weight = _parse_weight(entry.get("weight"))

        if weight <= 0:
            raise ValueError(
                f"Encounter #{index} ({species_id}) needs a "
                f"weight greater than 0."
            )

        cleaned.append(
            {
                "species_id": species_id,
                "min_level": min_level,
                "max_level": max_level,
                "weight": weight,
            }
        )

    document = load_areas_document()

    # Look the area up inside this same document instance — a second
    # load_areas_document() (e.g. via get_area_by_id) returns a
    # different copy, and mutating that one would be silently lost.
    area = None

    for candidate in document["areas"]:
        if str(candidate.get("id", "")).lower() == str(area_id).strip().lower():
            area = candidate
            break

    if area is None:
        raise ValueError("Area not found.")

    area["encounters"] = cleaned

    save_areas_document(document)

    return area


def add_area_encounter(
    area_id: str,
    species_id: str,
    min_level: int = 1,
    max_level: int = 5,
    weight: float = 10.0,
) -> dict[str, Any]:
    """Append one validated encounter entry to an area."""

    area = get_area_by_id(area_id)

    if area is None:
        raise ValueError("Area not found.")

    return set_area_encounters(
        area_id,
        [
            *area.get("encounters", []),
            {
                "species_id": species_id,
                "min_level": min_level,
                "max_level": max_level,
                "weight": weight,
            },
        ],
    )


def delete_area_encounter(area_id: str, index: int) -> dict[str, Any]:
    """Remove the encounter at `index` (0-based) from an area."""

    area = get_area_by_id(area_id)

    if area is None:
        raise ValueError("Area not found.")

    encounters = list(area.get("encounters", []))

    if not 0 <= index < len(encounters):
        raise ValueError("Encounter not found.")

    del encounters[index]

    return set_area_encounters(area_id, encounters)


# ============================================================
# CATCH SETTINGS
# ============================================================

def _read_setting_float(
    value: Any,
    default: float,
    low: float,
    high: float,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default

    return max(low, min(high, parsed))


def get_catch_settings() -> dict[str, Any]:
    """
    The live catch tuning values, defaults from catching.py.

    Reads through the admin settings table when it exists (it always
    does once the admin dashboard has been opened).
    """

    from .catching import (
        DEFAULT_CATCH_RATE,
        MAX_CATCH_CHANCE,
        MIN_CATCH_CHANCE,
        SHINY_ODDS,
    )

    values: dict[str, Any] = {
        "shiny_odds": SHINY_ODDS,
        "min_catch_chance": MIN_CATCH_CHANCE,
        "max_catch_chance": MAX_CATCH_CHANCE,
        "default_catch_rate": DEFAULT_CATCH_RATE,
    }

    try:
        from .admin.services import get_setting

        values["shiny_odds"] = int(
            _read_setting_float(
                get_setting(SETTING_SHINY_ODDS, SHINY_ODDS),
                SHINY_ODDS,
                SHINY_ODDS_MIN,
                SHINY_ODDS_MAX,
            )
        )

        values["min_catch_chance"] = _read_setting_float(
            get_setting(SETTING_MIN_CATCH, MIN_CATCH_CHANCE),
            MIN_CATCH_CHANCE,
            CATCH_CHANCE_MIN,
            CATCH_CHANCE_MAX,
        )

        values["max_catch_chance"] = _read_setting_float(
            get_setting(SETTING_MAX_CATCH, MAX_CATCH_CHANCE),
            MAX_CATCH_CHANCE,
            CATCH_CHANCE_MIN,
            CATCH_CHANCE_MAX,
        )

        values["default_catch_rate"] = _read_setting_float(
            get_setting(SETTING_DEFAULT_RATE, DEFAULT_CATCH_RATE),
            DEFAULT_CATCH_RATE,
            DEFAULT_RATE_MIN,
            DEFAULT_RATE_MAX,
        )
    except ImportError:
        pass

    # Keep the clamps sane if someone saved min > max.
    if values["min_catch_chance"] > values["max_catch_chance"]:
        values["min_catch_chance"], values["max_catch_chance"] = (
            values["max_catch_chance"],
            values["min_catch_chance"],
        )

    return values


def save_catch_settings(
    shiny_odds: Any = None,
    min_catch_chance: Any = None,
    max_catch_chance: Any = None,
    default_catch_rate: Any = None,
) -> dict[str, Any]:
    """
    Persist catch tuning values into the admin settings table and
    return the effective (clamped) values.
    """

    from .admin.services import ensure_admin_tables, set_setting

    ensure_admin_tables()

    current = get_catch_settings()

    if shiny_odds is not None:
        set_setting(
            SETTING_SHINY_ODDS,
            str(
                int(
                    _read_setting_float(
                        shiny_odds,
                        current["shiny_odds"],
                        SHINY_ODDS_MIN,
                        SHINY_ODDS_MAX,
                    )
                )
            ),
        )

    if min_catch_chance is not None:
        set_setting(
            SETTING_MIN_CATCH,
            str(
                _read_setting_float(
                    min_catch_chance,
                    current["min_catch_chance"],
                    CATCH_CHANCE_MIN,
                    CATCH_CHANCE_MAX,
                )
            ),
        )

    if max_catch_chance is not None:
        set_setting(
            SETTING_MAX_CATCH,
            str(
                _read_setting_float(
                    max_catch_chance,
                    current["max_catch_chance"],
                    CATCH_CHANCE_MIN,
                    CATCH_CHANCE_MAX,
                )
            ),
        )

    if default_catch_rate is not None:
        set_setting(
            SETTING_DEFAULT_RATE,
            str(
                _read_setting_float(
                    default_catch_rate,
                    current["default_catch_rate"],
                    DEFAULT_RATE_MIN,
                    DEFAULT_RATE_MAX,
                )
            ),
        )

    return get_catch_settings()
