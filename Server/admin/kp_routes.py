"""
Krampus Points Admin Routes
===========================

Provides the admin-facing Blueprint for managing Krampus Points (KP):

    /admin/krampus-points/               — KP overview (player balances)
    /admin/krampus-points/award          — Award KP to a player  (POST)
    /admin/krampus-points/shop           — KP shop item list
    /admin/krampus-points/shop/create    — Create a shop item     (POST)
    /admin/krampus-points/shop/<id>/toggle  — Toggle active       (POST)
    /admin/krampus-points/shop/<id>/edit    — Edit a shop item    (POST)
    /admin/krampus-points/shop/<id>/delete  — Delete a shop item  (POST)
    /admin/krampus-points/transactions   — Full transaction log
"""

from __future__ import annotations

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .. import krampus_points as kp
from ..database import get_connection

from .audit import (
    log_action,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_DELETE,
)

from .decorators import (
    kp_view_required,
    kp_edit_required,
    kp_shop_view_required,
    kp_shop_edit_required,
)

from .services import (
    get_available_species,
    get_available_variants,
    get_players,
)


def _clean_variant(value: str) -> str:
    """
    Validate a submitted variant id against the live pokemon_variants
    table (the same resolution create_pokemon() uses), so a malformed
    value can never be stored and blow up at purchase time.
    """

    variant = str(value or "").strip().lower()

    if not variant or variant == "normal":
        return "normal"

    from ..services import get_variant

    if get_variant(variant) is None:
        valid = ", ".join(
            sorted(v["id"] for v in get_available_variants())
        )
        raise ValueError(
            f"Unknown variant '{variant}'. Valid variants: {valid}"
        )

    return variant


# ============================================================
# AUDIT CONSTANTS
# ============================================================

ACTION_KP_AWARD  = "kp_award"
TARGET_KP        = "krampus_points"
TARGET_KP_SHOP   = "kp_shop_item"


# ============================================================
# BLUEPRINT
# ============================================================

kp_admin_bp = Blueprint(
    "kp_admin",
    __name__,
    url_prefix="/admin/krampus-points",
    template_folder="templates",
)


# ============================================================
# OVERVIEW — player balances + award form
# ============================================================

@kp_admin_bp.route("/")
@kp_view_required
def kp_overview():
    """
    Show all player KP balances and recent transactions.
    """
    players              = kp.get_all_player_balances()
    recent_transactions  = kp.get_all_kp_transactions(limit=20)
    all_players          = get_players(limit=500)

    return render_template(
        "admin/kp_overview.html",
        players=players,
        recent_transactions=recent_transactions,
        all_players=all_players,
    )


@kp_admin_bp.post("/award")
@kp_edit_required
def kp_award():
    """
    Award Krampus Points to a player.
    """
    staff_id = session.get("player_id")

    player_id_raw = request.form.get("player_id", "").strip()
    amount_raw    = request.form.get("amount", "").strip()
    reason        = request.form.get("reason", "Admin award").strip()

    if not player_id_raw:
        flash("Please select a player.", "error")
        return redirect(url_for("kp_admin.kp_overview"))

    if not amount_raw:
        flash("Please enter an amount.", "error")
        return redirect(url_for("kp_admin.kp_overview"))

    try:
        player_id = int(player_id_raw)
    except (TypeError, ValueError):
        flash("Invalid player ID.", "error")
        return redirect(url_for("kp_admin.kp_overview"))

    try:
        amount = int(amount_raw)
    except (TypeError, ValueError):
        flash("Invalid amount.", "error")
        return redirect(url_for("kp_admin.kp_overview"))

    if amount <= 0:
        flash("Amount must be greater than 0.", "error")
        return redirect(url_for("kp_admin.kp_overview"))

    # Look up the player username for the flash message.
    with get_connection() as db:
        row = db.execute(
            "SELECT username FROM players WHERE id = ?", (player_id,)
        ).fetchone()

    if row is None:
        flash(f"Player #{player_id} not found.", "error")
        return redirect(url_for("kp_admin.kp_overview"))

    username = row["username"]

    result = kp.award_points_to_player(
        player_id=player_id,
        amount=amount,
        reason=reason or "Admin award",
        staff_id=staff_id,
    )

    log_action(
        player_id=staff_id,
        action=ACTION_KP_AWARD,
        target_type=TARGET_KP,
        target_id=player_id,
        details={
            "recipient": username,
            "amount": amount,
            "reason": reason,
            "new_balance": result.get("new_balance"),
        },
    )

    flash(
        f"Awarded {amount:,} KP to {username}. "
        f"New balance: {result['new_balance']:,} KP.",
        "success",
    )
    return redirect(url_for("kp_admin.kp_overview"))


# ============================================================
# SHOP — item list
# ============================================================

@kp_admin_bp.route("/shop")
@kp_shop_view_required
def kp_shop():
    """
    Show all KP shop items and a create form.
    """
    shop_items   = kp.get_shop_items(active_only=False)
    species_list = get_available_species()
    variants     = get_available_variants()

    return render_template(
        "admin/kp_shop.html",
        shop_items=shop_items,
        species_list=species_list,
        variants=variants,
    )


@kp_admin_bp.post("/shop/create")
@kp_shop_edit_required
def kp_shop_create():
    """
    Create a new KP shop item.
    """
    staff_id = session.get("player_id")

    item_type   = request.form.get("item_type", "item").strip()
    name        = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    item_ref    = request.form.get("item_ref", "").strip()
    variant     = request.form.get("variant", "normal").strip()
    level_raw   = request.form.get("level", "1").strip()
    price_raw   = request.form.get("price", "1").strip()
    stock_raw   = request.form.get("stock", "-1").strip()
    active      = request.form.get("active", "") == "1"
    starts_at   = request.form.get("starts_at", "").strip() or None
    ends_at     = request.form.get("ends_at", "").strip() or None
    sort_raw    = request.form.get("sort_order", "0").strip()

    if not name:
        flash("Item name is required.", "error")
        return redirect(url_for("kp_admin.kp_shop"))

    if item_type not in ("item", "pokemon", "area_unlock"):
        flash("Invalid item type.", "error")
        return redirect(url_for("kp_admin.kp_shop"))

    try:
        variant = _clean_variant(variant)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("kp_admin.kp_shop"))

    try:
        level      = max(1, int(level_raw))
        price      = max(0, int(price_raw))
        stock      = max(-1, int(stock_raw))
        sort_order = int(sort_raw)
    except (TypeError, ValueError):
        flash("Invalid numeric values.", "error")
        return redirect(url_for("kp_admin.kp_shop"))

    new_id = kp.create_shop_item(
        item_type=item_type,
        name=name,
        description=description,
        item_ref=item_ref,
        variant=variant,
        level=level,
        price=price,
        stock=stock,
        active=active,
        starts_at=starts_at,
        ends_at=ends_at,
        sort_order=sort_order,
    )

    log_action(
        player_id=staff_id,
        action=ACTION_CREATE,
        target_type=TARGET_KP_SHOP,
        target_id=new_id,
        details={
            "name": name,
            "item_type": item_type,
            "price": price,
        },
    )

    flash(f"Shop item '{name}' created successfully!", "success")
    return redirect(url_for("kp_admin.kp_shop"))


@kp_admin_bp.post("/shop/<int:item_id>/toggle")
@kp_shop_edit_required
def kp_shop_toggle(item_id: int):
    """Toggle the active status of a KP shop item."""
    staff_id = session.get("player_id")
    success  = kp.toggle_shop_item_active(item_id)

    if success:
        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type=TARGET_KP_SHOP,
            target_id=item_id,
            details={"action": "toggle_active"},
        )
        flash(f"Shop item #{item_id} status toggled.", "success")
    else:
        flash(f"Shop item #{item_id} not found.", "error")

    return redirect(url_for("kp_admin.kp_shop"))


@kp_admin_bp.post("/shop/<int:item_id>/edit")
@kp_shop_edit_required
def kp_shop_edit(item_id: int):
    """Update fields on an existing KP shop item."""
    staff_id = session.get("player_id")

    item_type   = request.form.get("item_type", "item").strip()
    name        = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    item_ref    = request.form.get("item_ref", "").strip()
    variant     = request.form.get("variant", "normal").strip()
    level_raw   = request.form.get("level", "1").strip()
    price_raw   = request.form.get("price", "1").strip()
    stock_raw   = request.form.get("stock", "-1").strip()
    active      = 1 if request.form.get("active", "") == "1" else 0
    starts_at   = request.form.get("starts_at", "").strip() or None
    ends_at     = request.form.get("ends_at", "").strip() or None
    sort_raw    = request.form.get("sort_order", "0").strip()

    try:
        level      = max(1, int(level_raw))
        price      = max(0, int(price_raw))
        stock      = max(-1, int(stock_raw))
        sort_order = int(sort_raw)
    except (TypeError, ValueError):
        flash("Invalid numeric values.", "error")
        return redirect(url_for("kp_admin.kp_shop"))

    try:
        variant = _clean_variant(variant)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("kp_admin.kp_shop"))

    success = kp.update_shop_item(
        item_id,
        item_type=item_type,
        name=name,
        description=description,
        item_ref=item_ref,
        variant=variant,
        level=level,
        price=price,
        stock=stock,
        active=active,
        starts_at=starts_at,
        ends_at=ends_at,
        sort_order=sort_order,
    )

    if success:
        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type=TARGET_KP_SHOP,
            target_id=item_id,
            details={"name": name, "price": price},
        )
        flash(f"Shop item '{name}' updated.", "success")
    else:
        flash(f"Shop item #{item_id} not found.", "error")

    return redirect(url_for("kp_admin.kp_shop"))


@kp_admin_bp.post("/shop/<int:item_id>/delete")
@kp_shop_edit_required
def kp_shop_delete(item_id: int):
    """Permanently delete a KP shop item."""
    staff_id = session.get("player_id")
    item     = kp.get_shop_item(item_id)

    if item is None:
        flash(f"Shop item #{item_id} not found.", "error")
        return redirect(url_for("kp_admin.kp_shop"))

    kp.delete_shop_item(item_id)

    log_action(
        player_id=staff_id,
        action=ACTION_DELETE,
        target_type=TARGET_KP_SHOP,
        target_id=item_id,
        details={"name": item.get("name")},
    )

    flash(f"Shop item '{item.get('name')}' deleted.", "success")
    return redirect(url_for("kp_admin.kp_shop"))


# ============================================================
# TRANSACTIONS
# ============================================================

@kp_admin_bp.route("/transactions")
@kp_view_required
def kp_transactions():
    """
    Show all KP transactions across all players.
    """
    transactions = kp.get_all_kp_transactions(limit=200)

    return render_template(
        "admin/kp_transactions.html",
        transactions=transactions,
    )
