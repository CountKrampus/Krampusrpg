"""
Krampus RPG Admin Services

Database and business-logic helpers used by the admin system.

The admin system follows the current Krampus RPG Pokémon architecture:

    Pokémon
       |
       +---- Party
       |
       +---- PC Storage

The legacy pokemon.is_active party system is intentionally NOT used.

Likewise, IVs, EVs, Nature, and permanent Status are not part of the
current Krampus RPG design.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import DATABASE_PATH
from ..database import get_connection

DATA_DIR = Path(__file__).resolve().parents[2] / "Data"
BACKUPS_DIR = Path(__file__).resolve().parents[2] / "Backups"


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _safe_limit(limit: int, maximum: int = 500) -> int:
    """Return a safe pagination limit."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 100

    return max(1, min(limit, maximum))


def _safe_offset(offset: int) -> int:
    """Return a safe pagination offset."""
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0

    return max(0, offset)


def _table_exists(db, table_name: str) -> bool:
    """Check whether a database table exists."""

    row = db.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def _column_exists(
    db,
    table_name: str,
    column_name: str,
) -> bool:
    """Check whether a table contains a column."""

    if not _table_exists(db, table_name):
        return False

    rows = db.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        row["name"] == column_name
        for row in rows
    )


def _optional_column(
    db,
    table_name: str,
    column_name: str,
    alias: str | None = None,
) -> str:
    """
    Return a safe SQL expression for an optional column.
    """

    alias = alias or column_name

    if _column_exists(db, table_name, column_name):
        return f"p.{column_name} AS {alias}"

    return f"NULL AS {alias}"


# ============================================================
# SCHEMA INITIALIZATION FOR ADMIN FEATURES
# ============================================================

def ensure_admin_tables() -> None:
    """
    Ensure optional admin-managed tables (reports, daily_promos, events, settings)
    exist with safe default schemas.
    """
    with get_connection() as db:
        # Reports table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id INTEGER,
                reported_player_id INTEGER,
                reason TEXT NOT NULL,
                details TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                resolved_by INTEGER,
                resolution_notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                FOREIGN KEY (reporter_id) REFERENCES players(id) ON DELETE SET NULL,
                FOREIGN KEY (reported_player_id) REFERENCES players(id) ON DELETE SET NULL,
                FOREIGN KEY (resolved_by) REFERENCES players(id) ON DELETE SET NULL
            )
            """
        )

        # Daily Promos table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_promos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                species_id TEXT NOT NULL,
                species_name TEXT,
                variant TEXT NOT NULL DEFAULT 'normal',
                level INTEGER NOT NULL DEFAULT 5,
                starts_at TEXT,
                ends_at TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                claim_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Events table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                starts_at TEXT,
                ends_at TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Settings table default seed
        if _table_exists(db, "settings"):
            default_settings = [
                ("site_name", "Krampus RPG", "The display name of the Krampus RPG website."),
                ("maintenance_mode", "0", "When enabled (1), only staff accounts can access the game."),
                ("registration_enabled", "1", "Controls whether new player registrations are accepted."),
                ("exp_multiplier", "1.0", "Global experience gain multiplier for battles."),
                ("shiny_rate_multiplier", "1.0", "Global shiny encounter rate multiplier."),
                ("daily_promo_enabled", "1", "Whether daily Pokémon promo claims are active."),
            ]
            has_desc = _column_exists(db, "settings", "description")
            for name, val, desc in default_settings:
                row = db.execute(
                    "SELECT 1 FROM settings WHERE setting_name = ?", (name,)
                ).fetchone()
                if not row:
                    if has_desc:
                        db.execute(
                            "INSERT INTO settings (setting_name, setting_value, description) VALUES (?, ?, ?)",
                            (name, val, desc),
                        )
                    else:
                        db.execute(
                            "INSERT INTO settings (setting_name, setting_value) VALUES (?, ?)",
                            (name, val),
                        )

        db.commit()


# ============================================================
# DASHBOARD
# ============================================================

def get_dashboard_stats() -> dict[str, Any]:
    """
    Get comprehensive statistics displayed on the admin dashboard.
    """
    ensure_admin_tables()

    db = get_connection()

    try:
        stats: dict[str, Any] = {
            "players": _count_rows(db, "players"),
            "pokemon": _count_rows(db, "pokemon"),
            "items": _count_rows(db, "player_items"),
            "quests": _count_rows(db, "quests"),
            "party_pokemon": _count_rows(db, "party"),
            "pc_pokemon": _count_rows(db, "pc_storage"),
            "active_promos": 0,
            "active_events": 0,
            "open_reports": 0,
            "total_money": 0,
            "roles": _count_rows(db, "roles"),
        }

        if _table_exists(db, "daily_promos"):
            row = db.execute("SELECT COUNT(*) AS count FROM daily_promos WHERE active = 1").fetchone()
            if row:
                stats["active_promos"] = int(row["count"])

        if _table_exists(db, "events"):
            row = db.execute("SELECT COUNT(*) AS count FROM events WHERE active = 1").fetchone()
            if row:
                stats["active_events"] = int(row["count"])

        if _table_exists(db, "reports"):
            row = db.execute("SELECT COUNT(*) AS count FROM reports WHERE status = 'open'").fetchone()
            if row:
                stats["open_reports"] = int(row["count"])

        if _table_exists(db, "player_progress") and _column_exists(db, "player_progress", "money"):
            row = db.execute("SELECT SUM(money) AS total FROM player_progress").fetchone()
            if row and row["total"] is not None:
                stats["total_money"] = int(row["total"])

        return stats

    finally:
        db.close()


def _count_rows(
    db,
    table_name: str,
) -> int:
    """
    Safely count rows in a known database table.
    """

    allowed_tables = {
        "players",
        "pokemon",
        "player_items",
        "quests",
        "party",
        "pc_storage",
        "roles",
        "permissions",
        "audit_log",
        "reports",
        "daily_promos",
        "events",
        "settings",
    }

    if table_name not in allowed_tables:
        return 0

    if not _table_exists(db, table_name):
        return 0

    row = db.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM {table_name}
        """
    ).fetchone()

    return int(row["count"]) if row else 0


# ============================================================
# PLAYERS
# ============================================================

def get_players(
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Retrieve players for the admin player-management page.
    """
    return search_players(query=None, role_name=None, limit=limit, offset=offset)


def search_players(
    query: str | None = None,
    role_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Search and filter player accounts.
    """
    limit = _safe_limit(limit)
    offset = _safe_offset(offset)

    db = get_connection()

    try:
        role_join = ""
        role_select = "NULL AS role_name"

        if _table_exists(db, "roles"):
            role_join = """
                LEFT JOIN roles r
                    ON r.id = p.role_id
            """
            role_select = "r.name AS role_name"

        role_id = (
            "p.role_id AS role_id"
            if _column_exists(db, "players", "role_id")
            else "NULL AS role_id"
        )

        display_name = (
            "p.display_name AS display_name"
            if _column_exists(db, "players", "display_name")
            else "p.username AS display_name"
        )

        last_login = (
            "p.last_login AS last_login"
            if _column_exists(db, "players", "last_login")
            else "NULL AS last_login"
        )

        where_clauses: list[str] = []
        params: list[Any] = []

        if query and query.strip():
            q = f"%{query.strip()}%"
            where_clauses.append("(p.username LIKE ? OR p.display_name LIKE ?)")
            params.extend([q, q])

        if role_name and role_name.strip() and _table_exists(db, "roles"):
            where_clauses.append("r.name = ?")
            params.append(role_name.strip())

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        rows = db.execute(
            f"""
            SELECT
                p.id,
                p.username,
                {display_name},
                {role_id},
                {role_select},
                p.created_at,
                {last_login}
            FROM players p
            {role_join}
            {where_sql}
            ORDER BY p.id DESC
            LIMIT ?
            OFFSET ?
            """,
            (
                *params,
                limit,
                offset,
            ),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        db.close()


def get_player(
    player_id: int,
) -> dict[str, Any] | None:
    """
    Retrieve a single player by ID.
    """

    db = get_connection()

    try:
        role_join = ""
        role_name = "NULL AS role_name"

        if _table_exists(db, "roles"):
            role_join = """
                LEFT JOIN roles r
                    ON r.id = p.role_id
            """
            role_name = "r.name AS role_name"

        role_id = (
            "p.role_id AS role_id"
            if _column_exists(db, "players", "role_id")
            else "NULL AS role_id"
        )

        display_name = (
            "p.display_name AS display_name"
            if _column_exists(db, "players", "display_name")
            else "p.username AS display_name"
        )

        last_login = (
            "p.last_login AS last_login"
            if _column_exists(db, "players", "last_login")
            else "NULL AS last_login"
        )

        row = db.execute(
            f"""
            SELECT
                p.id,
                p.username,
                {display_name},
                {role_id},
                {role_name},
                p.created_at,
                {last_login}
            FROM players p
            {role_join}
            WHERE p.id = ?
            """,
            (player_id,),
        ).fetchone()

        if row is None:
            return None

        return dict(row)

    finally:
        db.close()


def get_player_details(player_id: int) -> dict[str, Any] | None:
    """
    Retrieve full player profile for administrative inspection.
    """
    player = get_player(player_id)
    if not player:
        return None

    db = get_connection()
    try:
        progress = None
        if _table_exists(db, "player_progress"):
            p_row = db.execute(
                """
                SELECT current_region, current_area, money, badges
                FROM player_progress
                WHERE player_id = ?
                """,
                (player_id,),
            ).fetchone()
            if p_row:
                progress = dict(p_row)

        pokemon_count = get_player_pokemon_count(player_id)
        party_count = get_player_party_count(player_id)
        pc_count = get_player_pc_count(player_id)

        # Fetch current party
        party_pokemon: list[dict[str, Any]] = []
        if _table_exists(db, "party") and _table_exists(db, "pokemon"):
            p_rows = db.execute(
                """
                SELECT p.id, p.species_id, p.nickname, p.level, p.shiny, p.variant, pt.slot
                FROM party pt
                JOIN pokemon p ON p.id = pt.pokemon_id
                WHERE pt.player_id = ?
                ORDER BY pt.slot ASC
                """,
                (player_id,),
            ).fetchall()
            party_pokemon = [dict(r) for r in p_rows]

        return {
            **player,
            "progress": progress or {"money": 0, "badges": 0, "current_region": "krampus", "current_area": "krampus_town"},
            "pokemon_count": pokemon_count,
            "party_count": party_count,
            "pc_count": pc_count,
            "party": party_pokemon,
        }
    finally:
        db.close()


def update_player_role(
    player_id: int,
    role_id: int,
) -> bool:
    """
    Change a player's assigned role.
    """

    db = get_connection()

    try:
        if not _column_exists(
            db,
            "players",
            "role_id",
        ):
            return False

        if _table_exists(db, "roles"):
            role = db.execute(
                """
                SELECT id
                FROM roles
                WHERE id = ?
                """,
                (role_id,),
            ).fetchone()

            if role is None:
                return False

        cursor = db.execute(
            """
            UPDATE players
            SET role_id = ?
            WHERE id = ?
            """,
            (
                role_id,
                player_id,
            ),
        )

        db.commit()

        return cursor.rowcount > 0

    finally:
        db.close()


# ============================================================
# POKÉMON
# ============================================================

def get_pokemon(
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Retrieve Pokémon for the admin Pokémon page.

    Party membership is determined from the party table.
    PC membership is determined from the pc_storage table.
    """

    limit = _safe_limit(limit)
    offset = _safe_offset(offset)

    db = get_connection()

    try:
        party_join = ""
        party_columns = """
            0 AS in_party,
            NULL AS party_slot
        """

        if _table_exists(db, "party"):
            party_join = """
                LEFT JOIN party pt
                    ON pt.pokemon_id = p.id
            """
            party_columns = """
                CASE
                    WHEN pt.id IS NULL THEN 0
                    ELSE 1
                END AS in_party,
                pt.slot AS party_slot
            """

        pc_join = ""
        pc_columns = """
            0 AS in_pc,
            NULL AS pc_page,
            NULL AS pc_slot
        """

        if _table_exists(db, "pc_storage"):
            pc_join = """
                LEFT JOIN pc_storage pc
                    ON pc.pokemon_id = p.id
            """
            pc_columns = """
                CASE
                    WHEN pc.id IS NULL THEN 0
                    ELSE 1
                END AS in_pc,
                pc.page AS pc_page,
                pc.slot AS pc_slot
            """

        rows = db.execute(
            f"""
            SELECT
                p.id,
                p.unique_id,
                p.owner_id,
                pl.username AS username,
                p.species_id,
                p.nickname,
                p.level,
                p.experience,
                p.gender,
                p.shiny,
                p.variant,
                p.current_hp,
                p.max_hp,

                {party_columns},
                {pc_columns},

                p.created_at

            FROM pokemon p
            LEFT JOIN players pl
                ON pl.id = p.owner_id

            {party_join}
            {pc_join}

            ORDER BY p.id DESC

            LIMIT ?
            OFFSET ?
            """,
            (
                limit,
                offset,
            ),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        db.close()


def get_pokemon_by_id(
    pokemon_id: int,
) -> dict[str, Any] | None:
    """
    Retrieve one Pokémon by database ID.
    """

    db = get_connection()

    try:
        party_join = ""
        party_columns = """
            0 AS in_party,
            NULL AS party_slot
        """

        if _table_exists(db, "party"):
            party_join = """
                LEFT JOIN party pt
                    ON pt.pokemon_id = p.id
            """
            party_columns = """
                CASE
                    WHEN pt.id IS NULL THEN 0
                    ELSE 1
                END AS in_party,
                pt.slot AS party_slot
            """

        pc_join = ""
        pc_columns = """
            0 AS in_pc,
            NULL AS pc_page,
            NULL AS pc_slot
        """

        if _table_exists(db, "pc_storage"):
            pc_join = """
                LEFT JOIN pc_storage pc
                    ON pc.pokemon_id = p.id
            """
            pc_columns = """
                CASE
                    WHEN pc.id IS NULL THEN 0
                    ELSE 1
                END AS in_pc,
                pc.page AS pc_page,
                pc.slot AS pc_slot
            """

        row = db.execute(
            f"""
            SELECT
                p.id,
                p.unique_id,
                p.owner_id,
                pl.username AS username,
                p.species_id,
                p.nickname,
                p.level,
                p.experience,
                p.gender,
                p.shiny,
                p.variant,
                p.current_hp,
                p.max_hp,

                {party_columns},
                {pc_columns},

                p.created_at

            FROM pokemon p
            LEFT JOIN players pl
                ON pl.id = p.owner_id

            {party_join}
            {pc_join}

            WHERE p.id = ?
            """,
            (pokemon_id,),
        ).fetchone()

        if row is None:
            return None

        return dict(row)

    finally:
        db.close()


def get_pokemon_location(
    pokemon_id: int,
) -> dict[str, Any]:
    """
    Determine where a Pokémon currently resides (party, pc, or unassigned).
    """

    db = get_connection()

    try:
        if _table_exists(db, "party"):
            row = db.execute(
                """
                SELECT
                    slot
                FROM party
                WHERE pokemon_id = ?
                LIMIT 1
                """,
                (pokemon_id,),
            ).fetchone()

            if row is not None:
                return {
                    "location": "party",
                    "slot": row["slot"],
                }

        if _table_exists(db, "pc_storage"):
            row = db.execute(
                """
                SELECT
                    page,
                    slot
                FROM pc_storage
                WHERE pokemon_id = ?
                LIMIT 1
                """,
                (pokemon_id,),
            ).fetchone()

            if row is not None:
                return {
                    "location": "pc",
                    "page": row["page"],
                    "slot": row["slot"],
                }

        return {
            "location": "unassigned",
        }

    finally:
        db.close()


def get_player_pokemon_count(
    player_id: int,
) -> int:
    """Return the total number of Pokémon owned by a player."""

    db = get_connection()

    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pokemon
            WHERE owner_id = ?
            """,
            (player_id,),
        ).fetchone()

        return int(row["count"]) if row else 0

    finally:
        db.close()


def get_player_party_count(
    player_id: int,
) -> int:
    """Return the number of Pokémon currently in the player's party."""

    db = get_connection()

    try:
        if not _table_exists(db, "party"):
            return 0

        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM party
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        return int(row["count"]) if row else 0

    finally:
        db.close()


def get_player_pc_count(
    player_id: int,
) -> int:
    """Return the number of Pokémon currently stored in the PC."""

    db = get_connection()

    try:
        if not _table_exists(db, "pc_storage"):
            return 0

        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pc_storage
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        return int(row["count"]) if row else 0

    finally:
        db.close()


# ============================================================
# DIRECT POKÉMON ASSIGNMENT & CATALOG HELPERS
# ============================================================

def get_available_species() -> list[dict[str, Any]]:
    """
    Return a list of available Pokémon species for selection in the admin panel.
    Checks database table first, falls back to Data/pokemon.json.
    """
    db = get_connection()
    try:
        if _table_exists(db, "pokemon_species"):
            rows = db.execute(
                """
                SELECT id, name
                FROM pokemon_species
                WHERE is_active = 1
                ORDER BY name ASC
                """
            ).fetchall()
            if rows:
                return [{"id": r["id"], "name": r["name"]} for r in rows]
    except Exception:
        pass
    finally:
        db.close()

    # Fallback to Data/pokemon.json
    json_path = DATA_DIR / "pokemon.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return sorted(
                    [{"id": str(p["id"]), "name": p.get("name", str(p["id"]).title())} for p in data],
                    key=lambda x: x["name"],
                )
        except Exception:
            pass

    return [
        {"id": "bulbasaur", "name": "Bulbasaur"},
        {"id": "charmander", "name": "Charmander"},
        {"id": "squirtle", "name": "Squirtle"},
        {"id": "pikachu", "name": "Pikachu"},
    ]


def get_available_variants() -> list[dict[str, str]]:
    """
    Return available Pokémon variants.

    Reads from the live pokemon_variants table (the same table
    Server/services.py:get_variant() resolves against when a Pokémon is
    actually created) rather than Data/variants.json, which is a
    separate, disconnected file that only ever had the original 7
    variants and had drifted out of sync with the 13 additional
    colors (amethyst, azure, copper, crimson, frost, inferno, lime,
    midnight, obsidian, pearl, rose, toxic, violet) that already have
    full sprite art and are registered in the database. Falls back to
    Data/variants.json, then a hardcoded list, only if the database is
    somehow unavailable.
    """
    try:
        from ..services import get_all_variants

        db_variants = get_all_variants()

        if db_variants:
            return [
                {
                    "id": v["id"],
                    "name": v.get("name", str(v["id"]).title()),
                }
                for v in db_variants
            ]
    except Exception:
        pass

    json_path = DATA_DIR / "variants.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [{"id": v["id"], "name": v.get("name", v["id"].title())} for v in data]
        except Exception:
            pass

    return [
        {"id": "normal", "name": "Normal"},
        {"id": "ruby", "name": "Ruby"},
        {"id": "sapphire", "name": "Sapphire"},
        {"id": "emerald", "name": "Emerald"},
        {"id": "gold", "name": "Gold"},
        {"id": "silver", "name": "Silver"},
        {"id": "undead", "name": "Undead"},
    ]


def admin_assign_pokemon(
    owner_id: int,
    species_id: str,
    level: int = 5,
    shiny: bool = False,
    variant: str = "normal",
    nickname: str | None = None,
) -> dict[str, Any]:
    """
    Directly assign a Pokémon to a player from the admin dashboard.

    Integrates with Krampus RPG core storage architecture:
    Places the new Pokémon in the player's Party if party has space (< 6),
    otherwise stores in the player's PC box.
    """
    # Verify player exists
    player = get_player(owner_id)
    if not player:
        raise ValueError(f"Player ID #{owner_id} does not exist.")

    # Clamp level
    level = max(1, min(100, int(level)))

    # Use the game's official create_pokemon service
    from ..services import create_pokemon

    new_mon = create_pokemon(
        owner_id=owner_id,
        species_id=species_id,
        level=level,
        shiny=bool(shiny),
        variant=variant or "normal",
        nickname=nickname.strip() if nickname and nickname.strip() else None,
        auto_store=True,
    )

    if not new_mon:
        raise RuntimeError("Failed to create Pokémon.")

    # Fetch storage location
    location = get_pokemon_location(new_mon["id"])

    return {
        "pokemon": new_mon,
        "location": location,
        "owner": player,
    }


# ============================================================
# ITEMS
# ============================================================

def get_player_items(
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Retrieve player inventory records for administration.
    """

    limit = _safe_limit(limit)
    offset = _safe_offset(offset)

    db = get_connection()

    try:
        if not _table_exists(db, "player_items"):
            return []

        rows = db.execute(
            """
            SELECT *
            FROM player_items
            ORDER BY player_id ASC
            LIMIT ?
            OFFSET ?
            """,
            (
                limit,
                offset,
            ),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        db.close()


# ============================================================
# QUESTS
# ============================================================

def get_quests(
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Retrieve quests for the admin quest page.
    """

    limit = _safe_limit(limit)
    offset = _safe_offset(offset)

    db = get_connection()

    try:
        if not _table_exists(db, "quests"):
            return []

        rows = db.execute(
            """
            SELECT *
            FROM quests
            ORDER BY id DESC
            LIMIT ?
            OFFSET ?
            """,
            (
                limit,
                offset,
            ),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        db.close()


# ============================================================
# ROLE MANAGEMENT
# ============================================================

def get_roles() -> list[dict[str, Any]]:
    """Retrieve all configured roles with permission counts."""

    db = get_connection()

    try:
        if not _table_exists(db, "roles"):
            return []

        if _table_exists(db, "role_permissions"):
            rows = db.execute(
                """
                SELECT
                    r.id,
                    r.name,
                    r.description,
                    COUNT(rp.permission_id) AS permission_count
                FROM roles r
                LEFT JOIN role_permissions rp
                    ON rp.role_id = r.id
                GROUP BY r.id, r.name, r.description
                ORDER BY r.id ASC
                """
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT
                    id,
                    name,
                    description,
                    0 AS permission_count
                FROM roles
                ORDER BY id ASC
                """
            ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        db.close()


def get_role(
    role_id: int,
) -> dict[str, Any] | None:
    """Retrieve a single role."""

    db = get_connection()

    try:
        if not _table_exists(db, "roles"):
            return None

        row = db.execute(
            """
            SELECT
                id,
                name,
                description
            FROM roles
            WHERE id = ?
            """,
            (role_id,),
        ).fetchone()

        if row is None:
            return None

        return dict(row)

    finally:
        db.close()


# ============================================================
# PERMISSION MANAGEMENT
# ============================================================

def get_permissions() -> list[dict[str, Any]]:
    """Retrieve every available permission."""

    db = get_connection()

    try:
        if not _table_exists(db, "permissions"):
            return []

        rows = db.execute(
            """
            SELECT
                id,
                permission_name,
                description
            FROM permissions
            ORDER BY permission_name ASC
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        db.close()


def get_role_permissions(
    role_id: int,
) -> list[dict[str, Any]]:
    """Retrieve all permissions assigned to a role."""

    db = get_connection()

    try:
        if not (
            _table_exists(db, "permissions")
            and _table_exists(db, "role_permissions")
        ):
            return []

        rows = db.execute(
            """
            SELECT
                p.id,
                p.permission_name,
                p.description
            FROM permissions p
            INNER JOIN role_permissions rp
                ON rp.permission_id = p.id
            WHERE rp.role_id = ?
            ORDER BY p.permission_name ASC
            """,
            (role_id,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        db.close()


def set_role_permissions(
    role_id: int,
    permission_ids: list[int],
) -> None:
    """
    Replace all permissions assigned to a role.
    """

    permission_ids = [
        int(permission_id)
        for permission_id in permission_ids
    ]

    db = get_connection()

    try:
        if not _table_exists(db, "role_permissions"):
            raise RuntimeError(
                "role_permissions table does not exist."
            )

        db.execute(
            """
            DELETE FROM role_permissions
            WHERE role_id = ?
            """,
            (role_id,),
        )

        for permission_id in permission_ids:
            db.execute(
                """
                INSERT OR IGNORE INTO role_permissions (
                    role_id,
                    permission_id
                )
                VALUES (?, ?)
                """,
                (
                    role_id,
                    permission_id,
                ),
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ============================================================
# AUDIT LOG
# ============================================================

def get_audit_logs(
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Retrieve administrative audit log entries, joined with staff usernames.
    """
    from .audit import get_audit_log
    return get_audit_log(limit=limit, offset=offset)


# ============================================================
# SITE SETTINGS
# ============================================================

def get_setting(
    setting_name: str,
    default: Any = None,
) -> Any:
    """
    Retrieve a site setting.
    """

    db = get_connection()

    try:
        if not _table_exists(db, "settings"):
            return default

        row = db.execute(
            """
            SELECT setting_value
            FROM settings
            WHERE setting_name = ?
            """,
            (setting_name,),
        ).fetchone()

        if row is None:
            return default

        return row["setting_value"]

    finally:
        db.close()


def set_setting(
    setting_name: str,
    value: Any,
) -> None:
    """
    Create or update a site setting.
    """

    db = get_connection()

    try:
        if not _table_exists(db, "settings"):
            raise RuntimeError(
                "settings table does not exist."
            )

        if _column_exists(
            db,
            "settings",
            "updated_at",
        ):
            db.execute(
                """
                INSERT INTO settings (
                    setting_name,
                    setting_value
                )
                VALUES (?, ?)
                ON CONFLICT(setting_name)
                DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    setting_name,
                    str(value),
                ),
            )
        else:
            db.execute(
                """
                INSERT INTO settings (
                    setting_name,
                    setting_value
                )
                VALUES (?, ?)
                ON CONFLICT(setting_name)
                DO UPDATE SET
                    setting_value = excluded.setting_value
                """,
                (
                    setting_name,
                    str(value),
                ),
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_all_settings() -> list[dict[str, Any]]:
    """
    Retrieve all configurable site settings.
    """
    ensure_admin_tables()

    db = get_connection()
    try:
        if not _table_exists(db, "settings"):
            return []

        has_desc = _column_exists(db, "settings", "description")
        desc_col = "description" if has_desc else "'' AS description"

        rows = db.execute(
            f"""
            SELECT setting_name, setting_value, {desc_col}
            FROM settings
            ORDER BY setting_name ASC
            """
        ).fetchall()

        return [
            {
                "name": row["setting_name"],
                "value": row["setting_value"],
                "description": row["description"] or "No description available.",
            }
            for row in rows
        ]
    finally:
        db.close()


def update_settings(settings_dict: dict[str, Any]) -> None:
    """
    Save multiple site settings simultaneously.
    """
    for name, value in settings_dict.items():
        set_setting(name, value)


# ============================================================
# REPORTS MANAGEMENT
# ============================================================

def get_reports(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Retrieve moderation reports, optionally filtered by status.
    """
    ensure_admin_tables()

    limit = _safe_limit(limit)
    offset = _safe_offset(offset)

    db = get_connection()
    try:
        where_sql = ""
        params: list[Any] = []

        if status and status.strip():
            where_sql = "WHERE r.status = ?"
            params.append(status.strip().lower())

        rows = db.execute(
            f"""
            SELECT
                r.id,
                r.reporter_id,
                p_rep.username AS reporter_username,
                r.reported_player_id,
                p_tgt.username AS reported_username,
                r.reason,
                r.details,
                r.status,
                r.resolved_by,
                p_staff.username AS resolved_by_username,
                r.resolution_notes,
                r.created_at,
                r.updated_at
            FROM reports r
            LEFT JOIN players p_rep ON p_rep.id = r.reporter_id
            LEFT JOIN players p_tgt ON p_tgt.id = r.reported_player_id
            LEFT JOIN players p_staff ON p_staff.id = r.resolved_by
            {where_sql}
            ORDER BY r.id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        db.close()


def get_report_by_id(report_id: int) -> dict[str, Any] | None:
    """Retrieve a single report."""
    ensure_admin_tables()
    db = get_connection()
    try:
        row = db.execute(
            """
            SELECT
                r.id,
                r.reporter_id,
                p_rep.username AS reporter_username,
                r.reported_player_id,
                p_tgt.username AS reported_username,
                r.reason,
                r.details,
                r.status,
                r.resolved_by,
                p_staff.username AS resolved_by_username,
                r.resolution_notes,
                r.created_at,
                r.updated_at
            FROM reports r
            LEFT JOIN players p_rep ON p_rep.id = r.reporter_id
            LEFT JOIN players p_tgt ON p_tgt.id = r.reported_player_id
            LEFT JOIN players p_staff ON p_staff.id = r.resolved_by
            WHERE r.id = ?
            """,
            (report_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def update_report_status(
    report_id: int,
    status: str,
    staff_player_id: int | None = None,
    resolution_notes: str | None = None,
) -> bool:
    """
    Update a moderation report's status (open, resolved, dismissed).
    """
    ensure_admin_tables()
    status = status.strip().lower()
    if status not in {"open", "resolved", "dismissed"}:
        raise ValueError(f"Invalid report status: {status}")

    now = datetime.now(timezone.utc).isoformat()
    db = get_connection()
    try:
        cursor = db.execute(
            """
            UPDATE reports
            SET status = ?,
                resolved_by = ?,
                resolution_notes = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (status, staff_player_id, resolution_notes, now, report_id),
        )
        db.commit()
        return cursor.rowcount > 0
    finally:
        db.close()


def create_report(
    reporter_id: int | None,
    reported_player_id: int | None,
    reason: str,
    details: str | None = None,
) -> int:
    """Create a new report."""
    ensure_admin_tables()
    now = datetime.now(timezone.utc).isoformat()
    db = get_connection()
    try:
        cursor = db.execute(
            """
            INSERT INTO reports (
                reporter_id,
                reported_player_id,
                reason,
                details,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, 'open', ?)
            """,
            (reporter_id, reported_player_id, reason, details, now),
        )
        db.commit()
        return int(cursor.lastrowid)
    finally:
        db.close()


# ============================================================
# PROMOS & EVENTS MANAGEMENT
# ============================================================

def get_promos(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Retrieve daily promos."""
    ensure_admin_tables()
    limit = _safe_limit(limit)
    offset = _safe_offset(offset)
    db = get_connection()
    try:
        rows = db.execute(
            """
            SELECT *
            FROM daily_promos
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def create_promo(
    species_id: str,
    variant: str = "normal",
    level: int = 5,
    starts_at: str | None = None,
    ends_at: str | None = None,
    active: bool = True,
) -> int:
    """Create a new daily promo."""
    ensure_admin_tables()
    level = max(1, min(100, int(level)))
    db = get_connection()
    try:
        cursor = db.execute(
            """
            INSERT INTO daily_promos (
                species_id,
                species_name,
                variant,
                level,
                starts_at,
                ends_at,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                species_id,
                species_id.title(),
                variant or "normal",
                level,
                starts_at,
                ends_at,
                1 if active else 0,
            ),
        )
        db.commit()
        return int(cursor.lastrowid)
    finally:
        db.close()


def toggle_promo_active(promo_id: int) -> bool:
    """Toggle a promo's active state."""
    ensure_admin_tables()
    db = get_connection()
    try:
        cursor = db.execute(
            """
            UPDATE daily_promos
            SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END
            WHERE id = ?
            """,
            (promo_id,),
        )
        db.commit()
        return cursor.rowcount > 0
    finally:
        db.close()


def get_events(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Retrieve game events."""
    ensure_admin_tables()
    limit = _safe_limit(limit)
    offset = _safe_offset(offset)
    db = get_connection()
    try:
        rows = db.execute(
            """
            SELECT *
            FROM events
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def create_event(
    name: str,
    description: str = "",
    starts_at: str | None = None,
    ends_at: str | None = None,
    active: bool = True,
) -> int:
    """Create a game event."""
    ensure_admin_tables()
    db = get_connection()
    try:
        cursor = db.execute(
            """
            INSERT INTO events (
                name,
                description,
                starts_at,
                ends_at,
                active
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, description, starts_at, ends_at, 1 if active else 0),
        )
        db.commit()
        return int(cursor.lastrowid)
    finally:
        db.close()


def toggle_event_active(event_id: int) -> bool:
    """Toggle an event's active state."""
    ensure_admin_tables()
    db = get_connection()
    try:
        cursor = db.execute(
            """
            UPDATE events
            SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END
            WHERE id = ?
            """,
            (event_id,),
        )
        db.commit()
        return cursor.rowcount > 0
    finally:
        db.close()


# ============================================================
# DATABASE DIAGNOSTICS & BACKUPS
# ============================================================

def get_database_diagnostics() -> dict[str, Any]:
    """
    Retrieve database engine status, size, and table row counts.
    """
    db = get_connection()
    try:
        sqlite_version = sqlite3.sqlite_version

        # Get file size
        file_size_bytes = 0
        if DATABASE_PATH and os.path.exists(DATABASE_PATH):
            file_size_bytes = os.path.getsize(DATABASE_PATH)

        file_size_kb = round(file_size_bytes / 1024, 2)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

        # Main table counts
        table_counts: dict[str, int] = {}
        tables = [
            "players", "pokemon", "party", "pc_storage", "player_items",
            "items", "quests", "player_quests", "roles", "permissions",
            "audit_log", "reports", "daily_promos", "events", "settings"
        ]
        for t in tables:
            table_counts[t] = _count_rows(db, t)

        return {
            "version": sqlite_version,
            "path": str(DATABASE_PATH),
            "size_bytes": file_size_bytes,
            "size_kb": file_size_kb,
            "size_mb": file_size_mb,
            "tables": table_counts,
        }
    finally:
        db.close()


def run_database_integrity_check() -> str:
    """
    Execute PRAGMA integrity_check and return the result.
    """
    db = get_connection()
    try:
        row = db.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"
    finally:
        db.close()


def create_database_backup() -> str:
    """
    Create a timestamped copy of the SQLite database in Backups/.
    """
    if not DATABASE_PATH or not os.path.exists(DATABASE_PATH):
        raise FileNotFoundError("Database file does not exist.")

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"krampus_backup_{timestamp}.sqlite3"
    backup_dest = BACKUPS_DIR / backup_filename

    shutil.copy2(DATABASE_PATH, backup_dest)

    return backup_filename