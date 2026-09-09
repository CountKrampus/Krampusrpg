"""
Krampus RPG Admin Permission System

Centralized role and permission handling for the admin system.

Roles:
    player
    moderator
    event_staff
    admin
    webmaster

Important:
    Permission checks are enforced server-side.

    Webmaster is the highest-level role and automatically has
    unrestricted access to every current and future permission.
"""

from functools import wraps
from typing import Callable, Any

from flask import abort, session


# ============================================================
# ROLE CONSTANTS
# ============================================================

ROLE_PLAYER = "player"
ROLE_MODERATOR = "moderator"
ROLE_EVENT_STAFF = "event_staff"
ROLE_ADMIN = "admin"
ROLE_WEBMASTER = "webmaster"


STAFF_ROLES = {
    ROLE_MODERATOR,
    ROLE_EVENT_STAFF,
    ROLE_ADMIN,
    ROLE_WEBMASTER,
}


# ============================================================
# PERMISSION CONSTANTS
# ============================================================

PERMISSION_ADMIN_DASHBOARD = "admin.dashboard"

PERMISSION_PLAYERS_VIEW = "admin.players.view"
PERMISSION_PLAYERS_EDIT = "admin.players.edit"

PERMISSION_POKEMON_VIEW = "admin.pokemon.view"
PERMISSION_POKEMON_EDIT = "admin.pokemon.edit"

PERMISSION_ITEMS_VIEW = "admin.items.view"
PERMISSION_ITEMS_EDIT = "admin.items.edit"

PERMISSION_QUESTS_VIEW = "admin.quests.view"
PERMISSION_QUESTS_EDIT = "admin.quests.edit"

PERMISSION_PROMOS_VIEW = "admin.promos.view"
PERMISSION_PROMOS_EDIT = "admin.promos.edit"

PERMISSION_EVENTS_VIEW = "admin.events.view"
PERMISSION_EVENTS_EDIT = "admin.events.edit"

PERMISSION_MODERATION_PLAYERS = "moderation.players"
PERMISSION_MODERATION_REPORTS = "moderation.reports"

PERMISSION_REPORTS_VIEW = "admin.reports.view"

PERMISSION_AUDIT_LOG = "admin.audit_log"

PERMISSION_ROLES = "admin.roles"

PERMISSION_SETTINGS = "admin.settings"

PERMISSION_DATABASE = "admin.database"


# ============================================================
# ALL PERMISSIONS
# ============================================================

ALL_PERMISSIONS = {
    PERMISSION_ADMIN_DASHBOARD,

    PERMISSION_PLAYERS_VIEW,
    PERMISSION_PLAYERS_EDIT,

    PERMISSION_POKEMON_VIEW,
    PERMISSION_POKEMON_EDIT,

    PERMISSION_ITEMS_VIEW,
    PERMISSION_ITEMS_EDIT,

    PERMISSION_QUESTS_VIEW,
    PERMISSION_QUESTS_EDIT,

    PERMISSION_PROMOS_VIEW,
    PERMISSION_PROMOS_EDIT,

    PERMISSION_EVENTS_VIEW,
    PERMISSION_EVENTS_EDIT,

    PERMISSION_MODERATION_PLAYERS,
    PERMISSION_MODERATION_REPORTS,

    PERMISSION_REPORTS_VIEW,

    PERMISSION_AUDIT_LOG,

    PERMISSION_ROLES,

    PERMISSION_SETTINGS,

    PERMISSION_DATABASE,
}


# ============================================================
# ALL ROLES
# ============================================================

ALL_ROLES = {
    ROLE_PLAYER,
    ROLE_MODERATOR,
    ROLE_EVENT_STAFF,
    ROLE_ADMIN,
    ROLE_WEBMASTER,
}


# ============================================================
# ROLE VALIDATION
# ============================================================

def is_valid_role(role_name: str) -> bool:
    """
    Return True if the supplied role exists.
    """

    return role_name in ALL_ROLES


def is_staff_role(role_name: str | None) -> bool:
    """
    Return True if the supplied role is a staff role.
    """

    if not role_name:
        return False

    return role_name in STAFF_ROLES


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_player_role(
    db,
    player_id: int,
) -> str:
    """
    Get the role name assigned to a player.

    Accounts without a valid role fall back to player.
    """

    row = db.execute(
        """
        SELECT r.name
        FROM players p
        LEFT JOIN roles r
            ON p.role_id = r.id
        WHERE p.id = ?
        """,
        (player_id,),
    ).fetchone()

    if not row:
        return ROLE_PLAYER

    role_name = row["name"]

    if not role_name:
        return ROLE_PLAYER

    return role_name


def get_player_permissions(
    db,
    player_id: int,
) -> set[str]:
    """
    Return every permission assigned to a player's role.

    Webmaster is a global superuser and therefore receives
    every known permission automatically.
    """

    role_name = get_player_role(
        db,
        player_id,
    )

    # ========================================================
    # WEBMASTER SUPERUSER
    # ========================================================

    if role_name == ROLE_WEBMASTER:
        return set(ALL_PERMISSIONS)

    rows = db.execute(
        """
        SELECT permission_name
        FROM permissions
        WHERE id IN (
            SELECT permission_id
            FROM role_permissions
            WHERE role_id = (
                SELECT role_id
                FROM players
                WHERE id = ?
            )
        )
        """,
        (player_id,),
    ).fetchall()

    return {
        row["permission_name"]
        for row in rows
        if row["permission_name"]
    }


# ============================================================
# ROLE CHECKS
# ============================================================

def player_has_role(
    db,
    player_id: int,
    role_name: str,
) -> bool:
    """
    Check whether a player has a specific role.
    """

    return (
        get_player_role(
            db,
            player_id,
        )
        == role_name
    )


def player_is_staff(
    db,
    player_id: int,
) -> bool:
    """
    Check whether a player has any staff role.

    Webmaster is always considered staff.
    """

    role_name = get_player_role(
        db,
        player_id,
    )

    return role_name in STAFF_ROLES


def player_is_webmaster(
    db,
    player_id: int,
) -> bool:
    """
    Check whether a player is a Webmaster.
    """

    return (
        get_player_role(
            db,
            player_id,
        )
        == ROLE_WEBMASTER
    )


# ============================================================
# PERMISSION CHECK
# ============================================================

def player_has_permission(
    db,
    player_id: int,
    permission: str,
) -> bool:
    """
    Check whether a player has a specific permission.

    Webmaster automatically passes every permission check.
    """

    role_name = get_player_role(
        db,
        player_id,
    )

    # ========================================================
    # WEBMASTER SUPERUSER BYPASS
    # ========================================================

    if role_name == ROLE_WEBMASTER:
        return True

    permissions = get_player_permissions(
        db,
        player_id,
    )

    return permission in permissions


# ============================================================
# CURRENT SESSION
# ============================================================

def get_current_player_id() -> int | None:
    """
    Get the currently authenticated player ID.

    Returns None if the player is not logged in.
    """

    player_id = session.get(
        "player_id"
    )

    if player_id is None:
        return None

    try:
        return int(player_id)

    except (
        TypeError,
        ValueError,
    ):
        return None


# ============================================================
# PERMISSION DECORATOR
# ============================================================

def require_permission(
    permission: str,
) -> Callable:
    """
    Protect a Flask route with a specific permission.

    Webmaster automatically passes the permission check.
    """

    if permission not in ALL_PERMISSIONS:
        raise ValueError(
            f"Unknown permission: {permission}"
        )

    def decorator(
        func: Callable,
    ) -> Callable:

        @wraps(func)
        def wrapper(
            *args: Any,
            **kwargs: Any,
        ):

            player_id = get_current_player_id()

            if player_id is None:
                abort(403)

            from ..database import get_connection

            db = get_connection()

            try:

                allowed = player_has_permission(
                    db,
                    player_id,
                    permission,
                )

            finally:
                db.close()

            if not allowed:
                abort(403)

            return func(
                *args,
                **kwargs,
            )

        return wrapper

    return decorator


# ============================================================
# ROLE DECORATOR
# ============================================================

def require_role(
    role_name: str,
) -> Callable:
    """
    Protect a Flask route with a specific role.

    Webmaster is the global superuser and therefore passes
    every role-protected administrative route.

    This means a Webmaster can also access routes that were
    originally intended for a specific staff role.
    """

    if not is_valid_role(role_name):
        raise ValueError(
            f"Unknown role: {role_name}"
        )

    def decorator(
        func: Callable,
    ) -> Callable:

        @wraps(func)
        def wrapper(
            *args: Any,
            **kwargs: Any,
        ):

            player_id = get_current_player_id()

            if player_id is None:
                abort(403)

            from ..database import get_connection

            db = get_connection()

            try:

                current_role = get_player_role(
                    db,
                    player_id,
                )

                # Webmaster bypass.
                if current_role == ROLE_WEBMASTER:
                    allowed = True

                else:
                    allowed = (
                        current_role
                        == role_name
                    )

            finally:
                db.close()

            if not allowed:
                abort(403)

            return func(
                *args,
                **kwargs,
            )

        return wrapper

    return decorator


# ============================================================
# STAFF DECORATOR
# ============================================================

def require_staff() -> Callable:
    """
    Protect a Flask route so only staff can access it.

    Webmaster automatically qualifies as staff.
    """

    def decorator(
        func: Callable,
    ) -> Callable:

        @wraps(func)
        def wrapper(
            *args: Any,
            **kwargs: Any,
        ):

            player_id = get_current_player_id()

            if player_id is None:
                abort(403)

            from ..database import get_connection

            db = get_connection()

            try:

                allowed = player_is_staff(
                    db,
                    player_id,
                )

            finally:
                db.close()

            if not allowed:
                abort(403)

            return func(
                *args,
                **kwargs,
            )

        return wrapper

    return decorator