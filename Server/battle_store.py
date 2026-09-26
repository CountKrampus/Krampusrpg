"""
Battle persistence

Battles are stored server-side in the battles table as a JSON blob of
the battle state (see Server/battle.py). Every action re-validates
against the stored state, so the client can never inject results.

States:

    active    — the battle is running
    finished  — the battle ended (winner recorded)
    fled      — the player ran from a wild battle

A player has at most one active battle at a time; starting a new one
cancels any stale active battle.

After a finished battle the player's party HP is synced back from the
battle state, so battle damage is real and persists.
"""

from __future__ import annotations

import json
import random
from typing import Any

from .database import get_connection
from .battle import (
    BattleError,
    apply_action,
    make_fighter_from_species,
    public_view,
)

BATTLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS battles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    format TEXT NOT NULL DEFAULT 'trainer',
    status TEXT NOT NULL DEFAULT 'active',
    context TEXT,
    state TEXT NOT NULL,
    winner TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_battles_player
    ON battles (player_id, status);
"""


def ensure_battle_tables() -> None:
    with get_connection() as db:
        db.executescript(BATTLE_SCHEMA)
        db.commit()


# ============================================================
# START
# ============================================================

def start_trainer_battle(
    player_id: int,
    npc_team: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Start a trainer battle against an NPC team (from quest encounter
    data: [{"species": "...", "level": N, "variant": "..."}, ...]).

    The player's party is built from their real party Pokémon (max 3
    out of 6 keep NPC teams fair); party members with 0 HP are skipped.
    Raises BattleError when the player has no healthy Pokémon.
    """

    ensure_battle_tables()

    party_fighters = _party_fighters(player_id)

    if not party_fighters:
        raise BattleError(
            "You need a healthy Pokémon in your party to battle!"
        )

    opponent_fighters = [
        make_fighter_from_species(
            str(member["species"]),
            int(member["level"]),
            variant=str(member.get("variant") or "normal"),
        )
        for member in npc_team
    ]

    return _start(
        player_id,
        format_name="trainer",
        player_team=party_fighters,
        opponent_team=opponent_fighters,
        context={"npc_team_size": len(npc_team)},
    )


def start_wild_battle(
    player_id: int,
    species_id: str,
    level: int,
    *,
    variant: str = "normal",
) -> dict[str, Any]:
    """Start a wild battle against one Pokémon."""

    ensure_battle_tables()

    party_fighters = _party_fighters(player_id)

    if not party_fighters:
        raise BattleError(
            "You need a healthy Pokémon in your party to battle!"
        )

    opponent = make_fighter_from_species(
        species_id,
        level,
        variant=variant,
    )

    return _start(
        player_id,
        format_name="wild",
        player_team=party_fighters,
        opponent_team=[opponent],
        context={"species": species_id, "level": level},
    )


def _party_fighters(player_id: int) -> list[dict[str, Any]]:
    """The player's party as fighters (max 3, healthy ones first)."""

    from .services import get_party

    party = get_party(player_id)

    fighters: list[dict[str, Any]] = []

    for member in party:
        if int(member.get("current_hp") or 0) <= 0:
            continue

        fighter = make_fighter_from_species(
            str(member["species_id"]),
            int(member["level"]),
            pokemon_id=int(member["pokemon_id"]),
            nickname=member.get("nickname"),
            variant=str(member.get("variant") or "normal"),
        )

        # Real current HP carries into battle.
        fighter["hp"] = min(
            int(member["current_hp"]),
            fighter["stats"]["hp"],
        )

        fighters.append(fighter)

        if len(fighters) >= 3:
            break

    return fighters


def _start(
    player_id: int,
    *,
    format_name: str,
    player_team: list[dict[str, Any]],
    opponent_team: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    state = {
        "format": format_name,
        "teams": {
            "player": player_team,
            "opponent": opponent_team,
        },
        "active": {"player": 0, "opponent": 0},
        "turn": 1,
        "log": ["The battle started!"],
        "over": False,
        "winner": None,
    }

    # Only one active battle per player: retire stale ones.
    with get_connection() as db:
        stale = db.execute(
            """
            SELECT id FROM battles
            WHERE player_id = ? AND status = 'active'
            """,
            (player_id,),
        ).fetchall()

        for row in stale:
            db.execute(
                """
                UPDATE battles
                SET status = 'cancelled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (row["id"],),
            )

        cursor = db.execute(
            """
            INSERT INTO battles (player_id, format, context, state)
            VALUES (?, ?, ?, ?)
            """,
            (
                player_id,
                format_name,
                json.dumps(context),
                json.dumps(state),
            ),
        )
        db.commit()
        battle_id = cursor.lastrowid

    return {
        "battle_id": battle_id,
        **public_view(state),
    }


# ============================================================
# GET / ACT
# ============================================================

def get_active_battle(player_id: int) -> dict[str, Any] | None:
    """The player's active battle (public view), or None."""

    ensure_battle_tables()

    with get_connection() as db:
        row = db.execute(
            """
            SELECT id, state
            FROM battles
            WHERE player_id = ? AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (player_id,),
        ).fetchone()

    if row is None:
        return None

    state = json.loads(row["state"])

    return {
        "battle_id": row["id"],
        **public_view(state),
    }


def battle_action(
    player_id: int,
    battle_id: int,
    action: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply one player action to their stored battle. Server
    authoritative: everything re-validates against the stored state.
    """

    ensure_battle_tables()

    with get_connection() as db:
        row = db.execute(
            """
            SELECT id, status, state
            FROM battles
            WHERE id = ? AND player_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (battle_id, player_id),
        ).fetchone()

        if row is None:
            raise BattleError("Battle not found.")

        if row["status"] != "active":
            raise BattleError("This battle is already over.")

        state = json.loads(row["state"])

    # ------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------

    apply_action(state, "player", action, rng=random.Random())

    status = "active"
    winner = None

    if state["over"]:
        if state.get("fled"):
            status = "fled"
        else:
            status = "finished"
            winner = state["winner"]

        _sync_party_after_battle(player_id, state)

    with get_connection() as db:
        db.execute(
            """
            UPDATE battles
            SET state = ?,
                status = ?,
                winner = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                json.dumps(state),
                status,
                winner,
                battle_id,
            ),
        )
        db.commit()

    return {
        "battle_id": battle_id,
        **public_view(state),
    }


def _sync_party_after_battle(
    player_id: int,
    state: dict[str, Any],
) -> None:
    """
    Write final HP from the battle back onto the party rows so damage
    persists after the battle ends.
    """

    with get_connection() as db:
        for fighter in state["teams"]["player"]:
            pokemon_id = fighter.get("pokemon_id")

            if pokemon_id is None:
                continue

            db.execute(
                """
                UPDATE pokemon
                SET current_hp = ?
                WHERE id = ? AND owner_id = ?
                """,
                (int(fighter["hp"]), pokemon_id, player_id),
            )

        db.commit()


# ============================================================
# HISTORY
# ============================================================

def battle_history(
    player_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Recent finished battles for the player (newest first)."""

    ensure_battle_tables()

    with get_connection() as db:
        rows = db.execute(
            """
            SELECT id, format, status, winner, context, updated_at
            FROM battles
            WHERE player_id = ?
              AND status IN ('finished', 'fled', 'cancelled')
            ORDER BY id DESC
            LIMIT ?
            """,
            (player_id, max(1, min(int(limit), 50))),
        ).fetchall()

    history = []

    for row in rows:
        context = json.loads(row["context"] or "{}")

        history.append(
            {
                "id": row["id"],
                "format": row["format"],
                "status": row["status"],
                "winner": row["winner"],
                "updated_at": row["updated_at"],
                "context": context,
            }
        )

    return history
