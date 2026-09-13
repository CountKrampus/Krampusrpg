from __future__ import annotations

import sqlite3
from typing import Any

from .database import (
    MAX_PARTY_SIZE,
    get_connection,
    ensure_party_schema,
    ensure_pc_schema,
)


# =============================================================================
# CONSTANTS
# =============================================================================

PARTY_SIZE = MAX_PARTY_SIZE


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _row_to_dict(
    row: sqlite3.Row | None,
) -> dict[str, Any] | None:

    if row is None:
        return None

    return dict(row)


def _get_pokemon(
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


def _get_party_record(
    db: sqlite3.Connection,
    pokemon_id: int,
) -> sqlite3.Row | None:

    return db.execute(
        """
        SELECT
            id,
            player_id,
            pokemon_id,
            slot,
            created_at
        FROM party
        WHERE pokemon_id = ?
        LIMIT 1
        """,
        (pokemon_id,),
    ).fetchone()


def _get_pc_record(
    db: sqlite3.Connection,
    pokemon_id: int,
) -> sqlite3.Row | None:

    return db.execute(
        """
        SELECT
            id,
            player_id,
            pokemon_id,
            page,
            slot,
            created_at
        FROM pc_storage
        WHERE pokemon_id = ?
        LIMIT 1
        """,
        (pokemon_id,),
    ).fetchone()


def _player_owns(
    pokemon: sqlite3.Row | None,
    player_id: int,
) -> bool:

    if pokemon is None:
        return False

    return int(
        pokemon["owner_id"]
    ) == int(player_id)


def _occupied_party_slots(
    db: sqlite3.Connection,
    player_id: int,
) -> set[int]:

    rows = db.execute(
        """
        SELECT slot
        FROM party
        WHERE player_id = ?
        ORDER BY slot
        """,
        (player_id,),
    ).fetchall()

    return {
        int(row["slot"])
        for row in rows
    }


def _next_party_slot(
    db: sqlite3.Connection,
    player_id: int,
) -> int | None:

    occupied = _occupied_party_slots(
        db,
        player_id,
    )

    for slot in range(
        1,
        PARTY_SIZE + 1,
    ):
        if slot not in occupied:
            return slot

    return None


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

    return int(
        row["count"]
    )


def _first_empty_pc_position(
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
            31,
        ):
            if (
                page,
                slot,
            ) not in occupied:
                return page, slot

        page += 1


def _move_to_pc(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> tuple[int, int]:

    existing_pc = _get_pc_record(
        db,
        pokemon_id,
    )

    if existing_pc is not None:

        if int(
            existing_pc["player_id"]
        ) != int(player_id):

            raise PermissionError(
                "The Pokémon is stored under another player."
            )

        return (
            int(existing_pc["page"]),
            int(existing_pc["slot"]),
        )

    page, slot = _first_empty_pc_position(
        db,
        player_id,
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

    return page, slot


# =============================================================================
# SCHEMA
# =============================================================================

def initialize_party() -> None:
    """
    Ensure the database-backed Party table exists.
    """

    ensure_party_schema()


def ensure_schema() -> None:
    initialize_party()


# =============================================================================
# PARTY
# =============================================================================

def get_party(
    player_id: int,
) -> list[dict[str, Any]]:

    with get_connection() as db:

        ensure_party_schema(db)

        rows = db.execute(
            """
            SELECT

                party.id AS party_id,

                party.player_id,

                party.pokemon_id,

                party.slot,

                party.created_at AS party_created_at,

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

            FROM party

            INNER JOIN pokemon p
                ON p.id = party.pokemon_id

            WHERE party.player_id = ?

            ORDER BY party.slot
            """,
            (player_id,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def get_party_pokemon(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any] | None:

    with get_connection() as db:

        ensure_party_schema(db)

        row = db.execute(
            """
            SELECT

                party.id AS party_id,

                party.player_id,

                party.pokemon_id,

                party.slot,

                party.created_at AS party_created_at,

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

            FROM party

            INNER JOIN pokemon p
                ON p.id = party.pokemon_id

            WHERE party.player_id = ?
              AND party.pokemon_id = ?

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


def is_in_party(
    pokemon_id: int,
) -> bool:

    with get_connection() as db:

        ensure_party_schema(db)

        row = db.execute(
            """
            SELECT 1
            FROM party
            WHERE pokemon_id = ?
            LIMIT 1
            """,
            (pokemon_id,),
        ).fetchone()

        return row is not None


def party_count(
    player_id: int,
) -> int:

    with get_connection() as db:

        ensure_party_schema(db)

        return _party_count(
            db,
            player_id,
        )


def party_is_full(
    player_id: int,
) -> bool:

    return (
        party_count(player_id)
        >= PARTY_SIZE
    )


# =============================================================================
# ADD TO PARTY
# =============================================================================

def add_to_party(
    player_id: int,
    pokemon_id: int,
    slot: int | None = None,
) -> dict[str, Any]:

    with get_connection() as db:

        ensure_party_schema(db)
        ensure_pc_schema(db)

        pokemon = _get_pokemon(
            db,
            pokemon_id,
        )

        if pokemon is None:
            raise ValueError(
                "Pokémon does not exist."
            )

        if not _player_owns(
            pokemon,
            player_id,
        ):
            raise PermissionError(
                "You do not own this Pokémon."
            )

        existing_party = _get_party_record(
            db,
            pokemon_id,
        )

        if existing_party is not None:

            if int(
                existing_party["player_id"]
            ) != int(player_id):

                raise PermissionError(
                    "This Pokémon belongs to another player's Party."
                )

            return get_party_pokemon(
                player_id,
                pokemon_id,
            )

        current_count = _party_count(
            db,
            player_id,
        )

        if current_count >= PARTY_SIZE:
            raise ValueError(
                "Your Party is full."
            )

        # ---------------------------------------------------------------------
        # If the Pokémon is in the PC, remove the PC record as part of the
        # same transaction before adding it to Party.
        # ---------------------------------------------------------------------

        pc_record = _get_pc_record(
            db,
            pokemon_id,
        )

        if pc_record is not None:

            if int(
                pc_record["player_id"]
            ) != int(player_id):

                raise PermissionError(
                    "This Pokémon is stored under another player."
                )

        # ---------------------------------------------------------------------
        # Determine Party slot.
        # ---------------------------------------------------------------------

        if slot is None:

            slot = _next_party_slot(
                db,
                player_id,
            )

        else:

            try:
                slot = int(slot)
            except (
                TypeError,
                ValueError,
            ):
                raise ValueError(
                    "Party slot must be between 1 and 6."
                )

            if not 1 <= slot <= PARTY_SIZE:
                raise ValueError(
                    "Party slot must be between 1 and 6."
                )

            occupied = db.execute(
                """
                SELECT pokemon_id
                FROM party
                WHERE player_id = ?
                  AND slot = ?
                LIMIT 1
                """,
                (
                    player_id,
                    slot,
                ),
            ).fetchone()

            if occupied is not None:

                raise ValueError(
                    "That Party slot is already occupied."
                )

        if slot is None:
            raise ValueError(
                "No Party slot is available."
            )

        # ---------------------------------------------------------------------
        # Remove from PC first.
        # ---------------------------------------------------------------------

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

        # ---------------------------------------------------------------------
        # Insert into Party.
        # ---------------------------------------------------------------------

        db.execute(
            """
            INSERT INTO party
            (
                player_id,
                pokemon_id,
                slot
            )
            VALUES (?, ?, ?)
            """,
            (
                player_id,
                pokemon_id,
                slot,
            ),
        )

        db.commit()

        result = get_party_pokemon(
            player_id,
            pokemon_id,
        )

        if result is None:
            raise RuntimeError(
                "Pokémon was added to Party but could not be loaded afterward."
            )

        return result


# =============================================================================
# REMOVE FROM PARTY
# =============================================================================

def remove_from_party(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:

    """
    Remove a Pokémon from Party.

    IMPORTANT:

        Removing a Pokémon from Party NEVER deletes it.

        The Pokémon is automatically moved into the PC.

    This maintains the core storage invariant:

        Every owned Pokémon is either:

            Party
            OR
            PC

        Never neither.
    """

    with get_connection() as db:

        ensure_party_schema(db)
        ensure_pc_schema(db)

        pokemon = _get_pokemon(
            db,
            pokemon_id,
        )

        if pokemon is None:
            raise ValueError(
                "Pokémon does not exist."
            )

        if not _player_owns(
            pokemon,
            player_id,
        ):
            raise PermissionError(
                "You do not own this Pokémon."
            )

        party_record = _get_party_record(
            db,
            pokemon_id,
        )

        if party_record is None:
            raise ValueError(
                "That Pokémon is not in your Party."
            )

        if int(
            party_record["player_id"]
        ) != int(player_id):

            raise PermissionError(
                "This Pokémon is not in your Party."
            )

        # ---------------------------------------------------------------------
        # If something already placed the Pokémon in PC, do not create a
        # duplicate PC record.
        # ---------------------------------------------------------------------

        existing_pc = _get_pc_record(
            db,
            pokemon_id,
        )

        if existing_pc is not None:

            if int(
                existing_pc["player_id"]
            ) != int(player_id):

                raise PermissionError(
                    "This Pokémon is already stored under another player."
                )

            pc_page = int(
                existing_pc["page"]
            )

            pc_slot = int(
                existing_pc["slot"]
            )

        else:

            pc_page, pc_slot = _move_to_pc(
                db,
                player_id,
                pokemon_id,
            )

        # ---------------------------------------------------------------------
        # Remove from Party only AFTER the PC record exists.
        #
        # This ordering prevents the Pokémon from ever becoming unassigned
        # if the transaction succeeds.
        # ---------------------------------------------------------------------

        db.execute(
            """
            DELETE FROM party
            WHERE player_id = ?
              AND pokemon_id = ?
            """,
            (
                player_id,
                pokemon_id,
            ),
        )

        db.commit()

        return {
            "success": True,
            "pokemon_id": pokemon_id,
            "location": "pc",
            "page": pc_page,
            "slot": pc_slot,
        }


# =============================================================================
# MOVE PARTY SLOT
# =============================================================================

def move_party_pokemon(
    player_id: int,
    pokemon_id: int,
    target_slot: int,
) -> dict[str, Any]:

    try:
        target_slot = int(
            target_slot
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "Party slot must be between 1 and 6."
        )

    if not 1 <= target_slot <= PARTY_SIZE:
        raise ValueError(
            "Party slot must be between 1 and 6."
        )

    with get_connection() as db:

        ensure_party_schema(db)

        source = _get_party_record(
            db,
            pokemon_id,
        )

        if source is None:
            raise ValueError(
                "That Pokémon is not in your Party."
            )

        if int(
            source["player_id"]
        ) != int(player_id):

            raise PermissionError(
                "That Pokémon is not in your Party."
            )

        source_slot = int(
            source["slot"]
        )

        if source_slot == target_slot:

            return get_party_pokemon(
                player_id,
                pokemon_id,
            )

        target = db.execute(
            """
            SELECT
                id,
                pokemon_id,
                slot
            FROM party
            WHERE player_id = ?
              AND slot = ?
            LIMIT 1
            """,
            (
                player_id,
                target_slot,
            ),
        ).fetchone()

        # ---------------------------------------------------------------------
        # Empty target slot.
        # ---------------------------------------------------------------------

        if target is None:

            db.execute(
                """
                UPDATE party
                SET slot = ?
                WHERE id = ?
                  AND player_id = ?
                """,
                (
                    target_slot,
                    int(source["id"]),
                    player_id,
                ),
            )

            db.commit()

            return get_party_pokemon(
                player_id,
                pokemon_id,
            )

        # ---------------------------------------------------------------------
        # Swap two Party Pokémon.
        # ---------------------------------------------------------------------

        temporary_slot = PARTY_SIZE + 1

        db.execute(
            """
            UPDATE party
            SET slot = ?
            WHERE id = ?
              AND player_id = ?
            """,
            (
                temporary_slot,
                int(source["id"]),
                player_id,
            ),
        )

        db.execute(
            """
            UPDATE party
            SET slot = ?
            WHERE id = ?
              AND player_id = ?
            """,
            (
                source_slot,
                int(target["id"]),
                player_id,
            ),
        )

        db.execute(
            """
            UPDATE party
            SET slot = ?
            WHERE id = ?
              AND player_id = ?
            """,
            (
                target_slot,
                int(source["id"]),
                player_id,
            ),
        )

        db.commit()

        return get_party_pokemon(
            player_id,
            pokemon_id,
        )


# =============================================================================
# CLEAR PARTY
# =============================================================================

def clear_party(
    player_id: int,
) -> dict[str, Any]:

    """
    Move every Party Pokémon into the PC.

    Pokémon are never deleted.
    """

    with get_connection() as db:

        ensure_party_schema(db)
        ensure_pc_schema(db)

        rows = db.execute(
            """
            SELECT
                pokemon_id
            FROM party
            WHERE player_id = ?
            ORDER BY slot
            """,
            (player_id,),
        ).fetchall()

        moved = []

        for row in rows:

            pokemon_id = int(
                row["pokemon_id"]
            )

            existing_pc = _get_pc_record(
                db,
                pokemon_id,
            )

            if existing_pc is None:

                page, slot = _move_to_pc(
                    db,
                    player_id,
                    pokemon_id,
                )

            else:

                page = int(
                    existing_pc["page"]
                )

                slot = int(
                    existing_pc["slot"]
                )

            db.execute(
                """
                DELETE FROM party
                WHERE player_id = ?
                  AND pokemon_id = ?
                """,
                (
                    player_id,
                    pokemon_id,
                ),
            )

            moved.append(
                {
                    "pokemon_id": pokemon_id,
                    "page": page,
                    "slot": slot,
                }
            )

        db.commit()

        return {
            "success": True,
            "moved": moved,
            "count": len(moved),
        }


# =============================================================================
# PARTY LOCATION
# =============================================================================

def get_party_slot(
    pokemon_id: int,
) -> int | None:

    with get_connection() as db:

        ensure_party_schema(db)

        row = db.execute(
            """
            SELECT slot
            FROM party
            WHERE pokemon_id = ?
            LIMIT 1
            """,
            (pokemon_id,),
        ).fetchone()

        if row is None:
            return None

        return int(
            row["slot"]
        )


def get_pokemon_location(
    pokemon_id: int,
) -> dict[str, Any]:

    with get_connection() as db:

        ensure_party_schema(db)
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

        pokemon = _get_pokemon(
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
# PARTY REPAIR
# =============================================================================

def repair_party(
    player_id: int | None = None,
) -> dict[str, int]:

    repaired = 0
    conflicts_removed = 0

    with get_connection() as db:

        ensure_party_schema(db)
        ensure_pc_schema(db)

        # ---------------------------------------------------------------------
        # Party always takes priority over PC.
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
        # Remove Party records for nonexistent Pokémon.
        # ---------------------------------------------------------------------

        db.execute(
            """
            DELETE FROM party
            WHERE pokemon_id NOT IN (
                SELECT id
                FROM pokemon
            )
            """
        )

        # ---------------------------------------------------------------------
        # Remove Party records where the storage owner doesn't match the
        # Pokémon owner.
        # ---------------------------------------------------------------------

        if player_id is None:

            mismatches = db.execute(
                """
                DELETE FROM party
                WHERE EXISTS (
                    SELECT 1
                    FROM pokemon p
                    WHERE p.id = party.pokemon_id
                      AND p.owner_id != party.player_id
                )
                """
            )

        else:

            mismatches = db.execute(
                """
                DELETE FROM party
                WHERE player_id = ?
                  AND EXISTS (
                    SELECT 1
                    FROM pokemon p
                    WHERE p.id = party.pokemon_id
                      AND p.owner_id != party.player_id
                )
                """,
                (player_id,),
            )

        conflicts_removed += mismatches.rowcount

        # ---------------------------------------------------------------------
        # Any Pokémon now not in Party or PC goes into PC.
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

        for pokemon in pokemon_rows:

            pokemon_id = int(
                pokemon["id"]
            )

            owner_id = int(
                pokemon["owner_id"]
            )

            party_record = _get_party_record(
                db,
                pokemon_id,
            )

            pc_record = _get_pc_record(
                db,
                pokemon_id,
            )

            if (
                party_record is not None
                or pc_record is not None
            ):
                continue

            page, slot = _first_empty_pc_position(
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


# =============================================================================
# LEGACY COMPATIBILITY FUNCTIONS
# =============================================================================

def add_pokemon_to_party(
    player_id: int,
    pokemon_id: int,
    slot: int | None = None,
):
    return add_to_party(
        player_id,
        pokemon_id,
        slot,
    )


def remove_pokemon_from_party(
    player_id: int,
    pokemon_id: int,
):
    return remove_from_party(
        player_id,
        pokemon_id,
    )


def move_pokemon_in_party(
    player_id: int,
    pokemon_id: int,
    target_slot: int,
):
    return move_party_pokemon(
        player_id,
        pokemon_id,
        target_slot,
    )


def get_player_party(
    player_id: int,
):
    return get_party(
        player_id
    )


def get_party_count(
    player_id: int,
):
    return party_count(
        player_id
    )


def is_party_full(
    player_id: int,
):
    return party_is_full(
        player_id
    )


# =============================================================================
# LEGACY MIGRATION ENTRY POINT
# =============================================================================

def migrate_existing_party() -> dict[str, int]:
    """
    Compatibility entry point for older code.

    The actual migration is handled by database.init_db().
    """

    with get_connection() as db:

        ensure_party_schema(db)
        ensure_pc_schema(db)

        players = db.execute(
            """
            SELECT id
            FROM players
            ORDER BY id
            """
        ).fetchall()

        repaired = 0

        for player in players:

            player_id = int(
                player["id"]
            )

            rows = db.execute(
                """
                SELECT
                    id,
                    pokemon_id
                FROM party
                WHERE player_id = ?
                ORDER BY slot, id
                """,
                (player_id,),
            ).fetchall()

            # -----------------------------------------------------------------
            # Re-number Party slots to 1–6.
            # -----------------------------------------------------------------

            for index, row in enumerate(
                rows[:PARTY_SIZE],
                start=1,
            ):

                current_slot = db.execute(
                    """
                    SELECT slot
                    FROM party
                    WHERE id = ?
                    """,
                    (int(row["id"]),),
                ).fetchone()

                if (
                    current_slot is not None
                    and int(current_slot["slot"]) != index
                ):

                    db.execute(
                        """
                        UPDATE party
                        SET slot = ?
                        WHERE id = ?
                        """,
                        (
                            PARTY_SIZE + 1,
                            int(row["id"]),
                        ),
                    )

            for index, row in enumerate(
                rows[:PARTY_SIZE],
                start=1,
            ):

                db.execute(
                    """
                    UPDATE party
                    SET slot = ?
                    WHERE id = ?
                    """,
                    (
                        index,
                        int(row["id"]),
                    ),
                )

                repaired += 1

            # -----------------------------------------------------------------
            # If legacy data somehow contains more than six Party records,
            # move the extras to PC rather than deleting them.
            # -----------------------------------------------------------------

            extras = rows[
                PARTY_SIZE:
            ]

            for row in extras:

                pokemon_id = int(
                    row["pokemon_id"]
                )

                existing_pc = _get_pc_record(
                    db,
                    pokemon_id,
                )

                if existing_pc is None:

                    page, slot = _first_empty_pc_position(
                        db,
                        player_id,
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

                db.execute(
                    """
                    DELETE FROM party
                    WHERE id = ?
                    """,
                    (int(row["id"]),),
                )

                repaired += 1

        db.commit()

    return {
        "repaired": repaired,
    }


# =============================================================================
# STARTUP
# =============================================================================

initialize_party()