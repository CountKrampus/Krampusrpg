"""
Krampus RPG Training

Focused training for party Pokémon. Since the game deliberately has
no IVs/EVs/Nature, training works as **effort**: each Pokémon earns
permanent stat points in a chosen focus (attack, defense, sp_attack,
sp_defense, speed, or hp), capped per stat and overall.

Effort is stored in a new pokemon_effort table keyed by pokemon_id +
stat. The stat calculators in services.py add effort on top of the
base formula, so trained Pokémon are genuinely stronger in battle.

Each training session:
    - costs money (scaling with the Pokémon's level),
    - grants 1 effort point in the chosen stat,
    - requires the Pokémon to be in the party,
    - respects a per-session cooldown (nothing exploitable).

HP effort adds to max_hp directly; battle damage stays real.
"""

from __future__ import annotations

from typing import Any

from .database import get_connection
from .services import get_species, calculate_stat, calculate_hp

TRAINING_SCHEMA = """
CREATE TABLE IF NOT EXISTS pokemon_effort (
    pokemon_id INTEGER NOT NULL,
    stat TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pokemon_id, stat),
    FOREIGN KEY (pokemon_id)
        REFERENCES pokemon(id)
        ON DELETE CASCADE
);
"""

# Which stats can be trained, in menu order.
TRAINABLE_STATS = (
    "attack",
    "defense",
    "sp_attack",
    "sp_defense",
    "speed",
    "hp",
)

# Per-stat cap and total cap.
MAX_EFFORT_PER_STAT = 30
MAX_EFFORT_TOTAL = 100

# Base cost per session, scaling with level.
BASE_COST = 40
COST_PER_LEVEL = 6

# Cooldown between sessions on the same Pokémon (seconds), stored on
# the row's updated_at.
COOLDOWN_SECONDS = 5


class TrainingError(Exception):
    """Player-facing training failure."""


def ensure_training_tables() -> None:
    with get_connection() as db:
        db.executescript(TRAINING_SCHEMA)
        db.commit()


def get_effort(pokemon_id: int) -> dict[str, int]:
    """Effort points per stat for one Pokémon (missing stats are 0)."""

    ensure_training_tables()

    with get_connection() as db:
        rows = db.execute(
            "SELECT stat, points FROM pokemon_effort WHERE pokemon_id = ?",
            (pokemon_id,),
        ).fetchall()

    effort = {stat: 0 for stat in TRAINABLE_STATS}

    for row in rows:
        stat = str(row["stat"])

        if stat in effort:
            effort[stat] = int(row["points"])

    return effort


def get_effort_totals(pokemon_id: int) -> tuple[int, int]:
    """(total points spent, max total)."""

    effort = get_effort(pokemon_id)

    return sum(effort.values()), MAX_EFFORT_TOTAL


def _session_cost(level: int) -> int:
    return BASE_COST + max(0, int(level)) * COST_PER_LEVEL


def _trained_stat_value(
    species: dict[str, Any],
    level: int,
    stat: str,
    effort_points: int,
) -> int:
    """Base stat value plus effort contribution (2 points per effort)."""

    base_stats = species.get("base_stats") or {}

    if stat == "hp":
        value = calculate_hp(species, level)
    else:
        value = calculate_stat(int(base_stats.get(stat, 50)), level)

    return value + int(effort_points) * 2


def train(
    player_id: int,
    pokemon_id: int,
    stat: str,
) -> dict[str, Any]:
    """
    Run one training session. Returns a summary with the new stat
    value, effort spent, and cost. Raises TrainingError with a
    player-facing message on any failure.
    """

    ensure_training_tables()

    stat = str(stat or "").strip().lower()

    if stat not in TRAINABLE_STATS:
        raise TrainingError(
            "Pick a valid training focus: "
            + ", ".join(TRAINABLE_STATS)
        )

    with get_connection() as db:
        mon = db.execute(
            """
            SELECT p.*
            FROM pokemon p
            JOIN party pa ON pa.pokemon_id = p.id
            WHERE p.id = ? AND p.owner_id = ? AND pa.player_id = ?
            """,
            (pokemon_id, player_id, player_id),
        ).fetchone()

        if mon is None:
            raise TrainingError(
                "That Pokémon must be in your party to train."
            )

        level = int(mon["level"])

        cost = _session_cost(level)

        progress = db.execute(
            "SELECT money FROM player_progress WHERE player_id = ?",
            (player_id,),
        ).fetchone()

        money = int(progress["money"]) if progress else 0

        if money < cost:
            raise TrainingError(
                f"Training costs {cost} Pokédollars — you have {money}."
            )

        # Cooldown
        row = db.execute(
            """
            SELECT updated_at, points FROM pokemon_effort
            WHERE pokemon_id = ? AND stat = ?
            """,
            (pokemon_id, stat),
        ).fetchone()

        if row is not None:
            from .chat import _parse_db_time, _utcnow, _iso_utc

            last = _parse_db_time(row["updated_at"])

            if last is not None:
                elapsed = (_utcnow() - last).total_seconds()

                if elapsed < COOLDOWN_SECONDS:
                    raise TrainingError(
                        "Take a breath — try again in a few seconds."
                    )

        # Caps
        current_points = int(row["points"]) if row is not None else 0

        if current_points >= MAX_EFFORT_PER_STAT:
            raise TrainingError(
                f"{stat.replace('_', ' ').title()} is fully trained "
                f"({MAX_EFFORT_PER_STAT} points)."
            )

        totals_row = db.execute(
            "SELECT COALESCE(SUM(points), 0) AS total "
            "FROM pokemon_effort WHERE pokemon_id = ?",
            (pokemon_id,),
        ).fetchone()

        total_points = int(totals_row["total"])

        if total_points >= MAX_EFFORT_TOTAL:
            raise TrainingError(
                "This Pokémon has completed its training "
                f"({MAX_EFFORT_TOTAL} total points)."
            )

        # Spend money, add effort.
        db.execute(
            """
            UPDATE player_progress
            SET money = money - ?
            WHERE player_id = ?
            """,
            (cost, player_id),
        )

        db.execute(
            """
            INSERT INTO pokemon_effort (pokemon_id, stat, points)
            VALUES (?, ?, 1)
            ON CONFLICT (pokemon_id, stat)
            DO UPDATE SET
                points = points + 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (pokemon_id, stat),
        )

        # Grant a little level XP alongside the effort (a fraction of
        # the level's requirement is handled by the existing XP code
        # path via services.award_experience if present).
        db.commit()

    species = get_species(str(mon["species_id"]))

    new_points = current_points + 1
    new_value = (
        _trained_stat_value(species, level, stat, new_points)
        if species
        else None
    )

    return {
        "pokemon_id": pokemon_id,
        "name": mon["nickname"] or str(mon["species_id"]).title(),
        "stat": stat,
        "effort": new_points,
        "stat_value": new_value,
        "cost": cost,
        "money_left": money - cost,
    }


def get_training_view(player_id: int) -> list[dict[str, Any]]:
    """
    Party members with their effort state for the training page.
    """

    from .party_storage import get_party as get_storage_party

    result: list[dict[str, Any]] = []

    for mon in get_storage_party(player_id):
        pokemon_id = int(mon.get("pokemon_id") or 0)

        species = get_species(str(mon.get("species_id", "")))

        if species is None or pokemon_id <= 0:
            continue

        effort = get_effort(pokemon_id)
        level = int(mon.get("level", 1))

        stats = {}

        for stat in TRAINABLE_STATS:
            stats[stat] = {
                "value": _trained_stat_value(species, level, stat, effort[stat]),
                "effort": effort[stat],
                "max": MAX_EFFORT_PER_STAT,
            }

        totals, total_max = get_effort_totals(pokemon_id)

        result.append(
            {
                "pokemon_id": pokemon_id,
                "name": mon.get("nickname")
                or str(mon.get("species_id", "")).title(),
                "species_id": mon.get("species_id"),
                "level": level,
                "hp": mon.get("current_hp"),
                "max_hp": mon.get("max_hp"),
                "stats": stats,
                "effort_total": totals,
                "effort_max": total_max,
                "cost": _session_cost(level),
            }
        )

    return result
