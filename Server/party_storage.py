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

    return int(pokemon["owner_id"]) == int(player_id)


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

    return int(row["count"])


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
    """
    Find the first available PC position.

    Pages are unlimited and each page contains 30 slots.
    """
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
            p.owner_id,
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

    return _row_to_dict(row)


def _load_pc_pokemon(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT
            pc.id AS pc_id,
            pc.player_id,
            pc.pokemon_id,
            pc.page,
            pc.slot,
            pc.created_at AS pc_created_at,

            p.unique_id,
            p.owner_id,
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


def _move_to_pc(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> tuple[int, int]:
    """
    Ensure a Pokémon has a PC location.

    Returns:
        (page, slot)
    """
    existing_pc = _get_pc_record(
        db,
        pokemon_id,
    )

    if existing_pc is not None:
        if int(existing_pc["player_id"]) != int(player_id):
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


def _remove_pc_record(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> None:
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


# =============================================================================
# SCHEMA
# =============================================================================

def initialize_party() -> None:
    """
    Ensure Party and PC storage schemas exist.
    """
    ensure_party_schema()
    ensure_pc_schema()


def ensure_schema() -> None:
    initialize_party()


# =============================================================================
# GET PARTY
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
                p.owner_id,
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


# =============================================================================
# ADD TO PARTY
# =============================================================================

def add_to_party(
    player_id: int,
    pokemon_id: int,
    slot: int | None = None,
) -> dict[str, Any]:
    """
    Add an owned Pokémon to the Party.

    A Pokémon can only occupy one storage location at a time.

    If it is currently in the player's PC, its PC record is
    removed inside the same transaction before Party insertion.
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

        existing_party = _get_party_record(
            db,
            pokemon_id,
        )

        if existing_party is not None:
            if int(existing_party["player_id"]) != int(player_id):
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

        existing_pc = _get_pc_record(
            db,
            pokemon_id,
        )

        if existing_pc is not None:
            if int(existing_pc["player_id"]) != int(player_id):
                raise PermissionError(
                    "This Pokémon is stored under another player."
                )

        current_party_count = _party_count(
            db,
            player_id,
        )

        if current_party_count >= PARTY_SIZE:
            raise ValueError(
                "Your Party is full."
            )

        # ---------------------------------------------------------
        # Resolve target slot.
        # ---------------------------------------------------------

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

        # ---------------------------------------------------------
        # Remove PC location if present.
        # ---------------------------------------------------------

        if existing_pc is not None:
            _remove_pc_record(
                db,
                player_id,
                pokemon_id,
            )

        # ---------------------------------------------------------
        # Insert Party record.
        # ---------------------------------------------------------

        try:
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

        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "Unable to place that Pokémon in the Party."
            ) from exc

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


# =============================================================================
# REMOVE FROM PARTY
# =============================================================================

def remove_from_party(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    """
    Move a Party Pokémon into the PC.

    The Pokémon is never deleted.

    The PC destination is created BEFORE the Party record is
    removed, so the Pokémon cannot be left unassigned if the
    transaction fails.
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

        if int(party_record["player_id"]) != int(player_id):
            raise PermissionError(
                "This Pokémon is not in your Party."
            )

        existing_pc = _get_pc_record(
            db,
            pokemon_id,
        )

        if existing_pc is not None:
            if int(existing_pc["player_id"]) != int(player_id):
                raise PermissionError(
                    "This Pokémon is stored under another player."
                )

            page = int(
                existing_pc["page"]
            )

            pc_slot = int(
                existing_pc["slot"]
            )

        else:
            page, pc_slot = _move_to_pc(
                db,
                player_id,
                pokemon_id,
            )

        # ---------------------------------------------------------
        # Remove Party membership only after PC location exists.
        # ---------------------------------------------------------

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


# =============================================================================
# MOVE PARTY POKÉMON
# =============================================================================

def move_party_pokemon(
    player_id: int,
    pokemon_id: int,
    target_slot: int,
) -> dict[str, Any]:
    """
    Move a Party Pokémon to another Party slot.

    If the target slot is occupied, the two Party Pokémon are
    swapped atomically.
    """
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

        if int(source["player_id"]) != int(player_id):
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

            return {
                "success": True,
                "pokemon_id": pokemon_id,
                "slot": target_slot,
                "swapped": False,
                "pokemon": result,
            }

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

        # ---------------------------------------------------------
        # Empty target slot: simple move.
        # ---------------------------------------------------------

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

            db.commit()

            result = _load_party_pokemon(
                db,
                player_id,
                pokemon_id,
            )

            if result is None:
                raise RuntimeError(
                    "Unable to load moved Party Pokémon."
                )

            return {
                "success": True,
                "pokemon_id": pokemon_id,
                "slot": target_slot,
                "swapped": False,
                "pokemon": result,
            }

        # ---------------------------------------------------------
        # Occupied target: swap the two slots.
        #
        # Use temporary negative slots so the UNIQUE
        # (player_id, slot) constraint cannot be violated.
        # ---------------------------------------------------------

        target_pokemon_id = int(
            target["pokemon_id"]
        )

        temporary_slot = -1

        while db.execute(
            """
            SELECT 1
            FROM party
            WHERE player_id = ?
              AND slot = ?
            LIMIT 1
            """,
            (
                player_id,
                temporary_slot,
            ),
        ).fetchone() is not None:
            temporary_slot -= 1

        db.execute(
            """
            UPDATE party
            SET slot = ?
            WHERE player_id = ?
              AND pokemon_id = ?
            """,
            (
                temporary_slot,
                player_id,
                pokemon_id,
            ),
        )

        db.execute(
            """
            UPDATE party
            SET slot = ?
            WHERE player_id = ?
              AND pokemon_id = ?
            """,
            (
                source_slot,
                player_id,
                target_pokemon_id,
            ),
        )

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

        db.commit()

        result = _load_party_pokemon(
            db,
            player_id,
            pokemon_id,
        )

        if result is None:
            raise RuntimeError(
                "Unable to load moved Party Pokémon."
            )

        return {
            "success": True,
            "pokemon_id": pokemon_id,
            "slot": target_slot,
            "swapped": True,
            "swapped_with": target_pokemon_id,
            "pokemon": result,
        }


# =============================================================================
# PARTY / PC LOCATION
# =============================================================================

def get_pokemon_location(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    """
    Determine where one of the player's Pokémon is stored.

    Valid locations:
        party
        pc
        unassigned

    A Pokémon belonging to another player is reported as
    not owned instead of exposing its storage location.
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

        party = _get_party_record(
            db,
            pokemon_id,
        )

        if party is not None:
            if int(party["player_id"]) == int(player_id):
                return {
                    "pokemon_id": pokemon_id,
                    "location": "party",
                    "slot": int(party["slot"]),
                    "page": None,
                }

            raise RuntimeError(
                "Storage invariant violation: Pokémon is in another player's Party."
            )

        pc = _get_pc_record(
            db,
            pokemon_id,
        )

        if pc is not None:
            if int(pc["player_id"]) == int(player_id):
                return {
                    "pokemon_id": pokemon_id,
                    "location": "pc",
                    "page": int(pc["page"]),
                    "slot": int(pc["slot"]),
                }

            raise RuntimeError(
                "Storage invariant violation: Pokémon is in another player's PC."
            )

        return {
            "pokemon_id": pokemon_id,
            "location": "unassigned",
            "page": None,
            "slot": None,
        }


def get_player_pokemon_location(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    return get_pokemon_location(
        player_id,
        pokemon_id,
    )


# =============================================================================
# STORAGE INVARIANT
# =============================================================================

def verify_storage_invariant(
    player_id: int | None = None,
) -> dict[str, Any]:
    """
    Verify that Party and PC storage contain no duplicate Pokémon.

    A Pokémon owned by a player may be:
        - in Party
        - in PC
        - temporarily unassigned

    It must never be in both Party and PC simultaneously.

    It also must never appear twice in either storage system.
    """
    with get_connection() as db:
        ensure_party_schema(db)
        ensure_pc_schema(db)

        parameters: tuple[Any, ...] = ()

        player_filter = ""

        if player_id is not None:
            player_filter = """
                WHERE p.owner_id = ?
            """
            parameters = (
                int(player_id),
            )

        rows = db.execute(
            f"""
            SELECT
                p.id AS pokemon_id,
                p.owner_id,

                party.player_id AS party_player_id,
                party.slot AS party_slot,

                pc_storage.player_id AS pc_player_id,
                pc_storage.page AS pc_page,
                pc_storage.slot AS pc_slot

            FROM pokemon p

            LEFT JOIN party
                ON party.pokemon_id = p.id

            LEFT JOIN pc_storage
                ON pc_storage.pokemon_id = p.id

            {player_filter}

            ORDER BY p.id
            """,
            parameters,
        ).fetchall()

        duplicate_pokemon: list[int] = []
        cross_player_conflicts: list[int] = []
        unassigned_pokemon: list[int] = []
        invalid_party_owners: list[int] = []
        invalid_pc_owners: list[int] = []

        for row in rows:
            pokemon_id = int(
                row["pokemon_id"]
            )

            owner_id = int(
                row["owner_id"]
            )

            party_player_id = row[
                "party_player_id"
            ]

            pc_player_id = row[
                "pc_player_id"
            ]

            if party_player_id is not None:
                party_player_id = int(
                    party_player_id
                )

            if pc_player_id is not None:
                pc_player_id = int(
                    pc_player_id
                )

            if (
                party_player_id is not None
                and pc_player_id is not None
            ):
                duplicate_pokemon.append(
                    pokemon_id
                )

            if (
                party_player_id is not None
                and party_player_id != owner_id
            ):
                invalid_party_owners.append(
                    pokemon_id
                )

            if (
                pc_player_id is not None
                and pc_player_id != owner_id
            ):
                invalid_pc_owners.append(
                    pokemon_id
                )

            if (
                party_player_id is not None
                and pc_player_id is not None
                and party_player_id != pc_player_id
            ):
                cross_player_conflicts.append(
                    pokemon_id
                )

            if (
                party_player_id is None
                and pc_player_id is None
            ):
                unassigned_pokemon.append(
                    pokemon_id
                )

        party_duplicate_slots = db.execute(
            """
            SELECT
                player_id,
                slot,
                COUNT(*) AS count
            FROM party
            GROUP BY player_id, slot
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        pc_duplicate_slots = db.execute(
            """
            SELECT
                player_id,
                page,
                slot,
                COUNT(*) AS count
            FROM pc_storage
            GROUP BY player_id, page, slot
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        party_duplicate_slot_count = len(
            party_duplicate_slots
        )

        pc_duplicate_slot_count = len(
            pc_duplicate_slots
        )

        valid = not any(
            (
                duplicate_pokemon,
                cross_player_conflicts,
                invalid_party_owners,
                invalid_pc_owners,
                party_duplicate_slot_count,
                pc_duplicate_slot_count,
            )
        )

        return {
            "valid": valid,
            "player_id": player_id,
            "duplicate_pokemon": duplicate_pokemon,
            "cross_player_conflicts": cross_player_conflicts,
            "invalid_party_owners": invalid_party_owners,
            "invalid_pc_owners": invalid_pc_owners,
            "unassigned_pokemon": unassigned_pokemon,
            "party_duplicate_slots": party_duplicate_slot_count,
            "pc_duplicate_slots": pc_duplicate_slot_count,
        }


def verify_party_invariant(
    player_id: int | None = None,
) -> dict[str, Any]:
    return verify_storage_invariant(
        player_id
    )


# =============================================================================
# MIGRATION / REPAIR
# =============================================================================

def repair_party_storage(
    player_id: int | None = None,
) -> dict[str, Any]:
    """
    Repair invalid Party/PC ownership records.

    This function never deletes Pokémon.

    Invalid storage records are removed, and affected owned
    Pokémon are restored to the player's PC when possible.
    """
    with get_connection() as db:
        ensure_party_schema(db)
        ensure_pc_schema(db)

        parameters: tuple[Any, ...] = ()

        player_filter = ""

        if player_id is not None:
            player_filter = """
                AND p.owner_id = ?
            """
            parameters = (
                int(player_id),
            )

        pokemon_rows = db.execute(
            f"""
            SELECT
                p.id,
                p.owner_id
            FROM pokemon p
            WHERE 1 = 1
            {player_filter}
            ORDER BY p.id
            """,
            parameters,
        ).fetchall()

        repaired = 0
        removed_party_records = 0
        removed_pc_records = 0
        moved_to_pc = 0

        for pokemon in pokemon_rows:
            pokemon_id = int(
                pokemon["id"]
            )

            owner_id = int(
                pokemon["owner_id"]
            )

            party_rows = db.execute(
                """
                SELECT
                    id,
                    player_id,
                    slot
                FROM party
                WHERE pokemon_id = ?
                ORDER BY id
                """,
                (pokemon_id,),
            ).fetchall()

            pc_rows = db.execute(
                """
                SELECT
                    id,
                    player_id,
                    page,
                    slot
                FROM pc_storage
                WHERE pokemon_id = ?
                ORDER BY id
                """,
                (pokemon_id,),
            ).fetchall()

            # -----------------------------------------------------
            # Keep at most one valid Party record belonging to owner.
            # -----------------------------------------------------

            valid_party = None

            for row in party_rows:
                if int(row["player_id"]) == owner_id:
                    valid_party = row
                    break

            for row in party_rows:
                if (
                    valid_party is not None
                    and int(row["id"]) == int(valid_party["id"])
                ):
                    continue

                db.execute(
                    """
                    DELETE FROM party
                    WHERE id = ?
                    """,
                    (int(row["id"]),),
                )

                removed_party_records += 1
                repaired += 1

            # -----------------------------------------------------
            # Keep at most one valid PC record belonging to owner.
            # -----------------------------------------------------

            valid_pc = None

            for row in pc_rows:
                if int(row["player_id"]) == owner_id:
                    valid_pc = row
                    break

            for row in pc_rows:
                if (
                    valid_pc is not None
                    and int(row["id"]) == int(valid_pc["id"])
                ):
                    continue

                db.execute(
                    """
                    DELETE FROM pc_storage
                    WHERE id = ?
                    """,
                    (int(row["id"]),),
                )

                removed_pc_records += 1
                repaired += 1

            # -----------------------------------------------------
            # Re-read storage after cleanup.
            # -----------------------------------------------------

            valid_party = _get_party_record(
                db,
                pokemon_id,
            )

            valid_pc = _get_pc_record(
                db,
                pokemon_id,
            )

            # -----------------------------------------------------
            # A Pokémon cannot occupy both locations.
            #
            # Party takes priority because moving a Party Pokémon
            # to PC should be an explicit action.
            # -----------------------------------------------------

            if (
                valid_party is not None
                and valid_pc is not None
            ):
                if int(valid_party["player_id"]) == owner_id:
                    db.execute(
                        """
                        DELETE FROM pc_storage
                        WHERE pokemon_id = ?
                        """,
                        (pokemon_id,),
                    )

                    removed_pc_records += 1
                    repaired += 1

            # -----------------------------------------------------
            # If the Pokémon is owned and completely unassigned,
            # restore it to PC storage.
            # -----------------------------------------------------

            valid_party = _get_party_record(
                db,
                pokemon_id,
            )

            valid_pc = _get_pc_record(
                db,
                pokemon_id,
            )

            if (
                valid_party is None
                and valid_pc is None
            ):
                _move_to_pc(
                    db,
                    owner_id,
                    pokemon_id,
                )

                moved_to_pc += 1
                repaired += 1

        db.commit()

        return {
            "success": True,
            "player_id": player_id,
            "repaired": repaired,
            "removed_party_records": removed_party_records,
            "removed_pc_records": removed_pc_records,
            "moved_to_pc": moved_to_pc,
        }


def migrate_existing_party() -> dict[str, Any]:
    """
    Compatibility migration entry point.

    The database layer now owns the legacy migration logic,
    so this function simply ensures the current schema and
    repairs storage invariants.
    """
    initialize_party()

    return repair_party_storage()


# =============================================================================
# COMPATIBILITY ALIASES
# =============================================================================

def add_pokemon_to_party(
    player_id: int,
    pokemon_id: int,
    slot: int | None = None,
) -> dict[str, Any]:
    return add_to_party(
        player_id,
        pokemon_id,
        slot=slot,
    )


def remove_pokemon_from_party(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    return remove_from_party(
        player_id,
        pokemon_id,
    )


def move_pokemon_in_party(
    player_id: int,
    pokemon_id: int,
    target_slot: int,
) -> dict[str, Any]:
    return move_party_pokemon(
        player_id,
        pokemon_id,
        target_slot,
    )


# =============================================================================
# INITIALIZATION
# =============================================================================

initialize_party()