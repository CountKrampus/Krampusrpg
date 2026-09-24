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

    # The development roadmap is database-backed.
    ensure_roadmap_tables()
    seed_roadmap()

    # ========================================================
    # BLUEPRINT REGISTRATION
    # ========================================================

    app.register_blueprint(
        admin_bp
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

        Expects JSON: {"area": "frostbite_route"}. Returns a transient
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

        encounter = start_encounter(area_id)

        if encounter is None:
            return jsonify(
                {
                    "success": True,
                    "encounter": None,
                    "message": "Nothing seems to be around here...",
                }
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
        return redirect(url_for("coming_soon"))

    @app.get("/story-adventure")
    def story_adventure():
        """
        The story quest hub: data-driven quest lines read from
        Data/quests/ (see Server/quest_chain.py). Shows quest line
        overview, quest chain, NPC teams, and the player's progress.
        """
        player_id = current_player_id()

        questlines = []

        for manifest in quest_chain.list_questlines():
            qid = manifest["id"]
            quests = quest_chain.get_quests(qid)
            totals = quest_chain.questline_totals(qid)

            # Decorate quests with resolved battles and completion state.
            completed: set[str] = set()
            active: set[str] = set()

            if player_id is not None:
                with get_connection() as db:
                    rows = db.execute(
                        """
                        SELECT quest_id, status
                        FROM player_quests
                        WHERE player_id = ?
                        """,
                        (player_id,),
                    ).fetchall()

                    for row in rows:
                        if row["status"] == "completed":
                            completed.add(row["quest_id"])
                        elif row["status"] == "active":
                            active.add(row["quest_id"])

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

            questlines.append(
                {
                    **manifest,
                    "quests": decorated,
                    "totals": totals,
                    "completed_count": completed_count,
                }
            )

        return render_template(
            "story_adventure.html",
            questlines=questlines,
        )

    # ========================================================
    # WORLD EXPLORATION (CATCHING)
    # ========================================================

    @app.get("/world-exploration")
    def world_exploration():
        """
        The wild area explorer: pick an area, search for wild
        Pokémon, and throw Poké Balls at what shows up.
        """
        player_id = current_player_id()

        areas = get_all_areas()

        player_area = None
        balls: list[dict[str, Any]] = []

        if player_id is not None:
            progress = get_player_progress(player_id)

            if progress:
                player_area = progress.get("current_area")

            balls = get_player_balls(player_id)

        return render_template(
            "world_exploration.html",
            areas=areas,
            player_area=player_area,
            balls=balls,
        )

    @app.get("/mines")
    def mines():
        return redirect(url_for("coming_soon"))

    @app.get("/pokemon-center")
    def pokemon_center():
        return redirect(url_for("coming_soon"))

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
    def training():
        return redirect(url_for("coming_soon"))

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

    @app.get("/locations")
    def locations():
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

    @app.get("/profile")
    def profile():
        """
        Player profile page.

        Profile ribbons are loaded from the existing role and
        badge systems.

        Ribbons are visual only and do not grant permissions.
        """

        player_id = current_player_id()

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