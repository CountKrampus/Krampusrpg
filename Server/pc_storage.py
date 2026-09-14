from __future__ import annotations

import sqlite3
from typing import Any

from .database import (
    MAX_PARTY_SIZE,
    PC_SLOTS_PER_PAGE,
    ensure_pc_schema,
    get_connection,
)


# =============================================================================
# CONSTANTS
# =============================================================================

SLOTS_PER_PAGE = PC_SLOTS_PER_PAGE


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _row_to_dict(
    row: sqlite3.Row | None,
) -> dict[str, Any] | None:
    if row is None:
        return None

    return dict(row)


def _pokemon_exists(
    db: sqlite3.Connection,
    pokemon_id: int,
) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT
            id,
            owner_id,
            unique_id,
            species_id,
            nickname,
            level,
            experience,
            gender,
            shiny,
            variant,
            current_hp,
            max_hp,
            created_at
        FROM pokemon
        WHERE id = ?
        LIMIT 1
        """,
        (pokemon_id,),
    ).fetchone()


def _pokemon_in_party(
    db: sqlite3.Connection,
    pokemon_id: int,
) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT
            id,
            player_id,
            pokemon_id,
            slot
        FROM party
        WHERE pokemon_id = ?
        LIMIT 1
        """,
        (pokemon_id,),
    ).fetchone()


def _pokemon_in_pc(
    db: sqlite3.Connection,
    pokemon_id: int,
    player_id: int | None = None,
) -> sqlite3.Row | None:
    if player_id is None:
        return db.execute(
            """
            SELECT
                id,
                player_id,
                pokemon_id,
                page,
                slot
            FROM pc_storage
            WHERE pokemon_id = ?
            LIMIT 1
            """,
            (pokemon_id,),
        ).fetchone()

    return db.execute(
        """
        SELECT
            id,
            player_id,
            pokemon_id,
            page,
            slot
        FROM pc_storage
        WHERE pokemon_id = ?
          AND player_id = ?
        LIMIT 1
        """,
        (
            pokemon_id,
            player_id,
        ),
    ).fetchone()


def _player_owns_pokemon(
    pokemon: sqlite3.Row | None,
    player_id: int,
) -> bool:
    if pokemon is None:
        return False

    return int(pokemon["owner_id"]) == int(player_id)


def _normalize_page(
    page: int | str | None,
) -> int:
    try:
        value = int(page or 1)
    except (TypeError, ValueError):
        value = 1

    return max(1, value)


def _normalize_slot(
    slot: int | str | None,
) -> int | None:
    try:
        value = int(slot)
    except (TypeError, ValueError):
        return None

    if not 1 <= value <= SLOTS_PER_PAGE:
        return None

    return value


def _next_empty_slot(
    db: sqlite3.Connection,
    player_id: int,
    page: int,
) -> int | None:
    rows = db.execute(
        """
        SELECT slot
        FROM pc_storage
        WHERE player_id = ?
          AND page = ?
        ORDER BY slot
        """,
        (
            player_id,
            page,
        ),
    ).fetchall()

    occupied = {
        int(row["slot"])
        for row in rows
    }

    for slot in range(1, SLOTS_PER_PAGE + 1):
        if slot not in occupied:
            return slot

    return None


def _first_empty_position(
    db: sqlite3.Connection,
    player_id: int,
    start_page: int = 1,
) -> tuple[int, int]:
    rows = db.execute(
        """
        SELECT
            page,
            slot
        FROM pc_storage
        WHERE player_id = ?
        ORDER BY page, slot
        """,
        (player_id,),
    ).fetchall()

    occupied = {
        (
            int(row["page"]),
            int(row["slot"]),
        )
        for row in rows
    }

    page = max(1, int(start_page))

    while True:
        for slot in range(1, SLOTS_PER_PAGE + 1):
            if (page, slot) not in occupied:
                return page, slot

        page += 1


def _party_count(
    db: sqlite3.Connection,
    player_id: int,
) -> int:
    row = db.execute(
        """
        SELECT COUNT(*) AS count
        FROM party
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()

    return int(row["count"] or 0)


def _next_party_slot(
    db: sqlite3.Connection,
    player_id: int,
) -> int | None:
    rows = db.execute(
        """
        SELECT slot
        FROM party
        WHERE player_id = ?
        ORDER BY slot
        """,
        (player_id,),
    ).fetchall()

    occupied = {
        int(row["slot"])
        for row in rows
    }

    for slot in range(1, MAX_PARTY_SIZE + 1):
        if slot not in occupied:
            return slot

    return None


def _location_from_connection(
    db: sqlite3.Connection,
    pokemon_id: int,
) -> dict[str, Any]:
    party = db.execute(
        """
        SELECT
            player_id,
            slot
        FROM party
        WHERE pokemon_id = ?
        LIMIT 1
        """,
        (pokemon_id,),
    ).fetchone()

    if party is not None:
        return {
            "pokemon_id": pokemon_id,
            "location": "party",
            "player_id": int(party["player_id"]),
            "slot": int(party["slot"]),
        }

    pc = db.execute(
        """
        SELECT
            player_id,
            page,
            slot
        FROM pc_storage
        WHERE pokemon_id = ?
        LIMIT 1
        """,
        (pokemon_id,),
    ).fetchone()

    if pc is not None:
        return {
            "pokemon_id": pokemon_id,
            "location": "pc",
            "player_id": int(pc["player_id"]),
            "page": int(pc["page"]),
            "slot": int(pc["slot"]),
        }

    pokemon = _pokemon_exists(
        db,
        pokemon_id,
    )

    if pokemon is not None:
        return {
            "pokemon_id": pokemon_id,
            "location": "unassigned",
            "player_id": int(pokemon["owner_id"]),
        }

    return {
        "pokemon_id": pokemon_id,
        "location": "not_found",
    }


def _slot_is_occupied(
    db: sqlite3.Connection,
    player_id: int,
    page: int,
    slot: int,
) -> bool:
    row = db.execute(
        """
        SELECT 1
        FROM pc_storage
        WHERE player_id = ?
          AND page = ?
          AND slot = ?
        LIMIT 1
        """,
        (
            player_id,
            page,
            slot,
        ),
    ).fetchone()

    return row is not None


# =============================================================================
# SCHEMA
# =============================================================================

def initialize_pc() -> None:
    """
    Ensure the database-backed PC table exists.
    """
    ensure_pc_schema()


def ensure_schema() -> None:
    """
    Compatibility alias for PC schema initialization.
    """
    initialize_pc()


# =============================================================================
# FIRST EMPTY SLOT
# =============================================================================

def first_empty_slot(
    player_id: int,
    page: int | None = None,
) -> tuple[int, int]:
    """
    Return the first available PC page and slot.

    When page is supplied, that page is preferred. If it is full,
    the next page is returned.
    """
    with get_connection() as db:
        ensure_pc_schema(db)

        if page is not None:
            normalized_page = _normalize_page(page)

            slot = _next_empty_slot(
                db,
                player_id,
                normalized_page,
            )

            if slot is not None:
                return normalized_page, slot

            return _first_empty_position(
                db,
                player_id,
                normalized_page + 1,
            )

        return _first_empty_position(
            db,
            player_id,
        )


# =============================================================================
# DEPOSIT
# =============================================================================

def deposit_pokemon(
    player_id: int,
    pokemon_id: int,
    page: int | None = None,
    slot: int | None = None,
) -> dict[str, Any]:
    """
    Put an owned, currently unassigned Pokémon into PC storage.

    A Pokémon already in the Party must first be removed from the Party.
    Party removal itself can automatically transfer the Pokémon to the PC.
    """
    with get_connection() as db:
        ensure_pc_schema(db)

        pokemon = _pokemon_exists(
            db,
            pokemon_id,
        )

        if pokemon is None:
            raise ValueError(
                "Pokémon does not exist."
            )

        if not _player_owns_pokemon(
            pokemon,
            player_id,
        ):
            raise PermissionError(
                "You do not own this Pokémon."
            )

        existing_pc = _pokemon_in_pc(
            db,
            pokemon_id,
        )

        if existing_pc is not None:
            if int(existing_pc["player_id"]) != int(player_id):
                raise PermissionError(
                    "This Pokémon belongs to another player."
                )

            return _location_from_connection(
                db,
                pokemon_id,
            )

        existing_party = _pokemon_in_party(
            db,
            pokemon_id,
        )

        if existing_party is not None:
            raise ValueError(
                "A Pokémon cannot be deposited while it is in the Party. "
                "Remove it from the Party first."
            )

        if page is None and slot is None:
            target_page, target_slot = _first_empty_position(
                db,
                player_id,
            )

        elif page is None:
            target_slot = _normalize_slot(slot)

            if target_slot is None:
                raise ValueError(
                    f"PC slot must be between 1 and {SLOTS_PER_PAGE}."
                )

            target_page = 1

            while _slot_is_occupied(
                db,
                player_id,
                target_page,
                target_slot,
            ):
                target_page += 1

        elif slot is None:
            target_page = _normalize_page(page)

            target_slot = _next_empty_slot(
                db,
                player_id,
                target_page,
            )

            if target_slot is None:
                target_page, target_slot = _first_empty_position(
                    db,
                    player_id,
                    target_page + 1,
                )

        else:
            target_page = _normalize_page(page)
            target_slot = _normalize_slot(slot)

            if target_slot is None:
                raise ValueError(
                    f"PC slot must be between 1 and {SLOTS_PER_PAGE}."
                )

        if _slot_is_occupied(
            db,
            player_id,
            target_page,
            target_slot,
        ):
            raise ValueError(
                "That PC slot is already occupied."
            )

        db.execute(
            """
            INSERT INTO pc_storage (
                player_id,
                pokemon_id,
                page,
                slot
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                player_id,
                pokemon_id,
                target_page,
                target_slot,
            ),
        )

        db.commit()

        return _location_from_connection(
            db,
            pokemon_id,
        )


# =============================================================================
# WITHDRAW
# =============================================================================

def withdraw_pokemon(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    """
    Withdraw a Pokémon from PC storage into the Party.

    This operation is atomic:
        PC record is removed
        Party record is created

    If the Party is full, nothing is changed.
    """
    with get_connection() as db:
        ensure_pc_schema(db)

        pokemon = _pokemon_exists(
            db,
            pokemon_id,
        )

        if pokemon is None:
            raise ValueError(
                "Pokémon does not exist."
            )

        if not _player_owns_pokemon(
            pokemon,
            player_id,
        ):
            raise PermissionError(
                "You do not own this Pokémon."
            )

        pc_record = _pokemon_in_pc(
            db,
            pokemon_id,
            player_id,
        )

        if pc_record is None:
            raise ValueError(
                "That Pokémon is not in the PC."
            )

        party_record = _pokemon_in_party(
            db,
            pokemon_id,
        )

        if party_record is not None:
            raise ValueError(
                "That Pokémon is already in the Party."
            )

        current_party_count = _party_count(
            db,
            player_id,
        )

        if current_party_count >= MAX_PARTY_SIZE:
            raise ValueError(
                f"Your Party is full. Maximum size is {MAX_PARTY_SIZE}."
            )

        party_slot = _next_party_slot(
            db,
            player_id,
        )

        if party_slot is None:
            raise ValueError(
                f"Your Party is full. Maximum size is {MAX_PARTY_SIZE}."
            )

        db.execute(
            """
            DELETE FROM pc_storage
            WHERE id = ?
              AND player_id = ?
              AND pokemon_id = ?
            """,
            (
                int(pc_record["id"]),
                player_id,
                pokemon_id,
            ),
        )

        if db.total_changes <= 0:
            raise RuntimeError(
                "The PC record could not be removed."
            )

        db.execute(
            """
            INSERT INTO party (
                player_id,
                pokemon_id,
                slot
            )
            VALUES (?, ?, ?)
            """,
            (
                player_id,
                pokemon_id,
                party_slot,
            ),
        )

        db.commit()

        return {
            "success": True,
            "pokemon_id": pokemon_id,
            "location": "party",
            "player_id": player_id,
            "slot": party_slot,
        }


# =============================================================================
# MOVE
# =============================================================================

def move_pokemon(
    player_id: int,
    pokemon_id: int,
    target_page: int,
    target_slot: int,
) -> dict[str, Any]:
    """
    Move a Pokémon to an empty PC position.
    """
    target_page = _normalize_page(target_page)
    target_slot = _normalize_slot(target_slot)

    if target_slot is None:
        raise ValueError(
            f"PC slot must be between 1 and {SLOTS_PER_PAGE}."
        )

    with get_connection() as db:
        ensure_pc_schema(db)

        source = _pokemon_in_pc(
            db,
            pokemon_id,
            player_id,
        )

        if source is None:
            raise ValueError(
                "That Pokémon is not in the PC."
            )

        if (
            int(source["page"]) == target_page
            and int(source["slot"]) == target_slot
        ):
            return {
                "success": True,
                "action": "none",
                "pokemon_id": pokemon_id,
                "location": _location_from_connection(
                    db,
                    pokemon_id,
                ),
            }

        occupied = db.execute(
            """
            SELECT
                id,
                pokemon_id
            FROM pc_storage
            WHERE player_id = ?
              AND page = ?
              AND slot = ?
            LIMIT 1
            """,
            (
                player_id,
                target_page,
                target_slot,
            ),
        ).fetchone()

        if occupied is not None:
            raise ValueError(
                "That PC slot is already occupied."
            )

        db.execute(
            """
            UPDATE pc_storage
            SET
                page = ?,
                slot = ?
            WHERE id = ?
              AND player_id = ?
            """,
            (
                target_page,
                target_slot,
                int(source["id"]),
                player_id,
            ),
        )

        db.commit()

        return {
            "success": True,
            "action": "move",
            "pokemon_id": pokemon_id,
            "location": _location_from_connection(
                db,
                pokemon_id,
            ),
        }


# =============================================================================
# SWAP
# =============================================================================

def swap_pokemon(
    player_id: int,
    pokemon_id: int,
    target_page: int,
    target_slot: int,
) -> dict[str, Any]:
    """
    Move one Pokémon into a target PC position.

    If the target is occupied, the two Pokémon are swapped atomically.
    """
    target_page = _normalize_page(target_page)
    target_slot = _normalize_slot(target_slot)

    if target_slot is None:
        raise ValueError(
            f"PC slot must be between 1 and {SLOTS_PER_PAGE}."
        )

    with get_connection() as db:
        ensure_pc_schema(db)

        source = _pokemon_in_pc(
            db,
            pokemon_id,
            player_id,
        )

        if source is None:
            raise ValueError(
                "That Pokémon is not in the PC."
            )

        source_page = int(source["page"])
        source_slot = int(source["slot"])
        source_storage_id = int(source["id"])

        if (
            source_page == target_page
            and source_slot == target_slot
        ):
            return {
                "success": True,
                "action": "none",
                "pokemon_id": pokemon_id,
                "location": _location_from_connection(
                    db,
                    pokemon_id,
                ),
            }

        target = db.execute(
            """
            SELECT
                id,
                pokemon_id,
                page,
                slot
            FROM pc_storage
            WHERE player_id = ?
              AND page = ?
              AND slot = ?
            LIMIT 1
            """,
            (
                player_id,
                target_page,
                target_slot,
            ),
        ).fetchone()

        if target is None:
            db.execute(
                """
                UPDATE pc_storage
                SET
                    page = ?,
                    slot = ?
                WHERE id = ?
                  AND player_id = ?
                """,
                (
                    target_page,
                    target_slot,
                    source_storage_id,
                    player_id,
                ),
            )

            db.commit()

            return {
                "success": True,
                "action": "move",
                "pokemon_id": pokemon_id,
                "location": _location_from_connection(
                    db,
                    pokemon_id,
                ),
            }

        target_storage_id = int(target["id"])
        target_pokemon_id = int(target["pokemon_id"])

        temporary_page, temporary_slot = _first_empty_position(
            db,
            player_id,
        )

        while (
            temporary_page == target_page
            and temporary_slot == target_slot
        ) or (
            temporary_page == source_page
            and temporary_slot == source_slot
        ):
            temporary_page, temporary_slot = _first_empty_position(
                db,
                player_id,
                temporary_page + 1,
            )

        # Move source to a temporary free location.
        db.execute(
            """
            UPDATE pc_storage
            SET
                page = ?,
                slot = ?
            WHERE id = ?
              AND player_id = ?
            """,
            (
                temporary_page,
                temporary_slot,
                source_storage_id,
                player_id,
            ),
        )

        # Move target into source's original position.
        db.execute(
            """
            UPDATE pc_storage
            SET
                page = ?,
                slot = ?
            WHERE id = ?
              AND player_id = ?
            """,
            (
                source_page,
                source_slot,
                target_storage_id,
                player_id,
            ),
        )

        # Move source into target position.
        db.execute(
            """
            UPDATE pc_storage
            SET
                page = ?,
                slot = ?
            WHERE id = ?
              AND player_id = ?
            """,
            (
                target_page,
                target_slot,
                source_storage_id,
                player_id,
            ),
        )

        db.commit()

        return {
            "success": True,
            "action": "swap",
            "pokemon_id": pokemon_id,
            "swapped_with": target_pokemon_id,
            "location": _location_from_connection(
                db,
                pokemon_id,
            ),
        }


# =============================================================================
# PAGE
# =============================================================================

def get_page(
    player_id: int,
    page: int = 1,
) -> dict[str, Any]:
    """
    Return one complete PC page.

    The returned slots list always contains exactly 30 entries.
    Empty positions contain None.
    """
    page = _normalize_page(page)

    with get_connection() as db:
        ensure_pc_schema(db)

        rows = db.execute(
            """
            SELECT
                pc.id AS storage_id,
                pc.player_id,
                pc.pokemon_id,
                pc.page,
                pc.slot,
                p.unique_id,
                p.species_id,
                p.nickname,
                p.level,
                p.experience,
                p.gender,
                p.shiny,
                p.variant,
                p.current_hp,
                p.max_hp,
                p.created_at
            FROM pc_storage pc
            INNER JOIN pokemon p
                ON p.id = pc.pokemon_id
            WHERE pc.player_id = ?
              AND pc.page = ?
            ORDER BY pc.slot
            """,
            (
                player_id,
                page,
            ),
        ).fetchall()

        slots: list[dict[str, Any] | None] = [
            None
            for _ in range(SLOTS_PER_PAGE)
        ]

        for row in rows:
            data = dict(row)
            slot = int(data["slot"])

            if 1 <= slot <= SLOTS_PER_PAGE:
                slots[slot - 1] = data

        count_row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pc_storage
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        total_count = int(
            count_row["count"] or 0
        )

        max_page_row = db.execute(
            """
            SELECT MAX(page) AS max_page
            FROM pc_storage
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        max_page = max(
            1,
            int(
                max_page_row["max_page"] or 1
            ),
        )

        return {
            "page": page,
            "max_page": max_page,
            "page_count": max_page,
            "total_count": total_count,
            "slots_per_page": SLOTS_PER_PAGE,
            "pokemon": slots,
            "slots": slots,
        }


# =============================================================================
# GET PC POKÉMON
# =============================================================================

def get_pc_pokemon(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any] | None:
    with get_connection() as db:
        ensure_pc_schema(db)

        row = db.execute(
            """
            SELECT
                pc.id AS storage_id,
                pc.player_id,
                pc.pokemon_id,
                pc.page,
                pc.slot,
                p.unique_id,
                p.species_id,
                p.nickname,
                p.level,
                p.experience,
                p.gender,
                p.shiny,
                p.variant,
                p.current_hp,
                p.max_hp,
                p.created_at
            FROM pc_storage pc
            INNER JOIN pokemon p
                ON p.id = pc.pokemon_id
            WHERE pc.player_id = ?
              AND pc.pokemon_id = ?
            LIMIT 1
            """,
            (
                player_id,
                pokemon_id,
            ),
        ).fetchone()

        return _row_to_dict(row)


def get_pokemon(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any] | None:
    return get_pc_pokemon(
        player_id,
        pokemon_id,
    )


# =============================================================================
# SEARCH
# =============================================================================

def search_pc(
    player_id: int,
    search: str | None = None,
    variant: str | None = None,
    pokemon_type: str | None = None,
    type_name: str | None = None,
    shiny: bool | None = None,
) -> list[dict[str, Any]]:
    """
    Search the player's entire PC.

    Supported filters:
        name / nickname
        species
        unique Pokémon ID
        variant
        type
        shiny

    Filters can be combined.
    """
    if pokemon_type is None:
        pokemon_type = type_name

    search_text = (
        str(search).strip()
        if search is not None
        else ""
    )

    variant_text = (
        str(variant).strip()
        if variant is not None
        else ""
    )

    type_text = (
        str(pokemon_type).strip()
        if pokemon_type is not None
        else ""
    )

    with get_connection() as db:
        ensure_pc_schema(db)

        tables = {
            str(row["name"])
            for row in db.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        has_species_types = (
            "pokemon_species_types" in tables
        )

        has_pokemon_types = (
            "pokemon_types" in tables
        )

        query = """
            SELECT DISTINCT
                pc.id AS storage_id,
                pc.player_id,
                pc.pokemon_id,
                pc.page,
                pc.slot,
                p.unique_id,
                p.species_id,
                p.nickname,
                p.level,
                p.experience,
                p.gender,
                p.shiny,
                p.variant,
                p.current_hp,
                p.max_hp,
                p.created_at
            FROM pc_storage pc
            INNER JOIN pokemon p
                ON p.id = pc.pokemon_id
        """

        parameters: list[Any] = [
            player_id
        ]

        if (
            type_text
            and has_species_types
            and has_pokemon_types
        ):
            query += """
                INNER JOIN pokemon_species_types pst
                    ON pst.species_id = p.species_id
                INNER JOIN pokemon_types pt
                    ON pt.id = pst.type_id
            """

        query += """
            WHERE pc.player_id = ?
        """

        if search_text:
            wildcard = f"%{search_text}%"

            query += """
                AND (
                    LOWER(
                        COALESCE(p.nickname, '')
                    ) LIKE LOWER(?)
                    OR LOWER(
                        COALESCE(p.species_id, '')
                    ) LIKE LOWER(?)
                    OR LOWER(
                        COALESCE(p.unique_id, '')
                    ) LIKE LOWER(?)
                )
            """

            parameters.extend(
                [
                    wildcard,
                    wildcard,
                    wildcard,
                ]
            )

        if variant_text:
            query += """
                AND LOWER(
                    COALESCE(p.variant, '')
                ) = LOWER(?)
            """

            parameters.append(
                variant_text
            )

        if (
            type_text
            and has_species_types
            and has_pokemon_types
        ):
            query += """
                AND LOWER(
                    COALESCE(pt.name, '')
                ) = LOWER(?)
            """

            parameters.append(
                type_text
            )

        if shiny is not None:
            query += """
                AND p.shiny = ?
            """

            parameters.append(
                1 if shiny else 0
            )

        query += """
            ORDER BY
                pc.page,
                pc.slot,
                p.id
        """

        rows = db.execute(
            query,
            parameters,
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def search_pokemon(
    player_id: int,
    search: str | None = None,
    variant: str | None = None,
    pokemon_type: str | None = None,
    shiny: bool | None = None,
) -> list[dict[str, Any]]:
    return search_pc(
        player_id=player_id,
        search=search,
        variant=variant,
        pokemon_type=pokemon_type,
        shiny=shiny,
    )


# =============================================================================
# COUNTS
# =============================================================================

def get_pc_count(
    player_id: int,
) -> int:
    with get_connection() as db:
        ensure_pc_schema(db)

        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pc_storage
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        return int(
            row["count"] or 0
        )


def get_pc_page_count(
    player_id: int,
) -> int:
    with get_connection() as db:
        ensure_pc_schema(db)

        row = db.execute(
            """
            SELECT MAX(page) AS max_page
            FROM pc_storage
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        return max(
            1,
            int(
                row["max_page"] or 1
            ),
        )


def get_page_count(
    player_id: int,
) -> int:
    return get_pc_page_count(
        player_id
    )


# =============================================================================
# FILTER DATA
# =============================================================================

def get_pc_search_filters(
    player_id: int,
) -> dict[str, list[str]]:
    with get_connection() as db:
        ensure_pc_schema(db)

        variant_rows = db.execute(
            """
            SELECT DISTINCT
                p.variant
            FROM pokemon p
            INNER JOIN pc_storage pc
                ON pc.pokemon_id = p.id
            WHERE pc.player_id = ?
              AND COALESCE(
                    TRIM(p.variant),
                    ''
                  ) != ''
            ORDER BY p.variant
            """,
            (player_id,),
        ).fetchall()

        variants = [
            str(row["variant"])
            for row in variant_rows
            if row["variant"]
        ]

        tables = {
            str(row["name"])
            for row in db.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        types: list[str] = []

        if (
            "pokemon_species_types" in tables
            and "pokemon_types" in tables
        ):
            type_rows = db.execute(
                """
                SELECT DISTINCT
                    pt.name
                FROM pokemon_types pt
                INNER JOIN pokemon_species_types pst
                    ON pst.type_id = pt.id
                INNER JOIN pokemon p
                    ON p.species_id = pst.species_id
                INNER JOIN pc_storage pc
                    ON pc.pokemon_id = p.id
                WHERE pc.player_id = ?
                ORDER BY pt.name
                """,
                (player_id,),
            ).fetchall()

            types = [
                str(row["name"])
                for row in type_rows
                if row["name"]
            ]

        return {
            "variants": variants,
            "types": types,
        }


def get_search_filters(
    player_id: int,
) -> dict[str, list[str]]:
    return get_pc_search_filters(
        player_id
    )


def is_in_pc(
    player_id: int,
    pokemon_id: int,
) -> bool:
    """Check if a Pokémon is in the player's PC storage."""
    with get_connection() as db:
        ensure_pc_schema(db)
        row = _pokemon_in_pc(
            db,
            pokemon_id,
            player_id,
        )
        return row is not None


# =============================================================================
# LOCATION
# =============================================================================

def get_pokemon_location(
    pokemon_id: int,
) -> dict[str, Any]:
    with get_connection() as db:
        ensure_pc_schema(db)

        return _location_from_connection(
            db,
            pokemon_id,
        )


def get_player_pokemon_location(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    with get_connection() as db:
        ensure_pc_schema(db)

        pokemon = _pokemon_exists(
            db,
            pokemon_id,
        )

        if pokemon is None:
            return {
                "pokemon_id": pokemon_id,
                "location": "not_found",
            }

        if not _player_owns_pokemon(
            pokemon,
            player_id,
        ):
            return {
                "pokemon_id": pokemon_id,
                "location": "not_owned",
            }

        location = _location_from_connection(
            db,
            pokemon_id,
        )

        if (
            location.get("player_id") is not None
            and int(location["player_id"]) != int(player_id)
        ):
            return {
                "pokemon_id": pokemon_id,
                "location": "not_owned",
            }

        return location


# =============================================================================
# ALL PC POKÉMON
# =============================================================================

def get_all_pc_pokemon(
    player_id: int,
) -> list[dict[str, Any]]:
    with get_connection() as db:
        ensure_pc_schema(db)

        rows = db.execute(
            """
            SELECT
                pc.id AS storage_id,
                pc.player_id,
                pc.pokemon_id,
                pc.page,
                pc.slot,
                p.unique_id,
                p.species_id,
                p.nickname,
                p.level,
                p.experience,
                p.gender,
                p.shiny,
                p.variant,
                p.current_hp,
                p.max_hp,
                p.created_at
            FROM pc_storage pc
            INNER JOIN pokemon p
                ON p.id = pc.pokemon_id
            WHERE pc.player_id = ?
            ORDER BY
                pc.page,
                pc.slot
            """,
            (player_id,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]


# =============================================================================
# LEGACY COMPATIBILITY ALIASES
# =============================================================================

def add_to_pc(
    player_id: int,
    pokemon_id: int,
    page: int | None = None,
    slot: int | None = None,
) -> dict[str, Any]:
    return deposit_pokemon(
        player_id,
        pokemon_id,
        page,
        slot,
    )


def remove_from_pc(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    return withdraw_pokemon(
        player_id,
        pokemon_id,
    )


def move_pc_pokemon(
    player_id: int,
    pokemon_id: int,
    target_page: int,
    target_slot: int,
) -> dict[str, Any]:
    return move_pokemon(
        player_id,
        pokemon_id,
        target_page,
        target_slot,
    )


# =============================================================================
# STORAGE REPAIR
# =============================================================================

def repair_pc_storage(
    player_id: int | None = None,
) -> dict[str, int]:
    """
    Repair PC storage so every owned Pokémon has exactly one location.

    Party takes precedence when a Pokémon exists in both Party and PC.

    Any owned Pokémon that has neither location is placed into the PC.
    """
    repaired = 0
    conflicts_removed = 0

    with get_connection() as db:
        ensure_pc_schema(db)

        # ---------------------------------------------------------------------
        # Remove PC duplicates of Pokémon already in the Party.
        # ---------------------------------------------------------------------

        if player_id is None:
            deleted = db.execute(
                """
                DELETE FROM pc_storage
                WHERE pokemon_id IN (
                    SELECT pokemon_id
                    FROM party
                )
                """
            )
        else:
            deleted = db.execute(
                """
                DELETE FROM pc_storage
                WHERE player_id = ?
                  AND pokemon_id IN (
                      SELECT pokemon_id
                      FROM party
                  )
                """,
                (player_id,),
            )

        conflicts_removed += max(
            0,
            int(deleted.rowcount),
        )

        # ---------------------------------------------------------------------
        # Find Pokémon owned by the requested player(s).
        # ---------------------------------------------------------------------

        if player_id is None:
            pokemon_rows = db.execute(
                """
                SELECT
                    id,
                    owner_id
                FROM pokemon
                ORDER BY id
                """
            ).fetchall()
        else:
            pokemon_rows = db.execute(
                """
                SELECT
                    id,
                    owner_id
                FROM pokemon
                WHERE owner_id = ?
                ORDER BY id
                """,
                (player_id,),
            ).fetchall()

        # ---------------------------------------------------------------------
        # Restore unassigned Pokémon to PC storage.
        # ---------------------------------------------------------------------

        for pokemon in pokemon_rows:
            pokemon_id = int(
                pokemon["id"]
            )

            owner_id = int(
                pokemon["owner_id"]
            )

            in_party = _pokemon_in_party(
                db,
                pokemon_id,
            )

            if in_party is not None:
                continue

            in_pc = _pokemon_in_pc(
                db,
                pokemon_id,
            )

            if in_pc is not None:
                # If a stale PC record exists under the wrong player,
                # remove it and restore the Pokémon to its actual owner.
                if int(in_pc["player_id"]) != owner_id:
                    db.execute(
                        """
                        DELETE FROM pc_storage
                        WHERE id = ?
                        """,
                        (int(in_pc["id"]),),
                    )

                    conflicts_removed += 1
                else:
                    continue

            page, slot = _first_empty_position(
                db,
                owner_id,
            )

            db.execute(
                """
                INSERT INTO pc_storage (
                    player_id,
                    pokemon_id,
                    page,
                    slot
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    owner_id,
                    pokemon_id,
                    page,
                    slot,
                ),
            )

            repaired += 1

        db.commit()

    return {
        "repaired": repaired,
        "conflicts_removed": conflicts_removed,
    }


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

try:
    initialize_pc()
except Exception:
    # Database initialization may legitimately happen later during
    # application startup. Do not prevent the module from importing.
    pass