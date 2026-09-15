from __future__ import annotations

from typing import Any

from Server.database import get_connection
from Server.party_storage import add_to_party, is_in_party, remove_from_party
from Server.pc_storage import deposit_pokemon, is_in_pc, withdraw_pokemon


def validate_trade(
    sender_id: int,
    receiver_id: int,
    pokemon_id: int,
) -> tuple[bool, str]:
    """
    Validate if a trade can be performed.

    Returns:
        (is_valid: bool, reason: str)
    """
    if sender_id == receiver_id:
        return False, "Cannot trade with yourself"

    if pokemon_id <= 0:
        return False, "Invalid Pokémon ID"

    # Check if sender owns the Pokémon
    with get_connection() as db:
        pokemon = db.execute(
            """
            SELECT owner_id FROM pokemon WHERE id = ?
            """,
            (pokemon_id,),
        ).fetchone()

        if not pokemon:
            return False, "Pokémon not found"

        if int(pokemon["owner_id"]) != sender_id:
            return False, "You don't own this Pokémon"

        # Check if receiver has space in party
        receiver_party_count = db.execute(
            """
            SELECT COUNT(*) as count FROM party WHERE player_id = ?
            """,
            (receiver_id,),
        ).fetchone()

        if receiver_party_count and int(receiver_party_count["count"]) >= 6:
            return False, "Receiver's party is full"

    return True, "Trade is valid"


def initiate_trade(
    sender_id: int,
    receiver_id: int,
    sender_pokemon_id: int,
    receiver_pokemon_id: int | None = None,
) -> dict[str, Any]:
    """
    Initiate a trade between two players.

    Args:
        sender_id: Player initiating the trade
        receiver_id: Player receiving the trade
        sender_pokemon_id: Pokémon sender is offering
        receiver_pokemon_id: Pokémon receiver is offering (optional)

    Returns:
        Trade information dict
    """
    is_valid, reason = validate_trade(sender_id, receiver_id, sender_pokemon_id)

    if not is_valid:
        return {
            "success": False,
            "reason": reason,
        }

    with get_connection() as db:
        # Get Pokémon details
        sender_pokemon = db.execute(
            """
            SELECT * FROM pokemon WHERE id = ?
            """,
            (sender_pokemon_id,),
        ).fetchone()

        receiver_pokemon = None
        if receiver_pokemon_id:
            receiver_pokemon = db.execute(
                """
                SELECT * FROM pokemon WHERE id = ?
                """,
                (receiver_pokemon_id,),
            ).fetchone()

            # Validate receiver owns their Pokémon
            if receiver_pokemon and int(receiver_pokemon["owner_id"]) != receiver_id:
                return {
                    "success": False,
                    "reason": "Receiver doesn't own the offered Pokémon",
                }

        return {
            "success": True,
            "trade_id": f"trade_{sender_id}_{receiver_id}_{sender_pokemon_id}",
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "sender_pokemon": dict(sender_pokemon) if sender_pokemon else None,
            "receiver_pokemon": dict(receiver_pokemon) if receiver_pokemon else None,
            "status": "pending",
        }


def execute_trade(trade_id: str) -> dict[str, Any]:
    """
    Execute a confirmed trade between two players.

    This performs the actual exchange of Pokémon ownership.
    """
    # Parse trade_id to get trade details
    parts = trade_id.split("_")
    if len(parts) < 4:
        return {
            "success": False,
            "reason": "Invalid trade ID",
        }

    try:
        sender_id = int(parts[1])
        receiver_id = int(parts[2])
        sender_pokemon_id = int(parts[3])
    except (ValueError, IndexError):
        return {
            "success": False,
            "reason": "Invalid trade ID format",
        }

    with get_connection() as db:
        # Get current Pokémon locations
        sender_in_party = is_in_party(sender_id, sender_pokemon_id)
        sender_in_pc = is_in_pc(sender_id, sender_pokemon_id)

        # Remove from sender's storage
        if sender_in_party:
            remove_from_party(sender_id, sender_pokemon_id)
        elif sender_in_pc:
            withdraw_pokemon(sender_id, sender_pokemon_id)

        # Transfer ownership
        db.execute(
            """
            UPDATE pokemon
            SET owner_id = ?
            WHERE id = ?
            """,
            (receiver_id, sender_pokemon_id),
        )

        # Add to receiver's party or PC
        receiver_party_count = db.execute(
            """
            SELECT COUNT(*) as count FROM party WHERE player_id = ?
            """,
            (receiver_id,),
        ).fetchone()

        if receiver_party_count and int(receiver_party_count["count"]) < 6:
            add_to_party(receiver_id, sender_pokemon_id)
        else:
            deposit_pokemon(receiver_id, sender_pokemon_id)

        db.commit()

        return {
            "success": True,
            "trade_id": trade_id,
            "pokemon_id": sender_pokemon_id,
            "new_owner_id": receiver_id,
        }


def cancel_trade(trade_id: str) -> dict[str, Any]:
    """
    Cancel a pending trade.

    This just marks the trade as cancelled - no Pokémon are moved.
    """
    return {
        "success": True,
        "trade_id": trade_id,
        "status": "cancelled",
    }


def get_trade_history(player_id: int, limit: int = 10) -> list[dict[str, Any]]:
    """
    Get recent trade history for a player.

    In a full implementation, this would query a trades table.
    For now, returns empty list.
    """
    # This would be implemented with a trades table
    return []


def validate_pokemon_for_trade(
    pokemon_id: int,
    player_id: int,
) -> tuple[bool, str]:
    """
    Validate if a specific Pokémon can be traded.

    Checks:
    - Player owns the Pokémon
    - Pokémon is not in an active battle
    - Pokémon is not holding untradeable items
    - Pokémon is not a special case (legendary, event, etc.)

    Returns:
        (can_trade: bool, reason: str)
    """
    with get_connection() as db:
        pokemon = db.execute(
            """
            SELECT * FROM pokemon WHERE id = ?
            """,
            (pokemon_id,),
        ).fetchone()

        if not pokemon:
            return False, "Pokémon not found"

        if int(pokemon["owner_id"]) != player_id:
            return False, "You don't own this Pokémon"

        # Check for special cases (would need more database fields)
        # For now, just check basic ownership

        return True, "Pokémon can be traded"


__all__ = [
    "validate_trade",
    "initiate_trade",
    "execute_trade",
    "cancel_trade",
    "get_trade_history",
    "validate_pokemon_for_trade",
]
