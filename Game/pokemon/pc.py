from __future__ import annotations

from typing import Any

from Server.pc_storage import (
    MAX_PARTY_SIZE,
    PC_SLOTS_PER_PAGE,
    deposit_pokemon,
    first_empty_slot,
    get_highest_page,
    get_page,
    get_pc_count,
    get_pc_search_filters,
    get_pokemon_location,
    is_in_pc,
    move_pokemon,
    search_pc,
    swap_pokemon,
    withdraw_pokemon,
)


__all__ = [
    "MAX_PARTY_SIZE",
    "PC_SLOTS_PER_PAGE",
    "deposit_pokemon",
    "first_empty_slot",
    "get_highest_page",
    "get_page",
    "get_pc_count",
    "get_pc_search_filters",
    "get_pokemon_location",
    "is_in_pc",
    "move_pokemon",
    "search_pc",
    "swap_pokemon",
    "withdraw_pokemon",
]


def get_pc_page(
    player_id: int,
    page: int = 1,
) -> dict[str, Any]:
    """
    Game-layer wrapper for retrieving a PC page.
    """

    return get_page(
        player_id,
        page,
    )


def find_pc_pokemon(
    player_id: int,
    name: str | None = None,
    variant: str | None = None,
    pokemon_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Game-layer wrapper for searching the player's entire PC.
    """

    return search_pc(
        player_id,
        name=name,
        variant=variant,
        pokemon_type=pokemon_type,
    )


def deposit_to_pc(
    player_id: int,
    pokemon_id: int,
    page: int | None = None,
    slot: int | None = None,
) -> dict[str, Any]:
    """
    Game-layer wrapper for depositing a party Pokémon.
    """

    return deposit_pokemon(
        player_id,
        pokemon_id,
        page=page,
        slot=slot,
    )


def withdraw_from_pc(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    """
    Game-layer wrapper for withdrawing a Pokémon into the party.
    """

    return withdraw_pokemon(
        player_id,
        pokemon_id,
    )


def move_in_pc(
    player_id: int,
    pokemon_id: int,
    page: int,
    slot: int,
) -> dict[str, Any]:
    """
    Game-layer wrapper for moving a Pokémon.
    """

    return move_pokemon(
        player_id,
        pokemon_id,
        page,
        slot,
    )


def swap_in_pc(
    player_id: int,
    pokemon_id_a: int,
    pokemon_id_b: int,
) -> bool:
    """
    Game-layer wrapper for swapping two PC Pokémon.
    """

    return swap_pokemon(
        player_id,
        pokemon_id_a,
        pokemon_id_b,
    )