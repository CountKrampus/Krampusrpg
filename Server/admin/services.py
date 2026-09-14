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

from typing import Any

from ..database import get_connection


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

    This allows the admin system to work against databases that may
    still contain older schemas during migration.
    """

    alias = alias or column_name

    if _column_exists(db, table_name, column_name):
        return f"p.{column_name} AS {alias}"

    return f"NULL AS {alias}"


# ============================================================
# DASHBOARD
# ============================================================

def get_dashboard_stats() -> dict[str, int]:
    """
    Get the basic statistics displayed on the admin dashboard.
    """

    db = get_connection()

    try:
        return {
            "players": _count_rows(
                db,
                "players",
            ),
            "pokemon": _count_rows(
                db,
                "pokemon",
            ),
            "items": _count_rows(
                db,
                "player_items",
            ),
            "quests": _count_rows(
                db,
                "quests",
            ),
        }

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
    }

    if table_name not in allowed_tables:
        raise ValueError(
            f"Invalid table name: {table_name}"
        )

    if not _table_exists(db, table_name):
        return 0

    row = db.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM {table_name}
        """
    ).fetchone()

    return int(row["count"])


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

    limit = _safe_limit(limit)
    offset = _safe_offset(offset)

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

        rows = db.execute(
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

    Party and PC location are calculated from their respective
    database tables.
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


# ============================================================
# POKÉMON LOCATION
# ============================================================

def get_pokemon_location(
    pokemon_id: int,
) -> dict[str, Any]:
    """
    Determine where a Pokémon currently resides.

    Possible locations:

        party
        pc
        unassigned

    An unassigned Pokémon should normally only exist temporarily
    during migration or recovery.
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


# ============================================================
# POKÉMON STORAGE SUMMARY
# ============================================================

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

        return int(row["count"])

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

        return int(row["count"])

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

        return int(row["count"])

    finally:
        db.close()


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
    """Retrieve all configured roles."""

    db = get_connection()

    try:
        if not _table_exists(db, "roles"):
            return []

        rows = db.execute(
            """
            SELECT
                id,
                name,
                description
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

    This operation is transactional.
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
    Retrieve administrative audit log entries.
    """

    limit = _safe_limit(limit)
    offset = _safe_offset(offset)

    db = get_connection()

    try:
        if not _table_exists(db, "audit_log"):
            return []

        rows = db.execute(
            """
            SELECT *
            FROM audit_log
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