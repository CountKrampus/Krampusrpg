from __future__ import annotations

import argparse
import json
import secrets
import sqlite3
import sys
from pathlib import Path
from textwrap import dedent


# ============================================================
# Krampus RPG - Complete Foundation Generator
#
# Usage:
#   python setup_krampus_rpg.py
#   python setup_krampus_rpg.py --force
#   python setup_krampus_rpg.py --path "F:\\New folder\\Krampus RPG"
#
# The generator creates the complete RPG foundation.
# Existing sprite files are never deleted or modified.
# ============================================================


DEFAULT_PROJECT_NAME = "Krampus RPG"


def clean(text: str) -> str:
    return dedent(text).lstrip()


FILES: dict[str, str] = {}


# ============================================================
# Root files
# ============================================================

FILES["run.py"] = clean(
    r'''
    from Server.app import create_app

    app = create_app()

    if __name__ == "__main__":
        app.run(host="127.0.0.1", port=5000, debug=True)
    '''
)

FILES["init_db.py"] = clean(
    r'''
    from Server.database import init_db, seed_database

    if __name__ == "__main__":
        init_db()
        seed_database()
        print("Krampus RPG database initialized.")
    '''
)

FILES["requirements.txt"] = clean(
    r'''
    Flask>=3.0,<4.0
    Werkzeug>=3.0,<4.0
    '''
)

FILES[".gitignore"] = clean(
    r'''
    __pycache__/
    *.py[cod]
    *.sqlite
    *.sqlite3
    instance/*.db
    instance/*.sqlite
    .venv/
    venv/
    env/
    .env
    '''
)

FILES["README.md"] = clean(
    r'''
    # Krampus RPG

    A browser-based Pokémon-inspired RPG foundation.

    ## Requirements

    Python 3.10 or newer.

    ## Install

    ```text
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    ```

    ## Initialize

    ```text
    python init_db.py
    ```

    ## Start

    ```text
    python run.py
    ```

    Open:

    http://127.0.0.1:5000

    ## Foundation

    - Player accounts
    - Login and logout
    - SQLite persistence
    - Player profiles
    - Pokémon ownership
    - Unique Pokémon IDs
    - Species
    - Levels
    - Experience
    - HP
    - Gender
    - Nature
    - IVs
    - Moves
    - Abilities
    - Shiny Pokémon
    - Custom variants
    - Party management
    - Starter selection
    - Areas
    - Encounters
    - Items
    - Quests
    - Badges
    - Transaction logging

    ## Sprite convention

    Sprites are expected to use names such as:

    pikachu.png
    pikachu-shiny.png
    pikachu-ruby.png
    pikachu-ruby-shiny.png
    pikachu-sapphire.png
    pikachu-emerald.png
    pikachu-gold.png
    pikachu-silver.png

    Existing sprite files are not modified by the foundation setup.
    '''
)


# ============================================================
# Server package
# ============================================================

FILES["Server/__init__.py"] = ""

FILES["Server/config.py"] = clean(
    r'''
    from pathlib import Path


    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "Data"
    WEB_DIR = BASE_DIR / "Web"
    INSTANCE_DIR = BASE_DIR / "instance"

    DATABASE_PATH = INSTANCE_DIR / "krampus_rpg.sqlite3"

    SECRET_KEY = "change-this-secret-key-before-public-deployment"

    HOST = "127.0.0.1"
    PORT = 5000
    '''
)

FILES["Server/auth.py"] = clean(
    r'''
    import sqlite3

    from flask import session
    from werkzeug.security import check_password_hash, generate_password_hash


    def create_password(password: str) -> str:
        return generate_password_hash(password)


    def verify_password(password: str, password_hash: str) -> bool:
        return check_password_hash(password_hash, password)


    def login_user(player_id: int) -> None:
        session["player_id"] = player_id


    def logout_user() -> None:
        session.pop("player_id", None)


    def current_player_id() -> int | None:
        player_id = session.get("player_id")

        if player_id is None:
            return None

        try:
            return int(player_id)
        except (TypeError, ValueError):
            return None


    def require_player(db: sqlite3.Connection):
        player_id = current_player_id()

        if player_id is None:
            return None

        return db.execute(
            "SELECT * FROM players WHERE id = ?",
            (player_id,),
        ).fetchone()
    '''
)

FILES["Server/database.py"] = clean(
    r'''
    from __future__ import annotations

    import json
    import sqlite3
    from pathlib import Path

    from .config import DATABASE_PATH, DATA_DIR, INSTANCE_DIR


    SCHEMA = """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login TEXT
    );

    CREATE TABLE IF NOT EXISTS player_progress (
        player_id INTEGER PRIMARY KEY,
        current_region TEXT NOT NULL DEFAULT 'krampus',
        current_area TEXT NOT NULL DEFAULT 'krampus_town',
        money INTEGER NOT NULL DEFAULT 1000,
        badges INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS pokemon (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unique_id TEXT NOT NULL UNIQUE,
        owner_id INTEGER NOT NULL,
        species_id TEXT NOT NULL,
        nickname TEXT,
        level INTEGER NOT NULL DEFAULT 5,
        experience INTEGER NOT NULL DEFAULT 0,
        gender TEXT NOT NULL DEFAULT 'unknown',
        shiny INTEGER NOT NULL DEFAULT 0,
        variant TEXT NOT NULL DEFAULT 'normal',
        nature TEXT NOT NULL DEFAULT 'Hardy',
        current_hp INTEGER NOT NULL DEFAULT 1,
        max_hp INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'healthy',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (owner_id) REFERENCES players(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS pokemon_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pokemon_id INTEGER NOT NULL UNIQUE,
        hp_iv INTEGER NOT NULL DEFAULT 0,
        attack_iv INTEGER NOT NULL DEFAULT 0,
        defense_iv INTEGER NOT NULL DEFAULT 0,
        sp_attack_iv INTEGER NOT NULL DEFAULT 0,
        sp_defense_iv INTEGER NOT NULL DEFAULT 0,
        speed_iv INTEGER NOT NULL DEFAULT 0,
        hp_ev INTEGER NOT NULL DEFAULT 0,
        attack_ev INTEGER NOT NULL DEFAULT 0,
        defense_ev INTEGER NOT NULL DEFAULT 0,
        sp_attack_ev INTEGER NOT NULL DEFAULT 0,
        sp_defense_ev INTEGER NOT NULL DEFAULT 0,
        speed_ev INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (pokemon_id) REFERENCES pokemon(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS pokemon_moves (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pokemon_id INTEGER NOT NULL,
        move_id TEXT NOT NULL,
        slot INTEGER NOT NULL,
        current_pp INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (pokemon_id) REFERENCES pokemon(id) ON DELETE CASCADE,
        UNIQUE(pokemon_id, slot)
    );

    CREATE TABLE IF NOT EXISTS player_items (
        player_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (player_id, item_id),
        FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS quests (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        reward_money INTEGER NOT NULL DEFAULT 0,
        reward_item TEXT,
        reward_quantity INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS player_quests (
        player_id INTEGER NOT NULL,
        quest_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'available',
        progress INTEGER NOT NULL DEFAULT 0,
        completed_at TEXT,
        PRIMARY KEY (player_id, quest_id),
        FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
        FOREIGN KEY (quest_id) REFERENCES quests(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id INTEGER NOT NULL,
        badge_id TEXT NOT NULL,
        earned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
        UNIQUE(player_id, badge_id)
    );

    CREATE TABLE IF NOT EXISTS transaction_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id INTEGER,
        transaction_type TEXT NOT NULL,
        amount INTEGER NOT NULL DEFAULT 0,
        details TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE SET NULL
    );
    """


    def get_connection() -> sqlite3.Connection:
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(DATABASE_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


    def init_db() -> None:
        with get_connection() as db:
            db.executescript(SCHEMA)


    def load_json(filename: str):
        path = DATA_DIR / filename

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return json.load(file)


    def seed_database() -> None:
        init_db()

        quests = load_json("quests.json")

        with get_connection() as db:
            for quest in quests:
                db.execute(
                    """
                    INSERT OR IGNORE INTO quests
                    (
                        id,
                        name,
                        description,
                        reward_money,
                        reward_item,
                        reward_quantity
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        quest["id"],
                        quest["name"],
                        quest["description"],
                        quest.get("reward_money", 0),
                        quest.get("reward_item"),
                        quest.get("reward_quantity", 0),
                    ),
                )

            db.commit()
    '''
)

FILES["Server/services.py"] = clean(
    r'''
    from __future__ import annotations

    import json
    import secrets
    from pathlib import Path

    from .database import get_connection


    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "Data"


    def load_data(filename: str):
        path = DATA_DIR / filename

        if not path.exists():
            return []

        with path.open("r", encoding="utf-8") as file:
            return json.load(file)


    def get_species(species_id: str):
        for species in load_data("pokemon.json"):
            if species.get("id") == species_id:
                return species

        return None


    def get_move(move_id: str):
        for move in load_data("moves.json"):
            if move.get("id") == move_id:
                return move

        return None


    def get_ability(ability_id: str):
        for ability in load_data("abilities.json"):
            if ability.get("id") == ability_id:
                return ability

        return None


    def get_variant(variant_id: str):
        for variant in load_data("variants.json"):
            if variant.get("id") == variant_id:
                return variant

        return None


    def generate_unique_pokemon_id() -> str:
        with get_connection() as db:
            while True:
                value = "KRP-" + secrets.token_hex(6).upper()

                exists = db.execute(
                    "SELECT 1 FROM pokemon WHERE unique_id = ?",
                    (value,),
                ).fetchone()

                if not exists:
                    return value


    def calculate_hp(species: dict, level: int, iv: int = 0) -> int:
        base_hp = int(species.get("base_stats", {}).get("hp", 50))

        return max(
            1,
            ((2 * base_hp + iv) * level // 100) + level + 10,
        )


    def create_pokemon(
        owner_id: int,
        species_id: str,
        level: int = 5,
        variant: str = "normal",
        shiny: bool = False,
        nickname: str | None = None,
    ):
        species = get_species(species_id)

        if species is None:
            raise ValueError("Unknown Pokémon species.")

        level = max(1, min(100, int(level)))

        unique_id = generate_unique_pokemon_id()

        hp_iv = secrets.randbelow(32)
        attack_iv = secrets.randbelow(32)
        defense_iv = secrets.randbelow(32)
        sp_attack_iv = secrets.randbelow(32)
        sp_defense_iv = secrets.randbelow(32)
        speed_iv = secrets.randbelow(32)

        max_hp = calculate_hp(species, level, hp_iv)

        gender = species.get("gender_ratio", "unknown")

        if gender == "male":
            actual_gender = "male"
        elif gender == "female":
            actual_gender = "female"
        elif gender == "genderless":
            actual_gender = "genderless"
        else:
            actual_gender = (
                "female"
                if secrets.randbelow(100) < 50
                else "male"
            )

        if variant not in {
            item["id"]
            for item in load_data("variants.json")
        }:
            variant = "normal"

        with get_connection() as db:
            cursor = db.execute(
                """
                INSERT INTO pokemon
                (
                    unique_id,
                    owner_id,
                    species_id,
                    nickname,
                    level,
                    experience,
                    gender,
                    shiny,
                    variant,
                    nature,
                    current_hp,
                    max_hp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    unique_id,
                    owner_id,
                    species_id,
                    nickname,
                    level,
                    0,
                    actual_gender,
                    int(shiny),
                    variant,
                    "Hardy",
                    max_hp,
                    max_hp,
                ),
            )

            pokemon_id = cursor.lastrowid

            db.execute(
                """
                INSERT INTO pokemon_stats
                (
                    pokemon_id,
                    hp_iv,
                    attack_iv,
                    defense_iv,
                    sp_attack_iv,
                    sp_defense_iv,
                    speed_iv
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pokemon_id,
                    hp_iv,
                    attack_iv,
                    defense_iv,
                    sp_attack_iv,
                    sp_defense_iv,
                    speed_iv,
                ),
            )

            starter_moves = species.get("starting_moves", ["tackle"])

            for slot, move_id in enumerate(starter_moves[:4], start=1):
                move = get_move(move_id)

                if move is None:
                    continue

                db.execute(
                    """
                    INSERT INTO pokemon_moves
                    (
                        pokemon_id,
                        move_id,
                        slot,
                        current_pp
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        pokemon_id,
                        move_id,
                        slot,
                        move.get("pp", 10),
                    ),
                )

            db.commit()

            return get_pokemon(owner_id, pokemon_id)


    def get_pokemon(owner_id: int, pokemon_id: int):
        with get_connection() as db:
            pokemon = db.execute(
                """
                SELECT *
                FROM pokemon
                WHERE id = ?
                  AND owner_id = ?
                """,
                (pokemon_id, owner_id),
            ).fetchone()

            if pokemon is None:
                return None

            result = dict(pokemon)

            stats = db.execute(
                """
                SELECT *
                FROM pokemon_stats
                WHERE pokemon_id = ?
                """,
                (pokemon_id,),
            ).fetchone()

            result["stats"] = dict(stats) if stats else {}

            moves = db.execute(
                """
                SELECT pm.*, m.name, m.type, m.power, m.accuracy
                FROM pokemon_moves pm
                LEFT JOIN (
                    SELECT
                        json_extract(value, '$.id') AS id,
                        json_extract(value, '$.name') AS name,
                        json_extract(value, '$.type') AS type,
                        json_extract(value, '$.power') AS power,
                        json_extract(value, '$.accuracy') AS accuracy
                    FROM json_each(
                        readfile(?)
                    )
                ) m ON m.id = pm.move_id
                WHERE pm.pokemon_id = ?
                ORDER BY pm.slot
                """,
                (
                    str(DATA_DIR / "moves.json"),
                    pokemon_id,
                ),
            ).fetchall()

            if moves:
                result["moves"] = [dict(move) for move in moves]
            else:
                raw_moves = db.execute(
                    """
                    SELECT *
                    FROM pokemon_moves
                    WHERE pokemon_id = ?
                    ORDER BY slot
                    """,
                    (pokemon_id,),
                ).fetchall()

                result["moves"] = [dict(move) for move in raw_moves]

            return result


    def get_player_pokemon(owner_id: int):
        with get_connection() as db:
            rows = db.execute(
                """
                SELECT *
                FROM pokemon
                WHERE owner_id = ?
                ORDER BY id
                """,
                (owner_id,),
            ).fetchall()

            return [dict(row) for row in rows]


    def add_to_party(owner_id: int, pokemon_id: int) -> bool:
        with get_connection() as db:
            pokemon = db.execute(
                """
                SELECT id
                FROM pokemon
                WHERE id = ?
                  AND owner_id = ?
                """,
                (pokemon_id, owner_id),
            ).fetchone()

            if pokemon is None:
                return False

            party_count = db.execute(
                """
                SELECT COUNT(*)
                FROM pokemon
                WHERE owner_id = ?
                  AND is_active = 1
                """,
                (owner_id,),
            ).fetchone()[0]

            if party_count >= 6:
                return False

            db.execute(
                """
                UPDATE pokemon
                SET is_active = 1
                WHERE id = ?
                  AND owner_id = ?
                """,
                (pokemon_id, owner_id),
            )

            db.commit()
            return True


    def remove_from_party(owner_id: int, pokemon_id: int) -> bool:
        with get_connection() as db:
            cursor = db.execute(
                """
                UPDATE pokemon
                SET is_active = 0
                WHERE id = ?
                  AND owner_id = ?
                """,
                (pokemon_id, owner_id),
            )

            db.commit()

            return cursor.rowcount > 0


    def get_party(owner_id: int):
        with get_connection() as db:
            rows = db.execute(
                """
                SELECT *
                FROM pokemon
                WHERE owner_id = ?
                  AND is_active = 1
                ORDER BY id
                LIMIT 6
                """,
                (owner_id,),
            ).fetchall()

            return [dict(row) for row in rows]


    def add_item(owner_id: int, item_id: str, quantity: int = 1):
        if quantity <= 0:
            return

        with get_connection() as db:
            db.execute(
                """
                INSERT INTO player_items
                (
                    player_id,
                    item_id,
                    quantity
                )
                VALUES (?, ?, ?)
                ON CONFLICT(player_id, item_id)
                DO UPDATE SET quantity = quantity + excluded.quantity
                """,
                (
                    owner_id,
                    item_id,
                    quantity,
                ),
            )

            db.commit()


    def remove_item(owner_id: int, item_id: str, quantity: int = 1) -> bool:
        if quantity <= 0:
            return False

        with get_connection() as db:
            row = db.execute(
                """
                SELECT quantity
                FROM player_items
                WHERE player_id = ?
                  AND item_id = ?
                """,
                (owner_id, item_id),
            ).fetchone()

            if row is None or row["quantity"] < quantity:
                return False

            new_quantity = row["quantity"] - quantity

            if new_quantity <= 0:
                db.execute(
                    """
                    DELETE FROM player_items
                    WHERE player_id = ?
                      AND item_id = ?
                    """,
                    (owner_id, item_id),
                )
            else:
                db.execute(
                    """
                    UPDATE player_items
                    SET quantity = ?
                    WHERE player_id = ?
                      AND item_id = ?
                    """,
                    (
                        new_quantity,
                        owner_id,
                        item_id,
                    ),
                )

            db.commit()
            return True


    def log_transaction(
        player_id: int | None,
        transaction_type: str,
        amount: int = 0,
        details: str = "",
    ):
        with get_connection() as db:
            db.execute(
                """
                INSERT INTO transaction_log
                (
                    player_id,
                    transaction_type,
                    amount,
                    details
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    player_id,
                    transaction_type,
                    amount,
                    details,
                ),
            )

            db.commit()
    '''
)

FILES["Server/app.py"] = clean(
    r'''
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


    def create_app() -> Flask:
        app = Flask(
            __name__,
            template_folder=str(WEB_DIR / "templates"),
            static_folder=str(WEB_DIR / "static"),
        )

        app.config["SECRET_KEY"] = SECRET_KEY
        app.config["DATABASE"] = DATABASE_PATH

        init_db()
        seed_database()

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

        @app.get("/logout")
        def logout():
            logout_user()
            return redirect(url_for("index"))

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

            return render_template(
                "dashboard.html",
                player=dict(player),
                progress=dict(progress) if progress else {},
                pokemon=pokemon,
                party=party,
            )

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
                    "player": dict(player) if player else None,
                    "progress": dict(progress)
                    if progress
                    else None,
                }
            )

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

        return app


    app = create_app()


    if __name__ == "__main__":
        app.run(
            host="127.0.0.1",
            port=5000,
            debug=True,
        )
    '''
)


# ============================================================
# Game packages
# ============================================================

GAME_PACKAGES = [
    "Game",
    "Game/players",
    "Game/pokemon",
    "Game/encounters",
    "Game/battles",
    "Game/items",
    "Game/shops",
    "Game/quests",
    "Game/trading",
]

for package in GAME_PACKAGES:
    FILES[f"{package}/__init__.py"] = ""


FILES["Game/players/player.py"] = clean(
    r'''
    from Server.database import get_connection


    def get_player(player_id: int):
        with get_connection() as db:
            row = db.execute(
                """
                SELECT
                    p.*,
                    pp.current_region,
                    pp.current_area,
                    pp.money,
                    pp.badges
                FROM players p
                LEFT JOIN player_progress pp
                    ON pp.player_id = p.id
                WHERE p.id = ?
                """,
                (player_id,),
            ).fetchone()

            return dict(row) if row else None
    '''
)

FILES["Game/pokemon/pokemon.py"] = clean(
    r'''
    from Server.services import (
        create_pokemon,
        get_player_pokemon,
        get_pokemon,
    )


    __all__ = [
        "create_pokemon",
        "get_player_pokemon",
        "get_pokemon",
    ]
    '''
)

FILES["Game/encounters/encounters.py"] = clean(
    r'''
    from __future__ import annotations

    import random

    from Server.database import get_connection
    from Server.services import load_data


    def get_area(area_id: str):
        for area in load_data("areas.json"):
            if area.get("id") == area_id:
                return area

        return None


    def roll_encounter(area_id: str):
        area = get_area(area_id)

        if area is None:
            return None

        encounters = area.get("encounters", [])

        if not encounters:
            return None

        total = sum(
            max(0, int(item.get("weight", 0)))
            for item in encounters
        )

        if total <= 0:
            return None

        roll = random.randint(1, total)

        current = 0

        for encounter in encounters:
            current += max(
                0,
                int(encounter.get("weight", 0)),
            )

            if roll <= current:
                return encounter

        return encounters[-1]
    '''
)

FILES["Game/battles/battle.py"] = clean(
    r'''
    from __future__ import annotations


    def calculate_damage(
        attack: int,
        defense: int,
        power: int,
        level: int,
    ) -> int:
        attack = max(1, attack)
        defense = max(1, defense)
        power = max(1, power)
        level = max(1, level)

        damage = (
            (
                ((2 * level // 5) + 2)
                * power
                * attack
                // defense
            )
            // 50
        ) + 2

        return max(1, damage)


    def apply_damage(current_hp: int, damage: int) -> int:
        return max(
            0,
            current_hp - max(0, damage),
        )
    '''
)

FILES["Game/items/items.py"] = clean(
    r'''
    from Server.services import (
        add_item,
        remove_item,
    )


    __all__ = [
        "add_item",
        "remove_item",
    ]
    '''
)

FILES["Game/shops/shop.py"] = clean(
    r'''
    from Server.services import load_data


    def get_shop_items():
        return load_data("items.json")


    def get_item(item_id: str):
        for item in get_shop_items():
            if item.get("id") == item_id:
                return item

        return None
    '''
)

FILES["Game/quests/quests.py"] = clean(
    r'''
    from Server.database import get_connection


    def get_quests():
        with get_connection() as db:
            rows = db.execute(
                """
                SELECT *
                FROM quests
                ORDER BY id
                """
            ).fetchall()

            return [dict(row) for row in rows]


    def get_player_quests(player_id: int):
        with get_connection() as db:
            rows = db.execute(
                """
                SELECT
                    pq.*,
                    q.name,
                    q.description,
                    q.reward_money,
                    q.reward_item,
                    q.reward_quantity
                FROM player_quests pq
                JOIN quests q
                    ON q.id = pq.quest_id
                WHERE pq.player_id = ?
                ORDER BY q.id
                """,
                (player_id,),
            ).fetchall()

            return [dict(row) for row in rows]
    '''
)

FILES["Game/trading/trading.py"] = clean(
    r'''
    from __future__ import annotations


    def validate_trade(
        sender_id: int,
        receiver_id: int,
        pokemon_id: int,
    ) -> bool:
        if sender_id == receiver_id:
            return False

        if pokemon_id <= 0:
            return False

        return True


    # Actual trading transactions should be implemented server-side
    # before multiplayer trading is enabled.
    '''
)


# ============================================================
# Data
# ============================================================

FILES["Data/pokemon.json"] = clean(
    r'''
    [
        {
            "id": "bulbasaur",
            "name": "Bulbasaur",
            "type": ["grass", "poison"],
            "base_stats": {
                "hp": 45,
                "attack": 49,
                "defense": 49,
                "sp_attack": 65,
                "sp_defense": 65,
                "speed": 45
            },
            "abilities": ["overgrow"],
            "starting_moves": ["tackle"],
            "gender_ratio": "mixed"
        },
        {
            "id": "charmander",
            "name": "Charmander",
            "type": ["fire"],
            "base_stats": {
                "hp": 39,
                "attack": 52,
                "defense": 43,
                "sp_attack": 60,
                "sp_defense": 50,
                "speed": 65
            },
            "abilities": ["blaze"],
            "starting_moves": ["scratch"],
            "gender_ratio": "mixed"
        },
        {
            "id": "squirtle",
            "name": "Squirtle",
            "type": ["water"],
            "base_stats": {
                "hp": 44,
                "attack": 48,
                "defense": 65,
                "sp_attack": 50,
                "sp_defense": 64,
                "speed": 43
            },
            "abilities": ["torrent"],
            "starting_moves": ["tackle"],
            "gender_ratio": "mixed"
        },
        {
            "id": "pikachu",
            "name": "Pikachu",
            "type": ["electric"],
            "base_stats": {
                "hp": 35,
                "attack": 55,
                "defense": 40,
                "sp_attack": 50,
                "sp_defense": 50,
                "speed": 90
            },
            "abilities": ["static"],
            "starting_moves": ["tackle", "thundershock"],
            "gender_ratio": "mixed"
        }
    ]
    '''
)

FILES["Data/moves.json"] = clean(
    r'''
    [
        {
            "id": "tackle",
            "name": "Tackle",
            "type": "normal",
            "category": "physical",
            "power": 40,
            "accuracy": 100,
            "pp": 35
        },
        {
            "id": "scratch",
            "name": "Scratch",
            "type": "normal",
            "category": "physical",
            "power": 40,
            "accuracy": 100,
            "pp": 35
        },
        {
            "id": "thundershock",
            "name": "Thunder Shock",
            "type": "electric",
            "category": "special",
            "power": 40,
            "accuracy": 100,
            "pp": 30
        }
    ]
    '''
)

FILES["Data/abilities.json"] = clean(
    r'''
    [
        {
            "id": "overgrow",
            "name": "Overgrow",
            "description": "Powers up Grass-type moves when HP is low."
        },
        {
            "id": "blaze",
            "name": "Blaze",
            "description": "Powers up Fire-type moves when HP is low."
        },
        {
            "id": "torrent",
            "name": "Torrent",
            "description": "Powers up Water-type moves when HP is low."
        },
        {
            "id": "static",
            "name": "Static",
            "description": "May paralyze an opponent that makes contact."
        }
    ]
    '''
)

FILES["Data/items.json"] = clean(
    r'''
    [
        {
            "id": "poke_ball",
            "name": "Poké Ball",
            "type": "pokeball",
            "price": 200,
            "sell_price": 100,
            "description": "A standard ball used to catch wild Pokémon."
        },
        {
            "id": "great_ball",
            "name": "Great Ball",
            "type": "pokeball",
            "price": 600,
            "sell_price": 300,
            "description": "A better ball with a higher catch rate."
        },
        {
            "id": "ultra_ball",
            "name": "Ultra Ball",
            "type": "pokeball",
            "price": 1200,
            "sell_price": 600,
            "description": "A high-performance Pokémon catching device."
        },
        {
            "id": "potion",
            "name": "Potion",
            "type": "healing",
            "price": 300,
            "sell_price": 150,
            "heal": 20,
            "description": "Restores HP."
        },
        {
            "id": "super_potion",
            "name": "Super Potion",
            "type": "healing",
            "price": 700,
            "sell_price": 350,
            "heal": 60,
            "description": "Restores a moderate amount of HP."
        }
    ]
    '''
)

FILES["Data/areas.json"] = clean(
    r'''
    [
        {
            "id": "krampus_town",
            "name": "Krampus Town",
            "region": "krampus",
            "type": "town",
            "description": "The starting town of the Krampus RPG world.",
            "encounters": []
        },
        {
            "id": "frostbite_route",
            "name": "Frostbite Route",
            "region": "krampus",
            "type": "route",
            "description": "A snowy route outside Krampus Town.",
            "encounters": [
                {
                    "species_id": "pikachu",
                    "min_level": 3,
                    "max_level": 6,
                    "weight": 20
                },
                {
                    "species_id": "bulbasaur",
                    "min_level": 3,
                    "max_level": 5,
                    "weight": 10
                },
                {
                    "species_id": "charmander",
                    "min_level": 3,
                    "max_level": 5,
                    "weight": 10
                },
                {
                    "species_id": "squirtle",
                    "min_level": 3,
                    "max_level": 5,
                    "weight": 10
                }
            ]
        }
    ]
    '''
)

FILES["Data/variants.json"] = clean(
    r'''
    [
        {
            "id": "normal",
            "name": "Normal",
            "suffix": ""
        },
        {
            "id": "ruby",
            "name": "Ruby",
            "suffix": "-ruby"
        },
        {
            "id": "sapphire",
            "name": "Sapphire",
            "suffix": "-sapphire"
        },
        {
            "id": "emerald",
            "name": "Emerald",
            "suffix": "-emerald"
        },
        {
            "id": "gold",
            "name": "Gold",
            "suffix": "-gold"
        },
        {
            "id": "silver",
            "name": "Silver",
            "suffix": "-silver"
        }
    ]
    '''
)

FILES["Data/quests.json"] = clean(
    r'''
    [
        {
            "id": "welcome_to_krampus",
            "name": "Welcome to Krampus RPG",
            "description": "Choose your first Pokémon and begin your adventure.",
            "reward_money": 500,
            "reward_item": "poke_ball",
            "reward_quantity": 5
        },
        {
            "id": "first_capture",
            "name": "First Capture",
            "description": "Catch your first wild Pokémon.",
            "reward_money": 250,
            "reward_item": "poke_ball",
            "reward_quantity": 3
        }
    ]
    '''
)


# ============================================================
# Web templates
# ============================================================

FILES["Web/templates/base.html"] = clean(
    r'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >
        <title>{% block title %}Krampus RPG{% endblock %}</title>
        <link
            rel="stylesheet"
            href="{{ url_for('static', filename='css/style.css') }}"
        >
    </head>
    <body>
        <header class="topbar">
            <div class="logo">KRAMPUS RPG</div>

            <nav>
                {% if session.get("player_id") %}
                    <a href="{{ url_for('dashboard') }}">Dashboard</a>
                    <a href="{{ url_for('starter') }}">Starter</a>
                    <a href="{{ url_for('logout') }}">Logout</a>
                {% else %}
                    <a href="{{ url_for('login') }}">Login</a>
                    <a href="{{ url_for('register') }}">Register</a>
                {% endif %}
            </nav>
        </header>

        <main class="container">
            {% block content %}{% endblock %}
        </main>

        <footer>
            Krampus RPG Foundation
        </footer>
    </body>
    </html>
    '''
)

FILES["Web/templates/index.html"] = clean(
    r'''
    {% extends "base.html" %}

    {% block title %}Krampus RPG{% endblock %}

    {% block content %}
    <section class="hero">
        <h1>Krampus RPG</h1>

        <p>
            Build your team. Explore the world. Catch Pokémon.
        </p>

        <div class="buttons">
            <a class="button" href="{{ url_for('register') }}">
                Create Account
            </a>

            <a class="button secondary" href="{{ url_for('login') }}">
                Login
            </a>
        </div>
    </section>
    {% endblock %}
    '''
)

FILES["Web/templates/register.html"] = clean(
    r'''
    {% extends "base.html" %}

    {% block title %}Create Account{% endblock %}

    {% block content %}
    <div class="card form-card">
        <h1>Create Account</h1>

        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}

        <form method="post">
            <label>Username</label>
            <input
                type="text"
                name="username"
                required
                minlength="3"
            >

            <label>Display Name</label>
            <input
                type="text"
                name="display_name"
            >

            <label>Password</label>
            <input
                type="password"
                name="password"
                required
                minlength="6"
            >

            <button type="submit">
                Create Account
            </button>
        </form>
    </div>
    {% endblock %}
    '''
)

FILES["Web/templates/login.html"] = clean(
    r'''
    {% extends "base.html" %}

    {% block title %}Login{% endblock %}

    {% block content %}
    <div class="card form-card">
        <h1>Login</h1>

        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}

        <form method="post">
            <label>Username</label>
            <input
                type="text"
                name="username"
                required
            >

            <label>Password</label>
            <input
                type="password"
                name="password"
                required
            >

            <button type="submit">
                Login
            </button>
        </form>
    </div>
    {% endblock %}
    '''
)

FILES["Web/templates/starter.html"] = clean(
    r'''
    {% extends "base.html" %}

    {% block title %}Choose Your Starter{% endblock %}

    {% block content %}
    <div class="card">
        <h1>Choose Your Starter</h1>

        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}

        <div class="starter-grid">
            <form method="post">
                <input
                    type="hidden"
                    name="species_id"
                    value="bulbasaur"
                >
                <button class="starter-button" type="submit">
                    <img
                        src="{{ url_for(
                            'static',
                            filename='sprites/bulbasaur.png'
                        ) }}"
                        alt="Bulbasaur"
                    >
                    <span>Bulbasaur</span>
                </button>
            </form>

            <form method="post">
                <input
                    type="hidden"
                    name="species_id"
                    value="charmander"
                >
                <button class="starter-button" type="submit">
                    <img
                        src="{{ url_for(
                            'static',
                            filename='sprites/charmander.png'
                        ) }}"
                        alt="Charmander"
                    >
                    <span>Charmander</span>
                </button>
            </form>

            <form method="post">
                <input
                    type="hidden"
                    name="species_id"
                    value="squirtle"
                >
                <button class="starter-button" type="submit">
                    <img
                        src="{{ url_for(
                            'static',
                            filename='sprites/squirtle.png'
                        ) }}"
                        alt="Squirtle"
                    >
                    <span>Squirtle</span>
                </button>
            </form>
        </div>
    </div>
    {% endblock %}
    '''
)

FILES["Web/templates/dashboard.html"] = clean(
    r'''
    {% extends "base.html" %}

    {% block title %}Dashboard{% endblock %}

    {% block content %}
    <div class="dashboard-header">
        <div>
            <h1>
                Welcome,
                {{ player.display_name }}
            </h1>

            <p>
                Region:
                {{ progress.current_region }}
                |
                Area:
                {{ progress.current_area }}
            </p>
        </div>

        <div class="money">
            {{ progress.money }} Pokécoins
        </div>
    </div>

    {% if pokemon|length == 0 %}
        <div class="card">
            <h2>Your adventure begins here.</h2>

            <p>
                You do not have a Pokémon yet.
            </p>

            <a
                class="button"
                href="{{ url_for('starter') }}"
            >
                Choose Starter
            </a>
        </div>
    {% else %}
        <section>
            <h2>Your Party</h2>

            <div class="pokemon-grid">
                {% for mon in party %}
                    <div class="pokemon-card">
                        <img
                            src="{{ url_for(
                                'static',
                                filename='sprites/' +
                                mon.species_id +
                                (
                                    '-' + mon.variant
                                    if mon.variant != 'normal'
                                    else ''
                                ) +
                                (
                                    '-shiny'
                                    if mon.shiny
                                    else ''
                                ) +
                                '.png'
                            ) }}"
                            alt="{{ mon.species_id }}"
                            onerror="this.style.display='none'"
                        >

                        <h3>
                            {{
                                mon.nickname
                                or
                                mon.species_id|title
                            }}
                        </h3>

                        <p>
                            Level {{ mon.level }}
                        </p>

                        <p>
                            HP
                            {{ mon.current_hp }}
                            /
                            {{ mon.max_hp }}
                        </p>

                        <p>
                            Variant:
                            {{ mon.variant }}
                        </p>

                        {% if mon.shiny %}
                            <p>✨ Shiny</p>
                        {% endif %}
                    </div>
                {% endfor %}
            </div>
        </section>

        <section>
            <h2>Pokémon Collection</h2>

            <div class="pokemon-grid">
                {% for mon in pokemon %}
                    <div class="pokemon-card small">
                        <h3>
                            {{
                                mon.nickname
                                or
                                mon.species_id|title
                            }}
                        </h3>

                        <p>
                            ID: {{ mon.unique_id }}
                        </p>

                        <p>
                            Level {{ mon.level }}
                        </p>

                        <p>
                            {{ mon.variant }}
                            {% if mon.shiny %}
                                · Shiny
                            {% endif %}
                        </p>
                    </div>
                {% endfor %}
            </div>
        </section>
    {% endif %}
    {% endblock %}
    '''
)


# ============================================================
# CSS
# ============================================================

FILES["Web/static/css/style.css"] = clean(
    r'''
    :root {
        font-family:
            Arial,
            Helvetica,
            sans-serif;

        background: #111318;
        color: #f4f4f4;
    }

    * {
        box-sizing: border-box;
    }

    body {
        margin: 0;
        min-height: 100vh;
        background:
            radial-gradient(
                circle at top,
                #252936,
                #111318 60%
            );
    }

    .topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 20px;
        padding: 16px 22px;
        background: #090a0d;
        border-bottom: 1px solid #333741;
        position: sticky;
        top: 0;
        z-index: 10;
    }

    .logo {
        font-weight: 900;
        letter-spacing: 2px;
    }

    nav {
        display: flex;
        gap: 14px;
        flex-wrap: wrap;
    }

    a {
        color: #ffffff;
        text-decoration: none;
    }

    nav a:hover {
        text-decoration: underline;
    }

    .container {
        width: min(1100px, 94%);
        margin: 0 auto;
        padding: 35px 0;
    }

    footer {
        text-align: center;
        padding: 30px 15px;
        opacity: 0.6;
    }

    .hero {
        text-align: center;
        padding: 80px 20px;
    }

    .hero h1 {
        font-size: clamp(42px, 9vw, 86px);
        margin: 0 0 20px;
    }

    .hero p {
        font-size: 20px;
        opacity: 0.8;
    }

    .buttons {
        display: flex;
        justify-content: center;
        gap: 12px;
        flex-wrap: wrap;
        margin-top: 30px;
    }

    .button,
    button {
        display: inline-block;
        border: 0;
        border-radius: 10px;
        padding: 13px 18px;
        background: #e7e7e7;
        color: #111318;
        cursor: pointer;
        font-weight: 700;
        font-size: 15px;
        text-decoration: none;
    }

    .button.secondary {
        background: #343945;
        color: #ffffff;
    }

    button:hover,
    .button:hover {
        transform: translateY(-1px);
        filter: brightness(1.08);
    }

    .card {
        background: #1a1d24;
        border: 1px solid #343945;
        border-radius: 16px;
        padding: 25px;
        margin-bottom: 25px;
    }

    .form-card {
        max-width: 480px;
        margin: 30px auto;
    }

    form {
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    label {
        margin-top: 8px;
        font-weight: 700;
    }

    input {
        width: 100%;
        padding: 13px;
        border-radius: 9px;
        border: 1px solid #414652;
        background: #101218;
        color: #ffffff;
        outline: none;
    }

    input:focus {
        border-color: #888f9e;
    }

    .error {
        padding: 12px;
        margin-bottom: 15px;
        border-radius: 8px;
        background: #542727;
        border: 1px solid #8c4141;
    }

    .dashboard-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 20px;
        margin-bottom: 30px;
        flex-wrap: wrap;
    }

    .money {
        font-weight: 900;
        font-size: 20px;
    }

    .pokemon-grid {
        display: grid;
        grid-template-columns:
            repeat(
                auto-fit,
                minmax(180px, 1fr)
            );
        gap: 16px;
        margin-bottom: 35px;
    }

    .pokemon-card {
        background: #1a1d24;
        border: 1px solid #343945;
        border-radius: 14px;
        padding: 16px;
        text-align: center;
    }

    .pokemon-card img {
        width: 120px;
        height: 120px;
        object-fit: contain;
        image-rendering: pixelated;
    }

    .pokemon-card.small {
        text-align: left;
    }

    .starter-grid {
        display: grid;
        grid-template-columns:
            repeat(
                auto-fit,
                minmax(180px, 1fr)
            );
        gap: 20px;
    }

    .starter-button {
        width: 100%;
        min-height: 220px;
        background: #111318;
        color: #ffffff;
        border: 1px solid #343945;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 12px;
    }

    .starter-button img {
        width: 140px;
        height: 140px;
        object-fit: contain;
        image-rendering: pixelated;
    }

    @media (max-width: 600px) {
        .topbar {
            align-items: flex-start;
            flex-direction: column;
        }

        .container {
            width: 92%;
            padding-top: 25px;
        }

        .hero {
            padding: 50px 10px;
        }

        .hero h1 {
            font-size: 46px;
        }
    }
    '''
)


# ============================================================
# JavaScript
# ============================================================

FILES["Web/static/js/app.js"] = clean(
    r'''
    async function getPlayer() {
        const response = await fetch("/api/me");

        if (!response.ok) {
            return null;
        }

        return await response.json();
    }


    async function getPokemon() {
        const response = await fetch("/api/pokemon");

        if (!response.ok) {
            return null;
        }

        return await response.json();
    }


    async function addPokemonToParty(pokemonId) {
        const response = await fetch(
            `/api/pokemon/${pokemonId}/party`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    action: "add"
                })
            }
        );

        return await response.json();
    }


    async function removePokemonFromParty(pokemonId) {
        const response = await fetch(
            `/api/pokemon/${pokemonId}/party`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    action: "remove"
                })
            }
        );

        return await response.json();
    }
    '''
)


# ============================================================
# Static sprite directory placeholder
# ============================================================

FILES["Web/static/sprites/README.txt"] = clean(
    r'''
    Place your existing Pokémon sprite files in this folder.

    Examples:

    pikachu.png
    pikachu-shiny.png
    pikachu-ruby.png
    pikachu-ruby-shiny.png
    pikachu-sapphire.png
    pikachu-sapphire-shiny.png
    pikachu-emerald.png
    pikachu-emerald-shiny.png
    pikachu-gold.png
    pikachu-gold-shiny.png
    pikachu-silver.png
    pikachu-silver-shiny.png

    The setup script does not modify or delete existing sprite files.
    '''
)


# ============================================================
# Generator functions
# ============================================================

def create_directories(root: Path) -> None:
    for relative_path in FILES:
        path = root / relative_path
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )


def write_files(
    root: Path,
    force: bool,
) -> tuple[int, int]:
    created = 0
    skipped = 0

    for relative_path, content in FILES.items():
        path = root / relative_path

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if path.exists() and not force:
            skipped += 1
            continue

        path.write_text(
            content,
            encoding="utf-8",
            newline="\n",
        )

        created += 1

    return created, skipped


def validate_generated_python(root: Path) -> list[str]:
    errors: list[str] = []

    for relative_path in FILES:
        if not relative_path.endswith(".py"):
            continue

        path = root / relative_path

        if not path.exists():
            continue

        try:
            source = path.read_text(
                encoding="utf-8",
            )

            compile(
                source,
                str(path),
                "exec",
            )

        except SyntaxError as exc:
            errors.append(
                f"{relative_path}: "
                f"line {exc.lineno}: "
                f"{exc.msg}"
            )

    return errors


def create_instance(root: Path) -> None:
    instance = root / "instance"
    instance.mkdir(
        parents=True,
        exist_ok=True,
    )

    gitkeep = instance / ".gitkeep"

    if not gitkeep.exists():
        gitkeep.write_text(
            "",
            encoding="utf-8",
        )


def print_summary(
    root: Path,
    created: int,
    skipped: int,
) -> None:
    print()
    print("=" * 60)
    print("Krampus RPG foundation created")
    print("=" * 60)
    print()
    print(f"Project: {root}")
    print(f"Files created: {created}")
    print(f"Files skipped: {skipped}")
    print()
    print("Next steps:")
    print()
    print("1. Install dependencies:")
    print("   pip install -r requirements.txt")
    print()
    print("2. Initialize the database:")
    print("   python init_db.py")
    print()
    print("3. Start the server:")
    print("   python run.py")
    print()
    print("4. Open:")
    print("   http://127.0.0.1:5000")
    print()
    print("Your existing sprite files were not modified.")
    print("=" * 60)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create the complete Krampus RPG foundation."
        )
    )

    parser.add_argument(
        "--path",
        default=None,
        help="Project directory to create.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated files.",
    )

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent

    if args.path:
        root = Path(args.path).expanduser().resolve()
    else:
        root = script_dir

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    create_directories(root)
    create_instance(root)

    created, skipped = write_files(
        root,
        args.force,
    )

    errors = validate_generated_python(root)

    if errors:
        print()
        print("ERROR: Generated Python validation failed.")
        print()

        for error in errors:
            print(error)

        print()

        return 1

    print_summary(
        root,
        created,
        skipped,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())