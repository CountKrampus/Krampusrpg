"""
Krampus RPG Admin Services

Database and business-logic helpers used by the admin system.

Routes should call functions in this module instead of putting
large amounts of database logic directly inside route handlers.
"""

from __future__ import annotations

from typing import Any

from ..database import get_connection


# ============================================================
# DASHBOARD
# ============================================================

def get_dashboard_stats() -> dict[str, int]:
    """
    Get the basic statistics displayed on the admin dashboard.
    """

    db = get_connection()

    try:
        stats = {
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

        return stats

    finally:
        db.close()


def _count_rows(
    db,
    table_name: str,
) -> int:
    """
    Safely count rows in a known database table.

    This helper intentionally accepts only known table names
    from internal code rather than user input.
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

    row = db.execute(
        f"SELECT COUNT(*) AS count FROM {table_name}"
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

    The current players table does not contain an email column,
    so this query intentionally uses only fields that exist in
    the current database schema.
    """

    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    db = get_connection()

    try:
        rows = db.execute(
            """
            SELECT
                p.id,
                p.username,
                p.display_name,
                p.role_id,
                r.name AS role_name,
                p.created_at,
                p.last_login
            FROM players p
            LEFT JOIN roles r
                ON r.id = p.role_id
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

    The current players table does not contain an email column.
    """

    db = get_connection()

    try:
        row = db.execute(
            """
            SELECT
                p.id,
                p.username,
                p.display_name,
                p.role_id,
                r.name AS role_name,
                p.created_at,
                p.last_login
            FROM players p
            LEFT JOIN roles r
                ON r.id = p.role_id
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

    Returns True when the player was updated.
    """

    db = get_connection()

    try:
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
    """

    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    db = get_connection()

    try:
        rows = db.execute(
            """
            SELECT
                p.id,
                p.unique_id,
                p.owner_id,
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
                p.is_active,
                p.created_at
            FROM pokemon p
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
        row = db.execute(
            """
            SELECT
                p.id,
                p.unique_id,
                p.owner_id,
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
                p.is_active,
                p.created_at
            FROM pokemon p
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
# ITEMS
# ============================================================

def get_player_items(
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Retrieve player inventory records for administration.
    """

    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    db = get_connection()

    try:
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

    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    db = get_connection()

    try:
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
    """
    Retrieve all configured roles.
    """

    db = get_connection()

    try:
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
    """
    Retrieve a single role.
    """

    db = get_connection()

    try:
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
    """
    Retrieve every available permission.
    """

    db = get_connection()

    try:
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
    """
    Retrieve all permissions assigned to a role.
    """

    db = get_connection()

    try:
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

    This operation is intentionally transactional.
    """

    permission_ids = [
        int(permission_id)
        for permission_id in permission_ids
    ]

    db = get_connection()

    try:
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
                INSERT INTO role_permissions (
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

    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    db = get_connection()

    try:
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

    The settings table uses setting_name and setting_value
    in the current database schema.
    """

    db = get_connection()

    try:
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

        db.commit()

    finally:
        db.close()