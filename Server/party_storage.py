from __future__ import annotations

import sqlite3
from typing import Any

from .database import get_connection


MAX_PARTY_SIZE = 6


PARTY_SCHEMA = """
CREATE TABLE IF NOT EXISTS party (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    player_id INTEGER NOT NULL,
    pokemon_id INTEGER NOT NULL UNIQUE,
    slot INTEGER NOT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE,

    FOREIGN KEY (pokemon_id)
        REFERENCES pokemon(id)
        ON DELETE CASCADE,

    CHECK (slot >= 1 AND slot <= 6),

    UNIQUE(player_id, slot)
);

CREATE INDEX IF NOT EXISTS idx_party_player
ON party(player_id);

CREATE INDEX IF NOT EXISTS idx_party_pokemon
ON party(pokemon_id);

CREATE INDEX IF NOT EXISTS idx_party_player_slot
ON party(player_id, slot);
"""


def ensure_party_schema(
    db: sqlite3.Connection | None = None,
) -> None:
    """
    Ensure the database-backed Party table exists.

    The Party table is the only source of truth for party membership.
    """

    if db is not None:
        db.executescript(PARTY_SCHEMA)
        return

    with get_connection() as connection:
        connection.executescript(PARTY_SCHEMA)
        connection.commit()


def _pokemon_belongs_to_player(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> bool:
    row = db.execute(
        """
        SELECT 1
        FROM pokemon
        WHERE id = ?
          AND owner_id = ?
        LIMIT 1
        """,
        (
            pokemon_id,
            player_id,
        ),
    ).fetchone()

    return row is not None


def _party_count(
    db: sqlite3.Connection,
    player_id: int,
) -> int:
    row = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM party
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()

    return int(row["total"] or 0)


def _next_party_slot(
    db: sqlite3.Connection,
    player_id: int,
) -> int | None:
    occupied = {
        int(row["slot"])
        for row in db.execute(
            """
            SELECT slot
            FROM party
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchall()
    }

    for slot in range(1, MAX_PARTY_SIZE + 1):
        if slot not in occupied:
            return slot

    return None


def _pc_table_exists(
    db: sqlite3.Connection,
) -> bool:
    row = db.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'pc_storage'
        LIMIT 1
        """
    ).fetchone()

    return row is not None


def _pokemon_in_pc(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> bool:
    if not _pc_table_exists(db):
        return False

    row = db.execute(
        """
        SELECT 1
        FROM pc_storage
        WHERE player_id = ?
          AND pokemon_id = ?
        LIMIT 1
        """,
        (
            player_id,
            pokemon_id,
        ),
    ).fetchone()

    return row is not None


def get_party(
    player_id: int,
) -> list[dict[str, Any]]:
    """
    Return the player's party.

    Party membership comes exclusively from the party table.
    """

    with get_connection() as db:
        ensure_party_schema(db)

        rows = db.execute(
            """
            SELECT
                party.id AS party_id,
                party.player_id,
                party.pokemon_id,
                party.slot,
                party.created_at,

                p.unique_id,
                p.species_id,
                p.nickname,
                p.level,
                p.experience,
                p.gender,
                p.shiny,
                p.variant,
                p.nature,
                p.current_hp,
                p.max_hp,
                p.status

            FROM party

            INNER JOIN pokemon p
                ON p.id = party.pokemon_id

            WHERE party.player_id = ?
              AND p.owner_id = ?

            ORDER BY party.slot
            """,
            (
                player_id,
                player_id,
            ),
        ).fetchall()

        return [dict(row) for row in rows]


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
                party.created_at,

                p.unique_id,
                p.species_id,
                p.nickname,
                p.level,
                p.experience,
                p.gender,
                p.shiny,
                p.variant,
                p.nature,
                p.current_hp,
                p.max_hp,
                p.status

            FROM party

            INNER JOIN pokemon p
                ON p.id = party.pokemon_id

            WHERE party.player_id = ?
              AND party.pokemon_id = ?
              AND p.owner_id = ?
            """,
            (
                player_id,
                pokemon_id,
                player_id,
            ),
        ).fetchone()

        return dict(row) if row else None


def is_in_party(
    player_id: int,
    pokemon_id: int,
) -> bool:
    with get_connection() as db:
        ensure_party_schema(db)

        row = db.execute(
            """
            SELECT 1
            FROM party
            WHERE player_id = ?
              AND pokemon_id = ?
            LIMIT 1
            """,
            (
                player_id,
                pokemon_id,
            ),
        ).fetchone()

        return row is not None


def add_to_party(
    player_id: int,
    pokemon_id: int,
    slot: int | None = None,
) -> dict[str, Any]:
    """
    Move a Pokémon into the Party.

    If the Pokémon is currently in the PC, it is removed from the PC
    as part of the same transaction.
    """

    with get_connection() as db:
        ensure_party_schema(db)

        if not _pokemon_belongs_to_player(
            db,
            player_id,
            pokemon_id,
        ):
            raise ValueError(
                "That Pokémon does not belong to this player."
            )

        existing = db.execute(
            """
            SELECT pokemon_id, slot
            FROM party
            WHERE player_id = ?
              AND pokemon_id = ?
            """,
            (
                player_id,
                pokemon_id,
            ),
        ).fetchone()

        if existing is not None:
            return {
                "pokemon_id": pokemon_id,
                "slot": int(existing["slot"]),
            }

        if _party_count(db, player_id) >= MAX_PARTY_SIZE:
            raise ValueError(
                "The player's party is already full."
            )

        if slot is None:
            slot = _next_party_slot(
                db,
                player_id,
            )
        else:
            slot = int(slot)

            if slot < 1 or slot > MAX_PARTY_SIZE:
                raise ValueError(
                    "Party slots must be between 1 and 6."
                )

            occupied = db.execute(
                """
                SELECT 1
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
                    "That party slot is already occupied."
                )

        if slot is None:
            raise ValueError(
                "No party slot is available."
            )

        try:
            if _pc_table_exists(db):
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

        except Exception:
            db.rollback()
            raise

        return {
            "pokemon_id": pokemon_id,
            "slot": slot,
        }


def remove_from_party(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    """
    Remove a Pokémon from the Party and AUTOMATICALLY place it into PC.

    This function never deletes the Pokémon.

    Party -> PC is one atomic database transaction.
    """

    from .pc_storage import first_empty_slot

    with get_connection() as db:
        ensure_party_schema(db)

        if not _pokemon_belongs_to_player(
            db,
            player_id,
            pokemon_id,
        ):
            raise ValueError(
                "That Pokémon does not belong to this player."
            )

        party_row = db.execute(
            """
            SELECT id, slot
            FROM party
            WHERE player_id = ?
              AND pokemon_id = ?
            LIMIT 1
            """,
            (
                player_id,
                pokemon_id,
            ),
        ).fetchone()

        if party_row is None:
            raise ValueError(
                "That Pokémon is not in the player's party."
            )

        old_slot = int(party_row["slot"])

        from .pc_storage import ensure_pc_schema

        ensure_pc_schema(db)

        if _pokemon_in_pc(
            db,
            player_id,
            pokemon_id,
        ):
            raise ValueError(
                "That Pokémon is already in the PC."
            )

        pc_page, pc_slot = first_empty_slot(
            db,
            player_id,
        )

        try:
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
                    pc_page,
                    pc_slot,
                ),
            )

            db.commit()

        except Exception:
            db.rollback()
            raise

        return {
            "pokemon_id": pokemon_id,
            "old_slot": old_slot,
            "page": pc_page,
            "slot": pc_slot,
            "destination": "pc",
        }


def move_party_pokemon(
    player_id: int,
    pokemon_id: int,
    destination_slot: int,
) -> dict[str, Any]:
    destination_slot = int(destination_slot)

    if (
        destination_slot < 1
        or destination_slot > MAX_PARTY_SIZE
    ):
        raise ValueError(
            "Party slots must be between 1 and 6."
        )

    with get_connection() as db:
        ensure_party_schema(db)

        source = db.execute(
            """
            SELECT slot
            FROM party
            WHERE player_id = ?
              AND pokemon_id = ?
            LIMIT 1
            """,
            (
                player_id,
                pokemon_id,
            ),
        ).fetchone()

        if source is None:
            raise ValueError(
                "That Pokémon is not in the player's party."
            )

        source_slot = int(source["slot"])

        if source_slot == destination_slot:
            return {
                "pokemon_id": pokemon_id,
                "slot": source_slot,
            }

        destination = db.execute(
            """
            SELECT pokemon_id
            FROM party
            WHERE player_id = ?
              AND slot = ?
            LIMIT 1
            """,
            (
                player_id,
                destination_slot,
            ),
        ).fetchone()

        try:
            if destination is None:
                db.execute(
                    """
                    UPDATE party
                    SET slot = ?
                    WHERE player_id = ?
                      AND pokemon_id = ?
                    """,
                    (
                        destination_slot,
                        player_id,
                        pokemon_id,
                    ),
                )

            else:
                destination_pokemon_id = int(
                    destination["pokemon_id"]
                )

                db.execute(
                    """
                    DELETE FROM party
                    WHERE player_id = ?
                      AND pokemon_id IN (?, ?)
                    """,
                    (
                        player_id,
                        pokemon_id,
                        destination_pokemon_id,
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
                        destination_pokemon_id,
                        source_slot,
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
                        pokemon_id,
                        destination_slot,
                    ),
                )

            db.commit()

        except Exception:
            db.rollback()
            raise

        return {
            "pokemon_id": pokemon_id,
            "slot": destination_slot,
        }


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
    return party_count(player_id) >= MAX_PARTY_SIZE


def clear_party(
    player_id: int,
) -> int:
    """
    Move every Party Pokémon into the PC.

    This is intentionally implemented through the same Party -> PC
    storage rules rather than deleting Pokémon.
    """

    moved = 0

    while True:
        with get_connection() as db:
            ensure_party_schema(db)

            row = db.execute(
                """
                SELECT pokemon_id
                FROM party
                WHERE player_id = ?
                ORDER BY slot
                LIMIT 1
                """,
                (player_id,),
            ).fetchone()

        if row is None:
            break

        remove_from_party(
            player_id,
            int(row["pokemon_id"]),
        )

        moved += 1

    return moved


def migrate_existing_party(
    player_id: int,
) -> None:
    """
    Compatibility entry point.

    The old is_active field is intentionally NOT read.

    Existing migration is handled by the database migration layer.
    """

    with get_connection() as db:
        ensure_party_schema(db)
        db.commit()