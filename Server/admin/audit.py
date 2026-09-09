"""
Krampus RPG Admin Audit Logging

Centralized audit logging for staff actions.

Every important administrative action should be recorded here
so we can later see:

    - Who performed the action
    - What they did
    - What type of object they changed
    - Which object was affected
    - When it happened
    - Additional details about the action
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..database import get_connection


# ============================================================
# AUDIT ACTION TYPES
# ============================================================

ACTION_LOGIN = "login"
ACTION_LOGOUT = "logout"

ACTION_VIEW = "view"
ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"

ACTION_GRANT = "grant"
ACTION_REVOKE = "revoke"

ACTION_BAN = "ban"
ACTION_UNBAN = "unban"

ACTION_WARN = "warn"

ACTION_PROMO_CLAIM = "promo_claim"

ACTION_ROLE_CHANGE = "role_change"
ACTION_PERMISSION_CHANGE = "permission_change"

ACTION_SETTING_CHANGE = "setting_change"

ACTION_DATABASE_OPERATION = "database_operation"


# ============================================================
# COMMON TARGET TYPES
# ============================================================

TARGET_PLAYER = "player"
TARGET_POKEMON = "pokemon"
TARGET_ITEM = "item"
TARGET_QUEST = "quest"

TARGET_PROMO = "daily_promo"
TARGET_EVENT = "event"

TARGET_ROLE = "role"
TARGET_PERMISSION = "permission"

TARGET_SETTING = "setting"

TARGET_DATABASE = "database"


# ============================================================
# TIME
# ============================================================

def utc_now() -> str:
    """
    Return the current UTC time as an ISO-8601 string.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# SERIALIZATION
# ============================================================

def _serialize_details(
    details: dict[str, Any] | None,
) -> str | None:
    """
    Convert audit details into JSON.

    This allows us to store useful information such as:

        {
            "old_role": "player",
            "new_role": "moderator"
        }

    without requiring a separate database column for every
    possible action.
    """

    if details is None:
        return None

    return json.dumps(
        details,
        ensure_ascii=False,
        default=str,
    )


# ============================================================
# CREATE AUDIT LOG
# ============================================================

def log_action(
    player_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Record an administrative action.

    Parameters:
        player_id:
            Account that performed the action.

        action:
            Type of action performed.

        target_type:
            Type of object affected.

        target_id:
            ID of the affected object.

        details:
            Optional additional information.

    Example:

        log_action(
            player_id=5,
            action=ACTION_ROLE_CHANGE,
            target_type=TARGET_PLAYER,
            target_id=42,
            details={
                "old_role": "player",
                "new_role": "moderator",
            },
        )
    """

    serialized_details = _serialize_details(
        details
    )

    db = get_connection()

    try:
        db.execute(
            """
            INSERT INTO audit_log (
                player_id,
                action,
                target_type,
                target_id,
                details,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                player_id,
                action,
                target_type,
                str(target_id)
                if target_id is not None
                else None,
                serialized_details,
                utc_now(),
            ),
        )

        db.commit()

    finally:
        db.close()


# ============================================================
# CURRENT STAFF ACCOUNT
# ============================================================

def log_current_player_action(
    action: str,
    target_type: str | None = None,
    target_id: int | str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Log an action performed by the currently logged-in account.

    This is the easiest function for admin routes to use.
    """

    from .permissions import get_current_player_id

    player_id = get_current_player_id()

    log_action(
        player_id=player_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )


# ============================================================
# SPECIALIZED HELPERS
# ============================================================

def log_player_change(
    player_id: int,
    target_player_id: int,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Log an administrative player change.
    """

    log_action(
        player_id=player_id,
        action=ACTION_UPDATE,
        target_type=TARGET_PLAYER,
        target_id=target_player_id,
        details=details,
    )


def log_pokemon_change(
    player_id: int,
    pokemon_id: int,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Log an administrative Pokémon change.
    """

    log_action(
        player_id=player_id,
        action=ACTION_UPDATE,
        target_type=TARGET_POKEMON,
        target_id=pokemon_id,
        details=details,
    )


def log_item_change(
    player_id: int,
    item_id: int | str,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Log an administrative item change.
    """

    log_action(
        player_id=player_id,
        action=ACTION_UPDATE,
        target_type=TARGET_ITEM,
        target_id=item_id,
        details=details,
    )


def log_quest_change(
    player_id: int,
    quest_id: int,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Log an administrative quest change.
    """

    log_action(
        player_id=player_id,
        action=ACTION_UPDATE,
        target_type=TARGET_QUEST,
        target_id=quest_id,
        details=details,
    )


def log_promo_change(
    player_id: int,
    promo_id: int,
    action: str = ACTION_UPDATE,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Log a Daily Promo change.
    """

    log_action(
        player_id=player_id,
        action=action,
        target_type=TARGET_PROMO,
        target_id=promo_id,
        details=details,
    )


def log_event_change(
    player_id: int,
    event_id: int,
    action: str = ACTION_UPDATE,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Log an event change.
    """

    log_action(
        player_id=player_id,
        action=action,
        target_type=TARGET_EVENT,
        target_id=event_id,
        details=details,
    )


def log_role_change(
    player_id: int,
    target_player_id: int,
    old_role: str,
    new_role: str,
) -> None:
    """
    Log a player role change.
    """

    log_action(
        player_id=player_id,
        action=ACTION_ROLE_CHANGE,
        target_type=TARGET_PLAYER,
        target_id=target_player_id,
        details={
            "old_role": old_role,
            "new_role": new_role,
        },
    )


def log_permission_change(
    player_id: int,
    role_id: int,
    permission_ids: list[int],
) -> None:
    """
    Log a role permission change.
    """

    log_action(
        player_id=player_id,
        action=ACTION_PERMISSION_CHANGE,
        target_type=TARGET_ROLE,
        target_id=role_id,
        details={
            "permission_ids": permission_ids,
        },
    )


def log_setting_change(
    player_id: int,
    setting_name: str,
    old_value: Any,
    new_value: Any,
) -> None:
    """
    Log a site setting change.
    """

    log_action(
        player_id=player_id,
        action=ACTION_SETTING_CHANGE,
        target_type=TARGET_SETTING,
        target_id=setting_name,
        details={
            "old_value": old_value,
            "new_value": new_value,
        },
    )


# ============================================================
# AUDIT LOG RETRIEVAL
# ============================================================

def get_audit_log(
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Retrieve audit log entries.

    Player username is included when available.
    """

    limit = max(
        1,
        min(int(limit), 500),
    )

    offset = max(
        0,
        int(offset),
    )

    db = get_connection()

    try:
        rows = db.execute(
            """
            SELECT
                a.id,
                a.player_id,
                p.username,
                a.action,
                a.target_type,
                a.target_id,
                a.details,
                a.created_at
            FROM audit_log a
            LEFT JOIN players p
                ON a.player_id = p.id
            ORDER BY a.id DESC
            LIMIT ?
            OFFSET ?
            """,
            (
                limit,
                offset,
            ),
        ).fetchall()

        results = []

        for row in rows:

            entry = dict(row)

            if entry.get("details"):
                try:
                    entry["details"] = json.loads(
                        entry["details"]
                    )
                except (
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                ):
                    pass

            results.append(entry)

        return results

    finally:
        db.close()