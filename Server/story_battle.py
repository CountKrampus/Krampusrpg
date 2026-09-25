"""
Krampus RPG Story Battle Engine
===============================

Powers the playable Story Adventure quest chain. Battle state lives in
a database table (story_battles) so turns are simple stateless POSTs.

Flow:

    1. Player opens /story-adventure/quest/<questline>/<quest_id>
       and clicks "Begin Battle" on the first not-yet-defeated battle.
    2. start_story_battle() creates a session: the NPC team is
       snapshotted into the row as JSON; the player party is
       snapshotted with real current HP so consecutive battles feel
       continuous. Victory restores the pre-battle HP snapshot.
    3. take_story_turn() resolves one exchange: the player's active
       Pokémon attacks with a chosen move, then the NPC's active
       Pokémon counterattacks. Fainting advances the next combatant
       on either side; the player may also switch (costs the turn).
    4. When the NPC team is exhausted the battle is won: the step is
       marked defeated in player_quest_battles and participants gain
       XP. When the player has no healthy Pokémon left, the battle is
       lost and the session cleared (retry starts fresh).

One live session per (player, questline, quest, battle_index) —
enforced by the table's primary key.
"""

from __future__ import annotations

import json
import random
from typing import Any

from .database import get_connection
from .quest_battle_storage import ensure_quest_battle_schema
from .services import get_move, get_species


# ============================================================
# TUNING
# ============================================================

RANDOM_SPREAD = 0.15          # ±15% damage variance
STAB_MULTIPLIER = 1.5         # same-type attack bonus
TYPE_CHART_BONUS = 1.3        # super-effective (simplified chart)
TYPE_CHART_PENALTY = 0.75     # not-very-effective

TYPE_CHART = {
    "fire": {"grass": TYPE_CHART_BONUS, "ice": TYPE_CHART_BONUS, "water": TYPE_CHART_PENALTY, "fire": TYPE_CHART_PENALTY},
    "water": {"fire": TYPE_CHART_BONUS, "water": TYPE_CHART_PENALTY, "grass": TYPE_CHART_PENALTY},
    "grass": {"water": TYPE_CHART_BONUS, "grass": TYPE_CHART_PENALTY, "fire": TYPE_CHART_PENALTY},
    "electric": {"water": TYPE_CHART_BONUS, "flying": TYPE_CHART_BONUS, "electric": TYPE_CHART_PENALTY, "grass": TYPE_CHART_PENALTY},
    "ice": {"grass": TYPE_CHART_BONUS, "flying": TYPE_CHART_BONUS, "ice": TYPE_CHART_PENALTY, "fire": TYPE_CHART_PENALTY, "water": TYPE_CHART_PENALTY},
    "dark": {"ghost": TYPE_CHART_BONUS, "dark": TYPE_CHART_PENALTY},
    "ghost": {"ghost": TYPE_CHART_BONUS},
    "flying": {"grass": TYPE_CHART_BONUS},
}


# ============================================================
# STAT / DAMAGE HELPERS
# ============================================================

def _stat_at_level(base: int, level: int) -> int:
    """Simplified stat scaling from base stats."""
    return max(1, int(base * (0.5 + level / 50.0)))


def _hp_at_level(base: int, level: int) -> int:
    return max(1, int(base * (0.5 + level / 50.0) * 1.4))


def _move_type(move: dict[str, Any]) -> str:
    """Move records carry either 'type' (JSON fallback) or
    'type_id' (database path) -- normalize."""
    return str(move.get("type") or move.get("type_id") or "normal").lower()


def _combatant(
    species_id: str,
    level: int,
    variant: str = "normal",
) -> dict[str, Any] | None:
    """
    Build a battle-ready combatant from species data: stats, HP, and
    up to 4 attack-capable moves (falling back to Tackle).
    """
    species = get_species(species_id)
    if species is None:
        return None

    base = species.get("base_stats") or {}
    level = max(1, int(level))
    hp = _hp_at_level(int(base.get("hp", 50)), level)

    move_ids: list[str] = []

    for entry in species.get("level_up_moves") or []:
        if isinstance(entry, dict):
            candidate = entry.get("move")
        else:
            candidate = entry
        if isinstance(candidate, str):
            move_ids.append(candidate)

    for move_id in species.get("starting_moves") or []:
        if isinstance(move_id, str):
            move_ids.append(move_id)

    attacking: list[str] = []
    for move_id in move_ids:
        if move_id in attacking:
            continue
        move = get_move(move_id)
        if move and int(move.get("power") or 0) > 0:
            attacking.append(move_id)

    moves = attacking[:4] or ["tackle"]

    return {
        "species_id": species_id,
        "name": species.get("name", species_id.title()),
        "level": level,
        "variant": variant or "normal",
        "types": [str(t).lower() for t in (species.get("type") or [])],
        "attack": _stat_at_level(int(base.get("attack", 50)), level),
        "defense": _stat_at_level(int(base.get("defense", 50)), level),
        "speed": _stat_at_level(int(base.get("speed", 50)), level),
        "max_hp": hp,
        "hp": hp,
        "moves": moves,
    }


def _party_move_ids(pokemon_id: int) -> list[str]:
    """A party member's equipped moves from pokemon_moves."""
    move_ids: list[str] = []

    try:
        with get_connection() as db:
            rows = db.execute(
                """
                SELECT move_id FROM pokemon_moves
                WHERE pokemon_id = ?
                ORDER BY slot
                """,
                (pokemon_id,),
            ).fetchall()

        move_ids = [str(r["move_id"]) for r in rows]
    except Exception:
        move_ids = []

    return move_ids


def _type_effectiveness(move_type: str, defender_types: list[str]) -> float:
    factor = 1.0
    for dtype in defender_types:
        factor *= TYPE_CHART.get(move_type, {}).get(dtype, 1.0)
    return factor


def _compute_damage(
    attacker: dict[str, Any],
    defender: dict[str, Any],
    move: dict[str, Any],
) -> tuple[int, str]:
    """Damage for one hit. Returns (damage, effectiveness_note)."""
    power = max(1, int(move.get("power") or 40))
    level = int(attacker.get("level", 5))

    damage = (
        ((2 * level / 5.0 + 2) * power / 50.0)
        * (attacker["attack"] / max(1, defender["defense"]))
        * 2.0
    )

    note = ""
    move_type = _move_type(move)
    eff = _type_effectiveness(move_type, defender.get("types") or [])

    if eff >= TYPE_CHART_BONUS:
        note = "It's super effective!"
        damage *= eff
    elif eff <= TYPE_CHART_PENALTY:
        note = "It's not very effective..."
        damage *= eff

    if move_type in (attacker.get("types") or []):
        damage *= STAB_MULTIPLIER

    damage *= 1.0 + random.uniform(-RANDOM_SPREAD, RANDOM_SPREAD)

    return max(1, int(damage)), note


# ============================================================
# SNAPSHOTS
# ============================================================

def _npc_team_from_quest(
    questline: str,
    npc_id: str,
) -> list[dict[str, Any]]:
    """Snapshot an NPC's team into battle combatants."""
    from .quest_chain import get_npc

    npc = get_npc(questline, npc_id)
    if npc is None:
        return []

    team: list[dict[str, Any]] = []
    for entry in npc.get("team") or []:
        if not isinstance(entry, dict):
            continue
        mon = _combatant(
            str(entry.get("species", "")),
            int(entry.get("level", 5)),
            str(entry.get("variant", "normal") or "normal"),
        )
        if mon:
            team.append(mon)

    return team


def _player_party_snapshot(player_id: int) -> list[dict[str, Any]]:
    """
    Snapshot the player's party. Carries over real current HP so
    consecutive battles feel continuous.
    """
    from .party_storage import get_party as get_storage_party

    snapshot: list[dict[str, Any]] = []

    for mon in get_storage_party(player_id):
        species = get_species(str(mon.get("species_id", "")))
        if species is None:
            continue

        base = species.get("base_stats") or {}
        level = max(1, int(mon.get("level", 5)))
        max_hp = int(
            mon.get("max_hp")
            or _hp_at_level(int(base.get("hp", 50)), level)
        )
        current_hp = int(mon.get("current_hp", max_hp))

        # Party rows use pokemon_id as the Pokémon's key.
        pokemon_id = int(mon.get("pokemon_id") or 0)

        # Equipped moves; fall back to species attacking moves.
        move_ids = _party_move_ids(pokemon_id)
        attacking: list[str] = []
        for move_id in move_ids:
            if move_id in attacking:
                continue
            move = get_move(move_id)
            if move and int(move.get("power") or 0) > 0:
                attacking.append(move_id)

        if not attacking:
            for entry in species.get("level_up_moves") or []:
                candidate = entry.get("move") if isinstance(entry, dict) else entry
                if not isinstance(candidate, str) or candidate in attacking:
                    continue
                move = get_move(candidate)
                if move and int(move.get("power") or 0) > 0:
                    attacking.append(candidate)
                    break

        snapshot.append({
            "pokemon_id": pokemon_id,
            "species_id": str(mon.get("species_id", "")),
            "name": mon.get("nickname")
            or species.get("name", str(mon.get("species_id", "")).title()),
            "level": level,
            "variant": str(mon.get("variant", "normal") or "normal"),
            "types": [str(t).lower() for t in (species.get("type") or [])],
            "attack": _stat_at_level(int(base.get("attack", 50)), level),
            "defense": _stat_at_level(int(base.get("defense", 50)), level),
            "speed": _stat_at_level(int(base.get("speed", 50)), level),
            "max_hp": max_hp,
            "hp": max(0, current_hp),
            "moves": attacking[:4] or ["tackle"],
        })

    return snapshot


# ============================================================
# POST-BATTLE EFFECTS
# ============================================================

def _restore_party_hp(player_id: int, snapshot: list[dict[str, Any]]) -> None:
    """After victory, restore each party member's real HP to its
    pre-battle value — story battles don't drain the roster."""
    from .party_storage import get_party as get_storage_party

    by_id = {int(s.get("pokemon_id") or 0): s for s in snapshot}

    with get_connection() as db:
        for mon in get_storage_party(player_id):
            snap = by_id.get(int(mon["pokemon_id"]))
            if snap is None:
                continue
            db.execute(
                "UPDATE pokemon SET current_hp = ? WHERE id = ?",
                (int(snap.get("hp") or 0), int(mon["pokemon_id"])),
            )
        db.commit()


def _award_victory_xp(player_id: int, defeated: list[dict[str, Any]]) -> int:
    """Distribute XP across living party members. Returns per-mon XP."""
    if not defeated:
        return 0

    total = sum(25 * int(mon.get("level", 5)) for mon in defeated)

    from .party_storage import get_party as get_storage_party

    alive = [
        m
        for m in get_storage_party(player_id)
        if int(m.get("current_hp") or 0) > 0
    ]

    if not alive:
        return 0

    share = max(1, total // len(alive))

    with get_connection() as db:
        for mon in alive:
            db.execute(
                "UPDATE pokemon SET experience = experience + ? WHERE id = ?",
                (share, int(mon["pokemon_id"])),
            )
        db.commit()

    return share


# ============================================================
# SESSIONS
# ============================================================

def _ensure_schema() -> None:
    ensure_quest_battle_schema()

    with get_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS story_battles (
                player_id    INTEGER NOT NULL,
                questline    TEXT NOT NULL,
                quest_id     TEXT NOT NULL,
                battle_index INTEGER NOT NULL,

                npc_id       TEXT NOT NULL,
                npc_team     TEXT NOT NULL,
                party        TEXT NOT NULL,

                player_slot  INTEGER NOT NULL DEFAULT 0,
                npc_slot     INTEGER NOT NULL DEFAULT 0,

                log          TEXT NOT NULL DEFAULT '[]',

                PRIMARY KEY (player_id, questline, quest_id, battle_index),

                FOREIGN KEY (player_id)
                    REFERENCES players(id)
                    ON DELETE CASCADE
            );
            """
        )
        db.commit()


def start_story_battle(
    player_id: int,
    questline: str,
    quest_id: str,
    battle_index: int,
) -> dict[str, Any]:
    """
    Create (or return the existing) battle session for this quest
    battle. Raises ValueError on bad references or a wiped party.
    """
    _ensure_schema()

    from .quest_chain import get_quests, quest_battles

    quest = next(
        (
            q
            for q in get_quests(questline)
            if str(q.get("id", "")).lower() == str(quest_id).lower()
        ),
        None,
    )

    if quest is None:
        raise ValueError("Quest not found.")

    battles = quest_battles(questline, quest)
    if not 0 <= battle_index < len(battles):
        raise ValueError("Battle not found.")

    npc_id = str(battles[battle_index]["npc"].get("id", ""))

    existing = get_story_battle(player_id, questline, quest_id, battle_index)
    if existing is not None:
        return existing

    npc_team = _npc_team_from_quest(questline, npc_id)
    if not npc_team:
        raise ValueError("This battle has no valid NPC team.")

    party = _player_party_snapshot(player_id)
    lead_index = next((i for i, m in enumerate(party) if m["hp"] > 0), None)

    if lead_index is None:
        raise ValueError(
            "Your party has no healthy Pokémon. Visit the Pokémon Center first."
        )

    with get_connection() as db:
        db.execute(
            """
            INSERT INTO story_battles (
                player_id, questline, quest_id, battle_index,
                npc_id, npc_team, party, player_slot, npc_slot, log
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]')
            ON CONFLICT (player_id, questline, quest_id, battle_index)
            DO NOTHING
            """,
            (
                player_id,
                questline,
                quest_id,
                battle_index,
                npc_id,
                json.dumps(npc_team),
                json.dumps(party),
                lead_index,
                0,
            ),
        )
        db.commit()

    session = get_story_battle(player_id, questline, quest_id, battle_index)
    if session is None:
        raise RuntimeError("Failed to create battle session.")

    session["log"] = [
        f"A wild challenge! {battles[battle_index]['npc'].get('name', npc_id.replace('_', ' ').title())} wants to battle!",
        f"Go, {party[lead_index]['name']}!",
    ]
    return session


def get_story_battle(
    player_id: int,
    questline: str,
    quest_id: str,
    battle_index: int,
) -> dict[str, Any] | None:
    """Load a live battle session (decoded)."""
    _ensure_schema()

    with get_connection() as db:
        row = db.execute(
            """
            SELECT * FROM story_battles
            WHERE player_id = ? AND questline = ? AND quest_id = ?
              AND battle_index = ?
            """,
            (player_id, questline, quest_id, battle_index),
        ).fetchone()

    if row is None:
        return None

    session = dict(row)
    session["npc_team"] = json.loads(session["npc_team"])
    session["party"] = json.loads(session["party"])
    session["log"] = json.loads(session["log"])
    return session


def delete_story_battle(
    player_id: int,
    questline: str,
    quest_id: str,
    battle_index: int,
) -> None:
    with get_connection() as db:
        db.execute(
            """
            DELETE FROM story_battles
            WHERE player_id = ? AND questline = ? AND quest_id = ?
              AND battle_index = ?
            """,
            (player_id, questline, quest_id, battle_index),
        )
        db.commit()


# ============================================================
# TURN RESOLUTION
# ============================================================

def take_story_turn(
    player_id: int,
    questline: str,
    quest_id: str,
    battle_index: int,
    move_id: str | None = None,
    switch_to: int | None = None,
) -> dict[str, Any]:
    """
    Resolve one turn. Returns the session plus outcome:

        outcome: ongoing | won | lost
    """
    session = get_story_battle(player_id, questline, quest_id, battle_index)
    if session is None:
        raise ValueError("No active battle for this quest step.")

    npc_team: list[dict[str, Any]] = session["npc_team"]
    party: list[dict[str, Any]] = session["party"]
    player_slot = int(session["player_slot"])
    npc_slot = int(session["npc_slot"])
    log: list[str] = list(session["log"])

    # --- Switch (voluntary or forced) ---
    if move_id is None:
        if switch_to is None:
            raise ValueError("Provide a move or a switch target.")

        target = int(switch_to)

        if not 0 <= target < len(party):
            raise ValueError("Invalid switch target.")

        if party[target]["hp"] <= 0 or target == player_slot:
            raise ValueError("Can't switch to that Pokémon.")

        player_slot = target
        log.append(f"You sent out {party[player_slot]['name']}!")

        result = _persist(
            player_id, questline, quest_id, battle_index,
            npc_team, party, player_slot, npc_slot, log,
        )
        result["outcome"] = "ongoing"
        return result

    # --- Player attack ---
    attacker = party[player_slot]
    defender = npc_team[npc_slot]

    if move_id not in attacker["moves"]:
        raise ValueError("That move isn't available.")

    move = get_move(move_id)
    if move is None:
        raise ValueError("Unknown move.")

    damage, note = _compute_damage(attacker, defender, move)
    defender["hp"] = max(0, defender["hp"] - damage)
    log.append(
        f"{attacker['name']} used {move.get('name', move_id)}! "
        f"{damage} damage. {note}".strip()
    )

    if defender["hp"] <= 0:
        log.append(f"Enemy {defender['name']} fainted!")
        npc_slot += 1

        if npc_slot >= len(npc_team):
            # --- VICTORY ---
            xp_awarded = _award_victory_xp(player_id, npc_team)
            _restore_party_hp(player_id, party)
            _mark_battle_defeated(player_id, questline, quest_id, battle_index)
            delete_story_battle(player_id, questline, quest_id, battle_index)

            return {
                "outcome": "won",
                "log": log,
                "xp_awarded": xp_awarded,
            }

        log.append(f"Enemy sent out {npc_team[npc_slot]['name']}!")

    # --- NPC counterattack ---
    defender = npc_team[npc_slot]
    npc_move_id = random.choice(defender["moves"])
    npc_move = get_move(npc_move_id) or {
        "id": "tackle",
        "name": "Tackle",
        "type": "normal",
        "power": 40,
    }

    damage, note = _compute_damage(defender, attacker, npc_move)
    attacker["hp"] = max(0, attacker["hp"] - damage)
    log.append(
        f"Enemy {defender['name']} used {npc_move.get('name', npc_move_id)}! "
        f"{damage} damage. {note}".strip()
    )

    if attacker["hp"] <= 0:
        log.append(f"{attacker['name']} fainted!")

        next_healthy = next(
            (
                i
                for i, m in enumerate(party)
                if m["hp"] > 0 and i != player_slot
            ),
            None,
        )

        if next_healthy is None:
            # --- DEFEAT ---
            delete_story_battle(player_id, questline, quest_id, battle_index)
            return {
                "outcome": "lost",
                "log": log,
            }

        player_slot = next_healthy
        log.append(f"Go, {party[player_slot]['name']}!")

    result = _persist(
        player_id, questline, quest_id, battle_index,
        npc_team, party, player_slot, npc_slot, log,
    )
    result["outcome"] = "ongoing"
    return result


def _persist(
    player_id: int,
    questline: str,
    quest_id: str,
    battle_index: int,
    npc_team: list[dict[str, Any]],
    party: list[dict[str, Any]],
    player_slot: int,
    npc_slot: int,
    log: list[str],
) -> dict[str, Any]:
    """Save session state and return the base result dict."""
    with get_connection() as db:
        db.execute(
            """
            UPDATE story_battles
            SET npc_team = ?, party = ?, player_slot = ?, npc_slot = ?, log = ?
            WHERE player_id = ? AND questline = ? AND quest_id = ?
              AND battle_index = ?
            """,
            (
                json.dumps(npc_team),
                json.dumps(party),
                player_slot,
                npc_slot,
                json.dumps(log[-30:]),
                player_id,
                questline,
                quest_id,
                battle_index,
            ),
        )
        db.commit()

    return {
        "log": log,
        "npc_team": npc_team,
        "party": party,
        "player_slot": player_slot,
        "npc_slot": npc_slot,
    }


def _mark_battle_defeated(
    player_id: int,
    questline: str,
    quest_id: str,
    battle_index: int,
) -> None:
    """Record that this quest battle step is defeated."""
    _ensure_schema()

    with get_connection() as db:
        db.execute(
            """
            INSERT INTO player_quest_battles
                (player_id, questline, quest_id, battle_index)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (player_id, questline, quest_id, battle_index)
            DO NOTHING
            """,
            (player_id, questline, quest_id, battle_index),
        )
        db.commit()


def get_defeated_battles(player_id: int, questline: str) -> set[tuple[str, int]]:
    """Set of (quest_id, battle_index) the player has defeated."""
    _ensure_schema()

    with get_connection() as db:
        rows = db.execute(
            """
            SELECT quest_id, battle_index FROM player_quest_battles
            WHERE player_id = ? AND questline = ?
            """,
            (player_id, questline),
        ).fetchall()

    return {(str(r["quest_id"]), int(r["battle_index"])) for r in rows}


# ============================================================
# QUEST PROGRESSION
# ============================================================

def start_quest(player_id: int, questline: str, quest_id: str) -> None:
    """Mark a quest active in player_quests."""
    with get_connection() as db:
        db.execute(
            """
            INSERT INTO player_quests (player_id, quest_id, status)
            VALUES (?, ?, 'active')
            ON CONFLICT (player_id, quest_id) DO NOTHING
            """,
            (player_id, quest_id),
        )
        db.commit()


def complete_quest(
    player_id: int,
    questline: str,
    quest_id: str,
) -> dict[str, Any] | None:
    """
    Mark a quest completed, grant its rewards (money, items, XP,
    pokemon_reward), and activate the next quest in the line.

    Returns a summary dict, or None when already completed.
    """
    from .quest_chain import get_quest

    quest = get_quest(questline, quest_id)
    if quest is None:
        raise ValueError("Quest not found.")

    with get_connection() as db:
        row = db.execute(
            """
            SELECT status FROM player_quests
            WHERE player_id = ? AND quest_id = ?
            """,
            (player_id, quest_id),
        ).fetchone()

        if row is not None and row["status"] == "completed":
            return None

        db.execute(
            """
            INSERT INTO player_quests (player_id, quest_id, status, completed_at)
            VALUES (?, ?, 'completed', CURRENT_TIMESTAMP)
            ON CONFLICT (player_id, quest_id) DO UPDATE SET
                status = 'completed',
                completed_at = CURRENT_TIMESTAMP
            """,
            (player_id, quest_id),
        )

        rewards = quest.get("rewards") or {}
        money = int(rewards.get("money") or 0)

        if money > 0:
            db.execute(
                """
                UPDATE player_progress
                SET money = money + ?
                WHERE player_id = ?
                """,
                (money, player_id),
            )

        granted_items: list[str] = []
        for entry in rewards.get("items") or []:
            item_id = str(entry.get("id", "")).strip()
            quantity = max(1, int(entry.get("quantity", 1) or 1))
            if not item_id:
                continue
            db.execute(
                """
                INSERT INTO player_items (player_id, item_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT (player_id, item_id) DO UPDATE SET
                    quantity = quantity + excluded.quantity
                """,
                (player_id, item_id, quantity),
            )
            granted_items.append(
                f"{quantity}× {item_id.replace('_', ' ').title()}"
            )

        db.commit()

    xp = int(rewards.get("xp") or 0)
    if xp > 0:
        _award_flat_xp(player_id, xp)

    summary: dict[str, Any] = {
        "quest_id": quest_id,
        "money": money,
        "items": granted_items,
        "xp": xp,
        "pokemon": None,
    }

    pokemon_reward = rewards.get("pokemon_reward")
    if isinstance(pokemon_reward, dict):
        summary["pokemon"] = _grant_pokemon_reward(
            player_id, questline, quest_id, pokemon_reward
        )

    _activate_next_quest(player_id, questline, quest_id)

    return summary


def _award_flat_xp(player_id: int, xp: int) -> int:
    """Give each living party member a flat XP amount."""
    from .party_storage import get_party as get_storage_party

    alive = [
        m
        for m in get_storage_party(player_id)
        if int(m.get("current_hp") or 0) > 0
    ]

    if not alive:
        return 0

    with get_connection() as db:
        for mon in alive:
            db.execute(
                "UPDATE pokemon SET experience = experience + ? WHERE id = ?",
                (xp, int(mon["pokemon_id"])),
            )
        db.commit()

    return xp


def _grant_pokemon_reward(
    player_id: int,
    questline: str,
    quest_id: str,
    pokemon_reward: dict[str, Any],
) -> str | None:
    """Deliver a quest's Pokémon reward. Returns a description."""
    from .admin.services import admin_assign_pokemon

    rtype = str(pokemon_reward.get("type", ""))

    species_id: str | None = None
    variant = str(pokemon_reward.get("variant", "normal") or "normal")
    level = int(pokemon_reward.get("level", 5))

    pool = [str(s) for s in pokemon_reward.get("pool") or []]

    if rtype == "reward_encounter":
        species_id = str(pokemon_reward.get("species", "")) or None

    elif rtype in ("marked_pokemon", "choice"):
        species_id = random.choice(pool) if pool else None

        chance_cfg = pokemon_reward.get("variant_chance") or {}
        try:
            odds = int(chance_cfg.get("odds", 10))
        except (TypeError, ValueError):
            odds = 10
        if odds > 0 and random.randint(1, odds) == 1:
            variant = str(chance_cfg.get("variant", "krampus"))

    if not species_id:
        return None

    try:
        admin_assign_pokemon(
            owner_id=player_id,
            species_id=species_id,
            level=level,
            shiny=False,
            variant=variant,
            nickname=None,
        )
    except Exception:
        return None

    label = species_id.replace("_", " ").title()
    if variant and variant != "normal":
        label = f"{variant.title()} {label}"

    return f"Level {level} {label} joined your team!"


def _activate_next_quest(
    player_id: int,
    questline: str,
    quest_id: str,
) -> None:
    """Mark the next quest in the line active (if any)."""
    from .quest_chain import get_quests

    quests = get_quests(questline)

    for i, q in enumerate(quests):
        if str(q.get("id", "")).lower() == str(quest_id).lower():
            if i + 1 < len(quests):
                start_quest(player_id, questline, str(quests[i + 1]["id"]))
            break
