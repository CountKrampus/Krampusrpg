"""
Krampus RPG NPC Editor Storage
==============================

Admin-facing edits to a quest line's NPC definitions in
Data/quests/<questline>/encounters.json:

- set_npc_sprite():  character sprite path shown on battle cards and
                     the live battle screen.
- set_npc_team():    replace an NPC's whole team (species, level,
                     variant per member).

Writes are atomic (temp file + os.replace) and preserve every other
key in the document. Validation mirrors the story battle engine so an
edit can't create a battle that can't run (unknown species/variant,
empty team, bad levels).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .config import DATA_DIR
from .services import clear_data_cache, get_species

QUESTS_DIR = DATA_DIR / "quests"

# Team members per NPC (matches the battle engine's expectations and
# the classic six-slot trainer team).
TEAM_MIN = 1
TEAM_MAX = 6

LEVEL_MIN = 1
# No upper cap: matches the uncapped-levels policy for player Pokémon.


def _encounters_path(questline_id: str) -> Path:
    return QUESTS_DIR / str(questline_id) / "encounters.json"


def _load(questline_id: str) -> dict[str, Any]:
    path = _encounters_path(questline_id)

    if not path.exists():
        raise ValueError(f"Quest line '{questline_id}' has no encounters file.")

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"encounters.json is unreadable: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("npcs"), dict):
        raise ValueError("encounters.json has no 'npcs' object.")

    return data


def _save(questline_id: str, data: dict[str, Any]) -> None:
    path = _encounters_path(questline_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        dir=str(path.parent),
        suffix=".tmp",
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")

        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

        raise

    clear_data_cache()


def _find_npc(data: dict[str, Any], npc_id: str) -> dict[str, Any]:
    wanted = str(npc_id).strip().lower()

    for key, npc in data["npcs"].items():
        if str(key).lower() == wanted or str(
            npc.get("id", "")
        ).lower() == wanted:
            return npc

    raise ValueError(f"NPC '{npc_id}' not found.")


def _clean_sprite(value: str) -> str:
    """
    Normalize the sprite field. Stored as a bare filename/relative
    path; blank clears the sprite. Path traversal is rejected.
    """
    sprite = str(value or "").strip().replace("\\", "/")

    if not sprite:
        return ""

    sprite = sprite.lstrip("/")

    if (
        ".." in sprite.split("/")
        or ":" in sprite
        or sprite.startswith("/")
    ):
        raise ValueError("Sprite must be a simple path inside /static.")

    return sprite


def _clean_team(team: Any) -> list[dict[str, Any]]:
    """
    Validate a submitted team: list of {species_id, level, variant}.
    Species must resolve, variant must be 'normal' or a known variant
    id, and the team must be TEAM_MIN..TEAM_MAX members.
    """
    from .services import get_variant

    if not isinstance(team, list):
        raise ValueError("Team must be a list.")

    if not TEAM_MIN <= len(team) <= TEAM_MAX:
        raise ValueError(
            f"Team needs {TEAM_MIN} to {TEAM_MAX} Pokémon "
            f"(got {len(team)})."
        )

    cleaned: list[dict[str, Any]] = []

    for index, entry in enumerate(team, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Team member #{index} is malformed.")

        species_id = str(entry.get("species_id", "")).strip().lower()

        if not species_id:
            raise ValueError(f"Team member #{index} is missing a species.")

        if get_species(species_id) is None:
            raise ValueError(
                f"Team member #{index}: unknown species '{species_id}'."
            )

        try:
            level = int(entry.get("level", 5))
        except (TypeError, ValueError):
            raise ValueError(
                f"Team member #{index}: level must be a number."
            ) from None

        if level < LEVEL_MIN:
            raise ValueError(
                f"Team member #{index}: level must be at least {LEVEL_MIN}."
            )

        variant = str(entry.get("variant", "") or "normal").strip().lower()

        if variant and variant != "normal" and get_variant(variant) is None:
            raise ValueError(
                f"Team member #{index}: unknown variant '{variant}'."
            )

        cleaned.append(
            {
                "species": species_id,
                "level": level,
                "variant": variant or "normal",
            }
        )

    return cleaned


def get_npc_editor_data(questline_id: str, npc_id: str) -> dict[str, Any] | None:
    """One NPC's full definition for the edit form."""

    try:
        data = _load(questline_id)
    except ValueError:
        return None

    try:
        npc = _find_npc(data, npc_id)
    except ValueError:
        return None

    return dict(npc)


def list_npcs(questline_id: str) -> list[dict[str, Any]]:
    """All NPCs in a quest line for the editor overview."""

    try:
        data = _load(questline_id)
    except ValueError:
        return []

    npcs: list[dict[str, Any]] = []

    for key, npc in data["npcs"].items():
        if not isinstance(npc, dict):
            continue

        npcs.append(
            {
                "key": key,
                "id": npc.get("id", key),
                "name": npc.get("name", key.replace("_", " ").title()),
                "rank": npc.get("rank", ""),
                "sprite": npc.get("sprite", ""),
                "team": npc.get("team", []),
            }
        )

    return npcs


def set_npc_sprite(questline_id: str, npc_id: str, sprite: str) -> dict[str, Any]:
    """
    Set (or clear, with an empty value) an NPC's character sprite.
    Returns the updated NPC.
    """

    data = _load(questline_id)
    npc = _find_npc(data, npc_id)

    sprite = _clean_sprite(sprite)

    if sprite:
        npc["sprite"] = sprite
    else:
        npc.pop("sprite", None)

    _save(questline_id, data)

    return npc


def set_npc_team(
    questline_id: str,
    npc_id: str,
    team: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Replace an NPC's whole team. Returns the updated NPC.
    """

    data = _load(questline_id)
    npc = _find_npc(data, npc_id)

    npc["team"] = _clean_team(team)

    _save(questline_id, data)

    return npc
