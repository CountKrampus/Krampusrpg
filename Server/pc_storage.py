from __future__ import annotations

import sqlite3
from typing import Any

from .database import get_connection
from .pokemon_catalog import ensure_catalog_schema
from .party_storage import (
    MAX_PARTY_SIZE,
    ensure_party_schema,
)


PC_SLOTS_PER_PAGE = 30


PC_SCHEMA = """
CREATE TABLE IF NOT EXISTS pc_storage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    player_id INTEGER NOT NULL,

    pokemon_id INTEGER NOT NULL UNIQUE,

    page INTEGER NOT NULL DEFAULT 1,

    slot INTEGER NOT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE,

    FOREIGN KEY (pokemon_id)
        REFERENCES pokemon(id)
        ON DELETE CASCADE,

    CHECK (page >= 1),

    CHECK (slot >= 1 AND slot <= 30),

    UNIQUE(player_id, page, slot)
);

CREATE INDEX IF NOT EXISTS idx_pc_storage_player
ON pc_storage(player_id);

CREATE INDEX IF NOT EXISTS idx_pc_storage_page
ON pc_storage(player_id, page);

CREATE INDEX IF NOT EXISTS idx_pc_storage_pokemon
ON pc_storage(pokemon_id);
"""


def ensure_pc_schema(
    db: sqlite3.Connection | None = None,
) -> None:
    """
    Create the PC and Party database structures.
    """

    if db is not None:
        ensure_catalog_schema(db)
        ensure_party_schema(db)
        db.executescript(PC_SCHEMA)
        db.commit()
        return

    with get_connection() as connection:
        ensure_catalog_schema(connection)
        ensure_party_schema(connection)
        connection.executescript(PC_SCHEMA)
        connection.commit()


def _pokemon_belongs_to_player(
    db: sqlite3.Connection,
    pokemon_id: int,
    player_id: int,
) -> bool:
    row = db.execute(
        """
        SELECT id
        FROM pokemon
        WHERE id = ?
          AND owner_id = ?
        """,
        (
            pokemon_id,
            player_id,
        ),
    ).fetchone()

    return row is not None


def _pokemon_in_party(
    db: sqlite3.Connection,
    pokemon_id: int,
    player_id: int,
) -> bool:
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


def _pokemon_in_pc(
    db: sqlite3.Connection,
    pokemon_id: int,
    player_id: int,
) -> bool:
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


def get_highest_page(
    db: sqlite3.Connection,
    player_id: int,
) -> int:
    row = db.execute(
        """
        SELECT MAX(page) AS highest_page
        FROM pc_storage
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()

    highest = row["highest_page"]

    if highest is None:
        return 1

    return max(1, int(highest))


def first_empty_slot(
    db: sqlite3.Connection,
    player_id: int,
    preferred_page: int | None = None,
) -> tuple[int, int]:
    if preferred_page is not None:
        preferred_page = max(
            1,
            int(preferred_page),
        )

        occupied = {
            int(row["slot"])
            for row in db.execute(
                """
                SELECT slot
                FROM pc_storage
                WHERE player_id = ?
                  AND page = ?
                """,
                (
                    player_id,
                    preferred_page,
                ),
            ).fetchall()
        }

        for slot in range(
            1,
            PC_SLOTS_PER_PAGE + 1,
        ):
            if slot not in occupied:
                return preferred_page, slot

    page = get_highest_page(
        db,
        player_id,
    )

    while True:
        occupied = {
            int(row["slot"])
            for row in db.execute(
                """
                SELECT slot
                FROM pc_storage
                WHERE player_id = ?
                  AND page = ?
                """,
                (
                    player_id,
                    page,
                ),
            ).fetchall()
        }

        for slot in range(
            1,
            PC_SLOTS_PER_PAGE + 1,
        ):
            if slot not in occupied:
                return page, slot

        page += 1


def deposit_pokemon(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
    page: int | None = None,
    slot: int | None = None,
) -> dict[str, Any]:
    """
    Move a Pokémon from the database-backed Party into the PC.
    """

    ensure_pc_schema(db)

    if not _pokemon_belongs_to_player(
        db,
        pokemon_id,
        player_id,
    ):
        raise ValueError(
            "That Pokémon does not belong to this player."
        )

    if not _pokemon_in_party(
        db,
        pokemon_id,
        player_id,
    ):
        raise ValueError(
            "A Pokémon must be in the player's party before "
            "it can be deposited."
        )

    if _pokemon_in_pc(
        db,
        pokemon_id,
        player_id,
    ):
        raise ValueError(
            "That Pokémon is already in the PC."
        )

    # Do not allow the party to become empty.
    party_count = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM party
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()["total"]

    if int(party_count) <= 1:
        raise ValueError(
            "A player must keep at least one Pokémon in the party."
        )

    if page is None or slot is None:
        page, slot = first_empty_slot(
            db,
            player_id,
            preferred_page=page,
        )
    else:
        page = max(
            1,
            int(page),
        )

        slot = int(slot)

        if slot < 1 or slot > PC_SLOTS_PER_PAGE:
            raise ValueError(
                "PC slots must be between 1 and 30."
            )

        occupied = db.execute(
            """
            SELECT pokemon_id
            FROM pc_storage
            WHERE player_id = ?
              AND page = ?
              AND slot = ?
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

    # Remove from Party first.
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

    # Keep legacy field synchronized.
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

    try:
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
    except sqlite3.IntegrityError:
        # Restore the party membership if the PC insert fails.
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
                1,
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

        raise ValueError(
            "Unable to store that Pokémon in the selected PC slot."
        )

    db.commit()

    return {
        "pokemon_id": pokemon_id,
        "page": page,
        "slot": slot,
    }


def withdraw_pokemon(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    """
    Move a Pokémon from the PC into the database-backed Party.
    """

    ensure_pc_schema(db)

    row = db.execute(
        """
        SELECT
            id,
            pokemon_id,
            page,
            slot
        FROM pc_storage
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
            "That Pokémon is not in this player's PC."
        )

    party_count = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM party
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()["total"]

    if int(party_count) >= MAX_PARTY_SIZE:
        raise ValueError(
            "The player's party is already full."
        )

    occupied_slots = {
        int(entry["slot"])
        for entry in db.execute(
            """
            SELECT slot
            FROM party
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchall()
    }

    party_slot = None

    for candidate in range(
        1,
        MAX_PARTY_SIZE + 1,
    ):
        if candidate not in occupied_slots:
            party_slot = candidate
            break

    if party_slot is None:
        raise ValueError(
            "No party slot is available."
        )

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
            party_slot,
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
        "old_page": int(row["page"]),
        "old_slot": int(row["slot"]),
        "party_slot": party_slot,
    }


def move_pokemon(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
    destination_page: int,
    destination_slot: int,
) -> dict[str, Any]:
    ensure_pc_schema(db)

    destination_page = max(
        1,
        int(destination_page),
    )

    destination_slot = int(destination_slot)

    if (
        destination_slot < 1
        or destination_slot > PC_SLOTS_PER_PAGE
    ):
        raise ValueError(
            "PC slots must be between 1 and 30."
        )

    source = db.execute(
        """
        SELECT
            page,
            slot
        FROM pc_storage
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
            "That Pokémon is not in the player's PC."
        )

    source_page = int(source["page"])
    source_slot = int(source["slot"])

    if (
        source_page == destination_page
        and source_slot == destination_slot
    ):
        return {
            "pokemon_id": pokemon_id,
            "page": source_page,
            "slot": source_slot,
        }

    occupied = db.execute(
        """
        SELECT pokemon_id
        FROM pc_storage
        WHERE player_id = ?
          AND page = ?
          AND slot = ?
        """,
        (
            player_id,
            destination_page,
            destination_slot,
        ),
    ).fetchone()

    if occupied is not None:
        raise ValueError(
            "The destination PC slot is occupied."
        )

    db.execute(
        """
        UPDATE pc_storage
        SET
            page = ?,
            slot = ?
        WHERE player_id = ?
          AND pokemon_id = ?
        """,
        (
            destination_page,
            destination_slot,
            player_id,
            pokemon_id,
        ),
    )

    db.commit()

    return {
        "pokemon_id": pokemon_id,
        "page": destination_page,
        "slot": destination_slot,
    }


def swap_pokemon(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_a: int,
    pokemon_b: int,
) -> dict[str, Any]:
    ensure_pc_schema(db)

    if pokemon_a == pokemon_b:
        raise ValueError(
            "Cannot swap a Pokémon with itself."
        )

    rows = db.execute(
        """
        SELECT
            pokemon_id,
            page,
            slot
        FROM pc_storage
        WHERE player_id = ?
          AND pokemon_id IN (?, ?)
        """,
        (
            player_id,
            pokemon_a,
            pokemon_b,
        ),
    ).fetchall()

    if len(rows) != 2:
        raise ValueError(
            "Both Pokémon must be in the player's PC."
        )

    locations = {
        int(row["pokemon_id"]): (
            int(row["page"]),
            int(row["slot"]),
        )
        for row in rows
    }

    page_a, slot_a = locations[pokemon_a]
    page_b, slot_b = locations[pokemon_b]

    db.execute(
        """
        UPDATE pc_storage
        SET
            page = -1,
            slot = -1
        WHERE player_id = ?
          AND pokemon_id = ?
        """,
        (
            player_id,
            pokemon_a,
        ),
    )

    db.execute(
        """
        UPDATE pc_storage
        SET
            page = ?,
            slot = ?
        WHERE player_id = ?
          AND pokemon_id = ?
        """,
        (
            page_a,
            slot_a,
            player_id,
            pokemon_b,
        ),
    )

    db.execute(
        """
        UPDATE pc_storage
        SET
            page = ?,
            slot = ?
        WHERE player_id = ?
          AND pokemon_id = ?
        """,
        (
            page_b,
            slot_b,
            player_id,
            pokemon_a,
        ),
    )

    db.commit()

    return {
        "pokemon_a": {
            "pokemon_id": pokemon_a,
            "page": page_b,
            "slot": slot_b,
        },
        "pokemon_b": {
            "pokemon_id": pokemon_b,
            "page": page_a,
            "slot": slot_a,
        },
    }


def get_page(
    db: sqlite3.Connection,
    player_id: int,
    page: int = 1,
) -> dict[str, Any]:
    ensure_pc_schema(db)

    page = max(
        1,
        int(page),
    )

    rows = db.execute(
        """
        SELECT
            pc.page,
            pc.slot,

            p.id AS pokemon_id,
            p.unique_id,
            p.species_id,
            p.nickname,
            p.level,
            p.experience,
            p.gender,
            p.shiny,
            p.variant,
            p.current_hp,
            p.max_hp

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

    by_slot = {
        int(row["slot"]): dict(row)
        for row in rows
    }

    slots = []

    for slot in range(
        1,
        PC_SLOTS_PER_PAGE + 1,
    ):
        slots.append(
            {
                "slot": slot,
                "pokemon": by_slot.get(slot),
            }
        )

    return {
        "page": page,
        "slots_per_page": PC_SLOTS_PER_PAGE,
        "highest_page": get_highest_page(
            db,
            player_id,
        ),
        "slots": slots,
        "pokemon_count": len(rows),
    }


def search_pc(
    db: sqlite3.Connection,
    player_id: int,
    name: str | None = None,
    variant: str | None = None,
    type_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Search the entire PC.

    Name, variant and type filters can be combined.
    """

    ensure_pc_schema(db)

    conditions = [
        "pc.player_id = ?",
    ]

    parameters: list[Any] = [
        player_id,
    ]

    if name:
        value = f"%{name.strip()}%"

        conditions.append(
            """
            (
                LOWER(COALESCE(s.name, '')) LIKE LOWER(?)
                OR LOWER(COALESCE(s.id, '')) LIKE LOWER(?)
                OR LOWER(COALESCE(p.nickname, '')) LIKE LOWER(?)
                OR LOWER(COALESCE(p.species_id, '')) LIKE LOWER(?)
            )
            """
        )

        parameters.extend(
            [
                value,
                value,
                value,
                value,
            ]
        )

    if variant:
        conditions.append(
            "LOWER(p.variant) = LOWER(?)"
        )

        parameters.append(
            variant.strip()
        )

    if type_id:
        conditions.append(
            """
            EXISTS (
                SELECT 1
                FROM pokemon_species_types pst
                WHERE pst.species_id = p.species_id
                  AND LOWER(pst.type_id) = LOWER(?)
            )
            """
        )

        parameters.append(
            type_id.strip()
        )

    query = f"""
        SELECT
            pc.page,
            pc.slot,

            p.id AS pokemon_id,
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

            s.name AS species_name

        FROM pc_storage pc

        INNER JOIN pokemon p
            ON p.id = pc.pokemon_id

        LEFT JOIN pokemon_species s
            ON s.id = p.species_id

        WHERE {" AND ".join(conditions)}

        ORDER BY
            pc.page,
            pc.slot

        LIMIT ?
    """

    parameters.append(
        max(
            1,
            min(
                int(limit),
                500,
            ),
        )
    )

    rows = db.execute(
        query,
        parameters,
    ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_pc_count(
    db: sqlite3.Connection,
    player_id: int,
) -> int:
    ensure_pc_schema(db)

    row = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM pc_storage
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()

    return int(row["total"] or 0)


def get_pokemon_location(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any] | None:
    ensure_pc_schema(db)

    pc = db.execute(
        """
        SELECT
            page,
            slot
        FROM pc_storage
        WHERE player_id = ?
          AND pokemon_id = ?
        """,
        (
            player_id,
            pokemon_id,
        ),
    ).fetchone()

    if pc is not None:
        return {
            "location": "pc",
            "page": int(pc["page"]),
            "slot": int(pc["slot"]),
        }

    party = db.execute(
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

    if party is not None:
        return {
            "location": "party",
            "slot": int(party["slot"]),
        }

    return None