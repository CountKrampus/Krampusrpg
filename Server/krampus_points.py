"""
Krampus Points (KP) — Premium Currency System
==============================================

Krampus Points are a premium currency that players earn through
admin awards, special events, and quests.  They are spent in the
KP Shop to unlock special areas, obtain exclusive Pokémon, and
purchase premium items.

Tables
------
krampus_points      — current balance per player
kp_transactions     — full ledger of every award / spend
kp_shop_items       — admin-configured purchasable items
kp_area_unlocks     — which players have unlocked which areas
kp_shop_purchases   — purchase history

This module is intentionally self-contained; call ensure_kp_schema()
once at application startup before using any other function here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .database import get_connection


# =============================================================================
# SCHEMA
# =============================================================================

_KP_SCHEMA = """
CREATE TABLE IF NOT EXISTS krampus_points (
    player_id INTEGER PRIMARY KEY,
    balance   INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE,

    CHECK (balance >= 0)
);

CREATE TABLE IF NOT EXISTS kp_transactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id  INTEGER,
    amount     INTEGER NOT NULL,
    reason     TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS kp_shop_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type   TEXT    NOT NULL DEFAULT 'item'
                        CHECK (item_type IN ('item', 'pokemon', 'area_unlock')),
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    item_ref    TEXT    NOT NULL DEFAULT '',
    variant     TEXT    NOT NULL DEFAULT 'normal',
    level       INTEGER NOT NULL DEFAULT 1,
    price       INTEGER NOT NULL DEFAULT 1,
    stock       INTEGER NOT NULL DEFAULT -1,
    active      INTEGER NOT NULL DEFAULT 1,
    starts_at   TEXT,
    ends_at     TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (price  >= 0),
    CHECK (stock  >= -1),
    CHECK (active IN (0, 1)),
    CHECK (level  >= 1),
    CHECK (level  <= 100)
);

CREATE TABLE IF NOT EXISTS kp_area_unlocks (
    player_id   INTEGER NOT NULL,
    area_id     TEXT    NOT NULL,
    unlocked_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (player_id, area_id),

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS kp_shop_purchases (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id    INTEGER,
    shop_item_id INTEGER,
    quantity     INTEGER NOT NULL DEFAULT 1,
    kp_spent     INTEGER NOT NULL DEFAULT 0,
    purchased_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE SET NULL,

    FOREIGN KEY (shop_item_id)
        REFERENCES kp_shop_items(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_kp_transactions_player
ON kp_transactions(player_id);

CREATE INDEX IF NOT EXISTS idx_kp_transactions_created_at
ON kp_transactions(created_at);

CREATE INDEX IF NOT EXISTS idx_kp_shop_items_active
ON kp_shop_items(active, sort_order);

CREATE INDEX IF NOT EXISTS idx_kp_area_unlocks_player
ON kp_area_unlocks(player_id);

CREATE INDEX IF NOT EXISTS idx_kp_shop_purchases_player
ON kp_shop_purchases(player_id);
"""


def ensure_kp_schema() -> None:
    """
    Create all Krampus Points tables and indexes if they do not exist.

    Safe to call multiple times; uses CREATE TABLE IF NOT EXISTS throughout.
    """
    with get_connection() as db:
        db.executescript(_KP_SCHEMA)
        db.commit()


# =============================================================================
# BALANCE
# =============================================================================

def get_balance(player_id: int) -> int:
    """
    Return a player's current KP balance.

    Returns 0 if the player has never received any KP.
    """
    db = get_connection()
    try:
        row = db.execute(
            "SELECT balance FROM krampus_points WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        return int(row["balance"]) if row else 0
    finally:
        db.close()


# =============================================================================
# AWARD / SPEND
# =============================================================================

def award_points(player_id: int, amount: int, reason: str = "") -> int:
    """
    Add *amount* KP to a player's balance and log the transaction.

    Parameters
    ----------
    player_id : int
    amount    : int   Must be > 0.
    reason    : str   Human-readable description shown in the admin log.

    Returns
    -------
    int   The player's new balance after the award.
    """
    if amount <= 0:
        raise ValueError("award_points: amount must be greater than 0.")

    db = get_connection()
    try:
        # Upsert the balance row.
        db.execute(
            """
            INSERT INTO krampus_points (player_id, balance)
            VALUES (?, ?)
            ON CONFLICT (player_id) DO UPDATE
                SET balance = balance + excluded.balance
            """,
            (player_id, amount),
        )

        # Log the transaction.
        db.execute(
            """
            INSERT INTO kp_transactions (player_id, amount, reason)
            VALUES (?, ?, ?)
            """,
            (player_id, amount, reason or "Admin award"),
        )

        db.commit()

        row = db.execute(
            "SELECT balance FROM krampus_points WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        return int(row["balance"]) if row else amount

    finally:
        db.close()


def spend_points(player_id: int, amount: int, reason: str = "") -> tuple[bool, int]:
    """
    Deduct *amount* KP from a player's balance if they have enough.

    Returns
    -------
    (True,  new_balance)  if the spend succeeded.
    (False, current_balance) if the player had insufficient funds.
    """
    if amount <= 0:
        raise ValueError("spend_points: amount must be greater than 0.")

    db = get_connection()
    try:
        row = db.execute(
            "SELECT balance FROM krampus_points WHERE player_id = ?",
            (player_id,),
        ).fetchone()

        current = int(row["balance"]) if row else 0

        if current < amount:
            return False, current

        db.execute(
            """
            UPDATE krampus_points
            SET balance = balance - ?
            WHERE player_id = ?
            """,
            (amount, player_id),
        )

        db.execute(
            """
            INSERT INTO kp_transactions (player_id, amount, reason)
            VALUES (?, ?, ?)
            """,
            (player_id, -amount, reason or "Purchase"),
        )

        db.commit()

        new_balance = current - amount
        return True, new_balance

    finally:
        db.close()


# =============================================================================
# TRANSACTION LOG
# =============================================================================

def get_kp_transactions(player_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent KP transactions for a single player."""
    limit = max(1, min(int(limit), 200))

    db = get_connection()
    try:
        rows = db.execute(
            """
            SELECT id, player_id, amount, reason, created_at
            FROM kp_transactions
            WHERE player_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (player_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def get_all_kp_transactions(
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Return KP transactions across all players for the admin view.
    Includes the player's username when available.
    """
    limit  = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    db = get_connection()
    try:
        rows = db.execute(
            """
            SELECT
                t.id,
                t.player_id,
                p.username,
                t.amount,
                t.reason,
                t.created_at
            FROM kp_transactions t
            LEFT JOIN players p ON p.id = t.player_id
            ORDER BY t.id DESC
            LIMIT ?
            OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


# =============================================================================
# SHOP ITEMS
# =============================================================================

def get_shop_items(active_only: bool = True) -> list[dict[str, Any]]:
    """
    Return KP shop items.

    Parameters
    ----------
    active_only : bool
        When True (default), only return items with ``active = 1`` that are
        within their starts_at / ends_at window (if set).
    """
    db = get_connection()
    try:
        if active_only:
            now = datetime.now(timezone.utc).isoformat()
            rows = db.execute(
                """
                SELECT *
                FROM kp_shop_items
                WHERE active = 1
                  AND (starts_at IS NULL OR starts_at <= ?)
                  AND (ends_at   IS NULL OR ends_at   >= ?)
                ORDER BY sort_order ASC, id ASC
                """,
                (now, now),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT *
                FROM kp_shop_items
                ORDER BY sort_order ASC, id ASC
                """
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def get_shop_item(item_id: int) -> dict[str, Any] | None:
    """Return a single shop item by ID, or None if not found."""
    db = get_connection()
    try:
        row = db.execute(
            "SELECT * FROM kp_shop_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def create_shop_item(
    item_type: str,
    name: str,
    description: str = "",
    item_ref: str = "",
    variant: str = "normal",
    level: int = 1,
    price: int = 1,
    stock: int = -1,
    active: bool = True,
    starts_at: str | None = None,
    ends_at: str | None = None,
    sort_order: int = 0,
) -> int:
    """
    Create a new KP shop item.

    Returns
    -------
    int   The new item's database ID.
    """
    db = get_connection()
    try:
        cursor = db.execute(
            """
            INSERT INTO kp_shop_items (
                item_type, name, description, item_ref,
                variant, level, price, stock,
                active, starts_at, ends_at, sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_type,
                name,
                description or "",
                item_ref or "",
                variant or "normal",
                max(1, int(level)),
                max(0, int(price)),
                int(stock),
                1 if active else 0,
                starts_at or None,
                ends_at or None,
                int(sort_order),
            ),
        )
        db.commit()
        return cursor.lastrowid
    finally:
        db.close()


_SHOP_ITEM_UPDATABLE_FIELDS = {
    "name", "description", "item_ref", "variant", "level",
    "price", "stock", "active", "starts_at", "ends_at", "sort_order",
}


def update_shop_item(item_id: int, **kwargs: Any) -> bool:
    """
    Update one or more fields on a KP shop item.

    Only fields listed in ``_SHOP_ITEM_UPDATABLE_FIELDS`` are accepted;
    unknown keys are silently ignored.

    Returns
    -------
    bool   True if a row was updated.
    """
    safe = {k: v for k, v in kwargs.items() if k in _SHOP_ITEM_UPDATABLE_FIELDS}
    if not safe:
        return False

    set_clause = ", ".join(f"{col} = ?" for col in safe)
    values     = list(safe.values()) + [item_id]

    db = get_connection()
    try:
        cursor = db.execute(
            f"UPDATE kp_shop_items SET {set_clause} WHERE id = ?",
            values,
        )
        db.commit()
        return cursor.rowcount > 0
    finally:
        db.close()


def toggle_shop_item_active(item_id: int) -> bool:
    """
    Flip the ``active`` flag on a KP shop item.

    Returns
    -------
    bool   True if the row was found and updated.
    """
    db = get_connection()
    try:
        cursor = db.execute(
            "UPDATE kp_shop_items SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (item_id,),
        )
        db.commit()
        return cursor.rowcount > 0
    finally:
        db.close()


def delete_shop_item(item_id: int) -> bool:
    """
    Permanently delete a KP shop item.

    Returns
    -------
    bool   True if a row was deleted.
    """
    db = get_connection()
    try:
        cursor = db.execute(
            "DELETE FROM kp_shop_items WHERE id = ?",
            (item_id,),
        )
        db.commit()
        return cursor.rowcount > 0
    finally:
        db.close()


# =============================================================================
# PURCHASE FLOW
# =============================================================================

def purchase_shop_item(player_id: int, shop_item_id: int) -> dict[str, Any]:
    """
    Execute a full KP shop purchase.

    Steps
    -----
    1. Validate the item exists and is currently active / in-window.
    2. Check stock > 0 or stock == -1 (unlimited).
    3. Check player has enough KP.
    4. Deduct KP via spend_points().
    5. Decrement stock if not unlimited.
    6. Deliver the reward:
       - 'item'        → increment player_items.quantity
       - 'pokemon'     → admin_assign_pokemon (party / PC)
       - 'area_unlock' → insert into kp_area_unlocks
    7. Record in kp_shop_purchases.

    Returns
    -------
    dict with keys: success (bool), message (str),
                    new_balance (int), item_type (str)

    Raises
    ------
    ValueError   with a user-friendly message on any failure.
    """
    item = get_shop_item(shop_item_id)
    if item is None:
        raise ValueError("That shop item does not exist.")

    if not item["active"]:
        raise ValueError("That item is not currently available.")

    # Time-window check.
    now = datetime.now(timezone.utc).isoformat()
    if item["starts_at"] and item["starts_at"] > now:
        raise ValueError("That item is not available yet.")
    if item["ends_at"] and item["ends_at"] < now:
        raise ValueError("That item is no longer available.")

    # Stock check.
    if item["stock"] == 0:
        raise ValueError("That item is out of stock.")

    # Balance check.
    balance = get_balance(player_id)
    price   = item["price"]
    if balance < price:
        raise ValueError(
            f"Insufficient Krampus Points. "
            f"You have {balance:,} KP but this costs {price:,} KP."
        )

    # --- All checks passed; now execute atomically. ---

    db = get_connection()
    try:
        # 1. Deduct KP.
        success, new_balance = spend_points(
            player_id,
            price,
            f"KP Shop: {item['name']}",
        )
        if not success:
            raise ValueError("Transaction failed: insufficient KP.")

        # 2. Decrement stock if limited.
        if item["stock"] != -1:
            db.execute(
                "UPDATE kp_shop_items SET stock = stock - 1 WHERE id = ?",
                (shop_item_id,),
            )

        # 3. Deliver reward.
        item_type = item["item_type"]
        item_ref  = item["item_ref"]

        if item_type == "item":
            # Give the player one of the referenced item.
            db.execute(
                """
                INSERT INTO player_items (player_id, item_id, quantity)
                VALUES (?, ?, 1)
                ON CONFLICT (player_id, item_id) DO UPDATE
                    SET quantity = quantity + 1
                """,
                (player_id, item_ref),
            )

        elif item_type == "pokemon":
            # Assign a Pokémon to the player's party / PC.
            # Import inline to avoid circular import.
            from .admin.services import admin_assign_pokemon
            admin_assign_pokemon(
                owner_id=player_id,
                species_id=item_ref,
                level=item["level"],
                shiny=False,
                variant=item["variant"] or "normal",
                nickname=None,
            )

        elif item_type == "area_unlock":
            db.execute(
                """
                INSERT OR IGNORE INTO kp_area_unlocks (player_id, area_id)
                VALUES (?, ?)
                """,
                (player_id, item_ref),
            )

        # 4. Log the purchase.
        db.execute(
            """
            INSERT INTO kp_shop_purchases
                (player_id, shop_item_id, quantity, kp_spent)
            VALUES (?, ?, 1, ?)
            """,
            (player_id, shop_item_id, price),
        )

        db.commit()

    finally:
        db.close()

    return {
        "success":     True,
        "message":     f"You purchased {item['name']}!",
        "new_balance": new_balance,
        "item_type":   item_type,
    }


# =============================================================================
# AREA UNLOCKS
# =============================================================================

def has_area_unlock(player_id: int, area_id: str) -> bool:
    """Return True if the player has unlocked the given special area."""
    db = get_connection()
    try:
        row = db.execute(
            """
            SELECT 1
            FROM kp_area_unlocks
            WHERE player_id = ? AND area_id = ?
            LIMIT 1
            """,
            (player_id, area_id),
        ).fetchone()
        return row is not None
    finally:
        db.close()


def get_player_area_unlocks(player_id: int) -> list[str]:
    """Return a list of area IDs the player has unlocked via KP."""
    db = get_connection()
    try:
        rows = db.execute(
            "SELECT area_id FROM kp_area_unlocks WHERE player_id = ?",
            (player_id,),
        ).fetchall()
        return [r["area_id"] for r in rows]
    finally:
        db.close()


# =============================================================================
# ADMIN HELPERS
# =============================================================================

def get_all_player_balances(
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Return all players with their KP balance for the admin overview.

    Uses a LEFT JOIN so players who have never earned KP appear with
    balance = 0.
    """
    limit  = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    db = get_connection()
    try:
        rows = db.execute(
            """
            SELECT
                p.id          AS player_id,
                p.username,
                p.display_name,
                COALESCE(kp.balance, 0) AS kp_balance
            FROM players p
            LEFT JOIN krampus_points kp ON kp.player_id = p.id
            ORDER BY kp_balance DESC, p.id ASC
            LIMIT ?
            OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def award_points_to_player(
    player_id: int,
    amount: int,
    reason: str,
    staff_id: int | None = None,
) -> dict[str, Any]:
    """
    Admin helper: award KP to a player and return a result summary.

    Parameters
    ----------
    player_id : int
    amount    : int
    reason    : str
    staff_id  : int | None   The staff member performing the action (for logging).

    Returns
    -------
    dict with keys: success (bool), new_balance (int), player_id (int)
    """
    new_balance = award_points(player_id, amount, reason)
    return {
        "success":     True,
        "new_balance": new_balance,
        "player_id":   player_id,
    }
