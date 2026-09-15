from __future__ import annotations

import random
from typing import Any

from Server.database import get_connection
from Server.services import get_player
from Game.battles.battle import simulate_turn, calculate_experience_gain


def find_pvp_opponent(
    player_id: int,
    min_level_diff: int = 5,
    max_level_diff: int = 10,
) -> dict[str, Any] | None:
    """
    Find a suitable PvP opponent for a player.

    Args:
        player_id: Player looking for a match
        min_level_diff: Minimum level difference between players
        max_level_diff: Maximum level difference between players

    Returns:
        Opponent player data or None if no suitable opponent found
    """
    with get_connection() as db:
        # Get player's average party level
        player_avg_level = db.execute(
            """
            SELECT AVG(p.level) as avg_level
            FROM pokemon p
            JOIN party pt ON pt.pokemon_id = p.id
            WHERE pt.player_id = ?
            """,
            (player_id,),
        ).fetchone()

        if not player_avg_level or not player_avg_level["avg_level"]:
            return None

        avg_level = int(player_avg_level["avg_level"])

        # Find players with similar level Pokémon
        potential_opponents = db.execute(
            """
            SELECT pl.id, pl.username, pl.display_name,
                   AVG(p.level) as avg_level
            FROM players pl
            JOIN pokemon p ON p.owner_id = pl.id
            JOIN party pt ON pt.pokemon_id = p.id
            WHERE pl.id != ?
              AND pl.id IN (
                  SELECT player_id FROM player_progress
                  WHERE money >= 100  -- Minimum requirement
              )
            GROUP BY pl.id
            HAVING AVG(p.level) BETWEEN ? AND ?
            ORDER BY RANDOM()
            LIMIT 10
            """,
            (player_id, avg_level - min_level_diff, avg_level + max_level_diff),
        ).fetchall()

        if not potential_opponents:
            return None

        # Select random opponent from candidates
        opponent = random.choice(potential_opponents)

        return dict(opponent)


def create_pvp_match(
    player1_id: int,
    player2_id: int,
) -> dict[str, Any]:
    """
    Create a new PvP match between two players.

    Returns:
        Match information with match ID
    """
    with get_connection() as db:
        # Create match record
        match_id = f"pvp_{player1_id}_{player2_id}_{random.randint(1000, 9999)}"

        db.execute(
            """
            INSERT INTO pvp_matches
            (match_id, player1_id, player2_id, status, created_at)
            VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP)
            """,
            (match_id, player1_id, player2_id),
        )

        db.commit()

        return {
            "match_id": match_id,
            "player1_id": player1_id,
            "player2_id": player2_id,
            "status": "active",
        }


def get_pvp_match(match_id: str) -> dict[str, Any] | None:
    """
    Get PvP match information.

    Returns:
        Match data or None if not found
    """
    with get_connection() as db:
        match = db.execute(
            """
            SELECT * FROM pvp_matches WHERE match_id = ?
            """,
            (match_id,),
        ).fetchone()

        return dict(match) if match else None


def validate_pvp_match(
    player_id: int,
    match_id: str,
) -> tuple[bool, str]:
    """
    Validate if a player can participate in a PvP match.

    Returns:
        (is_valid: bool, reason: str)
    """
    match = get_pvp_match(match_id)

    if not match:
        return False, "Match not found"

    if match["status"] != "active":
        return False, f"Match is {match['status']}"

    if match["player1_id"] != player_id and match["player2_id"] != player_id:
        return False, "You are not part of this match"

    return True, "Match is valid"


def get_pvp_party(player_id: int) -> list[dict[str, Any]]:
    """
    Get a player's PvP-ready party.

    Returns:
        List of Pokémon with battle data
    """
    with get_connection() as db:
        pokemon = db.execute(
            """
            SELECT p.*, ps.hp, ps.attack, ps.defense,
                   ps.sp_attack, ps.sp_defense, ps.speed,
                   pt.slot
            FROM pokemon p
            JOIN pokemon_stats ps ON ps.pokemon_id = p.id
            JOIN party pt ON pt.pokemon_id = p.id
            WHERE p.owner_id = ?
            ORDER BY pt.slot
            """,
            (player_id,),
        ).fetchall()

        party = []
        for row in pokemon:
            poke_dict = dict(row)
            poke_dict["stats"] = {
                "hp": row["hp"],
                "attack": row["attack"],
                "defense": row["defense"],
                "sp_attack": row["sp_attack"],
                "sp_defense": row["sp_defense"],
                "speed": row["speed"],
            }
            party.append(poke_dict)

        return party


def execute_pvp_turn(
    match_id: str,
    player_id: int,
    pokemon_id: int,
    move_id: str,
    target_pokemon_id: int,
) -> dict[str, Any]:
    """
    Execute a turn in a PvP battle.

    Returns:
        Turn result with damage and battle state
    """
    is_valid, reason = validate_pvp_match(player_id, match_id)
    if not is_valid:
        return {
            "success": False,
            "reason": reason,
        }

    # Get attacker and defender Pokémon
    with get_connection() as db:
        attacker = db.execute(
            """
            SELECT p.*, ps.hp, ps.attack, ps.defense,
                   ps.sp_attack, ps.sp_defense, ps.speed
            FROM pokemon p
            JOIN pokemon_stats ps ON ps.pokemon_id = p.id
            WHERE p.id = ?
            """,
            (pokemon_id,),
        ).fetchone()

        defender = db.execute(
            """
            SELECT p.*, ps.hp, ps.attack, ps.defense,
                   ps.sp_attack, ps.sp_defense, ps.speed
            FROM pokemon p
            JOIN pokemon_stats ps ON ps.pokemon_id = p.id
            WHERE p.id = ?
            """,
            (target_pokemon_id,),
        ).fetchone()

        if not attacker or not defender:
            return {
                "success": False,
                "reason": "Pokémon not found",
            }

        attacker_dict = dict(attacker)
        defender_dict = dict(defender)

        attacker_dict["stats"] = {
            "hp": attacker["hp"],
            "attack": attacker["attack"],
            "defense": attacker["defense"],
            "sp_attack": attacker["sp_attack"],
            "sp_defense": attacker["sp_defense"],
            "speed": attacker["speed"],
        }

        defender_dict["stats"] = {
            "hp": defender["hp"],
            "attack": defender["attack"],
            "defense": defender["defense"],
            "sp_attack": defender["sp_attack"],
            "sp_defense": defender["sp_defense"],
            "speed": defender["speed"],
        }

        # Simulate the turn
        result = simulate_turn(attacker_dict, defender_dict, move_id)

        # Update defender's HP
        if result["success"]:
            db.execute(
                """
                UPDATE pokemon
                SET current_hp = ?
                WHERE id = ?
                """,
                (result["new_hp"], target_pokemon_id),
            )

            db.commit()

        return result


def end_pvp_match(
    match_id: str,
    winner_id: int,
    loser_id: int,
) -> dict[str, Any]:
    """
    End a PvP match and record the result.

    Args:
        match_id: The match identifier
        winner_id: The winning player's ID
        loser_id: The losing player's ID

    Returns:
        Match result with rewards
    """
    with get_connection() as db:
        # Update match status
        db.execute(
            """
            UPDATE pvp_matches
            SET status = 'completed',
                winner_id = ?,
                loser_id = ?,
                completed_at = CURRENT_TIMESTAMP
            WHERE match_id = ?
            """,
            (winner_id, loser_id, match_id),
        )

        # Calculate rewards
        base_reward = 100
        winner_reward = base_reward * 2
        loser_reward = base_reward // 2

        # Give rewards
        db.execute(
            """
            UPDATE player_progress
            SET money = money + ?
            WHERE player_id = ?
            """,
            (winner_reward, winner_id),
        )

        db.execute(
            """
            UPDATE player_progress
            SET money = money + ?
            WHERE player_id = ?
            """,
            (loser_reward, loser_id),
        )

        # Record in PvP stats
        db.execute(
            """
            INSERT OR REPLACE INTO pvp_stats
            (player_id, wins, losses, total_matches)
            VALUES (
                ?,
                COALESCE((SELECT wins FROM pvp_stats WHERE player_id = ?), 0) + ?,
                COALESCE((SELECT losses FROM pvp_stats WHERE player_id = ?), 0) + ?,
                COALESCE((SELECT total_matches FROM pvp_stats WHERE player_id = ?), 0) + 1
            )
            """,
            (winner_id, winner_id, 1, winner_id, 0, winner_id),
        )

        db.execute(
            """
            INSERT OR REPLACE INTO pvp_stats
            (player_id, wins, losses, total_matches)
            VALUES (
                ?,
                COALESCE((SELECT wins FROM pvp_stats WHERE player_id = ?), 0),
                COALESCE((SELECT losses FROM pvp_stats WHERE player_id = ?), 0) + 1,
                COALESCE((SELECT total_matches FROM pvp_stats WHERE player_id = ?), 0) + 1
            )
            """,
            (loser_id, loser_id, loser_id, loser_id, loser_id),
        )

        db.commit()

        return {
            "success": True,
            "match_id": match_id,
            "winner_id": winner_id,
            "loser_id": loser_id,
            "winner_reward": winner_reward,
            "loser_reward": loser_reward,
        }


def get_pvp_leaderboard(limit: int = 10) -> list[dict[str, Any]]:
    """
    Get the PvP leaderboard.

    Returns:
        List of top players ranked by win rate
    """
    with get_connection() as db:
        leaderboard = db.execute(
            """
            SELECT
                ps.player_id,
                p.username,
                p.display_name,
                ps.wins,
                ps.losses,
                ps.total_matches,
                CASE
                    WHEN ps.total_matches > 0 THEN
                        CAST(ps.wins AS FLOAT) / ps.total_matches
                    ELSE
                        0
                END as win_rate
            FROM pvp_stats ps
            JOIN players p ON p.id = ps.player_id
            WHERE ps.total_matches >= 5
            ORDER BY win_rate DESC, ps.wins DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in leaderboard]


def get_pvp_stats(player_id: int) -> dict[str, Any] | None:
    """
    Get a player's PvP statistics.

    Returns:
        Player's PvP stats or None if no matches played
    """
    with get_connection() as db:
        stats = db.execute(
            """
            SELECT * FROM pvp_stats WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        return dict(stats) if stats else None


__all__ = [
    "find_pvp_opponent",
    "create_pvp_match",
    "get_pvp_match",
    "validate_pvp_match",
    "get_pvp_party",
    "execute_pvp_turn",
    "end_pvp_match",
    "get_pvp_leaderboard",
    "get_pvp_stats",
]
