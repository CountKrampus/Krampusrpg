"""
Krampus RPG Admin Routes

Central administrative dashboard and staff-management routes.

The admin system is organized around permissions rather than
a simple "is_admin" flag.
"""

from flask import Blueprint, render_template

from .decorators import (
    dashboard_required,

    players_view_required,
    players_edit_required,

    pokemon_view_required,
    pokemon_edit_required,

    items_view_required,
    items_edit_required,

    quests_view_required,
    quests_edit_required,

    promos_view_required,
    promos_edit_required,

    events_view_required,
    events_edit_required,

    reports_view_required,

    audit_log_required,

    roles_required,

    settings_required,

    database_required,
)

from .services import (
    get_dashboard_stats,
    get_players,
    get_pokemon,
    get_player_items,
    get_quests,
    get_roles,
    get_permissions,
    get_audit_logs,
)


# ============================================================
# BLUEPRINT
# ============================================================

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


# ============================================================
# MAIN DASHBOARD
# ============================================================

@admin_bp.route("/")
@dashboard_required
def dashboard():
    """
    Main staff dashboard.
    """

    stats = get_dashboard_stats()

    return render_template(
        "admin/dashboard.html",
        stats=stats,
    )


# ============================================================
# PLAYERS
# ============================================================

@admin_bp.route("/players")
@players_view_required
def players():
    """
    View player accounts.
    """

    player_list = get_players()

    return render_template(
        "admin/players.html",
        players=player_list,
    )


@admin_bp.route("/players/edit")
@players_edit_required
def players_edit():
    """
    Edit player accounts.
    """

    player_list = get_players()

    return render_template(
        "admin/players.html",
        players=player_list,
    )


# ============================================================
# POKÉMON
# ============================================================

@admin_bp.route("/pokemon")
@pokemon_view_required
def pokemon():
    """
    View Pokémon administration.
    """

    pokemon_list = get_pokemon()

    return render_template(
        "admin/pokemon.html",
        pokemon=pokemon_list,
    )


@admin_bp.route("/pokemon/edit")
@pokemon_edit_required
def pokemon_edit():
    """
    Edit Pokémon.
    """

    pokemon_list = get_pokemon()

    return render_template(
        "admin/pokemon.html",
        pokemon=pokemon_list,
    )


# ============================================================
# ITEMS
# ============================================================

@admin_bp.route("/items")
@items_view_required
def items():
    """
    View item administration.
    """

    item_list = get_player_items()

    return render_template(
        "admin/items.html",
        items=item_list,
    )


@admin_bp.route("/items/edit")
@items_edit_required
def items_edit():
    """
    Edit items.
    """

    item_list = get_player_items()

    return render_template(
        "admin/items.html",
        items=item_list,
    )


# ============================================================
# QUESTS
# ============================================================

@admin_bp.route("/quests")
@quests_view_required
def quests():
    """
    View quest administration.
    """

    quest_list = get_quests()

    return render_template(
        "admin/quests.html",
        quests=quest_list,
    )


@admin_bp.route("/quests/edit")
@quests_edit_required
def quests_edit():
    """
    Edit quests.
    """

    quest_list = get_quests()

    return render_template(
        "admin/quests.html",
        quests=quest_list,
    )


# ============================================================
# DAILY PROMOTIONS
# ============================================================

@admin_bp.route("/promos")
@promos_view_required
def promos():
    """
    View daily promotions.
    """

    return render_template(
        "admin/promos.html"
    )


@admin_bp.route("/promos/edit")
@promos_edit_required
def promos_edit():
    """
    Create/edit daily promotions.

    The Daily Promo system will be implemented separately.
    """

    return render_template(
        "admin/promos.html"
    )


# ============================================================
# EVENTS
# ============================================================

@admin_bp.route("/events")
@events_view_required
def events():
    """
    View events.
    """

    return render_template(
        "admin/events.html"
    )


@admin_bp.route("/events/edit")
@events_edit_required
def events_edit():
    """
    Create/edit events.

    Event functionality will be implemented separately.
    """

    return render_template(
        "admin/events.html"
    )


# ============================================================
# REPORTS
# ============================================================

@admin_bp.route("/reports")
@reports_view_required
def reports():
    """
    Administrative reports.
    """

    return render_template(
        "admin/reports.html"
    )


# ============================================================
# AUDIT LOG
# ============================================================

@admin_bp.route("/audit-log")
@audit_log_required
def audit_log():
    """
    View staff audit history.
    """

    logs = get_audit_logs()

    return render_template(
        "admin/audit_log.html",
        logs=logs,
    )


# ============================================================
# ROLE / PERMISSION MANAGEMENT
# ============================================================

@admin_bp.route("/roles")
@roles_required
def roles():
    """
    Manage roles and permissions.
    """

    role_list = get_roles()
    permission_list = get_permissions()

    return render_template(
        "admin/roles.html",
        roles=role_list,
        permissions=permission_list,
    )


# ============================================================
# SETTINGS
# ============================================================

@admin_bp.route("/settings")
@settings_required
def settings():
    """
    Administrative site settings.
    """

    return render_template(
        "admin/settings.html"
    )


# ============================================================
# DATABASE
# ============================================================

@admin_bp.route("/database")
@database_required
def database():
    """
    Database administration.
    """

    return render_template(
        "admin/database.html"
    )