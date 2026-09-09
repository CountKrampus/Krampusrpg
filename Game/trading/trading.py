from __future__ import annotations


def validate_trade(
    sender_id: int,
    receiver_id: int,
    pokemon_id: int,
) -> bool:
    if sender_id == receiver_id:
        return False

    if pokemon_id <= 0:
        return False

    return True


# Actual trading transactions should be implemented server-side
# before multiplayer trading is enabled.
