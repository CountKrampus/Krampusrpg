"""
Krampus RPG Admin Route Decorators

Convenience decorators used to protect administrative routes.

The actual permission logic lives in permissions.py.

Webmaster is the highest-level role and automatically bypasses
all permission checks.
"""

from functools import wraps
from typing import Callable, Any

from flask import abort

from .permissions import (
    require_permission,
    require_role,
    require_staff,

    ROLE_WEBMASTER,

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
)


# ============================================================
# GENERAL ADMIN ACCESS
# ============================================================

def admin_required(
    func: Callable,
) -> Callable:
    """
    Require staff access.

    Webmaster automatically qualifies as staff.
    """

    return require_staff()(func)


# ============================================================
# DASHBOARD
# ============================================================

def dashboard_required(
    func: Callable,
) -> Callable:
    """
    Require access to the main admin dashboard.
    """

    return require_permission(
        PERMISSION_ADMIN_DASHBOARD
    )(func)


# ============================================================
# PLAYERS
# ============================================================

def players_view_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_PLAYERS_VIEW
    )(func)


def players_edit_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_PLAYERS_EDIT
    )(func)


# ============================================================
# POKÉMON
# ============================================================

def pokemon_view_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_POKEMON_VIEW
    )(func)


def pokemon_edit_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_POKEMON_EDIT
    )(func)


# ============================================================
# ITEMS
# ============================================================

def items_view_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_ITEMS_VIEW
    )(func)


def items_edit_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_ITEMS_EDIT
    )(func)


# ============================================================
# QUESTS
# ============================================================

def quests_view_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_QUESTS_VIEW
    )(func)


def quests_edit_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_QUESTS_EDIT
    )(func)


# ============================================================
# PROMOTIONS
# ============================================================

def promos_view_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_PROMOS_VIEW
    )(func)


def promos_edit_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_PROMOS_EDIT
    )(func)


# ============================================================
# EVENTS
# ============================================================

def events_view_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_EVENTS_VIEW
    )(func)


def events_edit_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_EVENTS_EDIT
    )(func)


# ============================================================
# MODERATION
# ============================================================

def moderation_players_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_MODERATION_PLAYERS
    )(func)


def moderation_reports_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_MODERATION_REPORTS
    )(func)


# ============================================================
# REPORTS
# ============================================================

def reports_view_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_REPORTS_VIEW
    )(func)


# ============================================================
# AUDIT LOG
# ============================================================

def audit_log_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_AUDIT_LOG
    )(func)


# ============================================================
# ROLES / PERMISSIONS
# ============================================================

def roles_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_ROLES
    )(func)


# ============================================================
# SETTINGS
# ============================================================

def settings_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_SETTINGS
    )(func)


# ============================================================
# DATABASE
# ============================================================

def database_required(
    func: Callable,
) -> Callable:

    return require_permission(
        PERMISSION_DATABASE
    )(func)


# ============================================================
# WEBMASTER ONLY
# ============================================================

def webmaster_required(
    func: Callable,
) -> Callable:
    """
    Restrict a route to Webmaster-level access.

    Webmaster is the highest role in the system.
    """

    return require_role(
        ROLE_WEBMASTER
    )(func)


# ============================================================
# ANY PERMISSION
# ============================================================

def require_any_permission(
    *permissions: str,
) -> Callable:
    """
    Allow access if the current account has at least one
    of the supplied permissions.

    Webmaster automatically passes.
    """

    if not permissions:
        raise ValueError(
            "require_any_permission() requires at least "
            "one permission."
        )

    def decorator(
        func: Callable,
    ) -> Callable:

        @wraps(func)
        def wrapper(
            *args: Any,
            **kwargs: Any,
        ):

            from .permissions import (
                get_current_player_id,
                player_has_permission,
            )

            from ..database import get_connection

            player_id = get_current_player_id()

            if player_id is None:
                abort(403)

            db = get_connection()

            try:

                for permission in permissions:

                    if player_has_permission(
                        db,
                        player_id,
                        permission,
                    ):
                        return func(
                            *args,
                            **kwargs,
                        )

            finally:
                db.close()

            abort(403)

        return wrapper

    return decorator


# ============================================================
# ALL PERMISSIONS
# ============================================================

def require_all_permissions(
    *permissions: str,
) -> Callable:
    """
    Require every supplied permission.

    Webmaster automatically passes every permission.
    """

    if not permissions:
        raise ValueError(
            "require_all_permissions() requires at least "
            "one permission."
        )

    def decorator(
        func: Callable,
    ) -> Callable:

        @wraps(func)
        def wrapper(
            *args: Any,
            **kwargs: Any,
        ):

            from .permissions import (
                get_current_player_id,
                player_has_permission,
            )

            from ..database import get_connection

            player_id = get_current_player_id()

            if player_id is None:
                abort(403)

            db = get_connection()

            try:

                for permission in permissions:

                    if not player_has_permission(
                        db,
                        player_id,
                        permission,
                    ):
                        abort(403)

            finally:
                db.close()

            return func(
                *args,
                **kwargs,
            )

        return wrapper

    return decorator