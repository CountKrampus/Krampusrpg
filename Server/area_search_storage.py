"""
Krampus RPG Area Search Progression
===================================

Powers progression-based area locking on the world exploration map:

- Every successful search ("Search for Pokémon") in an area bumps the
  player's search count for that area.
- An area whose "unlock_searches" requirement has not been met yet is
  locked for that player: the map shows a lock, and the encounter API
  refuses to generate anything there.
- Areas with no requirement (or a requirement <= 0) are always open.

Search counts live in the area_searches table; area requirements live
in Data/areas.json (editable from the admin world config page).
"""

from __future__ import annotations

from .database import get_connection


_SCHEMA = """
CREATE TABLE IF NOT EXISTS area_searches (
    player_id INTEGER NOT NULL,

    area_id   TEXT NOT NULL,

    searches  INTEGER NOT NULL DEFAULT 0,

    last_search_at TEXT,

    PRIMARY KEY (player_id, area_id),

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE
);
"""


def ensure_area_search_schema() -> None:
    with get_connection() as db:
        db.executescript(_SCHEMA)
        db.commit()


def get_area_search_count(player_id: int, area_id: str) -> int:
    """How many times the player has searched this area (0 if never)."""
    ensure_area_search_schema()

    with get_connection() as db:
        row = db.execute(
            """
            SELECT searches FROM area_searches
            WHERE player_id = ? AND area_id = ?
            """,
            (player_id, str(area_id).strip().lower()),
        ).fetchone()

    return int(row["searches"]) if row else 0


def get_area_search_counts(player_id: int) -> dict[str, int]:
    """All of the player's area search counts keyed by area id."""
    ensure_area_search_schema()

    with get_connection() as db:
        rows = db.execute(
            """
            SELECT area_id, searches FROM area_searches
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchall()

    return {str(r["area_id"]): int(r["searches"]) for r in rows}


def record_area_search(player_id: int, area_id: str) -> int:
    """
    Count one search in the area. Returns the new total for the area.
    """
    ensure_area_search_schema()

    area_id = str(area_id).strip().lower()

    with get_connection() as db:
        db.execute(
            """
            INSERT INTO area_searches (player_id, area_id, searches, last_search_at)
            VALUES (?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (player_id, area_id) DO UPDATE SET
                searches = searches + 1,
                last_search_at = CURRENT_TIMESTAMP
            """,
            (player_id, area_id),
        )
        db.commit()

        row = db.execute(
            """
            SELECT searches FROM area_searches
            WHERE player_id = ? AND area_id = ?
            """,
            (player_id, area_id),
        ).fetchone()

    return int(row["searches"]) if row else 0


def get_total_searches(player_id: int) -> int:
    """Searches across all areas — used for global progression gates."""
    return sum(get_area_search_counts(player_id).values())
