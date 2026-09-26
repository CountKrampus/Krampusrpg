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
        "sprite": str(npc.get("sprite", "") or ""),
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


def get_chapters(questline_id: str) -> list[dict[str, Any]]:
    """
    Chapter (sub-category) definitions for a quest line.

    Chapters come from the manifest's "chapters" list. Each chapter is
    a dict with at least an "id" and "name"; it may also carry a
    "description" and a "quests" list of quest ids belonging to it.
    Quests not listed in any chapter fall into an implicit "Other"
    chapter appended at the end, so quest lines without explicit
    chapters still render as a single group.
    """

    manifest = get_questline(questline_id)
    if manifest is None:
        return []

    raw = manifest.get("chapters")
    chapters: list[dict[str, Any]] = []

    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict) and entry.get("id"):
                chapters.append(dict(entry))

    if not chapters:
        return [
            {
                "id": "all",
                "name": "All Quests",
                "description": "",
                "quests": [
                    str(q.get("id", "")) for q in get_quests(questline_id)
                ],
            }
        ]

    return chapters


def chapter_for_quest(quest: dict[str, Any]) -> str | None:
    """The chapter id a quest belongs to (explicit "chapter" field)."""

    chapter = quest.get("chapter")
    if chapter is None:
        return None

    return str(chapter).strip().lower() or None


def group_quests_by_chapter(
    questline_id: str,
    quests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Group decorated quests into their chapters, in manifest order.

    Returns a list of {chapter, quests} dicts. Quests whose "chapter"
    field does not match a manifest chapter are grouped under the
    chapter that lists them in its "quests" array, then under a final
    catch-all group. Quest lines with no chapters at all yield a
    single "All Quests" group.
    """

    chapters = get_chapters(questline_id)

    if len(chapters) == 1 and chapters[0].get("id") == "all":
        return [
            {
                "chapter": chapters[0],
                "quests": list(quests),
            }
        ]

    # Map quest id -> chapter id via the manifest's chapter listings.
    listed: dict[str, str] = {}
    for chapter in chapters:
        for quest_id in chapter.get("quests") or []:
            listed[str(quest_id).strip().lower()] = str(chapter["id"]).strip().lower()

    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []

    def _push(chapter_id: str, quest: dict[str, Any]) -> None:
        if chapter_id not in groups:
            groups[chapter_id] = []
            order.append(chapter_id)
        groups[chapter_id].append(quest)

    for quest in quests:
        quest_id = str(quest.get("id", "")).strip().lower()

        chapter_id = chapter_for_quest(quest) or listed.get(quest_id)

        if chapter_id is None:
            # Fall back to the catch-all group, created on demand.
            chapter_id = "_ungrouped"

        _push(chapter_id, quest)

    result: list[dict[str, Any]] = []

    for chapter in chapters:
        chapter_id = str(chapter["id"]).strip().lower()
        if chapter_id in groups:
            result.append(
                {
                    "chapter": chapter,
                    "quests": groups[chapter_id],
                }
            )

    if "_ungrouped" in groups:
        result.append(
            {
                "chapter": {
                    "id": "_ungrouped",
                    "name": "Other Quests",
                    "description": "",
                },
                "quests": groups["_ungrouped"],
            }
        )

    return result


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


# ============================================================
# SECTIONS (QUEST LINE GROUPING) + QUEST LINE CHAIN LOCKS
# ============================================================

# Manifests may carry a "section" field; quest lines without one fall
# into the default section.
DEFAULT_SECTION = "standalone"

# Section id -> display label on the Story Adventure page.
SECTION_LABELS = {
    "team_krampus": "Team Krampus",
    "standalone": "Side Stories",
}

# Display order of sections (anything unlisted sorts last).
SECTION_ORDER = {
    "team_krampus": 1,
    "standalone": 2,
}


def get_player_completed_quest_ids(player_id: int | None) -> set[str]:
    """All quest ids (any quest line) the player has completed."""

    if player_id is None:
        return set()

    from .database import get_connection

    with get_connection() as db:
        rows = db.execute(
            """
            SELECT quest_id FROM player_quests
            WHERE player_id = ? AND status = 'completed'
            """,
            (player_id,),
        ).fetchall()

    return {str(row["quest_id"]) for row in rows}


def group_questlines_by_section(
    manifests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Group quest line manifests into sections for the Story Adventure
    hub. Returns a list of {id, label, order, questlines} dicts, where
    each quest line keeps every key added by the caller (decorated
    quests, totals, ...) and is sorted by its manifest "order" field.
    """

    sections: dict[str, list[dict[str, Any]]] = {}

    for manifest in manifests:
        section_id = (
            str(manifest.get("section") or DEFAULT_SECTION).strip().lower()
            or DEFAULT_SECTION
        )
        sections.setdefault(section_id, []).append(manifest)

    grouped: list[dict[str, Any]] = []

    for section_id, lines in sections.items():
        lines.sort(
            key=lambda m: (
                int(m.get("order", 0) or 0),
                str(m.get("id", "")),
            )
        )
        grouped.append(
            {
                "id": section_id,
                "label": SECTION_LABELS.get(
                    section_id, section_id.replace("_", " ").title()
                ),
                "order": SECTION_ORDER.get(section_id, 90),
                "questlines": lines,
            }
        )

    grouped.sort(key=lambda s: (s["order"], s["id"]))

    return grouped


def apply_questline_chain_locks(
    sections: list[dict[str, Any]],
    completed: set[str],
) -> None:
    """
    Walk quest lines across all sections in display order and lock
    every quest line whose predecessor still has unfinished quests.

    Mutates each manifest in place:

    - line_unlocked / line_locked: chain state.
    - line_completed: every quest in the line is finished.
    - line_locked_previous_title / line_locked_remaining: what the
      player still needs to finish before this line opens.
    """

    previous: dict[str, Any] | None = None

    for section in sections:
        for manifest in section["questlines"]:
            questline_id = str(manifest.get("id", ""))
            quests = get_quests(questline_id)

            total = len(quests)
            done = sum(
                1
                for q in quests
                if str(q.get("id", "")) in completed
            )

            manifest["line_total"] = total
            manifest["line_done"] = done
            manifest["line_completed"] = total > 0 and done == total

            unlocked = previous is None or bool(
                previous.get("line_completed")
            )

            manifest["line_unlocked"] = unlocked
            manifest["line_locked"] = not unlocked

            if not unlocked:
                previous_title = str(
                    previous.get("title") or previous.get("id", "")
                )
                manifest["line_locked_previous"] = str(
                    previous.get("id", "")
                )
                manifest["line_locked_previous_title"] = previous_title
                manifest["line_locked_remaining"] = int(
                    previous.get("line_total", 0)
                ) - int(previous.get("line_done", 0))
                manifest["line_locked_reason"] = (
                    f"Finish {previous_title} to unlock this quest line."
                )
            else:
                manifest["line_locked_previous"] = None
                manifest["line_locked_previous_title"] = None
                manifest["line_locked_remaining"] = 0
                manifest["line_locked_reason"] = None

            previous = manifest


def is_questline_locked(
    questline_id: str,
    completed: set[str],
) -> tuple[bool, str | None]:
    """
    Whether a quest line is chain-locked right now, and the reason
    string to show the player when it is.
    """

    wanted = str(questline_id).strip().lower()

    sections = group_questlines_by_section(list_questlines())
    apply_questline_chain_locks(sections, completed)

    for section in sections:
        for manifest in section["questlines"]:
            if str(manifest.get("id", "")).strip().lower() == wanted:
                return bool(manifest.get("line_locked")), manifest.get(
                    "line_locked_reason"
                )

    return False, None


__all__ = [
    "list_questlines",
    "get_questline",
    "get_quests",
    "get_quest",
    "get_encounters",
    "get_npc",
    "get_rewards",
    "get_chapters",
    "chapter_for_quest",
    "group_quests_by_chapter",
    "resolve_battle",
    "quest_battles",
    "questline_totals",
    "get_player_completed_quest_ids",
    "group_questlines_by_section",
    "apply_questline_chain_locks",
    "is_questline_locked",
]
