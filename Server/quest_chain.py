"""
Krampus RPG Quest Chain Loader

Data-driven access to quest lines stored under Data/quests/. Each
quest line lives in its own directory:

    Data/quests/team_krampus/
        manifest.json     — quest line metadata (title, premise, NPCs)
        encounters.json   — NPC definitions (organization, rank, teams)
        rewards.json      — per-quest rewards and quest items
        quests/           — one JSON file per quest, in play order

Quest files reference NPCs from encounters.json and rewards from
rewards.json by id, so the quest engine can resolve teams, dialogue,
prerequisites, and rewards without hardcoding anything.

Nothing in here is player-stateful: it only reads the data files.
Progress tracking stays in the existing player_quests table.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import DATA_DIR
from .services import clear_data_cache

QUESTS_DIR = DATA_DIR / "quests"


# ============================================================
# LOW-LEVEL LOADING
# ============================================================

def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return None


def list_questlines() -> list[dict[str, Any]]:
    """All quest line manifests found under Data/quests/."""
    manifests: list[dict[str, Any]] = []

    if not QUESTS_DIR.exists():
        return manifests

    for entry in sorted(QUESTS_DIR.iterdir()):
        if not entry.is_dir():
            continue

        manifest = _read_json(entry / "manifest.json")
        if isinstance(manifest, dict) and manifest.get("id"):
            manifests.append(manifest)

    return manifests


def get_questline(questline_id: str) -> dict[str, Any] | None:
    """One quest line manifest by id."""
    wanted = str(questline_id).strip().lower()

    for manifest in list_questlines():
        if str(manifest.get("id", "")).lower() == wanted:
            return manifest

    return None


def get_quests(questline_id: str) -> list[dict[str, Any]]:
    """
    All quests in a quest line, ordered by their "number" field
    (falls back to filename order).
    """

    directory = QUESTS_DIR / str(questline_id) / "quests"

    if not directory.exists():
        return []

    quests: list[dict[str, Any]] = []

    for path in sorted(directory.glob("*.json")):
        quest = _read_json(path)
        if isinstance(quest, dict) and quest.get("id"):
            quests.append(quest)

    quests.sort(key=lambda q: (q.get("number", 0), q.get("id", "")))

    return quests


def get_quest(questline_id: str, quest_id: str) -> dict[str, Any] | None:
    """One quest by id (e.g. tk_007) or slug within a quest line."""

    wanted = str(quest_id).strip().lower()

    for quest in get_quests(questline_id):
        if str(quest.get("id", "")).lower() == wanted:
            return quest
        if str(quest.get("slug", "")).lower() == wanted:
            return quest

    return None


def get_encounters(questline_id: str) -> dict[str, Any]:
    """The NPC encounter definitions for a quest line."""

    raw = _read_json(QUESTS_DIR / str(questline_id) / "encounters.json")

    if not isinstance(raw, dict):
        return {"npcs": {}}

    npcs = raw.get("npcs")
    return raw if isinstance(npcs, dict) else {"npcs": {}}


def get_npc(questline_id: str, npc_id: str) -> dict[str, Any] | None:
    """One NPC definition by id."""

    npcs = get_encounters(questline_id).get("npcs", {})
    wanted = str(npc_id).strip().lower()

    for key, npc in npcs.items():
        if str(key).lower() == wanted or str(
            npc.get("id", "")
        ).lower() == wanted:
            return npc

    return None


def get_rewards(questline_id: str) -> dict[str, Any]:
    """The rewards document for a quest line."""

    raw = _read_json(QUESTS_DIR / str(questline_id) / "rewards.json")
    return raw if isinstance(raw, dict) else {}


# ============================================================
# RESOLUTION HELPERS
# ============================================================

def resolve_battle(questline_id: str, battle: Any) -> dict[str, Any] | None:
    """
    Resolve a quest's battle reference into a full NPC battle dict
    (npc info + concrete team with species/levels/variant).
    """

    if not isinstance(battle, dict):
        return None

    npc = get_npc(questline_id, str(battle.get("npc", "")))

    if npc is None:
        return None

    return {
        "npc": npc,
        "escapes": bool(battle.get("escapes", npc.get("escapes", False))),
        "boss_mechanic": npc.get("boss_mechanic"),
        "team_size": len(npc.get("team", [])),
    }


def quest_battles(questline_id: str, quest: dict[str, Any]) -> list[dict[str, Any]]:
    """
    All NPC battles for a quest, resolved. Handles both a single
    "battle" and a multi-battle "battles" list.
    """

    resolved: list[dict[str, Any]] = []

    single = resolve_battle(questline_id, quest.get("battle"))
    if single is not None:
        resolved.append(single)

    for battle in quest.get("battles") or []:
        resolved_battle = resolve_battle(questline_id, battle)
        if resolved_battle is not None:
            resolved.append(resolved_battle)

    return resolved


def questline_totals(questline_id: str) -> dict[str, int]:
    """Aggregate stats for a quest line (quests, battles, max team size)."""

    quests = get_quests(questline_id)

    battle_count = 0
    max_team = 0

    for quest in quests:
        for battle in quest_battles(questline_id, quest):
            battle_count += 1
            max_team = max(max_team, battle["team_size"])

    return {
        "quests": len(quests),
        "battles": battle_count,
        "max_team_size": max_team,
    }
