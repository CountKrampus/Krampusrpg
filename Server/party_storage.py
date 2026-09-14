from __future__ import annotations

import sqlite3
from typing import Any

from .database import (
    MAX_PARTY_SIZE,
    ensure_party_schema,
    ensure_pc_schema,
    get_connection,
)


PARTY_SIZE = MAX_PARTY_SIZE
PC_SLOTS_PER_PAGE = 30


# ============================================================
# INTERNAL HELPERS
# ============================================================

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


def _occupied_party_slots(
    db: sqlite3.Connection,
    player_id: int,
) -> set[int]:

    rows = db.execute(
        """
        SELECT slot
        FROM party
        WHERE player_id = ?
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
            PC_SLOTS_PER_PAGE + 1,
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


def _load_party_pokemon(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any] | None:

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


# ============================================================
# SCHEMA
# ============================================================

def initialize_party() -> None:
    """
    Ensure the database-backed Party table exists.
    """

    ensure_party_schema()


def ensure_schema() -> None:
    initialize_party()


# ============================================================
# GET PARTY
# ============================================================

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

        return _load_party_pokemon(
            db,
            player_id,
            pokemon_id,
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


# ============================================================
# ADD TO PARTY
# ============================================================

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

            result = _load_party_pokemon(
                db,
                player_id,
                pokemon_id,
            )

            if result is None:
                raise RuntimeError(
                    "Unable to load Party Pokémon."
                )

            return result

        if _party_count(
            db,
            player_id,
        ) >= PARTY_SIZE:

            raise ValueError(
                "Your Party is full."
            )

        # ----------------------------------------------------
        # Determine target slot.
        # ----------------------------------------------------

        if slot is None:

            target_slot = _next_party_slot(
                db,
                player_id,
            )

            if target_slot is None:
                raise ValueError(
                    "No Party slot is available."
                )

        else:

            try:
                target_slot = int(slot)
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
                    target_slot,
                ),
            ).fetchone()

            if occupied is not None:
                raise ValueError(
                    "That Party slot is already occupied."
                )

        # ----------------------------------------------------
        # Make sure the Pokémon isn't simultaneously assigned
        # to another player's PC.
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Remove the PC location first.
        # ----------------------------------------------------

        db.execute(
            """
            DELETE FROM pc_storage
            WHERE player_id = ?
              AND pokemon_id = ?
            """,
            (
                player_id,
                pokemon_id,
            ),
        )

        # ----------------------------------------------------
        # Insert into Party.
        # ----------------------------------------------------

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
                target_slot,
            ),
        )

        db.commit()

        result = _load_party_pokemon(
            db,
            player_id,
            pokemon_id,
        )

        if result is None:
            raise RuntimeError(
                "Pokémon was added to Party but could not be loaded afterward."
            )

        return result


# ============================================================
# REMOVE FROM PARTY
# ============================================================

def remove_from_party(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:

    """
    Remove a Pokémon from Party and automatically move it to PC.

    The Pokémon itself is NEVER deleted.
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

        # ----------------------------------------------------
        # Ensure PC location exists BEFORE deleting Party
        # membership.
        # ----------------------------------------------------

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

            page = int(
                pc_record["page"]
            )

            pc_slot = int(
                pc_record["slot"]
            )

        else:

            page, pc_slot = _move_to_pc(
                db,
                player_id,
                pokemon_id,
            )

        # ----------------------------------------------------
        # Now remove the Party record.
        # ----------------------------------------------------

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
            "page": page,
            "slot": pc_slot,
        }


# ============================================================
# MOVE PARTY POKÉMON
# ============================================================

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
                "This Pokémon is not in your Party."
            )

        source_slot = int(
            source["slot"]
        )

        if source_slot == target_slot:

            result = _load_party_pokemon(
                db,
                player_id,
                pokemon_id,
            )

            if result is None:
                raise RuntimeError(
                    "Unable to load Party Pokémon."
                )

            return result

        target = db.execute(
            """
            SELECT
                id,
                player_id,
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

        # ----------------------------------------------------
        # Empty target slot.
        # ----------------------------------------------------

        if target is None:

            db.execute(
                """
                UPDATE party
                SET slot = ?
                WHERE player_id = ?
                  AND pokemon_id = ?
                """,
                (
                    target_slot,
                    player_id,
                    pokemon_id,
                ),
            )

        # ----------------------------------------------------
        # Occupied target slot.
        #
        # We cannot use slot 7 as a temporary value because the
        # schema deliberately restricts Party slots to 1–6.
        #
        # Instead, delete the two Party records and reinsert
        # them in their swapped positions inside one transaction.
        # ----------------------------------------------------

        else:

            target_pokemon_id = int(
                target["pokemon_id"]
            )

            # Remove both records.

            db.execute(
                """
                DELETE FROM party
                WHERE player_id = ?
                  AND pokemon_id IN (?, ?)
                """,
                (
                    player_id,
                    pokemon_id,
                    target_pokemon_id,
                ),
            )

            # Reinsert both records with swapped slots.

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
                    target_slot,
                ),
            )

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
                    target_pokemon_id,
                    source_slot,
                ),
            )

        db.commit()

        result = _load_party_pokemon(
            db,
            player_id,
            pokemon_id,
        )

        if result is None:
            raise RuntimeError(
                "Unable to load Party Pokémon after moving it."
            )

        return result


# ============================================================
# CLEAR PARTY
# ============================================================

def clear_party(
    player_id: int,
) -> dict[str, Any]:

    with get_connection() as db:

        ensure_party_schema(db)
        ensure_pc_schema(db)

        rows = db.execute(
            """
            SELECT pokemon_id
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

            page, slot = _move_to_pc(
                db,
                player_id,
                pokemon_id,
            )

            moved.append(
                {
                    "pokemon_id": pokemon_id,
                    "page": page,
                    "slot": slot,
                }
            )

        db.execute(
            """
            DELETE FROM party
            WHERE player_id = ?
            """,
            (player_id,),
        )

        db.commit()

        return {
            "success": True,
            "moved": moved,
            "count": len(moved),
        }


# ============================================================
# PARTY LOCATION
# ============================================================

def get_pokemon_location(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:

    with get_connection() as db:

        ensure_party_schema(db)
        ensure_pc_schema(db)

        pokemon = _get_pokemon(
            db,
            pokemon_id,
        )

        if pokemon is None:
            return {
                "location": None,
                "pokemon_id": pokemon_id,
            }

        if not _player_owns(
            pokemon,
            player_id,
        ):
            return {
                "location": None,
                "pokemon_id": pokemon_id,
            }

        party = _get_party_record(
            db,
            pokemon_id,
        )

        if party is not None:

            if int(
                party["player_id"]
            ) == int(player_id):

                return {
                    "location": "party",
                    "pokemon_id": pokemon_id,
                    "slot": int(
                        party["slot"]
                    ),
                }

        pc = _get_pc_record(
            db,
            pokemon_id,
        )

        if pc is not None:

            if int(
                pc["player_id"]
            ) == int(player_id):

                return {
                    "location": "pc",
                    "pokemon_id": pokemon_id,
                    "page": int(
                        pc["page"]
                    ),
                    "slot": int(
                        pc["slot"]
                    ),
                }

        return {
            "location": "unassigned",
            "pokemon_id": pokemon_id,
        }


# ============================================================
# REPAIR PARTY STORAGE
# ============================================================

def repair_party(
    player_id: int | None = None,
) -> dict[str, Any]:

    """
    Repair Party/PC storage inconsistencies.

    No Pokémon are intentionally deleted.

    Any owned Pokémon found in Party is kept there.

    Any owned Pokémon not represented by Party or PC storage
    is placed into the PC.

    Duplicate/conflicting Party records are removed while
    preserving the underlying Pokémon.
    """

    with get_connection() as db:

        ensure_party_schema(db)
        ensure_pc_schema(db)

        if player_id is None:

            players = db.execute(
                """
                SELECT DISTINCT owner_id AS player_id
                FROM pokemon
                WHERE owner_id IS NOT NULL
                ORDER BY owner_id
                """
            ).fetchall()

            player_ids = [
                int(row["player_id"])
                for row in players
            ]

        else:

            player_ids = [
                int(player_id)
            ]

        repaired = 0
        moved_to_pc = 0
        removed_duplicates = 0

        for current_player_id in player_ids:

            # ------------------------------------------------
            # Remove invalid Party records where the Pokémon
            # no longer exists or belongs to another player.
            # ------------------------------------------------

            party_rows = db.execute(
                """
                SELECT
                    party.id,
                    party.pokemon_id,
                    party.slot,
                    p.owner_id
                FROM party
                LEFT JOIN pokemon p
                    ON p.id = party.pokemon_id
                WHERE party.player_id = ?
                ORDER BY party.slot, party.id
                """,
                (
                    current_player_id,
                ),
            ).fetchall()

            used_slots: set[int] = set()
            seen_pokemon: set[int] = set()

            for row in party_rows:

                party_id = int(
                    row["id"]
                )

                pokemon_id = int(
                    row["pokemon_id"]
                )

                owner_id = row["owner_id"]

                slot = int(
                    row["slot"]
                )

                invalid = (
                    owner_id is None
                    or int(owner_id)
                    != current_player_id
                    or pokemon_id
                    in seen_pokemon
                    or slot < 1
                    or slot > PARTY_SIZE
                    or slot in used_slots
                )

                if invalid:

                    db.execute(
                        """
                        DELETE FROM party
                        WHERE id = ?
                        """,
                        (party_id,),
                    )

                    removed_duplicates += 1

                    continue

                seen_pokemon.add(
                    pokemon_id
                )

                used_slots.add(
                    slot
                )

            # ------------------------------------------------
            # Remove PC records belonging to the wrong owner,
            # duplicates, or invalid positions.
            # ------------------------------------------------

            pc_rows = db.execute(
                """
                SELECT
                    pc.id,
                    pc.pokemon_id,
                    pc.page,
                    pc.slot,
                    p.owner_id
                FROM pc_storage pc
                LEFT JOIN pokemon p
                    ON p.id = pc.pokemon_id
                WHERE pc.player_id = ?
                ORDER BY pc.page, pc.slot, pc.id
                """,
                (
                    current_player_id,
                ),
            ).fetchall()

            seen_pc_pokemon: set[int] = set()
            used_pc_positions: set[
                tuple[int, int]
            ] = set()

            for row in pc_rows:

                pc_id = int(
                    row["id"]
                )

                pokemon_id = int(
                    row["pokemon_id"]
                )

                page = int(
                    row["page"]
                )

                slot = int(
                    row["slot"]
                )

                owner_id = row["owner_id"]

                invalid = (
                    owner_id is None
                    or int(owner_id)
                    != current_player_id
                    or pokemon_id
                    in seen_pc_pokemon
                    or page < 1
                    or slot < 1
                    or slot > PC_SLOTS_PER_PAGE
                    or (
                        page,
                        slot,
                    )
                    in used_pc_positions
                    or pokemon_id
                    in seen_pokemon
                )

                if invalid:

                    db.execute(
                        """
                        DELETE FROM pc_storage
                        WHERE id = ?
                        """,
                        (pc_id,),
                    )

                    removed_duplicates += 1

                    continue

                seen_pc_pokemon.add(
                    pokemon_id
                )

                used_pc_positions.add(
                    (
                        page,
                        slot,
                    )
                )

            # ------------------------------------------------
            # Every owned Pokémon must have exactly one valid
            # storage location.
            # ------------------------------------------------

            owned_rows = db.execute(
                """
                SELECT id
                FROM pokemon
                WHERE owner_id = ?
                ORDER BY id
                """,
                (
                    current_player_id,
                ),
            ).fetchall()

            for pokemon_row in owned_rows:

                pokemon_id = int(
                    pokemon_row["id"]
                )

                in_party = (
                    pokemon_id
                    in seen_pokemon
                )

                in_pc = (
                    pokemon_id
                    in seen_pc_pokemon
                )

                if in_party or in_pc:
                    continue

                page, slot = _first_empty_pc_position(
                    db,
                    current_player_id,
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
                        current_player_id,
                        pokemon_id,
                        page,
                        slot,
                    ),
                )

                seen_pc_pokemon.add(
                    pokemon_id
                )

                used_pc_positions.add(
                    (
                        page,
                        slot,
                    )
                )

                moved_to_pc += 1

        db.commit()

        repaired = (
            removed_duplicates
            + moved_to_pc
        )

        return {
            "success": True,
            "players_checked": len(
                player_ids
            ),
            "repaired": repaired,
            "moved_to_pc": moved_to_pc,
            "removed_duplicates": removed_duplicates,
        }


# ============================================================
# MIGRATION COMPATIBILITY
# ============================================================

def migrate_existing_party(
    player_id: int | None = None,
) -> dict[str, Any]:

    """
    Compatibility wrapper for older code.

    The old implementation used an invalid temporary Party slot
    outside the 1–6 range.

    The current implementation performs a safe storage repair
    without ever writing an invalid Party slot.
    """

    return repair_party(
        player_id
    )


# ============================================================
# STORAGE INVARIANT VERIFICATION
# ============================================================

def verify_party_invariant(
    player_id: int,
) -> dict[str, Any]:

    with get_connection() as db:

        ensure_party_schema(db)
        ensure_pc_schema(db)

        owned_count = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pokemon
            WHERE owner_id = ?
            """,
            (player_id,),
        ).fetchone()["count"]

        party_count_value = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM party
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()["count"]

        pc_count = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pc_storage
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()["count"]

        overlap_count = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM party pa
            INNER JOIN pc_storage pc
                ON pc.pokemon_id = pa.pokemon_id
            WHERE pa.player_id = ?
              AND pc.player_id = ?
            """,
            (
                player_id,
                player_id,
            ),
        ).fetchone()["count"]

        unassigned_count = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pokemon p
            LEFT JOIN party pa
                ON pa.pokemon_id = p.id
               AND pa.player_id = ?
            LEFT JOIN pc_storage pc
                ON pc.pokemon_id = p.id
               AND pc.player_id = ?
            WHERE p.owner_id = ?
              AND pa.pokemon_id IS NULL
              AND pc.pokemon_id IS NULL
            """,
            (
                player_id,
                player_id,
                player_id,
            ),
        ).fetchone()["count"]

        duplicate_storage_count = db.execute(
            """
            SELECT COUNT(*)
            FROM
            (
                SELECT pokemon_id
                FROM party
                WHERE player_id = ?

                UNION ALL

                SELECT pokemon_id
                FROM pc_storage
                WHERE player_id = ?

                GROUP BY pokemon_id
                HAVING COUNT(*) > 1
            )
            """,
            (
                player_id,
                player_id,
            ),
        ).fetchone()[0]

        valid = (
            int(overlap_count) == 0
            and int(unassigned_count) == 0
            and int(duplicate_storage_count) == 0
            and (
                int(party_count_value)
                + int(pc_count)
                == int(owned_count)
            )
        )

        return {
            "valid": valid,
            "player_id": player_id,
            "owned_count": int(
                owned_count
            ),
            "party_count": int(
                party_count_value
            ),
            "pc_count": int(
                pc_count
            ),
            "overlap_count": int(
                overlap_count
            ),
            "unassigned_count": int(
                unassigned_count
            ),
            "duplicate_storage_count": int(
                duplicate_storage_count
            ),
        }


# ============================================================
# LEGACY COMPATIBILITY ALIASES
# ============================================================

get_player_party = get_party
get_party_for_player = get_party
add_pokemon_to_party = add_to_party
remove_pokemon_from_party = remove_from_party
move_pokemon_in_party = move_party_pokemon
party_is_at_capacity = party_is_full


# ============================================================
# MODULE INITIALIZATION
# ============================================================

try:
    ensure_party_schema()
except Exception:
    # Database initialization is also performed by the
    # application factory. Importing this module should not
    # make the application impossible to start if the database
    # has not yet been created.
    pass