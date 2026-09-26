"""
Krampus RPG Gyms

Gym challenges built on the shared battle engine. Each gym has a
leader with a fixed team; beating a leader awards a badge (stored in
the existing badges table), money, and progression toward gyms that
require earlier badges.

Gym battles run through Server/battle_store.py (server-authoritative
state, party HP synced back on finish) — the same flow as the Battle
Arena, just with a fixed opponent team and a badge on the line.
"""

from __future__ import annotations

import json
from typing import Any

from .database import get_connection
from .services import load_data

GYMS_FILE = "gyms.json"


# ============================================================
# LOADING
# ============================================================

def _raw() -> dict[str, Any]:
    data = load_data(GYMS_FILE)
    return data if isinstance(data, dict) else {}


def get_gyms() -> list[dict[str, Any]]:
    """All gyms in definition order."""

    gyms = _raw().get("gyms")
    return [g for g in gyms if isinstance(g, dict)] if isinstance(gyms, list) else []


def get_gym(gym_id: str) -> dict[str, Any] | None:
    wanted = str(gym_id).strip().lower()

    for gym in get_gyms():
        if str(gym.get("id", "")).lower() == wanted:
            return gym

    return None


def get_badge_definitions() -> dict[str, dict[str, Any]]:
    return _raw().get("badges") or {}


# ============================================================
# PLAYER BADGE STATE
# ============================================================

def get_player_badges(player_id: int) -> list[str]:
    """Badge ids the player has earned (from the existing badges table)."""

    with get_connection() as db:
        rows = db.execute(
            "SELECT badge_id FROM badges WHERE player_id = ?",
            (player_id,),
        ).fetchall()

    return [str(row["badge_id"]) for row in rows]


def has_badge(player_id: int, badge_id: str) -> bool:
    return badge_id in get_player_badges(player_id)


def gym_available(gym: dict[str, Any], player_id: int) -> tuple[bool, str | None]:
    """
    (available, lock_reason): a gym is challengeable when the player
    holds at least required_badges gym badges.
    """

    required = int(gym.get("required_badges") or 0)

    if required <= 0:
        return True, None

    badge_defs = get_badge_definitions()
    gym_badges_held = sum(
        1
        for badge_id in get_player_badges(player_id)
        if badge_id in badge_defs
    )

    if gym_badges_held >= required:
        return True, None

    return False, (
        f"Requires {required} gym badges "
        f"(you have {gym_badges_held})."
    )


# ============================================================
# CHALLENGE + AWARD
# ============================================================

def start_gym_battle(player_id: int, gym_id: str) -> dict[str, Any]:
    """
    Start a battle against a gym leader's team. Raises ValueError for
    unknown/locked gyms or missing prerequisites.
    """

    from . import battle_store

    gym = get_gym(gym_id)

    if gym is None:
        raise ValueError("Unknown gym.")

    available, reason = gym_available(gym, player_id)

    if not available:
        raise ValueError(reason or "This gym is locked.")

    battle = battle_store.start_trainer_battle(
        player_id,
        list(gym.get("team") or []),
    )

    # Tag the battle context as a gym challenge so awarding only
    # happens for gym battles won.
    _tag_battle_context(
        battle["battle_id"],
        {
            "gym_id": gym["id"],
            "badge": gym.get("badge"),
        },
    )

    return battle


def _tag_battle_context(battle_id: int, extra: dict[str, Any]) -> None:
    """Merge extra keys into the stored battle's context JSON."""

    with get_connection() as db:
        row = db.execute(
            "SELECT context FROM battles WHERE id = ?",
            (battle_id,),
        ).fetchone()

        if row is None:
            return

        try:
            context = json.loads(row["context"] or "{}")
        except json.JSONDecodeError:
            context = {}

        context.update(extra)

        db.execute(
            "UPDATE battles SET context = ? WHERE id = ?",
            (json.dumps(context), battle_id),
        )
        db.commit()


def read_battle_context(battle_id: int) -> dict[str, Any]:
    with get_connection() as db:
        row = db.execute(
            "SELECT context FROM battles WHERE id = ?",
            (battle_id,),
        ).fetchone()

    if row is None:
        return {}

    try:
        return json.loads(row["context"] or "{}")
    except json.JSONDecodeError:
        return {}


def award_gym_victory(player_id: int, battle_id: int) -> dict[str, Any] | None:
    """
    Check a finished gym battle and award badge + money exactly once.
    Returns an award summary, or None when nothing was awarded
    (not a gym battle, not won, or already awarded).
    """

    from .database import get_connection as _gc

    with _gc() as db:
        row = db.execute(
            """
            SELECT status, winner, context
            FROM battles
            WHERE id = ? AND player_id = ?
            """,
            (battle_id, player_id),
        ).fetchone()

    if row is None or row["status"] != "finished" or row["winner"] != "player":
        return None

    context = read_battle_context(battle_id)
    gym_id = context.get("gym_id")

    if not gym_id:
        return None

    gym = get_gym(str(gym_id))

    if gym is None:
        return None

    badge_id = str(gym.get("badge") or "")
    awarded_badge = False
    money = int((gym.get("rewards") or {}).get("money") or 0)

    with _gc() as db:
        # Badge (idempotent via the badges table's uniqueness per player)
        if badge_id:
            existing = db.execute(
                """
                SELECT 1 FROM badges
                WHERE player_id = ? AND badge_id = ?
                """,
                (player_id, badge_id),
            ).fetchone()

            if existing is None:
                db.execute(
                    """
                    INSERT INTO badges (player_id, badge_id)
                    VALUES (?, ?)
                    """,
                    (player_id, badge_id),
                )
                awarded_badge = True

        if money > 0:
            db.execute(
                """
                UPDATE player_progress
                SET money = money + ?
                WHERE player_id = ?
                """,
                (money, player_id),
            )

        db.commit()

    return {
        "gym": gym["name"],
        "leader": gym.get("leader"),
        "badge": badge_id if awarded_badge else None,
        "badge_name": (
            get_badge_definitions().get(badge_id, {}).get("name", badge_id)
            if badge_id
            else None
        ),
        "money": money,
        "leader_defeat": gym.get("leader_defeat"),
    }
