"""
Krampus RPG Chat (Shoutbox)

Native Cbox-style chat built directly on the game's existing accounts.
No second account system: messages are authored by the logged-in player
and render with the same username, display name, role, and badges the
rest of the game already knows.

Tables:

    chat_messages   — every chat message (history is kept)
    chat_mutes      — active mutes: player is blocked until expires_at
    chat_bans       — active bans: player cannot even view/post chat
    chat_presence   — last-seen heartbeat, drives the online counter

Moderation model:

    Roles moderator/admin/webmaster can delete any message, and
    mute/ban/unmute/unban players. Muted players may still read chat
    but cannot post; banned players are excluded from chat entirely.

    Mutes and bans are rows in chat_mutes/chat_bans with
    expires_at NULL meaning permanent.

Rate limiting:

    A player may post at most CHAT_MAX_MESSAGES messages within
    CHAT_RATE_WINDOW_SECONDS. The window is evaluated from the
    chat_messages timestamps, so no extra state is needed.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import get_connection
from .admin.permissions import (
    get_player_role,
    is_staff_role,
)

# ============================================================
# TUNING
# ============================================================

CHAT_MAX_MESSAGES = 5          # messages per window
CHAT_RATE_WINDOW_SECONDS = 20  # window length
CHAT_HISTORY_LIMIT = 80        # messages returned to the client
CHAT_ONLINE_WINDOW_SECONDS = 300  # heartbeat freshness (5 minutes)
CHAT_MESSAGE_MAX_LENGTH = 300

VALID_ROLES = {"player", "moderator", "event_staff", "admin", "webmaster"}

_MENTION_PATTERN = re.compile(r"@([A-Za-z0-9_]{2,32})")


# ============================================================
# TABLES
# ============================================================

CHAT_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_html TEXT,
    deleted INTEGER NOT NULL DEFAULT 0,
    deleted_by INTEGER,
    system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE,
    FOREIGN KEY (deleted_by)
        REFERENCES players(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_created
    ON chat_messages (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_chat_messages_player
    ON chat_messages (player_id);

CREATE TABLE IF NOT EXISTS chat_mutes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    reason TEXT,
    issued_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT,
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_mutes_player
    ON chat_mutes (player_id, expires_at);

CREATE TABLE IF NOT EXISTS chat_bans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    reason TEXT,
    issued_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT,
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_bans_player
    ON chat_bans (player_id, expires_at);

CREATE TABLE IF NOT EXISTS chat_presence (
    player_id INTEGER PRIMARY KEY,
    last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE
);
"""


def ensure_chat_tables() -> None:
    """Create chat tables and indexes if they do not exist."""

    with get_connection() as db:
        db.executescript(CHAT_SCHEMA)
        db.commit()


# ============================================================
# TIME HELPERS
# ============================================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse_db_time(value: str | None) -> datetime | None:
    """Parse CURRENT_TIMESTAMP-style values into aware UTC datetimes."""

    if not value:
        return None

    try:
        dt = datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    return dt.replace(tzinfo=timezone.utc)


# ============================================================
# SANCTION CHECKS
# ============================================================

def _active_sanction(db, table: str, player_id: int) -> dict[str, Any] | None:
    """
    The newest active sanction row for a player, or None.
    expires_at NULL means permanent.
    """

    now = _iso_utc(_utcnow())

    row = db.execute(
        f"""
        SELECT id, reason, created_at, expires_at
        FROM {table}
        WHERE player_id = ?
          AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY
            CASE WHEN expires_at IS NULL THEN 1 ELSE 0 END DESC,
            id DESC
        LIMIT 1
        """,
        (player_id, now),
    ).fetchone()

    return dict(row) if row else None


def get_active_mute(player_id: int) -> dict[str, Any] | None:
    """Active mute for the player, or None."""

    ensure_chat_tables()

    with get_connection() as db:
        return _active_sanction(db, "chat_mutes", player_id)


def get_active_ban(player_id: int) -> dict[str, Any] | None:
    """Active chat ban for the player, or None."""

    ensure_chat_tables()

    with get_connection() as db:
        return _active_sanction(db, "chat_bans", player_id)


def is_chat_banned(player_id: int) -> bool:
    return get_active_ban(player_id) is not None


def is_chat_muted(player_id: int) -> bool:
    return get_active_mute(player_id) is not None


# ============================================================
# PRESENCE
# ============================================================

def heartbeat(player_id: int) -> None:
    """Record that the player is in chat right now."""

    ensure_chat_tables()

    with get_connection() as db:
        db.execute(
            """
            INSERT INTO chat_presence (player_id, last_seen)
            VALUES (?, ?)
            ON CONFLICT(player_id)
            DO UPDATE SET last_seen = excluded.last_seen
            """,
            (player_id, _iso_utc(_utcnow())),
        )
        db.commit()


def get_online_players() -> list[dict[str, Any]]:
    """
    Players seen in chat within CHAT_ONLINE_WINDOW_SECONDS,
    oldest first (page load order feels natural).
    """

    ensure_chat_tables()

    cutoff = _iso_utc(
        _utcnow() - timedelta(seconds=CHAT_ONLINE_WINDOW_SECONDS)
    )

    with get_connection() as db:
        rows = db.execute(
            """
            SELECT
                p.id,
                p.display_name,
                p.username,
                r.name AS role
            FROM chat_presence cp
            JOIN players p
                ON p.id = cp.player_id
            LEFT JOIN roles r
                ON r.id = p.role_id
            WHERE cp.last_seen > ?
            ORDER BY p.display_name COLLATE NOCASE ASC
            """,
            (cutoff,),
        ).fetchall()

    return [dict(row) for row in rows]


def online_count() -> int:
    return len(get_online_players())


# ============================================================
# MESSAGE HISTORY
# ============================================================

def _message_query(limit: int, before_id: int | None) -> str:
    return f"""
        SELECT
            m.id,
            m.content,
            m.content_html,
            m.system,
            m.created_at,
            m.player_id,
            p.display_name,
            p.username,
            r.name AS role,
            m.deleted,
            m.deleted_by,
            d.display_name AS deleted_by_name
        FROM chat_messages m
        JOIN players p
            ON p.id = m.player_id
        LEFT JOIN roles r
            ON r.id = p.role_id
        LEFT JOIN players d
            ON d.id = m.deleted_by
        WHERE m.id > ?
          AND m.deleted = 0
          AND m.player_id NOT IN (
              SELECT player_id FROM chat_bans
              WHERE expires_at IS NULL OR expires_at > {placeholders_now()}
          )
        ORDER BY m.id DESC
        LIMIT {int(limit)}
    """


def placeholders_now() -> str:
    # Helper kept tiny: the ban subquery needs the current time.
    return "'" + _iso_utc(_utcnow()) + "'"


def get_messages(
    after_id: int = 0,
    limit: int = CHAT_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    """
    Chat history newer than after_id (0 = the initial page load).
    Messages from banned players are hidden; deleted messages are
    never returned.
    """

    ensure_chat_tables()

    limit = max(1, min(int(limit), CHAT_HISTORY_LIMIT))
    after_id = max(0, int(after_id))

    with get_connection() as db:
        rows = db.execute(
            _message_query(limit, after_id),
            (after_id,),
        ).fetchall()

    # Oldest first for display.
    return [dict(row) for row in reversed(rows)]


def get_last_message_id() -> int:
    ensure_chat_tables()

    with get_connection() as db:
        row = db.execute(
            "SELECT COALESCE(MAX(id), 0) AS max_id FROM chat_messages"
        ).fetchone()

    return int(row["max_id"])


# ============================================================
# SENDING
# ============================================================

def _check_rate_limit(db, player_id: int) -> None:
    cutoff = _iso_utc(
        _utcnow() - timedelta(seconds=CHAT_RATE_WINDOW_SECONDS)
    )

    row = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM chat_messages
        WHERE player_id = ?
          AND system = 0
          AND created_at > ?
        """,
        (player_id, cutoff),
    ).fetchone()

    if int(row["n"]) >= CHAT_MAX_MESSAGES:
        raise RateLimited(
            "You're sending messages too quickly. "
            f"Up to {CHAT_MAX_MESSAGES} messages per "
            f"{CHAT_RATE_WINDOW_SECONDS} seconds."
        )


class ChatError(Exception):
    """Base class for chat send failures (message for the player)."""


class RateLimited(ChatError):
    pass


class ChatSanctioned(ChatError):
    pass


def send_message(
    player_id: int,
    content: str,
    *,
    system: bool = False,
    skip_rate_limit: bool = False,
) -> dict[str, Any]:
    """
    Post one chat message as the given player.

    Returns the stored message row (rendered fields included).
    Raises ChatError subclasses with player-facing messages on
    failure; sqlite errors bubble up.
    """

    ensure_chat_tables()

    text = str(content or "").strip()

    if not text:
        raise ChatError("Message cannot be empty.")

    if len(text) > CHAT_MESSAGE_MAX_LENGTH:
        raise ChatError(
            f"Message is too long (max {CHAT_MESSAGE_MAX_LENGTH} characters)."
        )

    with get_connection() as db:

        # Banned players cannot post (or read).
        ban = _active_sanction(db, "chat_bans", player_id)
        if ban is not None:
            raise ChatSanctioned(_sanction_message("banned", ban))

        # Muted players cannot post.
        mute = _active_sanction(db, "chat_mutes", player_id)
        if mute is not None and not system:
            raise ChatSanctioned(_sanction_message("muted", mute))

        if not skip_rate_limit and not system:
            _check_rate_limit(db, player_id)

        content_html = render_markup(text)

        cursor = db.execute(
            """
            INSERT INTO chat_messages (player_id, content, content_html, system)
            VALUES (?, ?, ?, ?)
            """,
            (
                player_id,
                text,
                content_html,
                1 if system else 0,
            ),
        )

        db.commit()

        message_id = cursor.lastrowid

    messages = [m for m in get_messages(after_id=message_id - 1, limit=1)]
    return messages[0]


def _sanction_message(kind: str, sanction: dict[str, Any]) -> str:
    """Player-facing notice for a mute or ban."""

    expires = _parse_db_time(sanction.get("expires_at"))

    if expires is None:
        when = "permanently"
    else:
        seconds = int((expires - _utcnow()).total_seconds())

        if seconds < 90:
            when = f"for {max(1, seconds)} more seconds"
        elif seconds < 3600:
            when = f"for {seconds // 60} more minutes"
        else:
            when = f"for {seconds // 3600} more hours"

    reason = sanction.get("reason")
    suffix = f' Reason: "{reason}".' if reason else ""

    return f"You are {kind} from chat {when}.{suffix}"


# ============================================================
# MARKUP (ESCAPING, LINKS, MENTIONS)
# ============================================================

def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_markup(text: str) -> str:
    """
    Escape message text, then apply:
      - automatic links (http/https only)
      - @Name mentions -> profile links
    Escaping happens first, so markup is inert.
    """

    escaped = _escape_html(text)

    # Links
    escaped = re.sub(
        r"(https?://[^\s<]+)",
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>',
        escaped,
    )

    # Mentions -> profile links
    escaped = _MENTION_PATTERN.sub(
        r'<a class="chat-mention" href="/profile/\1">\1</a>',
        escaped,
    )

    return escaped


# ============================================================
# MODERATION
# ============================================================

def _staffer_role(db, staff_player_id: int) -> str:
    return get_player_role(db, staff_player_id)


def _require_staff(staff_player_id: int) -> str:
    """Return the actor's role, raising if they are not staff."""

    with get_connection() as db:
        role = _staffer_role(db, staff_player_id)

    if not is_staff_role(role):
        raise ChatError("You do not have permission to moderate chat.")

    return role


def delete_message(message_id: int, staff_player_id: int) -> bool:
    """Soft-delete one message. Returns False if not found."""

    _require_staff(staff_player_id)

    with get_connection() as db:
        cursor = db.execute(
            """
            UPDATE chat_messages
            SET deleted = 1, deleted_by = ?
            WHERE id = ? AND deleted = 0
            """,
            (staff_player_id, message_id),
        )
        db.commit()

        return cursor.rowcount > 0


def mute_player(
    player_id: int,
    staff_player_id: int,
    *,
    duration_minutes: int | None = None,
    reason: str | None = None,
) -> bool:
    """Mute a player. duration_minutes None = permanent."""

    _require_staff(staff_player_id)

    expires_at = None

    if duration_minutes is not None:
        expires_at = _iso_utc(
            _utcnow() + timedelta(minutes=max(1, int(duration_minutes)))
        )

    with get_connection() as db:
        exists = db.execute(
            "SELECT 1 FROM players WHERE id = ?", (player_id,)
        ).fetchone()

        if exists is None:
            raise ChatError("No such player.")

        db.execute(
            """
            INSERT INTO chat_mutes (player_id, reason, issued_by, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (player_id, reason, staff_player_id, expires_at),
        )
        db.commit()

    return True


def unmute_player(player_id: int, staff_player_id: int) -> bool:
    """Expire all active mutes for a player."""

    _require_staff(staff_player_id)

    with get_connection() as db:
        cursor = db.execute(
            """
            UPDATE chat_mutes
            SET expires_at = ?
            WHERE player_id = ?
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (_iso_utc(_utcnow()), player_id, _iso_utc(_utcnow())),
        )
        db.commit()

        return cursor.rowcount > 0


def ban_player(
    player_id: int,
    staff_player_id: int,
    *,
    duration_minutes: int | None = None,
    reason: str | None = None,
) -> bool:
    """Ban a player from chat entirely. duration_minutes None = permanent."""

    _require_staff(staff_player_id)

    expires_at = None

    if duration_minutes is not None:
        expires_at = _iso_utc(
            _utcnow() + timedelta(minutes=max(1, int(duration_minutes)))
        )

    with get_connection() as db:
        exists = db.execute(
            "SELECT 1 FROM players WHERE id = ?", (player_id,)
        ).fetchone()

        if exists is None:
            raise ChatError("No such player.")

        db.execute(
            """
            INSERT INTO chat_bans (player_id, reason, issued_by, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (player_id, reason, staff_player_id, expires_at),
        )
        db.commit()

    return True


def unban_player(player_id: int, staff_player_id: int) -> bool:
    """Expire all active chat bans for a player."""

    _require_staff(staff_player_id)

    with get_connection() as db:
        cursor = db.execute(
            """
            UPDATE chat_bans
            SET expires_at = ?
            WHERE player_id = ?
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (_iso_utc(_utcnow()), player_id, _iso_utc(_utcnow())),
        )
        db.commit()

        return cursor.rowcount > 0


# ============================================================
# SYSTEM MESSAGES
# ============================================================

def send_system_message(
    text: str,
    *,
    actor_name: str | None = None,
) -> None:
    """
    Post a system notice. System messages skip rate limits and
    sanctions. They are attributed to the first player account
    (the founder/webmaster row) but render with a System tag and
    no player identity in the UI.
    """

    ensure_chat_tables()

    text = str(text or "").strip()
    if not text:
        return

    with get_connection() as db:
        row = db.execute(
            "SELECT id FROM players ORDER BY id ASC LIMIT 1"
        ).fetchone()

        # No players at all: nothing to attribute; skip.
        if row is None:
            return

        content = f"{actor_name} {text}".strip() if actor_name else text

        db.execute(
            """
            INSERT INTO chat_messages (player_id, content, content_html, system)
            VALUES (?, ?, ?, 1)
            """,
            (row["id"], text, render_markup(content)),
        )
        db.commit()
