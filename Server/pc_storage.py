from __future__ import annotations

import sqlite3
from typing import Any

from .database import (
    PC_SLOTS_PER_PAGE,
    get_connection,
    ensure_pc_schema,
)


# =============================================================================
# CONSTANTS
# =============================================================================

SLOTS_PER_PAGE = PC_SLOTS_PER_PAGE


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
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

    for slot in range(
        1,
        SLOTS_PER_PAGE + 1,
    ):
        if slot not in occupied:
            return slot

    return None


def _first_empty_position(
    db: sqlite3.Connection,
    player_id: int,
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

    page = 1

    while True:

        for slot in range(
            1,
            SLOTS_PER_PAGE + 1,
        ):
            if (
                page,
                slot,
            ) not in occupied:
                return page, slot

        page += 1


def _player_owns_pokemon(
    pokemon: sqlite3.Row | None,
    player_id: int,
) -> bool:

    if pokemon is None:
        return False

    return int(
        pokemon["owner_id"]
    ) == int(player_id)


def _normalize_page(
    page: int | str | None,
) -> int:

    try:
        value = int(page or 1)
    except (
        TypeError,
        ValueError,
    ):
        value = 1

    return max(
        1,
        value,
    )


def _normalize_slot(
    slot: int | str | None,
) -> int | None:

    try:
        value = int(slot)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if not 1 <= value <= SLOTS_PER_PAGE:
        return None

    return value


# =============================================================================
# SCHEMA
# =============================================================================

def initialize_pc() -> None:
    """
    Ensure the database-backed PC table exists.
    """

    ensure_pc_schema()


def ensure_schema() -> None:
    initialize_pc()


# =============================================================================
# FIRST EMPTY SLOT
# =============================================================================

def first_empty_slot(
    player_id: int,
    page: int | None = None,
) -> tuple[int, int]:

    with get_connection() as db:

        ensure_pc_schema(db)

        if page is not None:

            page = _normalize_page(
                page
            )

            slot = _next_empty_slot(
                db,
                player_id,
                page,
            )

            if slot is not None:
                return page, slot

            return (
                page + 1,
                1,
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

            if int(
                existing_pc["player_id"]
            ) != int(player_id):

                raise PermissionError(
                    "This Pokémon belongs to another player."
                )

            return get_pokemon_location(
                pokemon_id
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

            page, slot = _first_empty_position(
                db,
                player_id,
            )

        elif page is None:

            slot = _normalize_slot(
                slot
            )

            if slot is None:
                raise ValueError(
                    "PC slot must be between 1 and 30."
                )

            # Find the first page containing that slot.
            page = 1

            while True:

                existing = db.execute(
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

                if existing is None:
                    break

                page += 1

        elif slot is None:

            page = _normalize_page(
                page
            )

            slot = _next_empty_slot(
                db,
                player_id,
                page,
            )

            if slot is None:
                page += 1
                slot = 1

        else:

            page = _normalize_page(
                page
            )

            slot = _normalize_slot(
                slot
            )

            if slot is None:
                raise ValueError(
                    "PC slot must be between 1 and 30."
                )

        occupied = db.execute(
            """
            SELECT pokemon_id
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

        if occupied is not None:

            raise ValueError(
                "That PC slot is already occupied."
            )

        db.execute(
            """
            INSERT INTO pc_storage
            (
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
                page,
                slot,
            ),
        )

        db.commit()

        return get_pokemon_location(
            pokemon_id
        )


# =============================================================================
# WITHDRAW
# =============================================================================

def withdraw_pokemon(
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

        db.execute(
            """
            DELETE FROM pc_storage
            WHERE pokemon_id = ?
              AND player_id = ?
            """,
            (
                pokemon_id,
                player_id,
            ),
        )

        db.commit()

        return {
            "success": True,
            "pokemon_id": pokemon_id,
            "location": "withdrawn",
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

    target_page = _normalize_page(
        target_page
    )

    target_slot = _normalize_slot(
        target_slot
    )

    if target_slot is None:
        raise ValueError(
            "PC slot must be between 1 and 30."
        )

    with get_connection() as db:

        ensure_pc_schema(db)

        record = _pokemon_in_pc(
            db,
            pokemon_id,
            player_id,
        )

        if record is None:
            raise ValueError(
                "That Pokémon is not in the PC."
            )

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
                int(record["id"]),
                player_id,
            ),
        )

        db.commit()

        return get_pokemon_location(
            pokemon_id
        )


# =============================================================================
# SWAP
# =============================================================================

def swap_pokemon(
    player_id: int,
    pokemon_id: int,
    target_page: int,
    target_slot: int,
) -> dict[str, Any]:

    target_page = _normalize_page(
        target_page
    )

    target_slot = _normalize_slot(
        target_slot
    )

    if target_slot is None:
        raise ValueError(
            "PC slot must be between 1 and 30."
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

        target = db.execute(
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

        # ---------------------------------------------------------------------
        # Empty destination: normal move.
        # ---------------------------------------------------------------------

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
                    int(source["id"]),
                    player_id,
                ),
            )

            db.commit()

            return {
                "success": True,
                "action": "move",
                "pokemon_id": pokemon_id,
                "location": get_pokemon_location(
                    pokemon_id
                ),
            }

        # ---------------------------------------------------------------------
        # Same record.
        # ---------------------------------------------------------------------

        if int(
            target["id"]
        ) == int(
            source["id"]
        ):

            return {
                "success": True,
                "action": "none",
                "pokemon_id": pokemon_id,
                "location": get_pokemon_location(
                    pokemon_id
                ),
            }

        # ---------------------------------------------------------------------
        # Swap records.
        #
        # SQLite UNIQUE(player_id,page,slot) means a direct UPDATE can violate
        # the constraint. Temporarily move the source to an unused position.
        # ---------------------------------------------------------------------

        temporary_page, temporary_slot = (
            _first_empty_position(
                db,
                player_id,
            )
        )

        # If the first empty position happens to be the target, find another.
        if (
            temporary_page == target_page
            and temporary_slot == target_slot
        ):

            temporary_page += 1
            temporary_slot = 1

            while db.execute(
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
                    temporary_page,
                    temporary_slot,
                ),
            ).fetchone() is not None:

                temporary_page += 1

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
                int(source["id"]),
                player_id,
            ),
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
                int(source["page"]),
                int(source["slot"]),
                int(target["id"]),
                player_id,
            ),
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
            "action": "swap",
            "pokemon_id": pokemon_id,
            "swapped_with": int(
                target["pokemon_id"]
            ),
            "location": get_pokemon_location(
                pokemon_id
            ),
        }


# =============================================================================
# PAGE
# =============================================================================

def get_page(
    player_id: int,
    page: int = 1,
) -> dict[str, Any]:

    page = _normalize_page(
        page
    )

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

        slots = [
            None
            for _ in range(
                SLOTS_PER_PAGE
            )
        ]

        for row in rows:

            data = dict(
                row
            )

            slot = int(
                data["slot"]
            )

            if 1 <= slot <= SLOTS_PER_PAGE:

                slots[
                    slot - 1
                ] = data

        count_row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pc_storage
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        total_count = int(
            count_row["count"]
        )

        max_page_row = db.execute(
            """
            SELECT MAX(page) AS max_page
            FROM pc_storage
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        max_page = int(
            max_page_row["max_page"]
            or 1
        )

        return {
            "page": page,
            "max_page": max_page,
            "total_count": total_count,
            "slots_per_page": SLOTS_PER_PAGE,
            "pokemon": [
                slot
                for slot in slots
            ],
            "slots": slots,
        }


# =============================================================================
# GET POKÉMON
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

        return _row_to_dict(
            row
        )


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

    if pokemon_type is None:
        pokemon_type = type_name

    search = (
        str(search).strip()
        if search is not None
        else ""
    )

    variant = (
        str(variant).strip()
        if variant is not None
        else ""
    )

    pokemon_type = (
        str(pokemon_type).strip()
        if pokemon_type is not None
        else ""
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

    # -------------------------------------------------------------------------
    # Type filtering is intentionally handled without requiring a specific
    # catalog schema. If the optional species/type tables exist, use them.
    # Otherwise the basic name/variant/shiny search still works.
    # -------------------------------------------------------------------------

    type_join = ""

    with get_connection() as db:

        ensure_pc_schema(db)

        tables = {
            row["name"]
            for row in db.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        has_species_types = (
            "pokemon_species_types"
            in tables
        )

        has_pokemon_types = (
            "pokemon_types"
            in tables
        )

        if (
            pokemon_type
            and has_species_types
            and has_pokemon_types
        ):

            type_join = """
                INNER JOIN pokemon_species_types pst
                    ON pst.species_id = p.species_id

                INNER JOIN pokemon_types pt
                    ON pt.id = pst.type_id
            """

        query += type_join

        query += """
            WHERE pc.player_id = ?
        """

        if search:

            query += """
                AND (
                    LOWER(COALESCE(p.nickname, '')) LIKE LOWER(?)
                    OR LOWER(COALESCE(p.species_id, '')) LIKE LOWER(?)
                    OR LOWER(COALESCE(p.unique_id, '')) LIKE LOWER(?)
                )
            """

            wildcard = (
                "%"
                + search
                + "%"
            )

            parameters.extend(
                [
                    wildcard,
                    wildcard,
                    wildcard,
                ]
            )

        if variant:

            query += """
                AND LOWER(
                    COALESCE(
                        p.variant,
                        ''
                    )
                ) = LOWER(?)
            """

            parameters.append(
                variant
            )

        if pokemon_type and (
            has_species_types
            and has_pokemon_types
        ):

            query += """
                AND LOWER(
                    COALESCE(
                        pt.name,
                        ''
                    )
                ) = LOWER(?)
            """

            parameters.append(
                pokemon_type
            )

        if shiny is not None:

            query += """
                AND p.shiny = ?
            """

            parameters.append(
                1
                if shiny
                else 0
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


# =============================================================================
# SEARCH ALIASES
# =============================================================================

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
# PC COUNT
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
            row["count"]
        )


# =============================================================================
# PAGE COUNT
# =============================================================================

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
                row["max_page"]
                or 1
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

        variants = db.execute(
            """
            SELECT DISTINCT
                variant
            FROM pokemon p
            INNER JOIN pc_storage pc
                ON pc.pokemon_id = p.id
            WHERE pc.player_id = ?
              AND COALESCE(
                    TRIM(p.variant),
                    ''
                  ) != ''
            ORDER BY variant
            """,
            (player_id,),
        ).fetchall()

        types: list[str] = []

        tables = {
            row["name"]
            for row in db.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        if (
            "pokemon_species_types"
            in tables
            and "pokemon_types"
            in tables
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
            "variants": [
                str(row["variant"])
                for row in variants
                if row["variant"]
            ],
            "types": types,
        }


def get_search_filters(
    player_id: int,
) -> dict[str, list[str]]:
    return get_pc_search_filters(
        player_id
    )


# =============================================================================
# LOCATION
# =============================================================================

def get_pokemon_location(
    pokemon_id: int,
) -> dict[str, Any]:

    with get_connection() as db:

        ensure_pc_schema(db)

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
                "player_id": int(
                    party["player_id"]
                ),
                "slot": int(
                    party["slot"]
                ),
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
                "player_id": int(
                    pc["player_id"]
                ),
                "page": int(
                    pc["page"]
                ),
                "slot": int(
                    pc["slot"]
                ),
            }

        pokemon = _pokemon_exists(
            db,
            pokemon_id,
        )

        if pokemon is not None:

            return {
                "pokemon_id": pokemon_id,
                "location": "unassigned",
                "player_id": int(
                    pokemon["owner_id"]
                ),
            }

        return {
            "pokemon_id": pokemon_id,
            "location": "not_found",
        }


# =============================================================================
# PLAYER-SCOPED LOCATION
# =============================================================================

def get_player_pokemon_location(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:

    with get_connection() as db:

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

        return get_pokemon_location(
            pokemon_id
        )


# =============================================================================
# PC INVENTORY
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
# LEGACY COMPATIBILITY
# =============================================================================

def add_to_pc(
    player_id: int,
    pokemon_id: int,
    page: int | None = None,
    slot: int | None = None,
):
    return deposit_pokemon(
        player_id,
        pokemon_id,
        page,
        slot,
    )


def remove_from_pc(
    player_id: int,
    pokemon_id: int,
):
    return withdraw_pokemon(
        player_id,
        pokemon_id,
    )


def move_pc_pokemon(
    player_id: int,
    pokemon_id: int,
    target_page: int,
    target_slot: int,
):
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

    repaired = 0
    conflicts_removed = 0

    with get_connection() as db:

        ensure_pc_schema(db)

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
        # Party always wins if a Pokémon exists in both Party and PC.
        # ---------------------------------------------------------------------

        deleted = db.execute(
            """
            DELETE FROM pc_storage
            WHERE pokemon_id IN (
                SELECT pokemon_id
                FROM party
            )
            """
        )

        conflicts_removed += deleted.rowcount

        # ---------------------------------------------------------------------
        # Put unassigned owned Pokémon into PC.
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

            in_pc = _pokemon_in_pc(
                db,
                pokemon_id,
            )

            if (
                in_party is not None
                or in_pc is not None
            ):
                continue

            page, slot = _first_empty_position(
                db,
                owner_id,
            )

            db.execute(
                """
                INSERT INTO pc_storage
                (
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