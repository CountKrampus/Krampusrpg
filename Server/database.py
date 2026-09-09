from __future__ import annotations

import json
import sqlite3

from .config import DATABASE_PATH, DATA_DIR, INSTANCE_DIR


# ---------------------------------------------------------------------------
# Base database schema
# ---------------------------------------------------------------------------
#
# IMPORTANT:
# The role_id column is intentionally NOT included in the players table here.
# Existing installations need to be migrated safely.
#
# Indexes that depend on role_id are also created AFTER the migration.
#

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id)
        REFERENCES roles(id)
        ON DELETE CASCADE,
    FOREIGN KEY (permission_id)
        REFERENCES permissions(id)
        ON DELETE CASCADE
);

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
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE
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
    FOREIGN KEY (owner_id)
        REFERENCES players(id)
        ON DELETE CASCADE
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
    FOREIGN KEY (pokemon_id)
        REFERENCES pokemon(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pokemon_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pokemon_id INTEGER NOT NULL,
    move_id TEXT NOT NULL,
    slot INTEGER NOT NULL,
    current_pp INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (pokemon_id)
        REFERENCES pokemon(id)
        ON DELETE CASCADE,
    UNIQUE(pokemon_id, slot)
);

CREATE TABLE IF NOT EXISTS player_items (
    player_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, item_id),
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE
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
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE,
    FOREIGN KEY (quest_id)
        REFERENCES quests(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    badge_id TEXT NOT NULL,
    earned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE,
    UNIQUE(player_id, badge_id)
);

CREATE TABLE IF NOT EXISTS transaction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER,
    transaction_type TEXT NOT NULL,
    amount INTEGER NOT NULL DEFAULT 0,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_name TEXT NOT NULL UNIQUE,
    setting_value TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_role_permissions_role_id
ON role_permissions(role_id);

CREATE INDEX IF NOT EXISTS idx_role_permissions_permission_id
ON role_permissions(permission_id);

CREATE INDEX IF NOT EXISTS idx_audit_log_player_id
ON audit_log(player_id);

CREATE INDEX IF NOT EXISTS idx_audit_log_action
ON audit_log(action);

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
ON audit_log(created_at);
"""


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

ROLES = [
    (
        1,
        "player",
        "Normal game account with no staff permissions.",
    ),
    (
        2,
        "moderator",
        "Staff account responsible for player moderation and reports.",
    ),
    (
        3,
        "event_staff",
        "Staff account responsible for events and promotional content.",
    ),
    (
        4,
        "admin",
        "General support and administrative staff account.",
    ),
    (
        5,
        "webmaster",
        "Highest-level staff account with complete system access.",
    ),
]


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

PERMISSIONS = [
    (
        "admin.dashboard",
        "Access the staff dashboard.",
    ),
    (
        "admin.players.view",
        "View player accounts.",
    ),
    (
        "admin.players.edit",
        "Edit player accounts.",
    ),
    (
        "admin.pokemon.view",
        "View player Pokémon.",
    ),
    (
        "admin.pokemon.edit",
        "Edit player Pokémon.",
    ),
    (
        "admin.items.view",
        "View player items.",
    ),
    (
        "admin.items.edit",
        "Edit player items.",
    ),
    (
        "admin.quests.view",
        "View quests.",
    ),
    (
        "admin.quests.edit",
        "Edit quests.",
    ),
    (
        "admin.promos.view",
        "View daily promotions.",
    ),
    (
        "admin.promos.edit",
        "Create and edit daily promotions.",
    ),
    (
        "admin.events.view",
        "View events.",
    ),
    (
        "admin.events.edit",
        "Create and edit events.",
    ),
    (
        "moderation.players",
        "Moderate player accounts.",
    ),
    (
        "moderation.reports",
        "Review and manage player reports.",
    ),
    (
        "admin.reports.view",
        "View reports.",
    ),
    (
        "admin.audit_log",
        "View the administrative audit log.",
    ),
    (
        "admin.roles",
        "Manage roles and permissions.",
    ),
    (
        "admin.settings",
        "Manage server settings.",
    ),
    (
        "admin.database",
        "Perform database administration.",
    ),
]


# ---------------------------------------------------------------------------
# Role -> Permission assignments
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS = {
    "player": [],

    "moderator": [
        "admin.dashboard",
        "admin.players.view",
        "admin.pokemon.view",
        "admin.items.view",
        "admin.quests.view",
        "admin.promos.view",
        "admin.events.view",
        "moderation.players",
        "moderation.reports",
        "admin.reports.view",
        "admin.audit_log",
    ],

    "event_staff": [
        "admin.dashboard",
        "admin.promos.view",
        "admin.promos.edit",
        "admin.events.view",
        "admin.events.edit",
    ],

    "admin": [
        "admin.dashboard",
        "admin.players.view",
        "admin.players.edit",
        "admin.pokemon.view",
        "admin.pokemon.edit",
        "admin.items.view",
        "admin.items.edit",
        "admin.quests.view",
        "admin.quests.edit",
        "admin.promos.view",
        "admin.promos.edit",
        "admin.events.view",
        "admin.events.edit",
        "moderation.players",
        "moderation.reports",
        "admin.reports.view",
        "admin.audit_log",
    ],

    "webmaster": [
        permission_name
        for permission_name, _description in PERMISSIONS
    ],
}


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    INSTANCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# ---------------------------------------------------------------------------
# Database inspection helpers
# ---------------------------------------------------------------------------

def _table_exists(
    db: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = db.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def _column_exists(
    db: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    if not _table_exists(
        db,
        table_name,
    ):
        return False

    columns = db.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        column["name"] == column_name
        for column in columns
    )


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def _migrate_players_role(
    db: sqlite3.Connection,
) -> None:
    """
    Safely add role_id to an existing players table.

    SQLite does not allow adding a REFERENCES column with
    a non-NULL DEFAULT using ALTER TABLE.

    Therefore we:
        1. Add role_id as a nullable foreign-key column.
        2. Assign every existing player the normal player role.
        3. Leave the column nullable at the SQLite schema level.

    Existing accounts are never given staff permissions.
    """

    if not _table_exists(
        db,
        "players",
    ):
        return

    if _column_exists(
        db,
        "players",
        "role_id",
    ):
        return

    # SQLite-compatible migration.
    #
    # Do NOT use:
    #
    #     NOT NULL DEFAULT 1 REFERENCES roles(id)
    #
    # SQLite rejects that combination when using ALTER TABLE.

    db.execute(
        """
        ALTER TABLE players
        ADD COLUMN role_id INTEGER
        REFERENCES roles(id)
        """
    )

    # Existing accounts become normal players.
    db.execute(
        """
        UPDATE players
        SET role_id = 1
        WHERE role_id IS NULL
        """
    )
    """
    Add role_id to an existing players table.

    Existing accounts automatically become normal players.
    No existing account receives staff access.
    """

    if not _table_exists(
        db,
        "players",
    ):
        return

    if _column_exists(
        db,
        "players",
        "role_id",
    ):
        return

    db.execute(
        """
        ALTER TABLE players
        ADD COLUMN role_id INTEGER
        NOT NULL DEFAULT 1
        REFERENCES roles(id)
        """
    )


def _create_role_index(
    db: sqlite3.Connection,
) -> None:
    """
    Create the players.role_id index only after role_id
    has been migrated into the players table.
    """

    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_players_role_id
        ON players(role_id)
        """
    )


# ---------------------------------------------------------------------------
# Seed roles
# ---------------------------------------------------------------------------

def _seed_roles(
    db: sqlite3.Connection,
) -> None:
    for role_id, name, description in ROLES:
        db.execute(
            """
            INSERT INTO roles
            (
                id,
                name,
                description
            )
            VALUES (?, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET
                name = excluded.name,
                description = excluded.description
            """,
            (
                role_id,
                name,
                description,
            ),
        )


# ---------------------------------------------------------------------------
# Seed permissions
# ---------------------------------------------------------------------------

def _seed_permissions(
    db: sqlite3.Connection,
) -> None:
    for permission_name, description in PERMISSIONS:
        db.execute(
            """
            INSERT INTO permissions
            (
                permission_name,
                description
            )
            VALUES (?, ?)
            ON CONFLICT(permission_name)
            DO UPDATE SET
                description = excluded.description
            """,
            (
                permission_name,
                description,
            ),
        )


# ---------------------------------------------------------------------------
# Seed role permissions
# ---------------------------------------------------------------------------

def _seed_role_permissions(
    db: sqlite3.Connection,
) -> None:
    for role_name, permission_names in ROLE_PERMISSIONS.items():

        role = db.execute(
            """
            SELECT id
            FROM roles
            WHERE name = ?
            """,
            (role_name,),
        ).fetchone()

        if role is None:
            continue

        role_id = role["id"]

        for permission_name in permission_names:

            permission = db.execute(
                """
                SELECT id
                FROM permissions
                WHERE permission_name = ?
                """,
                (permission_name,),
            ).fetchone()

            if permission is None:
                continue

            db.execute(
                """
                INSERT OR IGNORE INTO role_permissions
                (
                    role_id,
                    permission_id
                )
                VALUES (?, ?)
                """,
                (
                    role_id,
                    permission["id"],
                ),
            )


# ---------------------------------------------------------------------------
# Repair existing players
# ---------------------------------------------------------------------------

def _repair_existing_players(
    db: sqlite3.Connection,
) -> None:
    """
    Make sure existing accounts have a valid role.

    NULL or invalid role assignments are reset to player.
    """

    if not _column_exists(
        db,
        "players",
        "role_id",
    ):
        return

    db.execute(
        """
        UPDATE players
        SET role_id = 1
        WHERE role_id IS NULL
        """
    )

    db.execute(
        """
        UPDATE players
        SET role_id = 1
        WHERE role_id NOT IN (
            SELECT id
            FROM roles
        )
        """
    )


# ---------------------------------------------------------------------------
# Default server settings
# ---------------------------------------------------------------------------

def _seed_default_settings(
    db: sqlite3.Connection,
) -> None:

    settings = [
        (
            "site_name",
            "Krampus RPG",
            "Displayed name of the game.",
        ),
        (
            "maintenance_mode",
            "false",
            "When enabled, normal game access can be restricted.",
        ),
        (
            "registration_enabled",
            "true",
            "Controls whether new player registrations are allowed.",
        ),
        (
            "daily_promo_enabled",
            "true",
            "Controls whether daily promotional Pokémon are enabled.",
        ),
    ]

    for (
        setting_name,
        setting_value,
        description,
    ) in settings:

        db.execute(
            """
            INSERT OR IGNORE INTO settings
            (
                setting_name,
                setting_value,
                description
            )
            VALUES (?, ?, ?)
            """,
            (
                setting_name,
                setting_value,
                description,
            ),
        )


# ---------------------------------------------------------------------------
# Initialize / migrate database
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Initialize the Krampus RPG database.

    This function is safe to run against an existing database.

    Existing:
        - Players
        - Pokémon
        - Items
        - Quests
        - Progress
        - Badges
        - Transactions

    are preserved.

    The admin system is added automatically.
    """

    with get_connection() as db:

        # ---------------------------------------------------------------
        # 1. Create roles first.
        # ---------------------------------------------------------------

        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                permission_name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                PRIMARY KEY (role_id, permission_id),
                FOREIGN KEY (role_id)
                    REFERENCES roles(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (permission_id)
                    REFERENCES permissions(id)
                    ON DELETE CASCADE
            );
            """
        )

        # ---------------------------------------------------------------
        # 2. Seed roles before players.role_id is added.
        # ---------------------------------------------------------------

        _seed_roles(db)

        # ---------------------------------------------------------------
        # 3. Create the original game tables plus the new admin tables.
        # ---------------------------------------------------------------

        db.executescript(SCHEMA)

        # ---------------------------------------------------------------
        # 4. Migrate an existing players table.
        # ---------------------------------------------------------------

        _migrate_players_role(db)

        # ---------------------------------------------------------------
        # 5. Now that players.role_id exists, create its index.
        # ---------------------------------------------------------------

        _create_role_index(db)

        # ---------------------------------------------------------------
        # 6. Seed permissions.
        # ---------------------------------------------------------------

        _seed_permissions(db)

        # ---------------------------------------------------------------
        # 7. Seed role -> permission relationships.
        # ---------------------------------------------------------------

        _seed_role_permissions(db)

        # ---------------------------------------------------------------
        # 8. Make sure existing accounts remain normal players.
        # ---------------------------------------------------------------

        _repair_existing_players(db)

        # ---------------------------------------------------------------
        # 9. Seed default server settings.
        # ---------------------------------------------------------------

        _seed_default_settings(db)

        db.commit()


# ---------------------------------------------------------------------------
# JSON data loading
# ---------------------------------------------------------------------------

def load_json(filename: str):
    path = DATA_DIR / filename

    if not path.exists():
        return {}

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


# ---------------------------------------------------------------------------
# Game data seeding
# ---------------------------------------------------------------------------

def seed_database() -> None:
    """
    Initialize the database and seed JSON-backed game data.
    """

    init_db()

    quests = load_json(
        "quests.json"
    )

    with get_connection() as db:

        if isinstance(quests, list):

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
                        quest.get(
                            "reward_money",
                            0,
                        ),
                        quest.get(
                            "reward_item",
                        ),
                        quest.get(
                            "reward_quantity",
                            0,
                        ),
                    ),
                )

        db.commit()