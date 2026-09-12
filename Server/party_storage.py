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

    When an existing connection is supplied, this function does not
    commit so that callers can include schema creation in a larger
    transaction.
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
        (pokemon_id, player_id),
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


def _party_table_exists(
    db: sqlite3.Connection,
) -> bool:
    row = db.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'party'
        LIMIT 1
        """
    ).fetchone()

    return row is not None


def _sync_legacy_active_flags(
    db: sqlite3.Connection,
    player_id: int,
) -> None:
    """
    Migrate old is_active-based party membership into the Party table.

    This is intentionally conservative:
    - Existing Party rows are never replaced.
    - Existing is_active Pokémon are added only when Party membership
      has not already been established.
    - The Party table becomes authoritative.
    """
    if not _party_table_exists(db):
        return

    existing = {
        int(row["pokemon_id"])
        for row in db.execute(
            """
            SELECT pokemon_id
            FROM party
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchall()
    }

    count = _party_count(db, player_id)

    if count < MAX_PARTY_SIZE:
        rows = db.execute(
            """
            SELECT id
            FROM pokemon
            WHERE owner_id = ?
              AND is_active = 1
            ORDER BY id
            """,
            (player_id,),
        ).fetchall()

        for row in rows:
            pokemon_id = int(row["id"])

            if pokemon_id in existing:
                continue

            if count >= MAX_PARTY_SIZE:
                break

            slot = _next_party_slot(db, player_id)

            if slot is None:
                break

            db.execute(
                """
                INSERT OR IGNORE INTO party
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

            existing.add(pokemon_id)
            count += 1

    # Keep the legacy column synchronized for older code.
    db.execute(
        """
        UPDATE pokemon
        SET is_active = 0
        WHERE owner_id = ?
        """,
        (player_id,),
    )

    db.execute(
        """
        UPDATE pokemon
        SET is_active = 1
        WHERE owner_id = ?
          AND id IN (
              SELECT pokemon_id
              FROM party
              WHERE player_id = ?
          )
        """,
        (
            player_id,
            player_id,
        ),
    )


def migrate_existing_party(
    player_id: int,
) -> None:
    with get_connection() as db:
        ensure_party_schema(db)

        _sync_legacy_active_flags(
            db,
            player_id,
        )

        db.commit()


def get_party(
    player_id: int,
) -> list[dict[str, Any]]:
    with get_connection() as db:
        ensure_party_schema(db)

        _sync_legacy_active_flags(
            db,
            player_id,
        )

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

            ORDER BY party.slot
            """,
            (player_id,),
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
            """,
            (
                player_id,
                pokemon_id,
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
    with get_connection() as db:
        ensure_party_schema(db)

        _sync_legacy_active_flags(
            db,
            player_id,
        )

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

        # PC is optional here because the Party module must also work
        # independently before the PC table has been initialized.
        pc_exists = db.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'pc_storage'
            LIMIT 1
            """
        ).fetchone()

        if pc_exists is not None:
            pc_row = db.execute(
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

            if pc_row is not None:
                raise ValueError(
                    "That Pokémon is currently stored in the PC."
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

        db.execute(
            """
            UPDATE pokemon
            SET is_active = 1
            WHERE id = ?
              AND owner_id = ?
            """,
            (
                pokemon_id,
                player_id,
            ),
        )

        db.commit()

        return {
            "pokemon_id": pokemon_id,
            "slot": slot,
        }


def remove_from_party(
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    with get_connection() as db:
        ensure_party_schema(db)

        row = db.execute(
            """
            SELECT id, slot
            FROM party
            WHERE player_id = ?
              AND pokemon_id = ?
            """,
            (
                player_id,
                pokemon_id,
            ),
        ).fetchone()

        if row is None:
            raise ValueError(
                "That Pokémon is not in the player's party."
            )

        old_slot = int(row["slot"])

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
            UPDATE pokemon
            SET is_active = 0
            WHERE id = ?
              AND owner_id = ?
            """,
            (
                pokemon_id,
                player_id,
            ),
        )

        db.commit()

        return {
            "pokemon_id": pokemon_id,
            "old_slot": old_slot,
        }


def move_party_pokemon(
    player_id: int,
    pokemon_id: int,
    destination_slot: int,
) -> dict[str, Any]:
    destination_slot = int(destination_slot)

    if destination_slot < 1 or destination_slot > MAX_PARTY_SIZE:
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
            """,
            (
                player_id,
                destination_slot,
            ),
        ).fetchone()

        # Use DELETE/INSERT instead of invalid temporary slot values.
        # This avoids violating CHECK(slot >= 1).
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

        if destination is None:
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
        else:
            destination_pokemon_id = int(
                destination["pokemon_id"]
            )

            db.execute(
                """
                DELETE FROM party
                WHERE player_id = ?
                  AND pokemon_id = ?
                """,
                (
                    player_id,
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
) -> None:
    with get_connection() as db:
        ensure_party_schema(db)

        rows = db.execute(
            """
            SELECT pokemon_id
            FROM party
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchall()

        db.execute(
            """
            DELETE FROM party
            WHERE player_id = ?
            """,
            (player_id,),
        )

        for row in rows:
            db.execute(
                """
                UPDATE pokemon
                SET is_active = 0
                WHERE id = ?
                  AND owner_id = ?
                """,
                (
                    int(row["pokemon_id"]),
                    player_id,
                ),
            )

        db.commit()


def get_party_with_details(
    player_id: int,
) -> list[dict[str, Any]]:
    from .services import get_pokemon

    party = get_party(player_id)
    result: list[dict[str, Any]] = []

    for entry in party:
        pokemon_id = int(entry["pokemon_id"])

        detailed = get_pokemon(
            player_id,
            pokemon_id,
        )

        if detailed is None:
            detailed = dict(entry)

        detailed["party_id"] = entry["party_id"]
        detailed["slot"] = entry["slot"]

        result.append(detailed)

    return result