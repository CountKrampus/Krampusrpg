"""
Krampus RPG Admin Routes

Central administrative dashboard and staff-management routes.

The admin system is organized around permissions rather than
a simple "is_admin" flag.

News management is restricted to Webmaster accounts.

Pokémon administration uses the current Party + PC storage
architecture and does not use the legacy pokemon.is_active field.
"""

from __future__ import annotations

from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .. import world_config
from ..world_config import REGION_LABELS
from ..database import get_connection
from ..services import get_all_moves

from ..news import (
    ensure_news_table,
    create_news_post,
    delete_news_post,
    get_all_news,
    get_news_post,
    update_news_post,
)

from ..roadmap import (
    CARD_PRIORITIES,
    CARD_STATUSES,
    STATUS_LABELS,
    create_card,
    create_milestone,
    create_task,
    delete_card,
    delete_milestone,
    delete_task,
    ensure_roadmap_tables,
    get_board,
    get_card,
    get_milestone,
    move_card,
    seed_roadmap,
    update_card,
    update_milestone,
    update_task,
)

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

from .permissions import (
    ROLE_WEBMASTER,
    ROLE_ADMIN,
    ROLE_MODERATOR,
    ROLE_EVENT_STAFF,
    get_player_role,
    player_has_permission,
)

from .audit import (
    log_action,
    log_role_change,
    log_setting_change,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_DELETE,
    ACTION_DATABASE_OPERATION,
    TARGET_POKEMON,
    TARGET_PLAYER,
    TARGET_PROMO,
    TARGET_EVENT,
    TARGET_ROLE,
    TARGET_SETTING,
    TARGET_DATABASE,
)

from .services import (
    ensure_admin_tables,
    get_dashboard_stats,
    get_players,
    search_players,
    get_player,
    get_player_details,
    update_player_role,
    get_pokemon,
    get_available_species,
    get_available_variants,
    admin_assign_pokemon,
    get_player_items,
    get_quests,
    get_roles,
    get_role,
    get_permissions,
    get_role_permissions,
    set_role_permissions,
    get_audit_logs,
    get_reports,
    get_report_by_id,
    update_report_status,
    create_report,
    get_promos,
    create_promo,
    toggle_promo_active,
    get_events,
    create_event,
    toggle_event_active,
    get_all_settings,
    update_settings,
    get_database_diagnostics,
    run_database_integrity_check,
    create_database_backup,
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
# ROLE & PERMISSION TEMPLATE GLOBALS
# ============================================================

def webmaster_required(func):
    """
    Restrict a route to Webmaster accounts only.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        player_id = session.get("player_id")
        if player_id is None:
            abort(403)

        try:
            player_id = int(player_id)
        except (TypeError, ValueError):
            abort(403)

        with get_connection() as db:
            role_name = get_player_role(db, player_id)

        if role_name != ROLE_WEBMASTER:
            abort(403)

        return func(*args, **kwargs)

    return wrapper


@admin_bp.app_template_global("current_user_is_webmaster")
def current_user_is_webmaster() -> bool:
    """Return True when the current logged-in account is Webmaster."""
    player_id = session.get("player_id")
    if player_id is None:
        return False

    try:
        player_id = int(player_id)
    except (TypeError, ValueError):
        return False

    with get_connection() as db:
        return get_player_role(db, player_id) == ROLE_WEBMASTER


@admin_bp.app_template_global("current_user_role")
def current_user_role() -> str:
    """Return the role name of the currently logged-in account."""
    player_id = session.get("player_id")
    if player_id is None:
        return "player"

    try:
        player_id = int(player_id)
    except (TypeError, ValueError):
        return "player"

    with get_connection() as db:
        return get_player_role(db, player_id)


@admin_bp.app_template_global("current_user_has_permission")
def current_user_has_permission(permission: str) -> bool:
    """Check if the currently logged-in account has a specific permission."""
    player_id = session.get("player_id")
    if player_id is None:
        return False

    try:
        player_id = int(player_id)
    except (TypeError, ValueError):
        return False

    with get_connection() as db:
        return player_has_permission(db, player_id, permission)


@admin_bp.app_template_global("current_user_profile")
def current_user_profile() -> dict:
    """Return the profile info (id, username, display_name, role) of the logged-in staff."""
    player_id = session.get("player_id")
    if player_id is None:
        return {"id": None, "username": "Guest", "display_name": "Guest", "role": "player"}

    try:
        player_id = int(player_id)
    except (TypeError, ValueError):
        return {"id": None, "username": "Guest", "display_name": "Guest", "role": "player"}

    player = get_player(player_id)
    if player:
        return {
            "id": player.get("id"),
            "username": player.get("username", f"Staff #{player_id}"),
            "display_name": player.get("display_name") or player.get("username", f"Staff #{player_id}"),
            "role": player.get("role_name", "staff"),
        }

    return {"id": player_id, "username": f"Staff #{player_id}", "display_name": f"Staff #{player_id}", "role": "staff"}


# ============================================================
# MAIN DASHBOARD
# ============================================================

@admin_bp.route("/")
@dashboard_required
def dashboard():
    """
    Main staff dashboard with role-adapted widgets and stats.
    """
    ensure_admin_tables()
    stats = get_dashboard_stats()
    recent_logs = get_audit_logs(limit=6)

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_logs=recent_logs,
    )


# ============================================================
# PLAYERS
# ============================================================

@admin_bp.route("/players")
@players_view_required
def players():
    """
    View and filter player accounts.
    """
    query = request.args.get("q", "").strip()
    role_filter = request.args.get("role", "").strip()

    player_list = search_players(query=query or None, role_name=role_filter or None)
    all_roles = get_roles()

    return render_template(
        "admin/players.html",
        players=player_list,
        search_query=query,
        selected_role=role_filter,
        roles=all_roles,
    )


@admin_bp.route("/players/<int:player_id>")
@players_view_required
def player_detail(player_id: int):
    """
    View detailed information for a single player.
    """
    details = get_player_details(player_id)
    if not details:
        flash(f"Player #{player_id} was not found.", "error")
        return redirect(url_for("admin.players"))

    all_roles = get_roles()

    return render_template(
        "admin/player_detail.html",
        player=details,
        roles=all_roles,
    )


@admin_bp.post("/players/<int:player_id>/role")
def player_set_role(player_id: int):
    """
    Assign a new role to a player account.
    """
    staff_id = session.get("player_id")
    if staff_id is None:
        abort(403)

    try:
        staff_id = int(staff_id)
    except (TypeError, ValueError):
        abort(403)

    # Permission check: must have admin.roles or admin.players.edit
    with get_connection() as db:
        is_allowed = player_has_permission(db, staff_id, "admin.roles") or player_has_permission(db, staff_id, "admin.players.edit")
        staff_role = get_player_role(db, staff_id)

    if not is_allowed:
        abort(403)

    role_id_raw = request.form.get("role_id")
    if not role_id_raw:
        flash("Please specify a role to assign.", "error")
        return redirect(request.referrer or url_for("admin.players"))

    try:
        new_role_id = int(role_id_raw)
    except (TypeError, ValueError):
        flash("Invalid role ID.", "error")
        return redirect(request.referrer or url_for("admin.players"))

    target_player = get_player(player_id)
    if not target_player:
        flash(f"Player #{player_id} not found.", "error")
        return redirect(url_for("admin.players"))

    old_role = target_player.get("role_name", "player")

    target_new_role = get_role(new_role_id)
    if not target_new_role:
        flash("Selected role does not exist.", "error")
        return redirect(request.referrer or url_for("admin.players"))

    new_role_name = target_new_role["name"]

    # Hierarchy protection: only Webmaster can promote to Webmaster or Admin
    if new_role_name in [ROLE_WEBMASTER, ROLE_ADMIN] and staff_role != ROLE_WEBMASTER:
        flash("Only Webmasters can assign the Webmaster or Admin roles.", "error")
        return redirect(request.referrer or url_for("admin.players"))

    success = update_player_role(player_id, new_role_id)
    if success:
        log_role_change(
            player_id=staff_id,
            target_player_id=player_id,
            old_role=old_role,
            new_role=new_role_name,
        )
        flash(f"Updated {target_player.get('username')}'s role from {old_role.title()} to {new_role_name.title()}.", "success")
    else:
        flash("Failed to update player role.", "error")

    return redirect(request.referrer or url_for("admin.players"))


@admin_bp.route("/players/edit")
@players_edit_required
def players_edit():
    return redirect(url_for("admin.players"))


# ============================================================
# POKÉMON
# ============================================================

@admin_bp.route("/pokemon")
@pokemon_view_required
def pokemon():
    """
    View Pokémon administration with direct assign controls.
    """
    pokemon_list = get_pokemon()
    species_list = get_available_species()
    variants = get_available_variants()
    all_players = get_players(limit=250)

    # Optional preselected player for modal
    preselect_player_id = request.args.get("player_id", "")

    return render_template(
        "admin/pokemon.html",
        pokemon=pokemon_list,
        species_list=species_list,
        variants=variants,
        players=all_players,
        preselect_player_id=preselect_player_id,
    )


@admin_bp.post("/pokemon/assign")
@pokemon_edit_required
@webmaster_required
def pokemon_assign():
    """
    Directly assign a Pokémon to a player.

    Webmaster-only: PERMISSION_POKEMON_EDIT (the underlying permission
    this route also requires) is granted to both the admin and
    webmaster roles, since it covers routine Pokémon edits generally.
    Manually creating new Pokémon out of thin air is a bigger power
    than editing an existing one, so this route specifically -- not
    the pokemon.edit permission itself -- is additionally locked to
    Webmaster, the same way News management is.
    """
    staff_id = session.get("player_id")

    player_id_raw = request.form.get("player_id", "").strip()
    species_id = request.form.get("species_id", "").strip().lower()
    level_raw = request.form.get("level", "5").strip()
    shiny = request.form.get("shiny", "") == "1"
    variant = request.form.get("variant", "normal").strip().lower()
    nickname = request.form.get("nickname", "").strip()

    if not player_id_raw:
        flash("Please select or enter a player to receive the Pokémon.", "error")
        return redirect(url_for("admin.pokemon"))

    try:
        owner_id = int(player_id_raw)
    except (TypeError, ValueError):
        flash("Invalid player ID format.", "error")
        return redirect(url_for("admin.pokemon"))

    if not species_id:
        flash("Please select a Pokémon species.", "error")
        return redirect(url_for("admin.pokemon"))

    try:
        level = int(level_raw)
    except (TypeError, ValueError):
        level = 5

    try:
        result = admin_assign_pokemon(
            owner_id=owner_id,
            species_id=species_id,
            level=level,
            shiny=shiny,
            variant=variant,
            nickname=nickname or None,
        )

        new_mon = result["pokemon"]
        location = result["location"]
        owner = result["owner"]

        loc_str = "Party" if location.get("location") == "party" else f"PC Box {location.get('page', 1)}"

        # Log audit action
        log_action(
            player_id=staff_id,
            action=ACTION_CREATE,
            target_type=TARGET_POKEMON,
            target_id=new_mon["id"],
            details={
                "owner_id": owner_id,
                "owner_username": owner.get("username"),
                "species_id": species_id,
                "level": level,
                "shiny": shiny,
                "variant": variant,
                "nickname": nickname,
                "location": loc_str,
            },
        )

        flash(
            f"Successfully assigned Level {level} {species_id.title()} "
            f"({'Shiny ' if shiny else ''}{variant.title()}) to {owner.get('username')}! "
            f"Stored in: {loc_str}.",
            "success",
        )

    except Exception as exc:
        flash(f"Error assigning Pokémon: {exc}", "error")

    return redirect(url_for("admin.pokemon"))


@admin_bp.route("/pokemon/edit")
@pokemon_edit_required
def pokemon_edit():
    return redirect(url_for("admin.pokemon"))


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
    return redirect(url_for("admin.items"))


# ============================================================
# MOVES
# ============================================================

@admin_bp.route("/moves")
@pokemon_view_required
def moves():
    """
    Browse the move database (Sprint 2 / roadmap Phase 5: "Move
    database. Every move: ID, Name, Type, Category, Power, Accuracy,
    PP, Description.").

    Gated by pokemon_view_required rather than a dedicated
    moves-specific permission -- moves are Pokémon reference data
    with no destructive actions here (read-only browse), so reusing
    the existing Pokémon-view permission avoids adding a near-duplicate
    permission for what's conceptually the same access level.

    Read-only for now: there's no move CREATE/EDIT here because
    get_all_moves()/get_move() currently source from Data/moves.json
    (only 3 moves) as a fallback for a live "moves" database table
    that doesn't exist yet -- editing would need to write back to
    whichever of those is actually authoritative, which isn't decided.
    This page exists to make what already exists actually visible.
    """
    move_list = get_all_moves()

    return render_template(
        "admin/moves.html",
        moves=move_list,
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
    return redirect(url_for("admin.quests"))


# ============================================================
# NPC EDITOR (SPRITES + TEAMS)
# ============================================================

@admin_bp.route("/quests/npcs")
@quests_view_required
def npc_editor():
    """
    Character sprites and battle teams for every NPC in every quest
    line. Edits write straight to Data/quests/<line>/encounters.json.
    """
    from .. import quest_chain, npc_editor as npc_ed

    questlines = []

    for manifest in quest_chain.list_questlines():
        npcs = npc_ed.list_npcs(manifest["id"])

        for npc in npcs:
            # Sprite previews resolve through the same lookup the
            # battle pages use.
            npc["sprite_exists"] = bool(npc["sprite"])

        questlines.append(
            {
                "id": manifest["id"],
                "title": manifest.get("title", manifest["id"]),
                "npcs": npcs,
            }
        )

    return render_template(
        "admin/npc_editor.html",
        questlines=questlines,
        species_list=get_available_species(),
        variants=get_available_variants(),
    )


@admin_bp.post("/quests/npcs/<questline_id>/<npc_id>/sprite")
@quests_edit_required
def npc_sprite_save(questline_id: str, npc_id: str):
    """Set (or clear) an NPC's character sprite."""
    staff_id = session.get("player_id")

    sprite = request.form.get("sprite", "").strip()

    try:
        from .. import npc_editor as npc_ed

        npc = npc_ed.set_npc_sprite(questline_id, npc_id, sprite)

        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type="quest_npc",
            target_id=npc_id,
            details={
                "questline": questline_id,
                "sprite": npc.get("sprite", ""),
            },
        )
        flash(
            f"Sprite updated for {npc.get('name', npc_id)}.",
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("admin.npc_editor"))


@admin_bp.post("/quests/npcs/<questline_id>/<npc_id>/team")
@quests_edit_required
def npc_team_save(questline_id: str, npc_id: str):
    """
    Replace an NPC's team from the inline editor: parallel arrays of
    species / level / variant per member.
    """
    staff_id = session.get("player_id")

    species_ids = request.form.getlist("team_species")
    levels = request.form.getlist("team_level")
    variants = request.form.getlist("team_variant")

    team = []

    for index, species_id in enumerate(species_ids):
        if not str(species_id).strip():
            continue

        team.append(
            {
                "species_id": species_id,
                "level": levels[index] if index < len(levels) else "5",
                "variant": (
                    variants[index]
                    if index < len(variants)
                    else "normal"
                ),
            }
        )

    try:
        from .. import npc_editor as npc_ed

        npc = npc_ed.set_npc_team(questline_id, npc_id, team)

        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type="quest_npc",
            target_id=npc_id,
            details={
                "questline": questline_id,
                "team_size": len(team),
            },
        )
        flash(
            f"Team updated for {npc.get('name', npc_id)} "
            f"({len(team)} Pokémon).",
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("admin.npc_editor"))


# ============================================================
# DAILY PROMOTIONS
# ============================================================

@admin_bp.route("/promos")
@promos_view_required
def promos():
    """
    View daily promotions.
    """
    promo_list = get_promos()
    species_list = get_available_species()
    variants = get_available_variants()

    return render_template(
        "admin/promos.html",
        promos=promo_list,
        species_list=species_list,
        variants=variants,
    )


@admin_bp.post("/promos/create")
@promos_edit_required
def promos_create():
    """
    Create a new daily promotion.
    """
    staff_id = session.get("player_id")

    species_id = request.form.get("species_id", "").strip().lower()
    variant = request.form.get("variant", "normal").strip().lower()
    level_raw = request.form.get("level", "5").strip()
    starts_at = request.form.get("starts_at", "").strip() or None
    ends_at = request.form.get("ends_at", "").strip() or None
    active = request.form.get("active", "") == "1"

    if not species_id:
        flash("Species is required to create a promo.", "error")
        return redirect(url_for("admin.promos"))

    try:
        level = int(level_raw)
    except (TypeError, ValueError):
        level = 5

    promo_id = create_promo(
        species_id=species_id,
        variant=variant,
        level=level,
        starts_at=starts_at,
        ends_at=ends_at,
        active=active,
    )

    log_action(
        player_id=staff_id,
        action=ACTION_CREATE,
        target_type=TARGET_PROMO,
        target_id=promo_id,
        details={"species_id": species_id, "variant": variant, "level": level},
    )

    flash(f"Daily promo for {species_id.title()} created successfully!", "success")
    return redirect(url_for("admin.promos"))


@admin_bp.post("/promos/<int:promo_id>/toggle")
@promos_edit_required
def promos_toggle(promo_id: int):
    """
    Toggle promo active status.
    """
    staff_id = session.get("player_id")
    success = toggle_promo_active(promo_id)
    if success:
        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type=TARGET_PROMO,
            target_id=promo_id,
            details={"action": "toggle_active"},
        )
        flash(f"Promo #{promo_id} status updated.", "success")
    else:
        flash("Failed to update promo status.", "error")

    return redirect(url_for("admin.promos"))


@admin_bp.route("/promos/edit")
@promos_edit_required
def promos_edit():
    return redirect(url_for("admin.promos"))


# ============================================================
# EVENTS
# ============================================================

@admin_bp.route("/events")
@events_view_required
def events():
    """
    View events.
    """
    event_list = get_events()

    return render_template(
        "admin/events.html",
        events=event_list,
    )


@admin_bp.post("/events/create")
@events_edit_required
def events_create():
    """
    Create a new game event.
    """
    staff_id = session.get("player_id")

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    starts_at = request.form.get("starts_at", "").strip() or None
    ends_at = request.form.get("ends_at", "").strip() or None
    active = request.form.get("active", "") == "1"

    if not name:
        flash("Event name is required.", "error")
        return redirect(url_for("admin.events"))

    event_id = create_event(
        name=name,
        description=description,
        starts_at=starts_at,
        ends_at=ends_at,
        active=active,
    )

    log_action(
        player_id=staff_id,
        action=ACTION_CREATE,
        target_type=TARGET_EVENT,
        target_id=event_id,
        details={"name": name, "active": active},
    )

    flash(f"Event '{name}' created successfully!", "success")
    return redirect(url_for("admin.events"))


@admin_bp.post("/events/<int:event_id>/toggle")
@events_edit_required
def events_toggle(event_id: int):
    """
    Toggle event active status.
    """
    staff_id = session.get("player_id")
    success = toggle_event_active(event_id)
    if success:
        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type=TARGET_EVENT,
            target_id=event_id,
            details={"action": "toggle_active"},
        )
        flash(f"Event #{event_id} status updated.", "success")
    else:
        flash("Failed to update event status.", "error")

    return redirect(url_for("admin.events"))


@admin_bp.route("/events/edit")
@events_edit_required
def events_edit():
    return redirect(url_for("admin.events"))


# ============================================================
# WORLD CONFIG (AREAS, ENCOUNTERS, CATCH RATES)
# ============================================================

def _world_context(
    editing_area_id: str | None = None,
    error: str | None = None,
):
    """Shared template context for the world admin page."""

    areas = world_config.load_areas_document()["areas"]

    # Compute each encounter's share of its area's total weight so the
    # editor can show effective encounter percentages.
    for area in areas:
        encounters = area.get("encounters") or []
        total_weight = sum(
            float(entry.get("weight", 0) or 0)
            for entry in encounters
        )

        for entry in encounters:
            weight = float(entry.get("weight", 0) or 0)
            entry["_share"] = (
                round(100 * weight / total_weight, 1)
                if total_weight > 0
                else 0.0
            )

    editing_area = None

    if editing_area_id:
        editing_area = world_config.get_area_by_id(editing_area_id)

    return {
        "areas": areas,
        "editing_area": editing_area,
        "area_types": (
            "town", "route", "cave", "forest", "water", "mountain",
        ),
        "region_labels": REGION_LABELS,
        "catch_settings": world_config.get_catch_settings(),
        "error": error,
    }


@admin_bp.route("/world")
@pokemon_view_required
def world():
    """
    World configuration: wild areas, encounter tables, and catch
    rate tuning. Read access follows Pokémon view (world data is
    Pokémon reference data); all writes require Pokémon edit.
    """
    return render_template(
        "admin/world.html",
        **_world_context(),
        species_list=get_available_species(),
        variants=get_available_variants(),
    )


@admin_bp.route("/world/areas/create", methods=["POST"])
@pokemon_edit_required
def world_area_create():
    """Create a new (empty) wild area."""
    staff_id = session.get("player_id")

    try:
        area = world_config.create_area(
            name=request.form.get("name", ""),
            area_type=request.form.get("type", "route"),
            description=request.form.get("description", ""),
            region=request.form.get("region", "hollyhollow"),
        )

        log_action(
            player_id=staff_id,
            action=ACTION_CREATE,
            target_type="world_area",
            target_id=area["id"],
            details={"name": area["name"], "type": area["type"]},
        )
        flash(f"Area '{area['name']}' created. Add encounters next.", "success")
    except ValueError as exc:
        return render_template(
            "admin/world.html",
            **_world_context(error=str(exc)),
        )

    return redirect(url_for("admin.world"))


@admin_bp.route("/world/areas/<area_id>/edit", methods=["GET", "POST"])
@pokemon_edit_required
def world_area_edit(area_id: str):
    """Edit an area's display fields."""
    staff_id = session.get("player_id")

    if request.method == "GET":
        return render_template(
            "admin/world.html",
            **_world_context(editing_area_id=area_id),
        )

    try:
        world_config.update_area(
            area_id,
            name=request.form.get("name"),
            area_type=request.form.get("type"),
            description=request.form.get("description"),
            region=request.form.get("region"),
        )

        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type="world_area",
            target_id=area_id,
            details={"fields": ["name", "type", "description", "region"]},
        )
        flash("Area updated.", "success")
    except ValueError as exc:
        return render_template(
            "admin/world.html",
            **_world_context(
                editing_area_id=area_id,
                error=str(exc),
            ),
        )

    return redirect(url_for("admin.world"))


@admin_bp.post("/world/areas/<area_id>/delete")
@pokemon_edit_required
def world_area_delete(area_id: str):
    """Delete an area and all of its encounters."""
    staff_id = session.get("player_id")

    try:
        world_config.delete_area(area_id)

        log_action(
            player_id=staff_id,
            action=ACTION_DELETE,
            target_type="world_area",
            target_id=area_id,
            details={},
        )
        flash("Area deleted.", "success")
    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("admin.world"))


@admin_bp.post("/world/areas/<area_id>/encounters/add")
@pokemon_edit_required
def world_encounter_add(area_id: str):
    """Add one species encounter entry to an area."""
    staff_id = session.get("player_id")

    try:
        world_config.add_area_encounter(
            area_id,
            species_id=request.form.get("species_id", ""),
            min_level=request.form.get("min_level", 1),
            max_level=request.form.get("max_level", 5),
            weight=request.form.get("weight", 10),
            variant=request.form.get("variant", "normal"),
        )

        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type="world_area",
            target_id=area_id,
            details={
                "encounter_added": request.form.get("species_id", ""),
                "variant": request.form.get("variant", "normal"),
            },
        )
        flash("Encounter added.", "success")
    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("admin.world"))


@admin_bp.post("/world/areas/<area_id>/encounters/save")
@pokemon_edit_required
def world_encounters_save(area_id: str):
    """
    Bulk-save an area's encounter table from the inline editor
    (edit species/levels/weights for all rows at once).
    """
    staff_id = session.get("player_id")

    species_ids = request.form.getlist("enc_species")
    min_levels = request.form.getlist("enc_min")
    max_levels = request.form.getlist("enc_max")
    weights = request.form.getlist("enc_weight")
    variants = request.form.getlist("enc_variant")

    encounters = []

    for index, (species_id, min_level, max_level, weight) in enumerate(
        zip(species_ids, min_levels, max_levels, weights)
    ):
        encounters.append(
            {
                "species_id": species_id,
                "min_level": min_level,
                "max_level": max_level,
                "weight": weight,
                "variant": (
                    variants[index]
                    if index < len(variants)
                    else "normal"
                ),
            }
        )

    try:
        world_config.set_area_encounters(area_id, encounters)

        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type="world_area",
            target_id=area_id,
            details={"encounters_saved": len(encounters)},
        )
        flash("Encounter table saved.", "success")
    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("admin.world"))


@admin_bp.post("/world/areas/<area_id>/encounters/<int:index>/delete")
@pokemon_edit_required
def world_encounter_delete(area_id: str, index: int):
    """Remove one encounter row from an area."""
    staff_id = session.get("player_id")

    try:
        world_config.delete_area_encounter(area_id, index)

        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type="world_area",
            target_id=area_id,
            details={"encounter_index_removed": index},
        )
        flash("Encounter removed.", "success")
    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("admin.world"))


@admin_bp.post("/world/areas/<area_id>/unlock-searches")
@pokemon_edit_required
def world_area_unlock_searches(area_id: str):
    """
    Set the progression gate for an area: how many completed searches
    unlock it for players (0 = always open).
    """
    staff_id = session.get("player_id")

    try:
        area = world_config.set_area_unlock_searches(
            area_id,
            request.form.get("unlock_searches", 0),
        )

        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type="world_area",
            target_id=area_id,
            details={
                "unlock_searches": area.get("unlock_searches", 0),
            },
        )
        flash(
            f"Unlock requirement for '{area['name']}' set to "
            f"{area.get('unlock_searches', 0)} searches.",
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("admin.world"))


@admin_bp.post("/world/catch-settings")
@pokemon_edit_required
def world_catch_settings_save():
    """Save the global catch tuning values (shiny odds, clamps)."""
    staff_id = session.get("player_id")

    try:
        saved = world_config.save_catch_settings(
            shiny_odds=request.form.get("shiny_odds"),
            min_catch_chance=request.form.get("min_catch_chance"),
            max_catch_chance=request.form.get("max_catch_chance"),
            default_catch_rate=request.form.get("default_catch_rate"),
        )

        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type=TARGET_SETTING,
            target_id="world_catch_settings",
            details={
                "shiny_odds": saved["shiny_odds"],
                "min_catch_chance": saved["min_catch_chance"],
                "max_catch_chance": saved["max_catch_chance"],
                "default_catch_rate": saved["default_catch_rate"],
            },
        )
        flash("Catch settings saved.", "success")
    except Exception as exc:
        flash(f"Failed to save catch settings: {exc}", "error")

    return redirect(url_for("admin.world"))


# ============================================================
# REPORTS
# ============================================================

@admin_bp.route("/reports")
@reports_view_required
def reports():
    """
    Administrative and moderation reports triage.
    """
    status = request.args.get("status", "").strip().lower()
    report_list = get_reports(status=status or None)

    return render_template(
        "admin/reports.html",
        reports=report_list,
        current_status=status,
    )


@admin_bp.post("/reports/<int:report_id>/status")
@reports_view_required
def report_update_status(report_id: int):
    """
    Update a report's status (resolved, dismissed, open) with moderator notes.
    """
    staff_id = session.get("player_id")
    new_status = request.form.get("status", "").strip().lower()
    notes = request.form.get("notes", "").strip()

    if new_status not in {"open", "resolved", "dismissed"}:
        flash("Invalid status choice.", "error")
        return redirect(url_for("admin.reports"))

    success = update_report_status(
        report_id=report_id,
        status=new_status,
        staff_player_id=staff_id,
        resolution_notes=notes or None,
    )

    if success:
        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type="report",
            target_id=report_id,
            details={"status": new_status, "notes": notes},
        )
        flash(f"Report #{report_id} has been marked as {new_status.title()}.", "success")
    else:
        flash(f"Failed to update Report #{report_id}.", "error")

    return redirect(url_for("admin.reports"))


@admin_bp.post("/reports/create")
def report_create_post():
    """
    Create a new report.
    """
    reporter_id = session.get("player_id")
    reported_id_raw = request.form.get("reported_player_id", "").strip()
    reason = request.form.get("reason", "").strip()
    details = request.form.get("details", "").strip()

    if not reason:
        flash("A reason is required to submit a report.", "error")
        return redirect(request.referrer or url_for("admin.reports"))

    reported_player_id = None
    if reported_id_raw:
        try:
            reported_player_id = int(reported_id_raw)
        except (TypeError, ValueError):
            pass

    report_id = create_report(
        reporter_id=reporter_id,
        reported_player_id=reported_player_id,
        reason=reason,
        details=details or None,
    )

    flash(f"Report #{report_id} has been filed.", "success")
    return redirect(url_for("admin.reports"))


# ============================================================
# AUDIT LOG
# ============================================================

@admin_bp.route("/audit-log")
@audit_log_required
def audit_log():
    """
    View staff audit history with username joins and parsed JSON details.
    """
    logs = get_audit_logs(limit=150)

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


@admin_bp.post("/roles/<int:role_id>/permissions")
@webmaster_required
def role_update_permissions(role_id: int):
    """
    Save the permission set for a role (Webmaster only).
    """
    staff_id = session.get("player_id")
    target_role = get_role(role_id)

    if not target_role:
        flash("Role not found.", "error")
        return redirect(url_for("admin.roles"))

    perm_ids = request.form.getlist("permission_id")
    int_perm_ids: list[int] = []
    for pid in perm_ids:
        try:
            int_perm_ids.append(int(pid))
        except (TypeError, ValueError):
            pass

    try:
        set_role_permissions(role_id, int_perm_ids)
        log_action(
            player_id=staff_id,
            action=ACTION_UPDATE,
            target_type=TARGET_ROLE,
            target_id=role_id,
            details={"permissions_count": len(int_perm_ids)},
        )
        flash(f"Updated permissions for role '{target_role['name'].title()}'.", "success")
    except Exception as exc:
        flash(f"Error saving role permissions: {exc}", "error")

    return redirect(url_for("admin.roles"))


# ============================================================
# SETTINGS
# ============================================================

@admin_bp.route("/settings")
@settings_required
def settings():
    """
    Administrative site settings.
    """
    settings_list = get_all_settings()

    return render_template(
        "admin/settings.html",
        settings=settings_list,
    )


@admin_bp.post("/settings")
@settings_required
def settings_save():
    """
    Save updated site settings.
    """
    staff_id = session.get("player_id")
    updates: dict[str, str] = {}

    for key, val in request.form.items():
        if key.startswith("setting_"):
            setting_name = key[len("setting_"):]
            updates[setting_name] = val.strip()

    if updates:
        try:
            update_settings(updates)
            for sname, sval in updates.items():
                log_setting_change(
                    player_id=staff_id,
                    setting_name=sname,
                    old_value="[previous]",
                    new_value=sval,
                )
            flash("Site settings updated successfully.", "success")
        except Exception as exc:
            flash(f"Error saving settings: {exc}", "error")
    else:
        flash("No settings were submitted.", "warning")

    return redirect(url_for("admin.settings"))


# ============================================================
# DATABASE
# ============================================================

@admin_bp.route("/database")
@database_required
def database():
    """
    Database administration and diagnostics.
    """
    diagnostics = get_database_diagnostics()

    return render_template(
        "admin/database.html",
        db_info=diagnostics,
    )


@admin_bp.post("/database/backup")
@database_required
def database_backup():
    """
    Create a database backup.
    """
    staff_id = session.get("player_id")
    try:
        filename = create_database_backup()
        log_action(
            player_id=staff_id,
            action=ACTION_DATABASE_OPERATION,
            target_type=TARGET_DATABASE,
            target_id=filename,
            details={"operation": "backup", "filename": filename},
        )
        flash(f"Database backup created successfully: {filename}", "success")
    except Exception as exc:
        flash(f"Failed to create database backup: {exc}", "error")

    return redirect(url_for("admin.database"))


@admin_bp.post("/database/integrity-check")
@database_required
def database_integrity_check():
    """
    Run SQLite integrity check.
    """
    staff_id = session.get("player_id")
    result = run_database_integrity_check()

    log_action(
        player_id=staff_id,
        action=ACTION_DATABASE_OPERATION,
        target_type=TARGET_DATABASE,
        target_id="integrity_check",
        details={"result": result},
    )

    if result.lower() == "ok":
        flash("Database integrity check passed: OK (no corruption detected).", "success")
    else:
        flash(f"Database integrity warning: {result}", "error")

    return redirect(url_for("admin.database"))


# ============================================================
# NEWS (WEBMASTER ONLY)
# ============================================================

@admin_bp.route("/news")
@webmaster_required
def news():
    """
    Webmaster news management.
    """
    ensure_news_table()
    posts = get_all_news()

    return render_template(
        "admin/news.html",
        posts=posts,
        editing=None,
        create_mode=False,
    )


@admin_bp.route(
    "/news/create",
    methods=["GET", "POST"],
)
@webmaster_required
def news_create():
    """
    Create a new news article.
    """
    ensure_news_table()

    if request.method == "GET":
        return render_template(
            "admin/news.html",
            posts=get_all_news(),
            editing=None,
            create_mode=True,
        )

    title = request.form.get("title", "")
    content = request.form.get("content", "")
    published = request.form.get("published", "") == "1"

    player_id = session.get("player_id")
    if player_id is None:
        abort(403)

    try:
        player_id = int(player_id)
    except (TypeError, ValueError):
        abort(403)

    try:
        create_news_post(
            title=title,
            content=content,
            author_id=player_id,
            published=published,
        )
    except ValueError as exc:
        return render_template(
            "admin/news.html",
            posts=get_all_news(),
            editing={
                "title": title,
                "content": content,
                "published": published,
            },
            create_mode=True,
            error=str(exc),
        )

    flash("News article published successfully!", "success")
    return redirect(url_for("admin.news"))


@admin_bp.route(
    "/news/edit/<int:post_id>",
    methods=["GET", "POST"],
)
@webmaster_required
def news_edit(post_id: int):
    """
    Edit an existing news article.
    """
    ensure_news_table()

    post = get_news_post(post_id)
    if post is None:
        abort(404)

    if request.method == "GET":
        return render_template(
            "admin/news.html",
            posts=get_all_news(),
            editing=post,
            create_mode=False,
        )

    title = request.form.get("title", "")
    content = request.form.get("content", "")
    published = request.form.get("published", "") == "1"

    try:
        success = update_news_post(
            post_id=post_id,
            title=title,
            content=content,
            published=published,
        )
    except ValueError as exc:
        editing = dict(post)
        editing["title"] = title
        editing["content"] = content
        editing["published"] = 1 if published else 0

        return render_template(
            "admin/news.html",
            posts=get_all_news(),
            editing=editing,
            create_mode=False,
            error=str(exc),
        )

    if not success:
        abort(404)

    flash("News article updated successfully!", "success")
    return redirect(url_for("admin.news"))


@admin_bp.post("/news/delete/<int:post_id>")
@webmaster_required
def news_delete(post_id: int):
    """
    Delete a news article.
    """
    ensure_news_table()
    delete_news_post(post_id)
    flash("News article deleted.", "success")
    return redirect(url_for("admin.news"))


# ============================================================
# DEVELOPMENT ROADMAP (WEBMASTER-ONLY)
# ============================================================

def _roadmap_context(
    editing_card=None,
    editing_milestone=None,
    create_card_mode=False,
    create_milestone_mode=False,
    error=None,
):
    """Shared template context for the roadmap admin pages."""

    ensure_roadmap_tables()
    seed_roadmap()

    return {
        "board": get_board(),
        "statuses": CARD_STATUSES,
        "status_labels": STATUS_LABELS,
        "priorities": CARD_PRIORITIES,
        "milestones": get_board()["milestones"],
        "editing_card": editing_card,
        "editing_milestone": editing_milestone,
        "create_card_mode": create_card_mode,
        "create_milestone_mode": create_milestone_mode,
        "error": error,
    }


@admin_bp.route("/roadmap")
@webmaster_required
def roadmap():
    """
    Webmaster-only Kanban board for the development roadmap.
    """
    create_milestone_mode = request.args.get("new") == "milestone"

    return render_template(
        "admin/roadmap.html",
        **_roadmap_context(
            create_milestone_mode=create_milestone_mode,
        ),
    )


# ------------------------------------------------------------
# MILESTONE CRUD
# ------------------------------------------------------------

@admin_bp.post("/roadmap/milestones/create")
@webmaster_required
def roadmap_milestone_create():
    """
    Create a new roadmap milestone.
    """
    name = request.form.get("name", "")
    description = request.form.get("description", "")

    try:
        create_milestone(name, description)
    except ValueError as exc:
        return render_template(
            "admin/roadmap.html",
            **_roadmap_context(
                create_milestone_mode=True,
                editing_milestone={
                    "name": name,
                    "description": description,
                },
                error=str(exc),
            ),
        )

    flash("Milestone created.", "success")
    return redirect(url_for("admin.roadmap"))


@admin_bp.route("/roadmap/milestones/<int:milestone_id>/edit", methods=["GET", "POST"])
@webmaster_required
def roadmap_milestone_edit(milestone_id: int):
    """
    Edit or delete a milestone.
    """
    milestone = get_milestone(milestone_id)

    if milestone is None:
        abort(404)

    if request.method == "GET":
        return render_template(
            "admin/roadmap.html",
            **_roadmap_context(editing_milestone=milestone),
        )

    if request.form.get("action") == "delete":
        delete_milestone(milestone_id)
        flash("Milestone and all its cards were deleted.", "success")
        return redirect(url_for("admin.roadmap"))

    try:
        update_milestone(
            milestone_id,
            name=request.form.get("name"),
            description=request.form.get("description"),
        )
    except ValueError as exc:
        return render_template(
            "admin/roadmap.html",
            **_roadmap_context(
                editing_milestone={
                    **milestone,
                    "name": request.form.get("name", milestone["name"]),
                    "description": request.form.get(
                        "description", milestone["description"]
                    ),
                },
                error=str(exc),
            ),
        )

    flash("Milestone updated.", "success")
    return redirect(url_for("admin.roadmap"))


# ------------------------------------------------------------
# CARD CRUD
# ------------------------------------------------------------

@admin_bp.route("/roadmap/cards/create", methods=["GET", "POST"])
@webmaster_required
def roadmap_card_create():
    """
    Create a new roadmap card.
    """
    if request.method == "GET":
        return render_template(
            "admin/roadmap.html",
            **_roadmap_context(create_card_mode=True),
        )

    form = request.form

    try:
        milestone_id = int(form.get("milestone_id", ""))
    except (TypeError, ValueError):
        milestone_id = None

    if milestone_id is None:
        return render_template(
            "admin/roadmap.html",
            **_roadmap_context(
                create_card_mode=True,
                editing_card={
                    "title": form.get("title", ""),
                    "description": form.get("description", ""),
                    "status": form.get("status", "backlog"),
                    "priority": form.get("priority", "medium"),
                    "sprint": form.get("sprint", ""),
                    "assignee": form.get("assignee", ""),
                },
                error="Please choose a milestone for this card.",
            ),
        )

    try:
        card_id = create_card(
            milestone_id=milestone_id,
            title=form.get("title", ""),
            description=form.get("description", ""),
            status=form.get("status", "backlog"),
            priority=form.get("priority", "medium"),
            sprint=form.get("sprint", ""),
            assignee=form.get("assignee", ""),
        )
    except ValueError as exc:
        return render_template(
            "admin/roadmap.html",
            **_roadmap_context(
                create_card_mode=True,
                editing_card={
                    "title": form.get("title", ""),
                    "description": form.get("description", ""),
                    "status": form.get("status", "backlog"),
                    "priority": form.get("priority", "medium"),
                    "sprint": form.get("sprint", ""),
                    "assignee": form.get("assignee", ""),
                },
                error=str(exc),
            ),
        )

    # Optional initial checklist, one task per line.
    for line in form.get("tasks", "").splitlines():
        line = line.strip()
        if line:
            create_task(card_id, line)

    flash("Card created.", "success")
    return redirect(url_for("admin.roadmap"))


@admin_bp.route("/roadmap/cards/<int:card_id>/edit", methods=["GET", "POST"])
@webmaster_required
def roadmap_card_edit(card_id: int):
    """
    Edit a card: fields, checklist items, or delete it.
    """
    card = get_card(card_id)

    if card is None:
        abort(404)

    if request.method == "GET":
        return render_template(
            "admin/roadmap.html",
            **_roadmap_context(editing_card=card),
        )

    form = request.form
    action = form.get("action", "save")

    if action == "delete":
        delete_card(card_id)
        flash("Card deleted.", "success")
        return redirect(url_for("admin.roadmap"))

    if action == "add_task":
        label = form.get("task_label", "")
        try:
            create_task(card_id, label)
            flash("Task added.", "success")
        except ValueError as exc:
            flash(str(exc), "error")

        return redirect(url_for("admin.roadmap_card_edit", card_id=card_id))

    if action == "delete_task":
        try:
            task_id = int(form.get("task_id", ""))
        except (TypeError, ValueError):
            task_id = None

        if task_id is not None:
            delete_task(task_id)
            flash("Task removed.", "success")

        return redirect(url_for("admin.roadmap_card_edit", card_id=card_id))

    if action == "toggle_task":
        try:
            task_id = int(form.get("task_id", ""))
        except (TypeError, ValueError):
            task_id = None

        if task_id is not None:
            task = next(
                (t for t in card["tasks"] if t["id"] == task_id),
                None,
            )

            if task is not None:
                update_task(task_id, done=not bool(task["done"]))

        return redirect(url_for("admin.roadmap_card_edit", card_id=card_id))

    # Default: save the card fields.
    try:
        milestone_id_raw = form.get("milestone_id")
        milestone_id = (
            int(milestone_id_raw)
            if milestone_id_raw not in (None, "")
            else None
        )

        update_card(
            card_id,
            title=form.get("title"),
            description=form.get("description"),
            status=form.get("status"),
            priority=form.get("priority"),
            sprint=form.get("sprint"),
            assignee=form.get("assignee"),
            milestone_id=milestone_id,
        )
    except ValueError as exc:
        return render_template(
            "admin/roadmap.html",
            **_roadmap_context(
                editing_card={
                    **card,
                    "title": form.get("title", card["title"]),
                    "description": form.get(
                        "description", card["description"]
                    ),
                    "status": form.get("status", card["status"]),
                    "priority": form.get("priority", card["priority"]),
                    "sprint": form.get("sprint", card["sprint"]),
                    "assignee": form.get("assignee", card["assignee"]),
                },
                error=str(exc),
            ),
        )

    flash("Card updated.", "success")
    return redirect(url_for("admin.roadmap"))


@admin_bp.post("/roadmap/cards/<int:card_id>/move")
@webmaster_required
def roadmap_card_move(card_id: int):
    """
    Move a card to another Kanban column. Used both by drag-and-drop
    (JavaScript) and the per-card status select.
    """
    status = request.form.get("status", "")

    try:
        moved = move_card(card_id, status)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.roadmap"))

    if not moved:
        abort(404)

    if request.form.get("ajax"):
        from flask import jsonify

        card = get_card(card_id)

        return jsonify(
            {
                "success": True,
                "card": card,
            }
        )

    flash("Card moved.", "success")
    return redirect(url_for("admin.roadmap"))