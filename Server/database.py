from __future__ import annotations

import json
import sqlite3

from .config import DATABASE_PATH, DATA_DIR, INSTANCE_DIR


# ---------------------------------------------------------------------------
# Base database schema
# ---------------------------------------------------------------------------

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
# Party / PC schemas
# ---------------------------------------------------------------------------

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
# Role permissions
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
# Database inspection
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
        LIMIT 1
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
# Storage helpers
# ---------------------------------------------------------------------------

def _ensure_storage_schema(
    db: sqlite3.Connection,
) -> None:
    """
    Create the authoritative Party and PC storage tables.
    """

    db.executescript(
        PARTY_SCHEMA
    )

    db.executescript(
        PC_SCHEMA
    )


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


def _next_pc_position(
    db: sqlite3.Connection,
    player_id: int,
) -> tuple[int, int]:
    """
    Find the first available PC slot.

    There is no maximum number of pages.
    Every page has 30 slots.
    """

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
) -> None:
    """
    Place a Pokémon into PC if it is not already stored and is not
    currently in Party.
    """

    if _pokemon_in_party(
        db,
        pokemon_id,
    ):
        return

    if _pokemon_in_pc(
        db,
        pokemon_id,
    ):
        return

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


# ---------------------------------------------------------------------------
# Legacy Party -> Party/PC migration
# ---------------------------------------------------------------------------

def _migrate_pokemon_storage(
    db: sqlite3.Connection,
) -> None:
    """
    Convert the old pokemon.is_active party system into the new
    database-backed Party + PC system.

    Rules:

        - Existing Party records are preserved.
        - Legacy is_active=1 Pokémon become Party members when space
          is available.
        - Party is limited to six Pokémon.
        - Every owned Pokémon not in Party goes into PC.
        - Existing PC records are preserved.
        - Pokémon are never duplicated.
        - No Pokémon are deleted.
        - is_active is removed only after migration succeeds.
    """

    if not _table_exists(
        db,
        "pokemon",
    ):
        return

    _ensure_storage_schema(
        db
    )

    has_is_active = _column_exists(
        db,
        "pokemon",
        "is_active",
    )

    players = db.execute(
        """
        SELECT id
        FROM players
        ORDER BY id
        """
    ).fetchall()

    # ---------------------------------------------------------------
    # Step 1:
    # Migrate old active Pokémon into Party.
    # ---------------------------------------------------------------

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

            active_pokemon = db.execute(
                """
                SELECT id
                FROM pokemon
                WHERE owner_id = ?
                  AND is_active = 1
                ORDER BY id
                """,
                (player_id,),
            ).fetchall()

            for pokemon in active_pokemon:

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

    # ---------------------------------------------------------------
    # Step 2:
    # Every owned Pokémon that is not Party goes to PC.
    # ---------------------------------------------------------------

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

    # ---------------------------------------------------------------
    # Step 3:
    # Remove the old is_active column.
    # ---------------------------------------------------------------

    if has_is_active:
        _remove_is_active_column(
            db
        )


def _remove_is_active_column(
    db: sqlite3.Connection,
) -> None:
    """
    Permanently remove pokemon.is_active.

    The migration has already moved every Pokémon into Party or PC
    before this function is called.
    """

    if not _column_exists(
        db,
        "pokemon",
        "is_active",
    ):
        return

    # SQLite 3.35+ supports DROP COLUMN.
    db.execute(
        """
        ALTER TABLE pokemon
        DROP COLUMN is_active
        """
    )


# ---------------------------------------------------------------------------
# Player role migration
# ---------------------------------------------------------------------------

def _migrate_players_role(
    db: sqlite3.Connection,
) -> None:
    """
    Add role_id to existing player accounts.

    Existing accounts become normal players.
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


def _create_role_index(
    db: sqlite3.Connection,
) -> None:
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
            VALUES (?, ?, ?)
            ON CONFLICT(permission_name)
            DO UPDATE SET
                description = excluded.description
            """.replace(
                "VALUES (?, ?, ?)",
                "VALUES (?, ?)",
            ),
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

        role_id = int(
            role["id"]
        )

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
# Repair players
# ---------------------------------------------------------------------------

def _repair_existing_players(
    db: sqlite3.Connection,
) -> None:

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
# Default settings
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
# Initialize database
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Initialize the Krampus RPG database.

    Existing Pokémon are migrated from the old is_active system into
    the database-backed Party and PC systems.
    """

    with get_connection() as db:

        # ---------------------------------------------------------------
        # 1. Create role infrastructure.
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
        # 2. Seed roles.
        # ---------------------------------------------------------------

        _seed_roles(
            db
        )

        # ---------------------------------------------------------------
        # 3. Create base game schema.
        # ---------------------------------------------------------------

        db.executescript(
            SCHEMA
        )

        # ---------------------------------------------------------------
        # 4. Migrate player roles.
        # ---------------------------------------------------------------

        _migrate_players_role(
            db
        )

        _create_role_index(
            db
        )

        # ---------------------------------------------------------------
        # 5. Seed permissions.
        # ---------------------------------------------------------------

        _seed_permissions(
            db
        )

        # ---------------------------------------------------------------
        # 6. Seed role permissions.
        # ---------------------------------------------------------------

        _seed_role_permissions(
            db
        )

        # ---------------------------------------------------------------
        # 7. Repair existing players.
        # ---------------------------------------------------------------

        _repair_existing_players(
            db
        )

        # ---------------------------------------------------------------
        # 8. Create Party/PC and migrate old storage.
        # ---------------------------------------------------------------

        _migrate_pokemon_storage(
            db
        )

        # ---------------------------------------------------------------
        # 9. Default settings.
        # ---------------------------------------------------------------

        _seed_default_settings(
            db
        )

        db.commit()


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------

def load_json(
    filename: str,
):
    path = DATA_DIR / filename

    if not path.exists():
        return {}

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


# ---------------------------------------------------------------------------
# Seed game data
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

        if isinstance(
            quests,
            list,
        ):

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