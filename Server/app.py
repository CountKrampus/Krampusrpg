"""
Krampus RPG Application

Main Flask application.

Current Pokémon storage architecture:

    pokemon
       |
       +---- party
       |
       +---- pc_storage

The legacy pokemon.is_active party system is not used.

Current Pokémon design intentionally does not use:

    IVs
    EVs
    Nature
    Permanent Status

Party and PC are database-backed systems.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .auth import (
    create_password,
    current_player_id,
    login_user,
    logout_user,
    verify_password,
)

from .config import (
    DATABASE_PATH,
    SECRET_KEY,
    WEB_DIR,
)

from .database import (
    get_connection,
    init_db,
    seed_database,
)

from .services import (
    add_to_party,
    create_pokemon,
    get_party,
    get_player,
    get_player_pokemon,
    get_player_progress,
    get_species,
    remove_from_party,
)

from .services import (
    get_all_areas,
    get_area,
    update_player_progress,
)

from .world_config import REGION_LABELS

from .news import (
    ensure_news_table,
    get_published_news,
)

from .catching import (
    attempt_catch,
    calculate_catch_chance,
    get_player_balls,
    start_encounter,
)

from .roadmap import (
    ensure_roadmap_tables,
    get_board,
    seed_roadmap,
)

from .pc_storage import (
    ensure_pc_schema,
)

from .party_storage import (
    ensure_party_schema,
)

from .pc_routes import (
    pc_bp,
)

from .admin.routes import (
    admin_bp,
)

from .profile_ribbons import (
    get_player_ribbons,
)

from . import quest_chain
from . import chat
from .chat import (
    ChatError,
    CHAT_MESSAGE_MAX_LENGTH,
)

from . import battle_store
from .battle import BattleError

from . import gyms

from . import training
from .training import TrainingError

from . import krampus_points
from . import story_battle
from . import area_search_storage as area_search
from . import pokemon_center as pokemon_center_service
from .admin.kp_routes import kp_admin_bp


def world_config_area_requirement(area: dict[str, Any]) -> int:
    """
    An area's unlock_searches requirement (0 = always open), read
    defensively so hand-edited areas.json values can't crash the map.
    """

    try:
        return max(0, int(area.get("unlock_searches", 0) or 0))
    except (TypeError, ValueError):
        return 0

# ============================================================
# APPLICATION FACTORY
# ============================================================

def create_app() -> Flask:
    """
    Create and configure the Krampus RPG Flask application.
    """

    app = Flask(
        __name__,
        template_folder=str(
            WEB_DIR / "templates"
        ),
        static_folder=str(
            WEB_DIR / "static"
        ),
    )

    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["DATABASE"] = DATABASE_PATH

    # ========================================================
    # DATABASE INITIALIZATION
    # ========================================================

    init_db()
    seed_database()

    # Party and PC are both database-backed.
    ensure_party_schema()
    ensure_pc_schema()

    # News is database-backed.
    ensure_news_table()

    # Chat (shoutbox) is database-backed.
    chat.ensure_chat_tables()

    # Battles are database-backed.
    battle_store.ensure_battle_tables()

    # Training effort is database-backed.
    training.ensure_training_tables()

    # The development roadmap is database-backed.
    ensure_roadmap_tables()
    seed_roadmap()

    # Krampus Points premium currency is database-backed.
    krampus_points.ensure_kp_schema()

    # ========================================================
    # BLUEPRINT REGISTRATION
    # ========================================================

    app.register_blueprint(
        admin_bp
    )

    app.register_blueprint(
        kp_admin_bp
    )

    app.register_blueprint(
        pc_bp
    )

    # ========================================================
    # TEMPLATE HELPERS
    # ========================================================

    @app.context_processor
    def _quest_template_helpers():
        """
        Template helpers for quest data. quest_npc() resolves an NPC
        definition from a quest line's encounters.json so templates can
        show names/teams without passing everything through the view.
        """

        def quest_npc(questline_id: str, npc_id: str):
            return quest_chain.get_npc(questline_id, npc_id)

        return {
            "quest_npc": quest_npc,
        }

    # ========================================================
    # PUBLIC HOME PAGE
    # ========================================================

    @app.get("/")
    def index():
        """
        Main landing page.
        """

        player_id = current_player_id()

        if player_id is not None:
            return redirect(
                url_for("dashboard")
            )

        return render_template(
            "index.html"
        )

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    @app.get("/health")
    def health():
        """
        Basic server health check.
        """

        return jsonify(
            {
                "status": "ok",
                "game": "Krampus RPG",
            }
        )

    # ========================================================
    # DEVELOPMENT ROADMAP (PUBLIC)
    # ========================================================

    @app.get("/roadmap")
    def roadmap():
        """
        Public development roadmap — a living Kanban board showing what
        the Krampus RPG team is working on. Editable by Webmasters in
        the admin panel.
        """
        board = get_board()

        return render_template(
            "roadmap.html",
            board=board,
        )

    # ========================================================
    # WILD ENCOUNTER / CATCHING API
    # ========================================================

    @app.get("/api/world/areas")
    def api_world_areas():
        """All explorable areas with their encounter tables."""

        return jsonify(
            {
                "success": True,
                "areas": get_all_areas(),
            }
        )

    @app.post("/api/world/encounter")
    def api_world_encounter():
        """
        Search a wild area for a Pokémon.

        Expects JSON: {"area": "frostpine_route"}. Returns a transient
        encounter description (species, level, shiny, catch rates per
        ball) that the client must echo back to /api/world/catch.
        Nothing is stored until the catch succeeds.
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}
        area_id = str(data.get("area", "")).strip()

        area = get_area(area_id) if area_id else None

        if area is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Unknown area.",
                }
            ), 400

        # Progression gate: areas with an unlock_searches requirement
        # stay locked until the player has searched enough times
        # (anywhere) to meet it.
        required = world_config_area_requirement(area)

        if required > 0:
            done = area_search.get_total_searches(player_id)

            if done < required:
                return jsonify(
                    {
                        "success": False,
                        "error": (
                            f"{area.get('name', area_id)} is still locked. "
                            f"Complete {required - done} more search(es) "
                            f"to unlock it."
                        ),
                        "locked": True,
                        "searches_done": done,
                        "searches_required": required,
                    }
                ), 403

        encounter = start_encounter(area_id)

        if encounter is None:
            return jsonify(
                {
                    "success": True,
                    "encounter": None,
                    "message": "Nothing seems to be around here...",
                }
            )

        # Count the search AFTER a successful roll so failed/locked
        # attempts don't burn progression credit.
        searches_done = area_search.record_area_search(player_id, area["id"])

        # Live progression state so the client can refresh the unlock
        # bar and lock badges without a page reload (Search Again).
        areas_all = get_all_areas()
        next_locked = None

        for other in areas_all:
            other_required = world_config_area_requirement(other)

            if other_required <= searches_done:
                continue

            if (
                next_locked is None
                or other_required < next_locked["required"]
            ):
                next_locked = {
                    "name": other.get("name"),
                    "required": other_required,
                }

        if next_locked is not None:
            next_locked["remaining"] = max(
                0, next_locked["required"] - searches_done
            )
            next_locked["percent"] = round(
                100
                * searches_done
                / max(1, next_locked["required"]),
                1,
            )

        # Show the player what each of their balls would achieve.
        ball_chances = [
            {
                **ball,
                "catch_chance": calculate_catch_chance(
                    encounter,
                    ball["item_id"],
                ),
            }
            for ball in get_player_balls(player_id)
            if ball["quantity"] > 0
        ]

        # Persist the player's current location.
        update_player_progress(
            player_id,
            current_area=area["id"],
        )

        return jsonify(
            {
                "success": True,
                "encounter": encounter,
                "balls": ball_chances,
                "searches_done": searches_done,
                "progression": {
                    "searches_done": searches_done,
                    "next_locked": next_locked,
                },
            }
        )

    @app.post("/api/world/catch")
    def api_world_catch():
        """
        Throw a Poké Ball at a wild encounter.

        Expects JSON:

            {
                "encounter": {...exactly what /api/world/encounter
                              returned...},
                "ball": "great_ball" (optional; strongest owned ball
                         is used otherwise)
            }

        The server re-validates the encounter (species must exist, level
        in range) and consumes one ball from the bag. On success the
        wild Pokémon is created into the player's Party/PC.
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}

        encounter = data.get("encounter")

        if not isinstance(encounter, dict):
            return jsonify(
                {
                    "success": False,
                    "error": "encounter is required.",
                }
            ), 400

        ball = data.get("ball")

        try:
            result = attempt_catch(
                player_id,
                encounter,
                ball_item_id=(
                    str(ball).strip()
                    if ball and str(ball).strip()
                    else ""
                ),
            )
        except ValueError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 400
        except Exception:
            return jsonify(
                {
                    "success": False,
                    "error": "The catch attempt failed.",
                }
            ), 500

        return jsonify(
            {
                "success": True,
                **result,
                "balls": get_player_balls(player_id),
            }
        )

    # ========================================================
    # KRAMPUS CHAT (SHOUTBOX)
    # ========================================================

    @app.get("/chat")
    def chat_page():
        """
        The Krampus Chat shoutbox page.
        """

        player_id = current_player_id()

        if player_id is None:
            return redirect(url_for("login"))

        return render_template("chat.html")

    @app.get("/api/chat/messages")
    def api_chat_messages():
        """
        Poll endpoint: messages newer than ?after=<id>, plus the
        online player list. Also records a presence heartbeat.
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        if chat.is_chat_banned(player_id):
            return jsonify(
                {
                    "success": False,
                    "error": "You are banned from chat.",
                    "banned": True,
                }
            ), 403

        try:
            after_id = int(request.args.get("after", 0))
        except (TypeError, ValueError):
            after_id = 0

        chat.heartbeat(player_id)

        messages = chat.get_messages(after_id=after_id)

        # Decorate with what the client needs to render identity.
        for message in messages:
            message["is_mine"] = message["player_id"] == player_id
            message["is_system"] = bool(message["system"])

        # Current player's own state, so the UI can reflect mutes.
        mute = chat.get_active_mute(player_id)

        return jsonify(
            {
                "success": True,
                "messages": messages,
                "online": chat.get_online_players(),
                "last_id": (
                    messages[-1]["id"] if messages else after_id
                ),
                "muted": mute is not None,
                "mute_reason": (
                    chat._sanction_message("muted", mute)
                    if mute
                    else None
                ),
            }
        )

    @app.post("/api/chat/send")
    def api_chat_send():
        """
        Post one chat message as the logged-in player.
        Expects JSON: {"content": "..."}
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}
        content = str(data.get("content", ""))

        try:
            message = chat.send_message(player_id, content)
        except chat.ChatSanctioned as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                    "sanctioned": True,
                }
            ), 403
        except chat.RateLimited as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                    "rate_limited": True,
                }
            ), 429
        except chat.ChatError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 400

        if message is not None:
            message["is_mine"] = True
            message["is_system"] = bool(message["system"])

        # message is None when the text was a slash command fully
        # handled server-side (feedback arrives as a system message).

        return jsonify(
            {
                "success": True,
                "message": message,
            }
        )

    # ========================================================
    # BATTLES
    # ========================================================

    # ========================================================
    # GYMS
    # ========================================================

    @app.get("/gyms")
    def gyms_page():
        """The gym challenge hub: leaders, badges, prerequisites."""

        player_id = current_player_id()

        held_badges: list[str] = []

        if player_id is not None:
            held_badges = gyms.get_player_badges(player_id)

        badge_defs = gyms.get_badge_definitions()

        decorated = []

        for gym in gyms.get_gyms():
            item = dict(gym)
            item["_badge_held"] = (
                gym.get("badge") in held_badges
                if gym.get("badge")
                else False
            )

            if player_id is not None:
                available, reason = gyms.gym_available(gym, player_id)
                item["_available"] = available
                item["_lock_reason"] = reason
            else:
                item["_available"] = False
                item["_lock_reason"] = "Sign in to challenge gyms."

            decorated.append(item)

        return render_template(
            "gyms.html",
            gyms=decorated,
            badge_defs=badge_defs,
            held_badges=held_badges,
        )

    @app.post("/api/gym/challenge")
    def api_gym_challenge():
        """Start a gym battle. JSON: {"gym_id": "frostpine_gym"}"""

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}
        gym_id = str(data.get("gym_id", "")).strip()

        try:
            battle = gyms.start_gym_battle(player_id, gym_id)
        except ValueError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 400
        except BattleError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 400

        return jsonify(
            {
                "success": True,
                "battle": battle,
            }
        )

    @app.get("/api/gym/context/<int:battle_id>")
    def api_gym_context(battle_id: int):
        """Battle context for the fight page (gym tag, etc.)."""

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        return jsonify(
            {
                "success": True,
                "context": gyms.read_battle_context(battle_id),
            }
        )

    @app.post("/api/gym/resolve/<int:battle_id>")
    def api_gym_resolve(battle_id: int):
        """
        After a gym battle finishes, award badge/money once. The
        battle page calls this when the battle it just fought ends.
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        try:
            award = gyms.award_gym_victory(player_id, battle_id)
        except Exception:
            return jsonify(
                {
                    "success": False,
                    "error": "Could not resolve gym battle.",
                }
            ), 500

        return jsonify(
            {
                "success": True,
                "award": award,
            }
        )

    @app.get("/battle")
    def battle_page():
        """The battle arena: start NPC battles and fight them out."""

        player_id = current_player_id()

        if player_id is None:
            return redirect(url_for("login"))

        party = get_party(player_id)

        return render_template(
            "battle.html",
            party=party,
        )

    @app.get("/api/battle/state")
    def api_battle_state():
        """The player's active battle, or null."""

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        battle = battle_store.get_active_battle(player_id)

        return jsonify(
            {
                "success": True,
                "battle": battle,
            }
        )

    @app.post("/api/battle/start")
    def api_battle_start():
        """
        Start a battle.

        JSON: {"format": "trainer", "team": [{"species": ..., "level": ...} ...]}
              {"format": "wild", "species": ..., "level": ...}

        For now the opponent team comes from the request (the arena's
        challenge options); quest/story integration passes the same
        shape from the quest encounter data.
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}
        battle_format = str(data.get("format", "trainer")).lower()

        try:
            if battle_format == "wild":
                species = str(data.get("species", "")).strip().lower()

                if not species:
                    return jsonify(
                        {
                            "success": False,
                            "error": "species is required.",
                        }
                    ), 400

                try:
                    # No upper level cap: opponents may exceed the
                    # classic level 100 (leaderboard progression).
                    level = max(1, int(data.get("level", 5)))
                except (TypeError, ValueError):
                    level = 5

                try:
                    battle = battle_store.start_wild_battle(
                        player_id,
                        species,
                        level,
                    )
                except ValueError:
                    return jsonify(
                        {
                            "success": False,
                            "error": "Unknown species.",
                        }
                    ), 400
            else:
                team = data.get("team")

                if not isinstance(team, list) or not team:
                    return jsonify(
                        {
                            "success": False,
                            "error": "team is required.",
                        }
                    ), 400

                clean_team: list[dict[str, Any]] = []

                for member in team[:6]:
                    if not isinstance(member, dict):
                        continue

                    species = str(member.get("species", "")).strip().lower()

                    if not species:
                        continue

                    try:
                        # No upper level cap (leaderboard progression).
                        level = max(1, int(member.get("level", 5)))
                    except (TypeError, ValueError):
                        level = 5

                    clean_team.append(
                        {
                            "species": species,
                            "level": level,
                            "variant": str(
                                member.get("variant") or "normal"
                            ),
                        }
                    )

                if not clean_team:
                    return jsonify(
                        {
                            "success": False,
                            "error": "No valid opponents in team.",
                        }
                    ), 400

                try:
                    battle = battle_store.start_trainer_battle(
                        player_id,
                        clean_team,
                    )
                except ValueError:
                    return jsonify(
                        {
                            "success": False,
                            "error": "Unknown species in opponent team.",
                        }
                    ), 400

        except BattleError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 400

        return jsonify(
            {
                "success": True,
                "battle": battle,
            }
        )

    @app.post("/api/battle/action")
    def api_battle_action():
        """
        Take one battle action.
        JSON: {"battle_id": N, "action": {"type": "move", "slot": 0}}
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}

        try:
            battle_id = int(data.get("battle_id", 0))
        except (TypeError, ValueError):
            return jsonify(
                {
                    "success": False,
                    "error": "battle_id is required.",
                }
            ), 400

        action = data.get("action")

        if not isinstance(action, dict):
            return jsonify(
                {
                    "success": False,
                    "error": "action is required.",
                }
            ), 400

        try:
            battle = battle_store.battle_action(
                player_id,
                battle_id,
                action,
            )
        except BattleError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 400

        return jsonify(
            {
                "success": True,
                "battle": battle,
            }
        )

    @app.get("/api/chat/context")
    def api_chat_context():
        """
        The current player's chat context: avatar, staff flag, and the
        avatar choices for the picker.
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        from .admin.permissions import (
            get_player_role,
            is_staff_role,
        )

        with get_connection() as db:
            role = get_player_role(db, player_id)

        avatar = chat.get_chat_avatar(player_id)

        # A curated starter set for the picker (fan favourites), plus
        # any species can be typed with /avatar <name>.
        featured = [
            "pikachu",
            "charmander",
            "squirtle",
            "bulbasaur",
            "eevee",
            "snorlax",
            "gyarados",
            "dragonite",
            "umbreon",
            "absol",
            "ninetales",
            "froslass",
            "houndoom",
            "weavile",
            "gengar",
            "lampent",
        ]

        all_ids = chat._avatar_species_ids()
        choices = [a for a in featured if a in all_ids]

        return jsonify(
            {
                "success": True,
                "avatar": avatar,
                "avatar_url": chat.avatar_url(avatar),
                "choices": [
                    {
                        "id": a,
                        "url": chat.avatar_url(a),
                    }
                    for a in choices
                ],
                "is_staff": is_staff_role(role),
                "role": role,
            }
        )

    @app.post("/api/chat/avatar")
    def api_chat_avatar():
        """Set the current player's chat avatar. JSON: {"avatar": "pikachu"}"""

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}

        try:
            avatar = chat.set_chat_avatar(
                player_id,
                str(data.get("avatar", "")),
            )
        except chat.ChatError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 400

        return jsonify(
            {
                "success": True,
                "avatar": avatar,
                "avatar_url": chat.avatar_url(avatar),
            }
        )

    @app.post("/api/chat/delete/<int:message_id>")
    def api_chat_delete(message_id: int):
        """Staff only: soft-delete one message."""

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        try:
            deleted = chat.delete_message(message_id, player_id)
        except chat.ChatError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 403

        return jsonify(
            {
                "success": deleted,
                "deleted": deleted,
            }
        )

    @app.post("/api/chat/moderate/<int:target_player_id>")
    def api_chat_moderate(target_player_id: int):
        """
        Staff only: mute/unmute/ban/unban a player.
        Expects JSON: {"action": "mute|unmute|ban|unban",
                       "duration": 30 (minutes, optional),
                       "reason": "..." (optional)}
        """

        staff_player_id = current_player_id()

        if staff_player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}
        action = str(data.get("action", "")).strip().lower()

        duration_raw = data.get("duration")
        duration: int | None
        if duration_raw in (None, "", "permanent"):
            duration = None
        else:
            try:
                duration = max(1, int(duration_raw))
            except (TypeError, ValueError):
                duration = None

        reason_raw = data.get("reason")
        reason = str(reason_raw).strip() or None if reason_raw else None

        try:
            if action == "mute":
                chat.mute_player(
                    target_player_id,
                    staff_player_id,
                    duration_minutes=duration,
                    reason=reason,
                )
            elif action == "unmute":
                chat.unmute_player(target_player_id, staff_player_id)
            elif action == "ban":
                chat.ban_player(
                    target_player_id,
                    staff_player_id,
                    duration_minutes=duration,
                    reason=reason,
                )
            elif action == "unban":
                chat.unban_player(target_player_id, staff_player_id)
            else:
                return jsonify(
                    {
                        "success": False,
                        "error": "Unknown action.",
                    }
                ), 400
        except chat.ChatError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 403

        return jsonify(
            {
                "success": True,
                "action": action,
            }
        )

    # ========================================================
    # PUBLIC PROFILE BY NAME (MENTION TARGETS)
    # ========================================================

    @app.get("/profile")
    def profile():
        """Current player's profile page."""

        player_id = current_player_id()

        return _render_profile(player_id)

    @app.get("/profile/<username>")
    def profile_by_name(username: str):
        """
        Resolve a username or display name to the player profile
        page. @mentions in chat link here.
        """

        with get_connection() as db:
            row = db.execute(
                """
                SELECT id
                FROM players
                WHERE username = ? COLLATE NOCASE
                   OR display_name = ? COLLATE NOCASE
                LIMIT 1
                """,
                (username, username),
            ).fetchone()

        if row is None:
            player_id = current_player_id()

            if player_id is None:
                return redirect(url_for("login"))

            return _render_profile(player_id)

        return _render_profile(row["id"])

    # ========================================================
    # COMING SOON PAGES
    # ========================================================

    @app.get("/coming-soon")
    def coming_soon():
        """
        Generic coming soon page for unimplemented features.
        """
        return render_template("coming_soon.html")

    # Add catch-all routes for common navigation links
    @app.get("/pokedex")
    def pokedex():
        return redirect(url_for("coming_soon"))

    @app.get("/trades")
    def trades():
        return redirect(url_for("coming_soon"))

    @app.get("/friends")
    def friends():
        return redirect(url_for("coming_soon"))

    @app.get("/staff")
    def staff():
        return redirect(url_for("coming_soon"))

    @app.get("/rules")
    def rules():
        return redirect(url_for("coming_soon"))

    @app.get("/forums")
    def forums():
        return redirect(url_for("coming_soon"))

    @app.get("/change-image")
    def change_image():
        return redirect(url_for("coming_soon"))

    @app.get("/applications")
    def applications():
        return redirect(url_for("coming_soon"))

    @app.get("/records")
    def records():
        return redirect(url_for("coming_soon"))

    @app.get("/awards")
    def awards():
        return redirect(url_for("coming_soon"))

    @app.get("/referral")
    def referral():
        return redirect(url_for("coming_soon"))

    @app.get("/music-shop")
    def music_shop():
        return redirect(url_for("coming_soon"))

    @app.get("/battle-arena")
    def battle_arena():
        return redirect(url_for("battle_page"))

    @app.get("/story-adventure")
    def story_adventure():
        """
        The story quest hub: data-driven quest lines read from
        Data/quests/ (see Server/quest_chain.py). Shows quest line
        overview, quest chain, NPC teams, and the player's progress.
        """
        player_id = current_player_id()

        completed: set[str] = quest_chain.get_player_completed_quest_ids(
            player_id
        )
        active: set[str] = set()

        if player_id is not None:
            with get_connection() as db:
                active_rows = db.execute(
                    """
                    SELECT quest_id FROM player_quests
                    WHERE player_id = ? AND status = 'active'
                    """,
                    (player_id,),
                ).fetchall()

            active = {str(row["quest_id"]) for row in active_rows}

        questlines = []

        for manifest in quest_chain.list_questlines():
            qid = manifest["id"]
            quests = quest_chain.get_quests(qid)
            totals = quest_chain.questline_totals(qid)

            # Decorate quests with resolved battles and completion state.
            decorated = []
            for quest in quests:
                item = dict(quest)
                item["battles"] = quest_chain.quest_battles(qid, quest)
                item["is_completed"] = quest["id"] in completed
                item["is_active"] = quest["id"] in active

                # Availability: no unmet prerequisites.
                prereqs = quest.get("requirements") or []
                item["is_available"] = (
                    all(prereq in completed for prereq in prereqs)
                    if prereqs
                    else True
                )
                item["is_locked"] = (
                    bool(prereqs)
                    and not item["is_available"]
                )

                decorated.append(item)

            completed_count = sum(
                1 for q in decorated if q["is_completed"]
            )

            # Group quests into their manifest-defined chapters.
            chapter_groups = quest_chain.group_quests_by_chapter(
                qid, decorated
            )

            # The chapter the player is currently working through
            # (has an active quest, or the first not-yet-completed
            # chapter with available quests). Used to auto-expand
            # the right accordion in the UI.
            current_chapter = None
            for group in chapter_groups:
                chapter_quests = group["quests"]
                if any(q["is_active"] for q in chapter_quests):
                    current_chapter = group["chapter"]["id"]
                    break
            if current_chapter is None:
                for group in chapter_groups:
                    chapter_quests = group["quests"]
                    if any(not q["is_completed"] for q in chapter_quests):
                        current_chapter = group["chapter"]["id"]
                        break

            line_finished = bool(decorated) and completed_count == len(
                decorated
            )

            questlines.append(
                {
                    **manifest,
                    "quests": decorated,
                    "totals": totals,
                    "completed_count": completed_count,
                    "line_finished": line_finished,
                    "chapters": chapter_groups,
                    "current_chapter": current_chapter,
                    "line_open": False,
                }
            )

        # Group quest lines into sections (e.g. every Team Krampus
        # quest line under one banner) and lock each quest line until
        # the previous one is fully completed.
        sections = quest_chain.group_questlines_by_section(questlines)
        quest_chain.apply_questline_chain_locks(sections, completed)

        # The auto-expanded line is the first unlocked, unfinished
        # quest line in display order; everything else stays
        # collapsed. Guests get the very first line open.
        for section in sections:
            for manifest in section["questlines"]:
                if (
                    manifest.get("line_unlocked", True)
                    and not manifest.get("line_finished")
                ):
                    manifest["line_open"] = True
                    break
            else:
                continue
            break

        return render_template(
            "story_adventure.html",
            sections=sections,
            areas=get_all_areas(),
            region_labels=REGION_LABELS,
        )

    @app.get("/story-adventure/quest/<questline>/<quest_id>")
    def story_quest_detail(questline: str, quest_id: str):
        """
        One quest: dialogue, battles, and the player's live battle
        session for this quest (if any).
        """
        player_id = current_player_id()

        manifest = quest_chain.get_questline(questline)
        if manifest is None:
            return redirect(url_for("story_adventure"))

        quest = quest_chain.get_quest(questline, quest_id)
        if quest is None:
            return redirect(url_for("story_adventure"))

        # Quest line chain lock: a quest line stays locked until the
        # previous quest line is fully completed.
        line_locked, line_lock_reason = quest_chain.is_questline_locked(
            questline,
            quest_chain.get_player_completed_quest_ids(player_id),
        )

        if line_locked:
            flash(
                line_lock_reason or "This quest line is still locked.",
                "error",
            )
            return redirect(url_for("story_adventure"))

        battles = quest_chain.quest_battles(questline, quest)

        # Prerequisite + completion state.
        prereqs = quest.get("requirements") or []
        completed_quests: set[str] = set()
        active_quests: set[str] = set()
        defeated: set[tuple[str, int]] = set()

        if player_id is not None:
            with get_connection() as db:
                rows = db.execute(
                    """
                    SELECT quest_id, status FROM player_quests
                    WHERE player_id = ?
                    """,
                    (player_id,),
                ).fetchall()

            for row in rows:
                if row["status"] == "completed":
                    completed_quests.add(row["quest_id"])
                elif row["status"] == "active":
                    active_quests.add(row["quest_id"])

            defeated = story_battle.get_defeated_battles(player_id, questline)

        is_completed = quest["id"] in completed_quests
        is_available = (
            all(p in completed_quests for p in prereqs) if prereqs else True
        )

        # Party health: warn before starting a battle with fainted
        # Pokémon — the Center heals the party for free.
        fainted_count = 0
        party_size = 0

        if player_id is not None:
            party_members = get_party(player_id)
            party_size = len(party_members)
            fainted_count = sum(
                1
                for m in party_members
                if int(m.get("current_hp", 0) or 0) <= 0
            )

        # The first battle step not yet defeated.
        next_battle_index = next(
            (
                i
                for i in range(len(battles))
                if (quest["id"], i) not in defeated
            ),
            None,
        )

        session = None
        current_battle = None
        if (
            player_id is not None
            and not is_completed
            and is_available
            and next_battle_index is not None
        ):
            session = story_battle.get_story_battle(
                player_id, questline, quest["id"], next_battle_index
            )

            # The battle card for the step in progress (or the first
            # undefeated one) — supplies the NPC's sprite for the
            # live battle header.
            current_battle = battles[next_battle_index]

        return render_template(
            "story_quest.html",
            questline=manifest,
            quest=quest,
            battles=battles,
            defeated=defeated,
            is_completed=is_completed,
            is_available=is_available,
            is_active=quest["id"] in active_quests,
            next_battle_index=next_battle_index,
            battle_session=session,
            current_battle=current_battle,
            fainted_count=fainted_count,
            party_size=party_size,
        )

    @app.post("/story-adventure/quest/<questline>/<quest_id>/begin")
    def story_quest_begin(questline: str, quest_id: str):
        """Start (or resume) the next battle step of a quest."""
        player_id = current_player_id()

        if player_id is None:
            flash("Log in to play the Story Adventure.", "error")
            return redirect(url_for("login"))

        # Chain lock: no starting battles in a locked quest line.
        locked, reason = quest_chain.is_questline_locked(
            questline,
            quest_chain.get_player_completed_quest_ids(player_id),
        )
        if locked:
            flash(reason or "This quest line is still locked.", "error")
            return redirect(url_for("story_adventure"))

        battle_index_raw = request.form.get("battle_index", "0")

        try:
            battle_index = int(battle_index_raw)
        except (TypeError, ValueError):
            battle_index = 0

        try:
            story_battle.start_story_battle(
                player_id, questline, quest_id, battle_index
            )
        except ValueError as exc:
            flash(str(exc), "error")

        return redirect(
            url_for("story_quest_detail", questline=questline, quest_id=quest_id)
        )

    @app.post("/story-adventure/quest/<questline>/<quest_id>/claim")
    def story_quest_claim(questline: str, quest_id: str):
        """Claim rewards for a battle-free (story) quest."""
        player_id = current_player_id()

        if player_id is None:
            flash("Log in to play the Story Adventure.", "error")
            return redirect(url_for("login"))

        # Chain lock: no claiming rewards in a locked quest line.
        locked, reason = quest_chain.is_questline_locked(
            questline,
            quest_chain.get_player_completed_quest_ids(player_id),
        )
        if locked:
            flash(reason or "This quest line is still locked.", "error")
            return redirect(url_for("story_adventure"))

        try:
            summary = story_battle.complete_quest(player_id, questline, quest_id)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(
                url_for(
                    "story_quest_detail",
                    questline=questline,
                    quest_id=quest_id,
                )
            )

        if summary is None:
            flash("Quest rewards were already claimed.", "error")
        else:
            bits = [f"Quest complete! +{summary['money']} Pokédollars"]
            if summary["items"]:
                bits.append("Received: " + ", ".join(summary["items"]))
            if summary["xp"]:
                bits.append(f"+{summary['xp']} XP each")
            if summary.get("pokemon"):
                bits.append(summary["pokemon"])
            flash(" ".join(bits), "success")

        return redirect(
            url_for("story_quest_detail", questline=questline, quest_id=quest_id)
        )

    @app.post("/story-adventure/quest/<questline>/<quest_id>/turn")
    def story_quest_turn(questline: str, quest_id: str):
        """Take one battle turn: use a move or switch Pokémon."""
        player_id = current_player_id()

        if player_id is None:
            return redirect(url_for("login"))

        # Chain lock: no battle turns in a locked quest line.
        locked, reason = quest_chain.is_questline_locked(
            questline,
            quest_chain.get_player_completed_quest_ids(player_id),
        )
        if locked:
            flash(reason or "This quest line is still locked.", "error")
            return redirect(url_for("story_adventure"))

        battle_index_raw = request.form.get("battle_index", "0")
        move_id = (request.form.get("move_id") or "").strip() or None
        switch_raw = (request.form.get("switch_to") or "").strip()
        switch_to = int(switch_raw) if switch_raw.isdigit() else None

        try:
            battle_index = int(battle_index_raw)
        except (TypeError, ValueError):
            battle_index = 0

        try:
            result = story_battle.take_story_turn(
                player_id,
                questline,
                quest_id,
                battle_index,
                move_id=move_id,
                switch_to=switch_to,
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(
                url_for(
                    "story_quest_detail",
                    questline=questline,
                    quest_id=quest_id,
                )
            )

        outcome = result.get("outcome")

        if outcome == "won":
            try:
                summary = story_battle.complete_quest(
                    player_id, questline, quest_id
                )
            except ValueError:
                summary = None

            if summary is not None:
                bits = [f"You won! +{summary['money']} Pokédollars"]
                if summary["items"]:
                    bits.append("Received: " + ", ".join(summary["items"]))
                if summary["xp"]:
                    bits.append(f"+{summary['xp']} XP each")
                if summary.get("pokemon"):
                    bits.append(summary["pokemon"])
                flash(" ".join(bits), "success")
            else:
                flash("Battle won!", "success")

        elif outcome == "lost":
            flash(
                "All your Pokémon fainted... heal up and try again!",
                "error",
            )

        return redirect(
            url_for("story_quest_detail", questline=questline, quest_id=quest_id)
        )

    # ========================================================
    # WORLD EXPLORATION (CATCHING)
    # ========================================================

    @app.get("/world-exploration")
    def world_exploration():
        """
        The wild area explorer: pick an area, search for wild
        Pokémon, and throw Poké Balls at what shows up.

        Each area card shows its spawn table (species and weighted
        odds). Areas with an unlock_searches requirement stay locked
        until the player's total search count reaches the threshold;
        the page also shows progress toward the next locked area.
        """
        player_id = current_player_id()

        areas = get_all_areas()

        player_area = None
        balls: list[dict[str, Any]] = []
        searches_done = 0

        if player_id is not None:
            progress = get_player_progress(player_id)

            if progress:
                player_area = progress.get("current_area")

            balls = get_player_balls(player_id)
            searches_done = area_search.get_total_searches(player_id)

        # Decorate every area: spawn table with share-of-weight odds,
        # lock state, and, for locked areas, how far away unlocking is.
        next_locked = None

        for area in areas:
            required = world_config_area_requirement(area)
            locked = required > searches_done

            area["_locked"] = locked
            area["_unlock_searches"] = required

            if locked:
                area["_searches_remaining"] = required - searches_done

                if next_locked is None or required < next_locked["_unlock_searches"]:
                    next_locked = area

            # Spawn odds: each entry's weight as a share of the
            # area's total weight. Sorted rarest-last for reading order.
            encounters = sorted(
                area.get("encounters") or [],
                key=lambda e: float(e.get("weight", 0) or 0),
                reverse=True,
            )
            total_weight = sum(
                float(e.get("weight", 0) or 0) for e in encounters
            )

            spawns: list[dict[str, Any]] = []
            for entry in encounters:
                weight = float(entry.get("weight", 0) or 0)
                variant = str(entry.get("variant", "") or "").strip()
                chance = entry.get("variant_chance") or {}

                spawns.append(
                    {
                        "species_id": entry.get("species_id", ""),
                        "min_level": entry.get("min_level", 1),
                        "max_level": entry.get("max_level", 1),
                        "variant": variant if variant and variant != "normal" else None,
                        "rare_variant": bool(
                            chance.get("odds")
                            and int(chance.get("odds", 0) or 0) > 0
                        ),
                        "odds": (
                            round(100 * weight / total_weight, 1)
                            if total_weight > 0
                            else 0.0
                        ),
                    }
                )

            area["_spawns"] = spawns

        next_locked = None if next_locked is None else {
            "name": next_locked.get("name"),
            "required": next_locked["_unlock_searches"],
            "remaining": next_locked["_searches_remaining"],
            "percent": (
                round(
                    100 * searches_done / max(1, next_locked["_unlock_searches"]),
                    1,
                )
                if next_locked["_unlock_searches"] > 0
                else 100.0
            ),
        }

        return render_template(
            "world_exploration.html",
            areas=areas,
            player_area=player_area,
            balls=balls,
            searches_done=searches_done,
            next_locked=next_locked,
        )

    @app.get("/map")
    def world_map():
        """
        The world map: every region and its areas at a glance, with
        spawn counts, lock states, and jump links into exploration.
        """
        player_id = current_player_id()

        areas = get_all_areas()

        searches_done = 0
        player_area = None

        if player_id is not None:
            progress = get_player_progress(player_id)

            if progress:
                player_area = progress.get("current_area")

            searches_done = area_search.get_total_searches(player_id)

        regions: dict[str, list[dict[str, Any]]] = {}

        for area in areas:
            required = world_config_area_requirement(area)
            locked = required > searches_done

            area["_locked"] = locked
            area["_unlock_searches"] = required

            if locked:
                area["_searches_remaining"] = required - searches_done

            area["_is_current"] = area.get("id") == player_area

            regions.setdefault(
                str(area.get("region", "unknown")), []
            ).append(area)

        region_list = [
            {
                "id": region,
                "label": REGION_LABELS.get(
                    region, region.replace("_", " ").title()
                ),
                "areas": region_areas,
            }
            for region, region_areas in regions.items()
        ]

        # Canonical region order first, then anything else by id.
        region_order = list(REGION_LABELS.keys())
        region_list.sort(
            key=lambda r: (
                region_order.index(r["id"])
                if r["id"] in region_order
                else len(region_order),
                r["id"],
            )
        )

        return render_template(
            "map.html",
            regions=region_list,
            searches_done=searches_done,
        )

    @app.get("/locations")
    def locations():
        return redirect(url_for("world_map"))

    @app.get("/mines")
    def mines():
        return redirect(url_for("coming_soon"))

    # ========================================================
    # KRAMPUS POINTS SHOP (PLAYER-FACING)
    # ========================================================

    @app.get("/kp-shop")
    def kp_shop():
        """
        The Krampus Points shop: browse active shop items and spend
        KP on exclusive Pokémon, items, and area unlocks.
        """
        player_id = current_player_id()

        balance = 0
        owned_unlocks: set[str] = set()

        if player_id is not None:
            balance = krampus_points.get_balance(player_id)
            owned_unlocks = set(
                krampus_points.get_player_area_unlocks(player_id)
            )

        items = []

        for item in krampus_points.get_shop_items(active_only=True):
            entry = dict(item)
            entry["affordable"] = (
                player_id is not None and balance >= item["price"]
            )
            entry["owned"] = (
                item["item_type"] == "area_unlock"
                and item["item_ref"] in owned_unlocks
            )
            items.append(entry)

        return render_template(
            "kp_shop.html",
            items=items,
            balance=balance,
        )

    @app.post("/kp-shop/purchase")
    def kp_shop_purchase():
        """
        Buy a KP shop item. purchase_shop_item() validates stock,
        timing, and balance, then delivers the reward.
        """
        player_id = current_player_id()

        if player_id is None:
            flash("Log in to spend Krampus Points.", "error")
            return redirect(url_for("login"))

        item_id_raw = request.form.get("item_id", "").strip()

        try:
            item_id = int(item_id_raw)
        except (TypeError, ValueError):
            item_id = 0

        try:
            result = krampus_points.purchase_shop_item(player_id, item_id)
            flash(result["message"], "success")
        except ValueError as exc:
            flash(str(exc), "error")

        return redirect(url_for("kp_shop"))

    @app.get("/pokemon-center")
    def pokemon_center():
        """
        The Pokémon Center: review your party's HP and fully heal the
        team. PC-boxed Pokémon are not healed (they aren't battling).
        """
        player_id = current_player_id()

        if player_id is None:
            flash("Log in to visit the Pokémon Center.", "error")
            return redirect(url_for("login"))

        overview = pokemon_center_service.get_center_overview(player_id)

        return render_template(
            "pokemon_center.html",
            **overview,
        )

    @app.post("/pokemon-center/heal")
    def pokemon_center_heal():
        """Heal All: restore every party member to full HP."""
        player_id = current_player_id()

        if player_id is None:
            flash("Log in to visit the Pokémon Center.", "error")
            return redirect(url_for("login"))

        result = pokemon_center_service.heal_party(player_id)

        if result["healed"]:
            fee_note = (
                f" Fee: {result['fee']:,} Pokédollars."
                if result["fee"]
                else ""
            )
            flash(
                f"Your team is fighting fit! Healed {result['healed']} "
                f"Pokémon ({result['hp_restored']} HP restored).{fee_note}",
                "success",
            )
        else:
            flash("Your team is already at full health!", "success")

        return redirect(url_for("pokemon_center"))

    @app.get("/minigame-center")
    def minigame_center():
        return redirect(url_for("coming_soon"))

    @app.get("/research-center")
    def research_center():
        return redirect(url_for("coming_soon"))

    @app.get("/rock-exchange")
    def rock_exchange():
        return redirect(url_for("coming_soon"))

    @app.get("/my-party")
    def my_party():
        return redirect(url_for("pc.pc_page"))

    @app.get("/krampus-pc")
    def krampus_pc():
        return redirect(url_for("pc.pc_page"))

    @app.get("/pokemon-items")
    def pokemon_items():
        return redirect(url_for("coming_soon"))

    @app.get("/training")
    def training_page():
        """Focused training: party Pokémon, effort state, costs."""

        player_id = current_player_id()

        if player_id is None:
            return redirect(url_for("login"))

        members = training.get_training_view(player_id)

        progress = get_player_progress(player_id)
        money = int(progress.get("money", 0)) if progress else 0

        return render_template(
            "training.html",
            members=members,
            money=money,
            stats=training.TRAINABLE_STATS,
        )

    @app.post("/api/training/session")
    def api_training_session():
        """
        One training session.
        JSON: {"pokemon_id": N, "stat": "attack"}
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}

        try:
            pokemon_id = int(data.get("pokemon_id", 0))
        except (TypeError, ValueError):
            return jsonify(
                {
                    "success": False,
                    "error": "pokemon_id is required.",
                }
            ), 400

        try:
            result = training.train(
                player_id,
                pokemon_id,
                str(data.get("stat", "")),
            )
        except TrainingError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 400

        return jsonify(
            {
                "success": True,
                "result": result,
            }
        )

    @app.get("/main-plaza")
    def main_plaza():
        return redirect(url_for("coming_soon"))

    @app.get("/plaza-trades")
    def plaza_trades():
        return redirect(url_for("coming_soon"))

    @app.get("/plaza-market")
    def plaza_market():
        return redirect(url_for("coming_soon"))

    @app.get("/pokemon-trades")
    def pokemon_trades():
        return redirect(url_for("coming_soon"))


    @app.get("/special-areas")
    def special_areas():
        return redirect(url_for("coming_soon"))

    @app.get("/events")
    def events():
        return redirect(url_for("coming_soon"))

    @app.get("/inventory")
    def inventory():
        return redirect(url_for("coming_soon"))

    @app.get("/account-data")
    def account_data():
        return redirect(url_for("coming_soon"))

    @app.get("/settings")
    def settings():
        return redirect(url_for("coming_soon"))

    @app.get("/daily-reward")
    def daily_reward():
        return redirect(url_for("coming_soon"))

    @app.get("/daily-bonus")
    def daily_bonus():
        return redirect(url_for("coming_soon"))

    @app.get("/event-reward")
    def event_reward():
        return redirect(url_for("coming_soon"))

    @app.get("/rank-pokemon")
    def rank_pokemon():
        return redirect(url_for("coming_soon"))

    @app.get("/rank-money")
    def rank_money():
        return redirect(url_for("coming_soon"))

    @app.get("/rank-battles")
    def rank_battles():
        return redirect(url_for("coming_soon"))

    @app.get("/rank-collection")
    def rank_collection():
        return redirect(url_for("coming_soon"))

    @app.get("/item-shop")
    def item_shop():
        return redirect(url_for("coming_soon"))

    @app.get("/pokemon-market")
    def pokemon_market():
        return redirect(url_for("coming_soon"))

    @app.get("/trading")
    def trading():
        return redirect(url_for("coming_soon"))

    # ========================================================
    # REGISTRATION
    # ========================================================

    @app.route(
        "/register",
        methods=["GET", "POST"],
    )
    def register():
        """
        Register a new player account.
        """

        if request.method == "GET":
            return render_template(
                "register.html"
            )

        username = request.form.get(
            "username",
            "",
        ).strip()

        password = request.form.get(
            "password",
            "",
        )

        display_name = request.form.get(
            "display_name",
            username,
        ).strip()

        # ----------------------------------------------------
        # Validation
        # ----------------------------------------------------

        if not username or not password:
            return render_template(
                "register.html",
                error=(
                    "Username and password are required."
                ),
            )

        if len(username) < 3:
            return render_template(
                "register.html",
                error=(
                    "Username must contain "
                    "at least 3 characters."
                ),
            )

        if len(password) < 6:
            return render_template(
                "register.html",
                error=(
                    "Password must contain "
                    "at least 6 characters."
                ),
            )

        # ----------------------------------------------------
        # Create player
        # ----------------------------------------------------

        with get_connection() as db:

            try:
                cursor = db.execute(
                    """
                    INSERT INTO players
                    (
                        username,
                        password_hash,
                        display_name
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        username,
                        create_password(password),
                        display_name or username,
                    ),
                )

                player_id = cursor.lastrowid

                db.execute(
                    """
                    INSERT INTO player_progress
                    (
                        player_id
                    )
                    VALUES (?)
                    """,
                    (
                        player_id,
                    ),
                )

                db.commit()

            except sqlite3.IntegrityError:
                return render_template(
                    "register.html",
                    error=(
                        "That username is already in use."
                    ),
                )

        login_user(
            player_id
        )

        return redirect(
            url_for("dashboard")
        )

    # ========================================================
    # LOGIN
    # ========================================================

    @app.route(
        "/login",
        methods=["GET", "POST"],
    )
    def login():
        """
        Authenticate an existing player.
        """

        if request.method == "GET":
            return render_template(
                "login.html"
            )

        username = request.form.get(
            "username",
            "",
        ).strip()

        password = request.form.get(
            "password",
            "",
        )

        with get_connection() as db:

            player = db.execute(
                """
                SELECT *
                FROM players
                WHERE username = ?
                """,
                (
                    username,
                ),
            ).fetchone()

        if player is None:
            return render_template(
                "login.html",
                error=(
                    "Invalid username or password."
                ),
            )

        if not verify_password(
            password,
            player["password_hash"],
        ):
            return render_template(
                "login.html",
                error=(
                    "Invalid username or password."
                ),
            )

        login_user(
            player["id"]
        )

        return redirect(
            url_for("dashboard")
        )

    # ========================================================
    # LOGOUT
    # ========================================================

    @app.get("/logout")
    def logout():
        """
        Log the current player out.
        """

        logout_user()

        return redirect(
            url_for("index")
        )

    # ========================================================
    # DASHBOARD
    # ========================================================

    @app.get("/dashboard")
    def dashboard():
        """
        Player dashboard.
        """

        player_id = current_player_id()

        if player_id is None:
            return redirect(
                url_for("login")
            )

        with get_connection() as db:

            player = db.execute(
                """
                SELECT *
                FROM players
                WHERE id = ?
                """,
                (
                    player_id,
                ),
            ).fetchone()

            if player is None:
                session.clear()

                return redirect(
                    url_for("login")
                )

            progress = db.execute(
                """
                SELECT *
                FROM player_progress
                WHERE player_id = ?
                """,
                (
                    player_id,
                ),
            ).fetchone()

        pokemon = get_player_pokemon(
            player_id
        )

        party = get_party(
            player_id
        )

        news_posts = get_published_news()

        return render_template(
            "dashboard.html",
            player=dict(player),
            progress=(
                dict(progress)
                if progress
                else {}
            ),
            pokemon=pokemon,
            party=party,
            news_posts=news_posts,
        )

        # ========================================================
    # PROFILE
    # ========================================================

    def _render_profile(player_id: int):
        """
        Player profile page.

        Profile ribbons are loaded from the existing role and
        badge systems.

        Ribbons are visual only and do not grant permissions.
        """

        if player_id is None:
            return redirect(
                url_for("login")
            )

        with get_connection() as db:

            player = db.execute(
                """
                SELECT
                    id,
                    username,
                    display_name,
                    created_at,
                    last_login
                FROM players
                WHERE id = ?
                """,
                (
                    player_id,
                ),
            ).fetchone()

            if player is None:
                session.clear()

                return redirect(
                    url_for("login")
                )

            progress = db.execute(
                """
                SELECT *
                FROM player_progress
                WHERE player_id = ?
                """,
                (
                    player_id,
                ),
            ).fetchone()

            pokemon_count = db.execute(
                """
                SELECT COUNT(*) AS count
                FROM pokemon
                WHERE owner_id = ?
                """,
                (
                    player_id,
                ),
            ).fetchone()["count"]

            # Party membership comes from the party table.
            # There is intentionally no pokemon.is_active
            # reference here.

            party_count = db.execute(
                """
                SELECT COUNT(*) AS count
                FROM party
                WHERE player_id = ?
                """,
                (
                    player_id,
                ),
            ).fetchone()["count"]

            # ------------------------------------------------
            # PROFILE RIBBONS
            # ------------------------------------------------
            #
            # This uses the existing role and badges tables.
            #
            # Role ribbons:
            #   moderator
            #   administration
            #   webmaster
            #
            # Award ribbons:
            #   beta_tester
            #   sponsor
            #   artist
            #
            # Multiple ribbons are supported.
            # ------------------------------------------------

            profile_ribbons = get_player_ribbons(
                db,
                player_id,
            )

        pokemon = get_player_pokemon(
            player_id
        )

        party = get_party(
            player_id
        )

        return render_template(
            "profile.html",
            player=dict(player),
            progress=(
                dict(progress)
                if progress
                else {}
            ),
            pokemon=pokemon,
            party=party,
            pokemon_count=pokemon_count,
            party_count=party_count,
            profile_ribbons=profile_ribbons,
        )

    # ========================================================
    # STARTER POKÉMON
    # ========================================================

    @app.route(
        "/starter",
        methods=["GET", "POST"],
    )
    def starter():
        """
        Starter Pokémon selection.

        A starter is created through the current Pokémon service,
        which is responsible for putting the Pokémon into Party
        or PC storage.

        The old is_active system is not used.
        """

        player_id = current_player_id()

        if player_id is None:
            return redirect(
                url_for("login")
            )

        if request.method == "GET":
            return render_template(
                "starter.html"
            )

        species_id = request.form.get(
            "species_id",
            "",
        ).strip().lower()

        allowed = {
            "bulbasaur",
            "charmander",
            "squirtle",
        }

        if species_id not in allowed:
            return render_template(
                "starter.html",
                error=(
                    "Invalid starter Pokémon."
                ),
            )

        # ----------------------------------------------------
        # Prevent a second starter.
        #
        # Ownership is checked rather than Party membership
        # because the player's starter may already be in the PC.
        # ----------------------------------------------------

        with get_connection() as db:

            existing = db.execute(
                """
                SELECT id
                FROM pokemon
                WHERE owner_id = ?
                LIMIT 1
                """,
                (
                    player_id,
                ),
            ).fetchone()

        if existing is not None:
            return redirect(
                url_for("dashboard")
            )

        # ----------------------------------------------------
        # Validate species.
        # ----------------------------------------------------

        species = get_species(
            species_id
        )

        if species is None:
            return render_template(
                "starter.html",
                error=(
                    "That starter species is "
                    "not currently available."
                ),
            )

        # ----------------------------------------------------
        # Create starter.
        # ----------------------------------------------------

        try:
            create_pokemon(
                owner_id=player_id,
                species_id=species_id,
                level=5,
                variant="normal",
                shiny=False,
            )

        except ValueError as exc:
            return render_template(
                "starter.html",
                error=str(exc),
            )

        # ----------------------------------------------------
        # Start welcome quest.
        #
        # IMPORTANT:
        # The current database schema uses quests.id as the
        # quest identifier. There is no quest_id column on
        # the quests table.
        # ----------------------------------------------------

        try:
            with get_connection() as db:

                quest = db.execute(
                    """
                    SELECT id
                    FROM quests
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (
                        "welcome_to_krampus",
                    ),
                ).fetchone()

                if quest is not None:

                    db.execute(
                        """
                        INSERT INTO player_quests
                        (
                            player_id,
                            quest_id,
                            status
                        )
                        VALUES (?, ?, 'active')
                        ON CONFLICT(
                            player_id,
                            quest_id
                        )
                        DO NOTHING
                        """,
                        (
                            player_id,
                            quest["id"],
                        ),
                    )

                    db.commit()

        except sqlite3.Error:
            # Quest setup must never cause the starter
            # to be lost.
            pass

        return redirect(
            url_for("dashboard")
        )

    # ========================================================
    # CURRENT PLAYER API
    # ========================================================

    @app.get("/api/me")
    def api_me():
        """
        Return information about the currently authenticated
        player.
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "logged_in": False,
                }
            )

        with get_connection() as db:

            player = db.execute(
                """
                SELECT
                    id,
                    username,
                    display_name,
                    created_at,
                    last_login
                FROM players
                WHERE id = ?
                """,
                (
                    player_id,
                ),
            ).fetchone()

            if player is None:
                session.clear()

                return jsonify(
                    {
                        "logged_in": False,
                    }
                )

            progress = db.execute(
                """
                SELECT *
                FROM player_progress
                WHERE player_id = ?
                """,
                (
                    player_id,
                ),
            ).fetchone()

        return jsonify(
            {
                "logged_in": True,
                "player": dict(player),
                "progress": (
                    dict(progress)
                    if progress
                    else None
                ),
            }
        )

    # ========================================================
    # PLAYER POKÉMON API
    # ========================================================

    @app.get("/api/pokemon")
    def api_pokemon():
        """
        Return all Pokémon owned by the current player plus
        their current Party.

        PC storage remains database-backed and is included
        through get_player_pokemon().
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "error": (
                        "Authentication required."
                    ),
                }
            ), 401

        return jsonify(
            {
                "pokemon": get_player_pokemon(
                    player_id
                ),
                "party": get_party(
                    player_id
                ),
            }
        )

    # ========================================================
    # CREATE POKÉMON API
    # ========================================================

    @app.post("/api/pokemon/create")
    def api_create_pokemon():
        """
        Create a Pokémon for the current player.

        This endpoint is primarily useful for development/admin
        testing at this stage.
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "error": (
                        "Authentication required."
                    ),
                }
            ), 401

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        species_id = str(
            data.get(
                "species_id",
                "",
            )
        ).strip().lower()

        if not species_id:
            return jsonify(
                {
                    "error": (
                        "species_id is required."
                    ),
                }
            ), 400

        species = get_species(
            species_id
        )

        if species is None:
            return jsonify(
                {
                    "error": (
                        "Unknown species."
                    ),
                }
            ), 400

        # ----------------------------------------------------
        # Level
        # ----------------------------------------------------

        try:
            level = int(
                data.get(
                    "level",
                    5,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            level = 5

        level = max(
            1,
            min(
                level,
                100,
            ),
        )

        # ----------------------------------------------------
        # Variant
        # ----------------------------------------------------

        variant = str(
            data.get(
                "variant",
                "normal",
            )
        ).strip().lower()

        if not variant:
            variant = "normal"

        # ----------------------------------------------------
        # Shiny
        # ----------------------------------------------------

        shiny_value = data.get(
            "shiny",
            False,
        )

        if isinstance(
            shiny_value,
            str,
        ):
            shiny = shiny_value.lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        else:
            shiny = bool(
                shiny_value
            )

        # ----------------------------------------------------
        # Nickname
        # ----------------------------------------------------

        nickname = data.get(
            "nickname"
        )

        if nickname is not None:
            nickname = str(
                nickname
            ).strip()

            if not nickname:
                nickname = None

        # ----------------------------------------------------
        # Create Pokémon.
        # ----------------------------------------------------

        try:
            pokemon = create_pokemon(
                owner_id=player_id,
                species_id=species_id,
                level=level,
                variant=variant,
                shiny=shiny,
                nickname=nickname,
            )

        except ValueError as exc:
            return jsonify(
                {
                    "error": str(exc),
                }
            ), 400

        return jsonify(
            {
                "success": True,
                "pokemon": pokemon,
            }
        ), 201

    # ========================================================
    # PARTY API
    # ========================================================

    @app.post(
        "/api/pokemon/<int:pokemon_id>/party"
    )
    def api_party(
        pokemon_id: int,
    ):
        """
        Add or remove a Pokémon from Party.

        Removing a Pokémon from Party MUST move it to PC storage.

        That behavior is implemented by party_storage/services.
        This route never deletes a Pokémon.
        """

        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "error": (
                        "Authentication required."
                    ),
                }
            ), 401

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        action = str(
            data.get(
                "action",
                "add",
            )
        ).strip().lower()

        try:

            # ------------------------------------------------
            # REMOVE
            # ------------------------------------------------

            if action == "remove":

                result = remove_from_party(
                    player_id,
                    pokemon_id,
                )

            # ------------------------------------------------
            # ADD
            # ------------------------------------------------

            else:

                result = add_to_party(
                    player_id,
                    pokemon_id,
                )

        except ValueError as exc:
            return jsonify(
                {
                    "success": False,
                    "error": str(exc),
                }
            ), 400

        except Exception:
            return jsonify(
                {
                    "success": False,
                    "error": (
                        "Party operation failed."
                    ),
                }
            ), 500

        return jsonify(
            {
                "success": True,
                "result": result,
                "party": get_party(
                    player_id
                ),
            }
        )

    # ========================================================
    # APPLICATION
    # ========================================================

    return app


# ============================================================
# APPLICATION INSTANCE
# ============================================================

app = create_app()


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5050,
        debug=False,
    )