"""
Krampus RPG Pokémon Center
==========================

Healing service for the Pokémon Center page:

- heal_party(): restore every party member's current_hp to max_hp.
- get_center_overview(): what the page shows — party with HP bars,
  counts of fainted/injured, and whether anything needs healing.

Only the active party is healed; PC-boxed Pokémon keep their stored
HP (they aren't battling).

Story battles deliberately restore pre-battle HP (see
Server/story_battle.py), so healing is only reachable through the
Pokémon Center page.
"""

from __future__ import annotations

from typing import Any

from .database import get_connection
from .party_storage import get_party

# Healing is free for low-level teams; once the party's average level
# passes this threshold each heal costs a small fee (scaled to the
# highest party level) — a light money sink that grows with progress.
FREE_HEAL_MAX_AVG_LEVEL = 15
FEE_PER_LEVEL = 25
FEE_MIN = 50
FEE_MAX = 5000


def get_heal_fee(party: list[dict[str, Any]]) -> int:
    """
    Fee (Pokédollars) for healing this party. Free while the team's
    average level is still within the free tier.
    """

    if not party:
        return 0

    avg_level = sum(int(m.get("level", 1) or 1) for m in party) / len(party)

    if avg_level <= FREE_HEAL_MAX_AVG_LEVEL:
        return 0

    top_level = max(int(m.get("level", 1) or 1) for m in party)

    return max(FEE_MIN, min(FEE_MAX, top_level * FEE_PER_LEVEL))


def heal_party(player_id: int) -> dict[str, Any]:
    """
    Fully heal every party member (HP restored to max_hp), charging
    the heal fee when the party is past the free tier.

    Returns a summary: how many were healed, how much HP was restored,
    and the fee charged (0 when free).
    """

    party = get_party(player_id)

    healed = 0
    hp_restored = 0

    for mon in party:
        current = int(mon.get("current_hp", 0) or 0)
        max_hp = max(1, int(mon.get("max_hp", 1) or 1))

        if current >= max_hp:
            continue

        hp_restored += max_hp - current
        healed += 1

    if healed == 0:
        return {
            "healed": 0,
            "hp_restored": 0,
            "fee": 0,
            "party_size": len(party),
        }

    fee = get_heal_fee(party)

    with get_connection() as db:
        # Charge the fee first (fails softly: a broke trainer still
        # gets healed — the balance just can't go negative).
        if fee > 0:
            db.execute(
                """
                UPDATE player_progress
                SET money = MAX(0, money - ?)
                WHERE player_id = ?
                """,
                (fee, player_id),
            )

        for mon in party:
            current = int(mon.get("current_hp", 0) or 0)
            max_hp = max(1, int(mon.get("max_hp", 1) or 1))

            if current >= max_hp:
                continue

            db.execute(
                """
                UPDATE pokemon
                SET current_hp = ?
                WHERE id = ?
                """,
                (max_hp, int(mon["pokemon_id"])),
            )

        db.commit()

    return {
        "healed": healed,
        "hp_restored": hp_restored,
        "fee": fee,
        "party_size": len(party),
    }


def get_center_overview(player_id: int) -> dict[str, Any]:
    """
    Everything the Pokémon Center page needs: the party with HP
    fractions, injury counts, and whether the Heal All button should
    do anything.
    """

    party = get_party(player_id)

    members: list[dict[str, Any]] = []
    fainted = 0
    injured = 0
    total_missing = 0

    for mon in party:
        current = int(mon.get("current_hp", 0) or 0)
        max_hp = max(1, int(mon.get("max_hp", 1) or 1))

        if current <= 0:
            fainted += 1
        elif current < max_hp:
            injured += 1

        total_missing += max(0, max_hp - current)

        members.append(
            {
                **mon,
                "hp_percent": round(100 * current / max_hp),
                "needs_heal": current < max_hp,
                "is_fainted": current <= 0,
            }
        )

    return {
        "party": members,
        "party_size": len(members),
        "fainted": fainted,
        "injured": injured,
        "hp_missing": total_missing,
        "needs_heal": total_missing > 0,
        "heal_fee": get_heal_fee(party),
    }
