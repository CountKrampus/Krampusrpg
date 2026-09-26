"""
Krampus RPG Battle Engine

Turn-based Pokémon battles, implemented as a pure state machine so it
can drive story battles (NPC teams from quest data), wild encounters,
and later PvP from the same code.

Design:

    A battle state is a plain JSON-serialisable dict:

        {
            "format": "trainer" | "wild",
            "teams": {
                "player": [fighter, fighter, ...],
                "opponent": [fighter, ...],
            },
            "active": {"player": 0, "opponent": 0},
            "turn": 1,
            "log": ["Turn 1 — ..."],
            "over": False,
            "winner": None,
        }

    A fighter:

        {
            "source": "party:<pokemon_id>" (player) or "npc" (opponent),
            "pokemon_id": int | None,
            "species_id": "charmander",
            "name": "Charmander",
            "level": 12,
            "types": ["fire"],
            "stats": {"hp": 30, "attack": 14, ...},
            "hp": 30,            # current
            "moves": [move dicts from the catalog],
        }

    Server authoritative: every action is validated against this state,
    which lives in the battles table (see battle_store.py). The client
    only ever says what it wants to do.

Damage model (matches the game's stat system, no IVs/EVs/Nature):

    damage = ((2*level/5 + 2) * power * A/D / 50 + 2) * modifiers

    modifiers: STAB (1.5), type effectiveness chart, random 0.85-1.0.

Type effectiveness is the classic chart for the types that exist in
the moves catalog (normal, fire, water, electric, grass, ice, fighting,
poison, ground, flying, psychic, bug, rock, ghost, dragon, dark,
steel, fairy), with unknown types defaulting to 1.0.
"""

from __future__ import annotations

import math
import random
from typing import Any

from .services import (
    get_move,
    get_species,
    get_species_learnset,
)

# ============================================================
# TYPE EFFECTIVENESS
# ============================================================

# chart[attacking][defending] = multiplier; missing pairs are 1.0.
TYPE_CHART: dict[str, dict[str, float]] = {
    "normal": {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire": {
        "fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 2.0,
        "bug": 2.0, "rock": 0.5, "dragon": 0.5, "steel": 2.0,
    },
    "water": {
        "fire": 2.0, "water": 0.5, "grass": 0.5, "ground": 2.0,
        "rock": 2.0, "dragon": 0.5,
    },
    "electric": {
        "water": 2.0, "electric": 0.5, "grass": 0.5, "ground": 0.0,
        "flying": 2.0, "dragon": 0.5,
    },
    "grass": {
        "fire": 0.5, "water": 2.0, "grass": 0.5, "poison": 0.5,
        "ground": 2.0, "flying": 0.5, "bug": 0.5, "rock": 2.0,
        "dragon": 0.5, "steel": 0.5,
    },
    "ice": {
        "fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 0.5,
        "ground": 2.0, "flying": 2.0, "dragon": 2.0, "steel": 0.5,
    },
    "fighting": {
        "normal": 2.0, "ice": 2.0, "poison": 0.5, "flying": 0.5,
        "psychic": 0.5, "bug": 0.5, "rock": 2.0, "ghost": 0.0,
        "dark": 2.0, "steel": 2.0, "fairy": 0.5,
    },
    "poison": {
        "grass": 2.0, "poison": 0.5, "ground": 0.5, "rock": 0.5,
        "ghost": 0.5, "steel": 0.0, "fairy": 2.0,
    },
    "ground": {
        "fire": 2.0, "electric": 2.0, "grass": 0.5, "poison": 2.0,
        "flying": 0.0, "bug": 0.5, "rock": 2.0, "steel": 2.0,
    },
    "flying": {
        "electric": 0.5, "grass": 2.0, "fighting": 2.0, "bug": 2.0,
        "rock": 0.5, "steel": 0.5,
    },
    "psychic": {
        "fighting": 2.0, "poison": 2.0, "psychic": 0.5, "dark": 0.0,
        "steel": 0.5,
    },
    "bug": {
        "fire": 0.5, "grass": 2.0, "fighting": 0.5, "poison": 0.5,
        "flying": 0.5, "psychic": 2.0, "ghost": 0.5, "dark": 2.0,
        "steel": 0.5, "fairy": 0.5,
    },
    "rock": {
        "fire": 2.0, "ice": 2.0, "fighting": 0.5, "ground": 0.5,
        "flying": 2.0, "bug": 2.0, "steel": 0.5,
    },
    "ghost": {
        "normal": 0.0, "psychic": 2.0, "ghost": 2.0, "dark": 0.5,
    },
    "dragon": {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "dark": {
        "fighting": 0.5, "psychic": 2.0, "ghost": 2.0, "dark": 0.5,
        "steel": 0.5, "fairy": 0.5,
    },
    "steel": {
        "fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2.0,
        "rock": 2.0, "steel": 0.5, "fairy": 2.0,
    },
    "fairy": {
        "fire": 0.5, "fighting": 2.0, "poison": 0.5, "dragon": 2.0,
        "dark": 2.0, "steel": 0.5,
    },
}


def type_effectiveness(move_type: str, defender_types: list[str]) -> float:
    """Multiplier of a move's type against the defender's type(s)."""

    chart = TYPE_CHART.get(move_type, {})
    multiplier = 1.0

    for defending in defender_types or []:
        multiplier *= chart.get(str(defending).lower(), 1.0)

    return multiplier


def effectiveness_label(multiplier: float) -> str:
    if multiplier == 0.0:
        return "It had no effect..."
    if multiplier >= 2.0:
        return "It's super effective!"
    if multiplier > 1.0:
        return "It's effective."
    if multiplier == 0.5:
        return "It's not very effective..."
    if multiplier < 1.0:
        return "It barely scratched them..."
    return ""


# ============================================================
# FIGHTER CONSTRUCTION
# ============================================================

def _moves_for_species(species_id: str, level: int, count: int = 4) -> list[dict[str, Any]]:
    """
    Battle move set: from the species learnset at/below `level`,
    preferring the highest-level moves. NPC teams use this; player
    Pokémon pass their actually-learned moves instead.
    """

    species = get_species(species_id)

    if species is None:
        return []

    entries = [
        entry
        for entry in get_species_learnset(species)
        if int(entry.get("level", 1)) <= max(1, int(level))
    ]

    entries.sort(key=lambda e: e.get("level", 1), reverse=True)

    moves: list[dict[str, Any]] = []

    for entry in entries[:count]:
        move = get_move(entry["id"])

        if move:
            # The moves catalog uses type_id for the element; the JSON
            # fallback used "type". Accept either.
            move_type = (
                move.get("type")
                or move.get("type_id")
                or "normal"
            )

            moves.append(
                {
                    "id": move["id"],
                    "name": move.get("name", move["id"]),
                    "type": str(move_type).lower(),
                    "category": move.get("category", "physical"),
                    "power": int(move.get("power") or 0),
                    "accuracy": int(
                        move.get("accuracy")
                        or 100
                    ),
                    "pp": int(
                        move.get("pp")
                        or move.get("max_pp")
                        or 10
                    ),
                }
            )

    # Every fighter needs at least a Struggle-like fallback.
    if not moves:
        moves = [
            {
                "id": "struggle",
                "name": "Struggle",
                "type": "normal",
                "category": "physical",
                "power": 40,
                "accuracy": 100,
                "pp": 99,
            }
        ]

    return moves


def make_fighter_from_species(
    species_id: str,
    level: int,
    *,
    pokemon_id: int | None = None,
    nickname: str | None = None,
    variant: str = "normal",
) -> dict[str, Any]:
    """Build a battle fighter from a species + level (NPC / wild)."""

    species = get_species(species_id)

    if species is None:
        raise ValueError(f"Unknown species: {species_id}")

    from .services import calculate_pokemon_stats

    stats = calculate_pokemon_stats(species, level)
    types = [
        str(t).lower()
        for t in (species.get("type") or [])
    ]

    name = nickname or str(species.get("name", species_id))

    return {
        "source": f"party:{pokemon_id}" if pokemon_id else "npc",
        "pokemon_id": pokemon_id,
        "species_id": str(species["id"]),
        "name": name,
        "level": int(level),
        "variant": variant,
        "types": types,
        "stats": stats,
        "hp": stats["hp"],
        "moves": _moves_for_species(str(species["id"]), level),
    }


# ============================================================
# DAMAGE
# ============================================================

def compute_damage(
    attacker: dict[str, Any],
    defender: dict[str, Any],
    move: dict[str, Any],
    *,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """
    Resolve one damaging hit. Status moves deal no damage; this
    returns their effect description instead.
    """

    rng = rng or random.Random()

    move_type = str(move.get("type", "normal")).lower()
    category = str(move.get("category", "physical")).lower()
    power = int(move.get("power") or 0)
    accuracy = int(move.get("accuracy") or 100)

    result: dict[str, Any] = {
        "move_id": move["id"],
        "move_name": move.get("name", move["id"]),
        "missed": False,
        "damage": 0,
        "effectiveness": 1.0,
        "crit": False,
        "stab": False,
        "note": "",
    }

    # Accuracy roll.
    if accuracy < 100 and rng.random() * 100 > accuracy:
        result["missed"] = True
        result["note"] = "The attack missed!"
        return result

    # Status moves: no damage formula. Treated as a supporting action
    # with a small self/buff narrative for now (real stat stages can
    # come later without changing the wire format).
    if category == "status" or power <= 0:
        result["note"] = (
            f"{move.get('name', move['id'])} was used, "
            "but nothing seemed to happen."
        )
        return result

    if category == "physical":
        attack = attacker["stats"]["attack"]
        defense = defender["stats"]["defense"]
    else:
        attack = attacker["stats"]["sp_attack"]
        defense = defender["stats"]["sp_defense"]

    level = max(1, int(attacker["level"]))

    base = (
        ((2 * level / 5 + 2) * power * attack / max(1, defense)) / 50
        + 2
    )

    # STAB
    stab = move_type in (attacker.get("types") or [])
    if stab:
        base *= 1.5

    # Type effectiveness
    effectiveness = type_effectiveness(
        move_type,
        defender.get("types") or [],
    )
    base *= effectiveness

    # Critical hit (1/16)
    crit = rng.random() < 0.0625
    if crit:
        base *= 1.5

    # Random spread 0.85 - 1.0
    base *= rng.uniform(0.85, 1.0)

    damage = max(1, math.floor(base)) if effectiveness > 0 else 0

    result["damage"] = damage
    result["effectiveness"] = effectiveness
    result["crit"] = crit
    result["stab"] = stab

    if effectiveness == 0:
        result["note"] = effectiveness_label(effectiveness)
    elif crit:
        result["note"] = "A critical hit! " + effectiveness_label(effectiveness)
    else:
        result["note"] = effectiveness_label(effectiveness)

    return result


# ============================================================
# TURN RESOLUTION
# ============================================================

def _is_fainted(fighter: dict[str, Any]) -> bool:
    return fighter["hp"] <= 0


def _first_alive(team: list[dict[str, Any]]) -> int | None:
    for index, fighter in enumerate(team):
        if not _is_fainted(fighter):
            return index

    return None


def _team_alive(team: list[dict[str, Any]]) -> bool:
    return _first_alive(team) is not None


def apply_action(
    state: dict[str, Any],
    side: str,
    action: dict[str, Any],
    *,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """
    Apply the player's action, then the opponent's, in speed order.

    action: {"type": "move", "slot": 0-3}
            {"type": "switch", "index": 0-5}   (player side only)
            {"type": "flee"}

    Returns the same state dict, mutated (log entries appended).
    Raises BattleError for illegal actions.
    """

    rng = rng or random.Random()

    if state.get("over"):
        raise BattleError("The battle is already over.")

    active = state["active"]
    teams = state["teams"]

    attacker = teams[side][active[side]]
    opponent_side = (
        "opponent" if side == "player" else "player"
    )

    action_type = str(action.get("type", "move")).lower()

    # ------------------------------------------------------------
    # FLEE
    # ------------------------------------------------------------

    if action_type == "flee":
        if state.get("format") == "trainer":
            raise BattleError("You can't flee from a trainer battle!")

        state["over"] = True
        state["winner"] = "opponent"
        state["fled"] = True
        state["log"].append("You fled from the battle.")
        return state

    # ------------------------------------------------------------
    # SWITCH (before any moves resolve)
    # ------------------------------------------------------------

    pending_switch: dict[str, int] | None = None

    if action_type == "switch":
        if side != "player":
            raise BattleError("Only the player can switch.")

        index = int(action.get("index", -1))

        if not 0 <= index < len(teams["player"]):
            raise BattleError("Invalid switch target.")

        if _is_fainted(teams["player"][index]):
            raise BattleError("That Pokémon has fainted.")

        if index == active["player"]:
            raise BattleError("That Pokémon is already out.")

        pending_switch = {"player": index}

    # ------------------------------------------------------------
    # CHOOSE MOVES
    # ------------------------------------------------------------

    player_move: dict[str, Any] | None = None
    opponent_move: dict[str, Any] | None = None

    if action_type == "move":
        slot = int(action.get("slot", -1))

        if not 0 <= slot < len(attacker["moves"]):
            raise BattleError("Invalid move slot.")

        player_move = attacker["moves"][slot]

    # Opponent AI: strongest effective move, naive but decent.
    opponent = teams["opponent"][active["opponent"]]

    if not _is_fainted(opponent):
        opponent_move = _choose_opponent_move(
            opponent,
            teams["player"][active["player"]],
            rng,
        )

    # ------------------------------------------------------------
    # TURN ORDER: switch resolves first, then speed, ties random
    # ------------------------------------------------------------

    order: list[tuple[str, dict[str, Any] | None]] = []

    if pending_switch is not None:
        index = pending_switch["player"]

        state["log"].append(
            "You sent out "
            f"{teams['player'][index]['name']}!"
        )
        active["player"] = index
        attacker = teams["player"][index]

        if player_move is not None:
            player_move = None  # switching costs the turn's move

    if player_move is not None and opponent_move is not None:
        player_first = (
            attacker["stats"]["speed"]
            > opponent["stats"]["speed"]
        ) or (
            attacker["stats"]["speed"]
            == opponent["stats"]["speed"]
            and rng.random() < 0.5
        )

        if player_first:
            order.append(("player", player_move))
            order.append(("opponent", opponent_move))
        else:
            order.append(("opponent", opponent_move))
            order.append(("player", player_move))
    elif player_move is not None:
        order.append(("player", player_move))
    elif opponent_move is not None:
        order.append(("opponent", opponent_move))

    # ------------------------------------------------------------
    # EXECUTE IN ORDER
    # ------------------------------------------------------------

    for acting_side, move in order:
        acting = teams[acting_side][state["active"][acting_side]]
        target_side = (
            "opponent" if acting_side == "player" else "player"
        )
        target = teams[target_side][state["active"][target_side]]

        if _is_fainted(acting):
            continue

        hit = compute_damage(acting, target, move, rng=rng)

        if hit["missed"]:
            state["log"].append(
                f"{acting['name']} used {hit['move_name']} — "
                f"{hit['note']}"
            )
        else:
            target["hp"] = max(0, target["hp"] - hit["damage"])

            message = (
                f"{acting['name']} used {hit['move_name']} on "
                f"{target['name']} — {hit['damage']} damage."
            )

            if hit["note"]:
                message += f" {hit['note']}"

            state["log"].append(message)

        # Faint handling: log + auto-send next opponent.
        if _is_fainted(target):
            state["log"].append(f"{target['name']} fainted!")

            next_index = _first_alive(teams[target_side])

            if next_index is None:
                state["over"] = True
                state["winner"] = acting_side
            elif target_side == "opponent":
                state["active"]["opponent"] = next_index
                state["log"].append(
                    f"Opponent sent out "
                    f"{teams[target_side][next_index]['name']}!"
                )

        if state["over"]:
            break

    if not state["over"]:
        state["turn"] += 1

    return state


def _choose_opponent_move(
    opponent: dict[str, Any],
    target: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    """
    Simple but not stupid: score each move by expected damage
    (power * effectiveness), with a 20% chance of picking randomly
    so it isn't perfectly predictable.
    """

    best: dict[str, Any] | None = None
    best_score = -1.0

    for move in opponent["moves"]:
        if str(move.get("category", "")).lower() == "status" or int(
            move.get("power") or 0
        ) <= 0:
            score = 0.5  # still occasionally use status moves
        else:
            score = int(move["power"]) * type_effectiveness(
                str(move.get("type", "normal")).lower(),
                target.get("types") or [],
            )

        if score > best_score:
            best_score = score
            best = move

    if best is not None and rng.random() < 0.2:
        best = rng.choice(opponent["moves"])

    return best or opponent["moves"][0]


class BattleError(Exception):
    """Illegal battle action; message is player-facing."""


# ============================================================
# STATE HELPERS
# ============================================================

def public_view(state: dict[str, Any]) -> dict[str, Any]:
    """
    Client-safe view of the battle state: full info for the player's
    own team, only public info for the opponent's (species, level,
    HP fraction — no exact stats).
    """

    def fighter_view(fighter: dict[str, Any], own: bool) -> dict[str, Any]:
        view = {
            "name": fighter["name"],
            "species_id": fighter["species_id"],
            "level": fighter["level"],
            "hp": fighter["hp"],
            "max_hp": fighter["stats"]["hp"],
            "fainted": fighter["hp"] <= 0,
            "types": fighter["types"],
        }

        if own:
            view["pokemon_id"] = fighter.get("pokemon_id")
            view["moves"] = [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "type": m["type"],
                    "category": m["category"],
                    "power": m["power"],
                }
                for m in fighter["moves"]
            ]

        return view

    active = state["active"]

    return {
        "format": state["format"],
        "turn": state["turn"],
        "log": state["log"][-30:],
        "over": state["over"],
        "winner": state["winner"],
        "player_team": [
            fighter_view(f, True) for f in state["teams"]["player"]
        ],
        "opponent_team": [
            fighter_view(f, False) for f in state["teams"]["opponent"]
        ],
        "active_player": active["player"],
        "active_opponent": active["opponent"],
    }
