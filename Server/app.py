from __future__ import annotations

import sqlite3

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
from .config import DATABASE_PATH, SECRET_KEY, WEB_DIR
from .database import get_connection, init_db, seed_database
from .services import (
    add_to_party,
    create_pokemon,
    get_party,
    get_player_pokemon,
    get_species,
    remove_from_party,
)
from .news import (
    ensure_news_table,
    get_published_news,
)
from .pc_storage import ensure_pc_schema
from .pc_routes import pc_bp
from .admin.routes import admin_bp


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(WEB_DIR / "templates"),
        static_folder=str(WEB_DIR / "static"),
    )

    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["DATABASE"] = DATABASE_PATH

    # ------------------------------------------------------------------
    # Database initialization
    # ------------------------------------------------------------------

    init_db()
    seed_database()
    ensure_news_table()

    # PC storage is initialized after the base player/Pokémon tables.
    ensure_pc_schema()

    # ------------------------------------------------------------------
    # Blueprint registration
    # ------------------------------------------------------------------

    app.register_blueprint(admin_bp)
    app.register_blueprint(pc_bp)

    # ------------------------------------------------------------------
    # Public pages
    # ------------------------------------------------------------------

    @app.get("/")
    def index():
        player_id = current_player_id()

        if player_id is not None:
            return redirect(url_for("dashboard"))

        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "game": "Krampus RPG",
            }
        )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "GET":
            return render_template("register.html")

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        display_name = request.form.get(
            "display_name",
            username,
        ).strip()

        if not username or not password:
            return render_template(
                "register.html",
                error="Username and password are required.",
            )

        if len(username) < 3:
            return render_template(
                "register.html",
                error="Username must contain at least 3 characters.",
            )

        if len(password) < 6:
            return render_template(
                "register.html",
                error="Password must contain at least 6 characters.",
            )

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
                    (player_id,),
                )

                db.commit()

            except sqlite3.IntegrityError:
                return render_template(
                    "register.html",
                    error="That username is already in use.",
                )

        login_user(player_id)

        return redirect(url_for("dashboard"))

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html")

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with get_connection() as db:
            player = db.execute(
                """
                SELECT *
                FROM players
                WHERE username = ?
                """,
                (username,),
            ).fetchone()

        if player is None:
            return render_template(
                "login.html",
                error="Invalid username or password.",
            )

        if not verify_password(
            password,
            player["password_hash"],
        ):
            return render_template(
                "login.html",
                error="Invalid username or password.",
            )

        login_user(player["id"])

        return redirect(url_for("dashboard"))

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    @app.get("/logout")
    def logout():
        logout_user()
        return redirect(url_for("index"))

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    @app.get("/dashboard")
    def dashboard():
        player_id = current_player_id()

        if player_id is None:
            return redirect(url_for("login"))

        with get_connection() as db:
            player = db.execute(
                """
                SELECT *
                FROM players
                WHERE id = ?
                """,
                (player_id,),
            ).fetchone()

            if player is None:
                session.clear()
                return redirect(url_for("login"))

            progress = db.execute(
                """
                SELECT *
                FROM player_progress
                WHERE player_id = ?
                """,
                (player_id,),
            ).fetchone()

        pokemon = get_player_pokemon(player_id)
        party = get_party(player_id)
        news_posts = get_published_news()

        return render_template(
            "dashboard.html",
            player=dict(player),
            progress=dict(progress) if progress else {},
            pokemon=pokemon,
            party=party,
            news_posts=news_posts,
        )

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    @app.get("/profile")
    def profile():
        player_id = current_player_id()

        if player_id is None:
            return redirect(url_for("login"))

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
                (player_id,),
            ).fetchone()

            if player is None:
                session.clear()
                return redirect(url_for("login"))

            progress = db.execute(
                """
                SELECT *
                FROM player_progress
                WHERE player_id = ?
                """,
                (player_id,),
            ).fetchone()

            pokemon_count = db.execute(
                """
                SELECT COUNT(*) AS count
                FROM pokemon
                WHERE owner_id = ?
                """,
                (player_id,),
            ).fetchone()["count"]

            party_count = db.execute(
                """
                SELECT COUNT(*) AS count
                FROM party
                WHERE player_id = ?
                """,
                (player_id,),
            ).fetchone()["count"]

        pokemon = get_player_pokemon(player_id)
        party = get_party(player_id)

        return render_template(
            "profile.html",
            player=dict(player),
            progress=dict(progress) if progress else {},
            pokemon=pokemon,
            party=party,
            pokemon_count=pokemon_count,
            party_count=party_count,
        )

    # ------------------------------------------------------------------
    # Starter Pokémon
    # ------------------------------------------------------------------

    @app.route("/starter", methods=["GET", "POST"])
    def starter():
        player_id = current_player_id()

        if player_id is None:
            return redirect(url_for("login"))

        if request.method == "GET":
            return render_template(
                "starter.html",
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
                error="Invalid starter Pokémon.",
            )

        with get_connection() as db:
            existing = db.execute(
                """
                SELECT id
                FROM pokemon
                WHERE owner_id = ?
                LIMIT 1
                """,
                (player_id,),
            ).fetchone()

        if existing:
            return redirect(url_for("dashboard"))

        create_pokemon(
            owner_id=player_id,
            species_id=species_id,
            level=5,
        )

        with get_connection() as db:
            db.execute(
                """
                INSERT INTO player_quests
                (
                    player_id,
                    quest_id,
                    status
                )
                VALUES (?, ?, 'active')
                ON CONFLICT(player_id, quest_id)
                DO NOTHING
                """,
                (
                    player_id,
                    "welcome_to_krampus",
                ),
            )

            db.commit()

        return redirect(url_for("dashboard"))

    # ------------------------------------------------------------------
    # Current player API
    # ------------------------------------------------------------------

    @app.get("/api/me")
    def api_me():
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
                (player_id,),
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
                (player_id,),
            ).fetchone()

        return jsonify(
            {
                "logged_in": True,
                "player": dict(player),
                "progress": dict(progress)
                if progress
                else None,
            }
        )

    # ------------------------------------------------------------------
    # Pokémon API
    # ------------------------------------------------------------------

    @app.get("/api/pokemon")
    def api_pokemon():
        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "error": "Authentication required.",
                }
            ), 401

        return jsonify(
            {
                "pokemon": get_player_pokemon(player_id),
                "party": get_party(player_id),
            }
        )

    # ------------------------------------------------------------------
    # Create Pokémon API
    # ------------------------------------------------------------------

    @app.post("/api/pokemon/create")
    def api_create_pokemon():
        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}

        species_id = str(
            data.get("species_id", "")
        ).strip().lower()

        if not species_id:
            return jsonify(
                {
                    "error": "species_id is required.",
                }
            ), 400

        if get_species(species_id) is None:
            return jsonify(
                {
                    "error": "Unknown species.",
                }
            ), 400

        try:
            level = int(data.get("level", 5))
        except (TypeError, ValueError):
            level = 5

        variant = str(
            data.get("variant", "normal")
        ).strip().lower()

        shiny = bool(data.get("shiny", False))

        nickname = data.get("nickname")

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

    # ------------------------------------------------------------------
    # Party API
    # ------------------------------------------------------------------

    @app.post("/api/pokemon/<int:pokemon_id>/party")
    def api_party(pokemon_id: int):
        player_id = current_player_id()

        if player_id is None:
            return jsonify(
                {
                    "error": "Authentication required.",
                }
            ), 401

        data = request.get_json(silent=True) or {}
        action = data.get("action", "add")

        if action == "remove":
            success = remove_from_party(
                player_id,
                pokemon_id,
            )
        else:
            success = add_to_party(
                player_id,
                pokemon_id,
            )

        if not success:
            return jsonify(
                {
                    "success": False,
                    "error": "Party operation failed.",
                }
            ), 400

        return jsonify(
            {
                "success": True,
                "party": get_party(player_id),
            }
        )

    # ------------------------------------------------------------------
    # Final application object
    # ------------------------------------------------------------------

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5050,
        debug=False,
    )