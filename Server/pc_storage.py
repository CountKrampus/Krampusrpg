from __future__ import annotations

import sqlite3
from typing import Any

from .database import get_connection
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
    if db is not None:
        ensure_party_schema(db)
        db.executescript(PC_SCHEMA)
        return

    with get_connection() as connection:
        ensure_party_schema(connection)
        connection.executescript(PC_SCHEMA)
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


def _pokemon_in_party(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
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
    player_id: int,
    pokemon_id: int,
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

    if (
        row is None
        or row["highest_page"] is None
    ):
        return 1

    return max(
        1,
        int(row["highest_page"]),
    )


def first_empty_slot(
    db: sqlite3.Connection,
    player_id: int,
    preferred_page: int | None = None,
) -> tuple[int, int]:
    """
    Find the first available PC slot.

    PC pages are unlimited.
    Each page contains exactly 30 possible slots.
    """

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
    Move a Pokémon from Party to PC.

    This is the authoritative Party -> PC operation.
    """

    ensure_pc_schema(db)

    if not _pokemon_belongs_to_player(
        db,
        player_id,
        pokemon_id,
    ):
        raise ValueError(
            "That Pokémon does not belong to this player."
        )

    if not _pokemon_in_party(
        db,
        player_id,
        pokemon_id,
    ):
        raise ValueError(
            "That Pokémon is not in the player's party."
        )

    if _pokemon_in_pc(
        db,
        player_id,
        pokemon_id,
    ):
        raise ValueError(
            "That Pokémon is already in the PC."
        )

    party_row = db.execute(
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

    if party_row is None:
        raise ValueError(
            "That Pokémon is not in the player's party."
        )

    old_party_slot = int(
        party_row["slot"]
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

        if (
            slot < 1
            or slot > PC_SLOTS_PER_PAGE
        ):
            raise ValueError(
                "PC slots must be between 1 and 30."
            )

        occupied = db.execute(
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

        if occupied is not None:
            raise ValueError(
                "That PC slot is already occupied."
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
                page,
                slot,
            ),
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "pokemon_id": pokemon_id,
        "page": page,
        "slot": slot,
        "old_party_slot": old_party_slot,
        "destination": "pc",
    }


def withdraw_pokemon(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any]:
    """
    Move a Pokémon from PC to Party.
    """

    ensure_pc_schema(db)

    row = db.execute(
        """
        SELECT page, slot
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
    ).fetchone()

    if int(party_count["total"]) >= MAX_PARTY_SIZE:
        raise ValueError(
            "The player's party is already full."
        )

    occupied = {
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

    party_slot = next(
        (
            candidate
            for candidate in range(
                1,
                MAX_PARTY_SIZE + 1,
            )
            if candidate not in occupied
        ),
        None,
    )

    if party_slot is None:
        raise ValueError(
            "No party slot is available."
        )

    old_page = int(row["page"])
    old_slot = int(row["slot"])

    try:
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

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "pokemon_id": pokemon_id,
        "old_page": old_page,
        "old_slot": old_slot,
        "party_slot": party_slot,
        "destination": "party",
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

    destination_slot = int(
        destination_slot
    )

    if (
        destination_slot < 1
        or destination_slot > PC_SLOTS_PER_PAGE
    ):
        raise ValueError(
            "PC slots must be between 1 and 30."
        )

    source = db.execute(
        """
        SELECT page, slot
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
        LIMIT 1
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
        SET page = ?,
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

    pokemon_a = int(pokemon_a)
    pokemon_b = int(pokemon_b)

    if pokemon_a == pokemon_b:
        raise ValueError(
            "Cannot swap a Pokémon with itself."
        )

    rows = db.execute(
        """
        SELECT pokemon_id, page, slot
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

    try:
        db.execute(
            """
            DELETE FROM pc_storage
            WHERE player_id = ?
              AND pokemon_id IN (?, ?)
            """,
            (
                player_id,
                pokemon_a,
                pokemon_b,
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
                pokemon_a,
                page_b,
                slot_b,
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
                pokemon_b,
                page_a,
                slot_a,
            ),
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "pokemon_id_a": pokemon_a,
        "pokemon_id_b": pokemon_b,
        "pokemon_a": {
            "page": page_b,
            "slot": slot_b,
        },
        "pokemon_b": {
            "page": page_a,
            "slot": slot_a,
        },
    }


def get_page(
    db: sqlite3.Connection,
    player_id: int,
    page: int,
) -> list[dict[str, Any]]:
    ensure_pc_schema(db)

    page = max(
        1,
        int(page),
    )

    rows = db.execute(
        """
        SELECT
            pc.id AS pc_id,
            pc.player_id,
            pc.pokemon_id,
            pc.page,
            pc.slot,
            pc.created_at,

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

        FROM pc_storage pc

        INNER JOIN pokemon p
            ON p.id = pc.pokemon_id

        WHERE pc.player_id = ?
          AND p.owner_id = ?
          AND pc.page = ?

        ORDER BY pc.slot
        """,
        (
            player_id,
            player_id,
            page,
        ),
    ).fetchall()

    return [dict(row) for row in rows]


def search_pc(
    db: sqlite3.Connection,
    player_id: int,
    name: str | None = None,
    variant: str | None = None,
    pokemon_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search the ENTIRE PC.

    Name, variant and type filters can be combined.
    """

    ensure_pc_schema(db)

    conditions = [
        "pc.player_id = ?",
        "p.owner_id = ?",
    ]

    parameters: list[Any] = [
        player_id,
        player_id,
    ]

    if name:
        conditions.append(
            """
            (
                LOWER(COALESCE(p.nickname, '')) LIKE ?
                OR LOWER(COALESCE(s.name, '')) LIKE ?
                OR LOWER(COALESCE(p.species_id, '')) LIKE ?
            )
            """
        )

        search_value = f"%{name.lower()}%"

        parameters.extend(
            [
                search_value,
                search_value,
                search_value,
            ]
        )

    if variant:
        conditions.append(
            "LOWER(COALESCE(p.variant, '')) = ?"
        )

        parameters.append(
            variant.lower()
        )

    if pokemon_type:
        conditions.append(
            """
            EXISTS (
                SELECT 1
                FROM pokemon_species_types filter_st
                INNER JOIN pokemon_types filter_t
                    ON filter_t.id = filter_st.type_id
                WHERE filter_st.species_id = p.species_id
                  AND LOWER(filter_t.name) = ?
            )
            """
        )

        parameters.append(
            pokemon_type.lower()
        )

    where_clause = " AND ".join(
        conditions
    )

    rows = db.execute(
        f"""
        SELECT
            pc.id AS pc_id,
            pc.player_id,
            pc.pokemon_id,
            pc.page,
            pc.slot,
            pc.created_at,

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
            p.status,

            s.name AS species_name,

            (
                SELECT GROUP_CONCAT(t.name, ', ')
                FROM pokemon_species_types st
                INNER JOIN pokemon_types t
                    ON t.id = st.type_id
                WHERE st.species_id = p.species_id
            ) AS types

        FROM pc_storage pc

        INNER JOIN pokemon p
            ON p.id = pc.pokemon_id

        LEFT JOIN pokemon_species s
            ON CAST(s.id AS TEXT)
             = CAST(p.species_id AS TEXT)

        WHERE {where_clause}

        ORDER BY pc.page, pc.slot
        """,
        parameters,
    ).fetchall()

    result = []

    for row in rows:
        item = dict(row)

        item["type_1"] = None
        item["type_2"] = None

        type_rows = db.execute(
            """
            SELECT t.name
            FROM pokemon_species_types st
            INNER JOIN pokemon_types t
                ON t.id = st.type_id
            WHERE st.species_id = ?
            ORDER BY st.slot
            LIMIT 2
            """,
            (item["species_id"],),
        ).fetchall()

        if len(type_rows) >= 1:
            item["type_1"] = type_rows[0]["name"]

        if len(type_rows) >= 2:
            item["type_2"] = type_rows[1]["name"]

        result.append(item)

    return result


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

    return int(
        row["total"] or 0
    )


def get_pc_search_filters(
    db: sqlite3.Connection,
    player_id: int,
) -> dict[str, list[str]]:
    ensure_pc_schema(db)

    variants = db.execute(
        """
        SELECT DISTINCT
            p.variant
        FROM pc_storage pc
        INNER JOIN pokemon p
            ON p.id = pc.pokemon_id
        WHERE pc.player_id = ?
          AND p.owner_id = ?
          AND COALESCE(p.variant, '') != ''
        ORDER BY p.variant
        """,
        (
            player_id,
            player_id,
        ),
    ).fetchall()

    types = db.execute(
        """
        SELECT DISTINCT
            LOWER(t.name) AS type_name
        FROM pc_storage pc
        INNER JOIN pokemon p
            ON p.id = pc.pokemon_id
        INNER JOIN pokemon_species_types st
            ON st.species_id = p.species_id
        INNER JOIN pokemon_types t
            ON t.id = st.type_id
        WHERE pc.player_id = ?
          AND p.owner_id = ?
          AND COALESCE(t.name, '') != ''
        ORDER BY type_name
        """,
        (
            player_id,
            player_id,
        ),
    ).fetchall()

    return {
        "variants": [
            str(row["variant"])
            for row in variants
        ],
        "types": [
            str(row["type_name"])
            for row in types
        ],
    }


def get_pokemon_location(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> dict[str, Any] | None:
    ensure_pc_schema(db)

    pc = db.execute(
        """
        SELECT page, slot
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
        LIMIT 1
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

    owned = db.execute(
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

    if owned is not None:
        return {
            "location": "unassigned",
        }

    return None