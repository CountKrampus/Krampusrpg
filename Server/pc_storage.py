from __future__ import annotations

import sqlite3
from typing import Any

from .pokemon_catalog import ensure_catalog_schema


PC_SLOTS_PER_PAGE = 30
MAX_PARTY_SIZE = 6


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
    db: sqlite3.Connection,
) -> None:
    ensure_catalog_schema(db)

    db.executescript(PC_SCHEMA)

    db.commit()


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


def _party_table_exists(
    db: sqlite3.Connection,
) -> bool:
    row = db.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'party'
        """
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
        preferred_page = max(1, int(preferred_page))

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

        for slot in range(1, PC_SLOTS_PER_PAGE + 1):
            if slot not in occupied:
                return preferred_page, slot

    highest_page = get_highest_page(
        db,
        player_id,
    )

    page = highest_page

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

        for slot in range(1, PC_SLOTS_PER_PAGE + 1):
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
    ensure_pc_schema(db)

    if not _pokemon_belongs_to_player(
        db,
        pokemon_id,
        player_id,
    ):
        raise ValueError(
            "That Pokémon does not belong to this player."
        )

    if _pokemon_in_pc(
        db,
        pokemon_id,
        player_id,
    ):
        raise ValueError(
            "That Pokémon is already in the PC."
        )

    if (
        _party_table_exists(db)
        and not _pokemon_in_party(
            db,
            pokemon_id,
            player_id,
        )
    ):
        raise ValueError(
            "A Pokémon must be in the player's party before "
            "it can be deposited."
        )

    if page is None or slot is None:
        page, slot = first_empty_slot(
            db,
            player_id,
            preferred_page=page,
        )
    else:
        page = max(1, int(page))
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

    if _party_table_exists(db):
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

    db.commit()

    return {
        "pokemon_id": pokemon_id,
        "old_page": int(row["page"]),
        "old_slot": int(row["slot"]),
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
        SET page = -1, slot = -1
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

    page = max(1, int(page))

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
        JOIN pokemon p
            ON p.id = pc.pokemon_id
        WHERE
            pc.player_id = ?
            AND pc.page = ?
        ORDER BY pc.slot
        """,
        (
            player_id,
            page,
        ),
    ).fetchall()

    slots: list[dict[str, Any]] = []

    by_slot = {
        int(row["slot"]): dict(row)
        for row in rows
    }

    for slot in range(
        1,
        PC_SLOTS_PER_PAGE + 1,
    ):
        pokemon = by_slot.get(slot)

        slots.append(
            {
                "slot": slot,
                "pokemon": pokemon,
            }
        )

    highest_page = get_highest_page(
        db,
        player_id,
    )

    return {
        "page": page,
        "slots_per_page": PC_SLOTS_PER_PAGE,
        "highest_page": highest_page,
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
    ensure_pc_schema(db)

    conditions = [
        "pc.player_id = ?"
    ]

    parameters: list[Any] = [
        player_id,
    ]

    if name:
        value = f"%{name.strip()}%"

        conditions.append(
            """
            (
                LOWER(s.name) LIKE LOWER(?)
                OR LOWER(s.id) LIKE LOWER(?)
                OR LOWER(COALESCE(p.nickname, '')) LIKE LOWER(?)
            )
            """
        )

        parameters.extend(
            [
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
                FROM pokemon_species_types filter_st
                WHERE filter_st.species_id = p.species_id
                  AND LOWER(filter_st.type_id) = LOWER(?)
            )
            """
        )

        parameters.append(
            type_id.strip()
        )

    parameters.append(
        max(1, min(int(limit), 500))
    )

    rows = db.execute(
        f"""
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

            s.name AS species_name,

            GROUP_CONCAT(
                DISTINCT t.name
            ) AS types

        FROM pc_storage pc

        JOIN pokemon p
            ON p.id = pc.pokemon_id

        JOIN pokemon_species s
            ON s.id = p.species_id

        LEFT JOIN pokemon_species_types st
            ON st.species_id = s.id

        LEFT JOIN pokemon_types t
            ON t.id = st.type_id

        WHERE {" AND ".join(conditions)}

        GROUP BY
            pc.page,
            pc.slot,
            p.id,
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
            s.name

        ORDER BY
            pc.page,
            pc.slot

        LIMIT ?
        """,
        parameters,
    ).fetchall()

    results = []

    for row in rows:
        item = dict(row)

        item["types"] = (
            item["types"].split(",")
            if item.get("types")
            else []
        )

        results.append(item)

    return results


def get_pokemon_location(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> dict[str, int] | None:
    ensure_pc_schema(db)

    row = db.execute(
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

    if row is None:
        return None

    return {
        "page": int(row["page"]),
        "slot": int(row["slot"]),
    }


def is_in_pc(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> bool:
    ensure_pc_schema(db)

    return (
        get_pokemon_location(
            db,
            player_id,
            pokemon_id,
        )
        is not None
    )