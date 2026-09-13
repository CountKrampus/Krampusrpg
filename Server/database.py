from __future__ import annotations

import json
import sqlite3

from .config import DATABASE_PATH, DATA_DIR, INSTANCE_DIR


# =============================================================================
# DATABASE SCHEMA
# =============================================================================

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
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role_id INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login TEXT,
    FOREIGN KEY (role_id) REFERENCES roles(id)
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
    current_hp INTEGER NOT NULL DEFAULT 1,
    max_hp INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pokemon_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pokemon_id INTEGER NOT NULL UNIQUE,
    hp INTEGER NOT NULL DEFAULT 1,
    attack INTEGER NOT NULL DEFAULT 1,
    defense INTEGER NOT NULL DEFAULT 1,
    sp_attack INTEGER NOT NULL DEFAULT 1,
    sp_defense INTEGER NOT NULL DEFAULT 1,
    speed INTEGER NOT NULL DEFAULT 1,
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

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_name TEXT NOT NULL UNIQUE,
    setting_value TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_players_role_id
ON players(role_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_owner
ON pokemon(owner_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_species
ON pokemon(species_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_unique_id
ON pokemon(unique_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_moves_pokemon
ON pokemon_moves(pokemon_id);

CREATE INDEX IF NOT EXISTS idx_player_items_player
ON player_items(player_id);

CREATE INDEX IF NOT EXISTS idx_audit_log_player_id
ON audit_log(player_id);

CREATE INDEX IF NOT EXISTS idx_audit_log_action
ON audit_log(action);

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
ON audit_log(created_at);
"""


# =============================================================================
# PARTY
# =============================================================================

PARTY_SCHEMA = """
CREATE TABLE IF NOT EXISTS party (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    player_id INTEGER NOT NULL,
    pokemon_id INTEGER NOT NULL UNIQUE,
    slot INTEGER NOT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE,

    FOREIGN KEY (pokemon_id)
        REFERENCES pokemon(id)
        ON DELETE CASCADE,

    CHECK (slot >= 1 AND slot <= 6),

    UNIQUE(player_id, slot)
);

CREATE INDEX IF NOT EXISTS idx_party_player
ON party(player_id);

CREATE INDEX IF NOT EXISTS idx_party_pokemon
ON party(pokemon_id);

CREATE INDEX IF NOT EXISTS idx_party_player_slot
ON party(player_id, slot);
"""


# =============================================================================
# PC
# =============================================================================

PC_SCHEMA = """
CREATE TABLE IF NOT EXISTS pc_storage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    player_id INTEGER NOT NULL,
    pokemon_id INTEGER NOT NULL UNIQUE,

    page INTEGER NOT NULL DEFAULT 1,
    slot INTEGER NOT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE,

    FOREIGN KEY (pokemon_id)
        REFERENCES pokemon(id)
        ON DELETE CASCADE,

    CHECK (page >= 1),
    CHECK (slot >= 1 AND slot <= 30),

    UNIQUE(player_id, page, slot)
);

CREATE INDEX IF NOT EXISTS idx_pc_storage_player
ON pc_storage(player_id);

CREATE INDEX IF NOT EXISTS idx_pc_storage_page
ON pc_storage(player_id, page);

CREATE INDEX IF NOT EXISTS idx_pc_storage_pokemon
ON pc_storage(pokemon_id);
"""


# =============================================================================
# ROLES
# =============================================================================

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


# =============================================================================
# PERMISSIONS
# =============================================================================

PERMISSIONS = [
    ("admin.dashboard", "Access the staff dashboard."),
    ("admin.players.view", "View player accounts."),
    ("admin.players.edit", "Edit player accounts."),
    ("admin.pokemon.view", "View player Pokémon."),
    ("admin.pokemon.edit", "Edit player Pokémon."),
    ("admin.items.view", "View player items."),
    ("admin.items.edit", "Edit player items."),
    ("admin.quests.view", "View quests."),
    ("admin.quests.edit", "Edit quests."),
    ("admin.promos.view", "View daily promotions."),
    ("admin.promos.edit", "Create and edit daily promotions."),
    ("admin.events.view", "View events."),
    ("admin.events.edit", "Create and edit events."),
    ("moderation.players", "Moderate player accounts."),
    ("moderation.reports", "Review and manage player reports."),
    ("admin.reports.view", "View reports."),
    ("admin.audit_log", "View the administrative audit log."),
    ("admin.roles", "Manage roles and permissions."),
    ("admin.settings", "Manage server settings."),
    ("admin.database", "Perform database administration."),
]


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


# =============================================================================
# CONNECTION
# =============================================================================

def get_connection() -> sqlite3.Connection:
    INSTANCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    db = sqlite3.connect(
        DATABASE_PATH,
        timeout=30,
    )

    db.row_factory = sqlite3.Row

    db.execute(
        "PRAGMA foreign_keys = ON"
    )

    db.execute(
        "PRAGMA busy_timeout = 30000"
    )

    return db


# =============================================================================
# DATABASE INSPECTION
# =============================================================================

def table_exists(
    db: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = db.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def column_exists(
    db: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    if not table_exists(
        db,
        table_name,
    ):
        return False

    rows = db.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        row["name"] == column_name
        for row in rows
    )


# Backwards-compatible private names.
_table_exists = table_exists
_column_exists = column_exists


# =============================================================================
# PARTY / PC HELPERS
# =============================================================================

def ensure_party_schema(
    db: sqlite3.Connection,
) -> None:
    db.executescript(
        PARTY_SCHEMA
    )


def ensure_pc_schema(
    db: sqlite3.Connection,
) -> None:
    db.executescript(
        PC_SCHEMA
    )


def _ensure_storage_schema(
    db: sqlite3.Connection,
) -> None:
    ensure_party_schema(db)
    ensure_pc_schema(db)


def _pokemon_in_party(
    db: sqlite3.Connection,
    pokemon_id: int,
) -> bool:
    row = db.execute(
        """
        SELECT 1
        FROM party
        WHERE pokemon_id = ?
        LIMIT 1
        """,
        (pokemon_id,),
    ).fetchone()

    return row is not None


def _pokemon_in_pc(
    db: sqlite3.Connection,
    pokemon_id: int,
) -> bool:
    row = db.execute(
        """
        SELECT 1
        FROM pc_storage
        WHERE pokemon_id = ?
        LIMIT 1
        """,
        (pokemon_id,),
    ).fetchone()

    return row is not None


def _next_party_slot(
    db: sqlite3.Connection,
    player_id: int,
) -> int | None:
    rows = db.execute(
        """
        SELECT slot
        FROM party
        WHERE player_id = ?
        ORDER BY slot
        """,
        (player_id,),
    ).fetchall()

    occupied = {
        int(row["slot"])
        for row in rows
    }

    for slot in range(1, 7):
        if slot not in occupied:
            return slot

    return None


def _next_pc_position(
    db: sqlite3.Connection,
    player_id: int,
) -> tuple[int, int]:
    rows = db.execute(
        """
        SELECT page, slot
        FROM pc_storage
        WHERE player_id = ?
        ORDER BY page, slot
        """,
        (player_id,),
    ).fetchall()

    occupied = {
        (
            int(row["page"]),
            int(row["slot"]),
        )
        for row in rows
    }

    page = 1

    while True:
        for slot in range(1, 31):
            if (page, slot) not in occupied:
                return page, slot

        page += 1


def _put_in_pc(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> bool:
    if _pokemon_in_party(
        db,
        pokemon_id,
    ):
        return False

    if _pokemon_in_pc(
        db,
        pokemon_id,
    ):
        return False

    owner = db.execute(
        """
        SELECT owner_id
        FROM pokemon
        WHERE id = ?
        """,
        (pokemon_id,),
    ).fetchone()

    if owner is None:
        return False

    if int(owner["owner_id"]) != int(player_id):
        return False

    page, slot = _next_pc_position(
        db,
        player_id,
    )

    db.execute(
        """
        INSERT INTO pc_storage
        (
            player_id,
            pokemon_id,
            page,
            slot
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            player_id,
            pokemon_id,
            page,
            slot,
        ),
    )

    return True


# =============================================================================
# LEGACY STORAGE MIGRATION
# =============================================================================

def _migrate_pokemon_storage(
    db: sqlite3.Connection,
) -> None:
    """
    Migrate the old pokemon.is_active system.

    Final rule:

        Every owned Pokémon is either:

            1. in Party
            2. in PC

        Never both.
        Never neither.
    """

    if not table_exists(
        db,
        "pokemon",
    ):
        return

    ensure_party_schema(db)
    ensure_pc_schema(db)

    players = db.execute(
        """
        SELECT id
        FROM players
        ORDER BY id
        """
    ).fetchall()

    has_is_active = column_exists(
        db,
        "pokemon",
        "is_active",
    )

    # -------------------------------------------------------------------------
    # Existing legacy active Pokémon -> Party
    # -------------------------------------------------------------------------

    if has_is_active:

        for player in players:

            player_id = int(
                player["id"]
            )

            existing_party = db.execute(
                """
                SELECT pokemon_id, slot
                FROM party
                WHERE player_id = ?
                ORDER BY slot
                """,
                (player_id,),
            ).fetchall()

            occupied_slots = {
                int(row["slot"])
                for row in existing_party
            }

            party_count = len(
                existing_party
            )

            if party_count >= 6:
                continue

            active_rows = db.execute(
                """
                SELECT id
                FROM pokemon
                WHERE owner_id = ?
                  AND is_active = 1
                ORDER BY id
                """,
                (player_id,),
            ).fetchall()

            for pokemon in active_rows:

                if party_count >= 6:
                    break

                pokemon_id = int(
                    pokemon["id"]
                )

                if _pokemon_in_party(
                    db,
                    pokemon_id,
                ):
                    continue

                if _pokemon_in_pc(
                    db,
                    pokemon_id,
                ):
                    continue

                available_slot = None

                for slot in range(1, 7):
                    if slot not in occupied_slots:
                        available_slot = slot
                        break

                if available_slot is None:
                    break

                db.execute(
                    """
                    INSERT INTO party
                    (
                        player_id,
                        pokemon_id,
                        slot
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        player_id,
                        pokemon_id,
                        available_slot,
                    ),
                )

                occupied_slots.add(
                    available_slot
                )

                party_count += 1

    # -------------------------------------------------------------------------
    # Every owned Pokémon not in Party -> PC
    # -------------------------------------------------------------------------

    for player in players:

        player_id = int(
            player["id"]
        )

        pokemon_rows = db.execute(
            """
            SELECT id
            FROM pokemon
            WHERE owner_id = ?
            ORDER BY id
            """,
            (player_id,),
        ).fetchall()

        for pokemon in pokemon_rows:

            pokemon_id = int(
                pokemon["id"]
            )

            if _pokemon_in_party(
                db,
                pokemon_id,
            ):
                continue

            if _pokemon_in_pc(
                db,
                pokemon_id,
            ):
                continue

            _put_in_pc(
                db,
                player_id,
                pokemon_id,
            )

    # -------------------------------------------------------------------------
    # Remove legacy is_active column
    # -------------------------------------------------------------------------

    if has_is_active:
        _remove_is_active_column(db)


def _remove_is_active_column(
    db: sqlite3.Connection,
) -> None:
    if not column_exists(
        db,
        "pokemon",
        "is_active",
    ):
        return

    db.execute(
        """
        ALTER TABLE pokemon
        DROP COLUMN is_active
        """
    )


# =============================================================================
# PLAYER ROLE MIGRATION
# =============================================================================

def _migrate_players_role(
    db: sqlite3.Connection,
) -> None:

    if not table_exists(
        db,
        "players",
    ):
        return

    if not column_exists(
        db,
        "players",
        "role_id",
    ):
        db.execute(
            """
            ALTER TABLE players
            ADD COLUMN role_id INTEGER
            REFERENCES roles(id)
            """
        )

    db.execute(
        """
        UPDATE players
        SET role_id = 1
        WHERE role_id IS NULL
        """
    )


# =============================================================================
# ROLE SEEDING
# =============================================================================

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


def _seed_role_permissions(
    db: sqlite3.Connection,
) -> None:

    for role_name, permission_names in ROLE_PERMISSIONS.items():

        role = db.execute(
            """
            SELECT id
            FROM roles
            WHERE name = ?
            LIMIT 1
            """,
            (role_name,),
        ).fetchone()

        if role is None:
            continue

        role_id = int(
            role["id"]
        )

        for permission_name in permission_names:

            permission = db.execute(
                """
                SELECT id
                FROM permissions
                WHERE permission_name = ?
                LIMIT 1
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
                    int(permission["id"]),
                ),
            )


def _repair_existing_players(
    db: sqlite3.Connection,
) -> None:

    if not column_exists(
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


# =============================================================================
# DEFAULT SETTINGS
# =============================================================================

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

    for setting_name, setting_value, description in settings:

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


# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

def init_db() -> None:
    """
    Initialize and migrate the Krampus RPG database.

    Party and PC are authoritative.
    pokemon.is_active is legacy only and is removed after migration.
    """

    with get_connection() as db:

        # ---------------------------------------------------------------------
        # Create the base schema.
        # ---------------------------------------------------------------------

        db.executescript(
            SCHEMA
        )

        # ---------------------------------------------------------------------
        # Make sure roles exist.
        # ---------------------------------------------------------------------

        _seed_roles(db)

        # ---------------------------------------------------------------------
        # Existing databases may have been created before role_id existed.
        # ---------------------------------------------------------------------

        _migrate_players_role(db)

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_players_role_id
            ON players(role_id)
            """
        )

        # ---------------------------------------------------------------------
        # Permissions.
        # ---------------------------------------------------------------------

        _seed_permissions(db)

        _seed_role_permissions(db)

        _repair_existing_players(db)

        # ---------------------------------------------------------------------
        # Party / PC migration.
        # ---------------------------------------------------------------------

        _migrate_pokemon_storage(db)

        # ---------------------------------------------------------------------
        # Settings.
        # ---------------------------------------------------------------------

        _seed_default_settings(db)

        db.commit()


# =============================================================================
# JSON DATA
# =============================================================================

def load_json(
    filename: str,
):
    path = DATA_DIR / filename

    if not path.exists():
        return {}

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {}


# =============================================================================
# GAME DATA SEEDING
# =============================================================================

def seed_database() -> None:
    """
    Initialize the database and seed JSON-backed game data.
    """

    init_db()

    quests = load_json(
        "quests.json"
    )

    if not isinstance(
        quests,
        list,
    ):
        return

    with get_connection() as db:

        for quest in quests:

            if not isinstance(
                quest,
                dict,
            ):
                continue

            quest_id = quest.get(
                "id"
            )

            name = quest.get(
                "name",
                "",
            )

            description = quest.get(
                "description",
                "",
            )

            if not quest_id:
                continue

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
                    quest_id,
                    name,
                    description,
                    quest.get(
                        "reward_money",
                        0,
                    ),
                    quest.get(
                        "reward_item"
                    ),
                    quest.get(
                        "reward_quantity",
                        0,
                    ),
                ),
            )

        db.commit()


# =============================================================================
# DIRECT EXECUTION
# =============================================================================

if __name__ == "__main__":
    seed_database()
    print("Krampus RPG database initialized.")