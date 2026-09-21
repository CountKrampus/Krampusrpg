from __future__ import annotations

import json
import sqlite3

from .config import DATABASE_PATH, DATA_DIR, INSTANCE_DIR


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_PARTY_SIZE = 6
PC_SLOTS_PER_PAGE = 30
STAT_NAMES = (
    "hp",
    "attack",
    "defense",
    "sp_attack",
    "sp_defense",
    "speed",
)


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
    role_id INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login TEXT,

    FOREIGN KEY (role_id)
        REFERENCES roles(id)
        ON DELETE SET DEFAULT
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

    current_hp INTEGER NOT NULL DEFAULT 1,
    max_hp INTEGER NOT NULL DEFAULT 1,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (owner_id)
        REFERENCES players(id)
        ON DELETE CASCADE,

    CHECK (level >= 1),
    CHECK (level <= 100),
    CHECK (experience >= 0),
    CHECK (shiny IN (0, 1)),
    CHECK (current_hp >= 0),
    CHECK (max_hp >= 1)
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

    UNIQUE (pokemon_id, slot),

    CHECK (slot >= 1),
    CHECK (slot <= 4),
    CHECK (current_pp >= 0)
);

CREATE TABLE IF NOT EXISTS player_items (
    player_id INTEGER NOT NULL,

    item_id TEXT NOT NULL,

    quantity INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (player_id, item_id),

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE,

    CHECK (quantity >= 0)
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    price INTEGER NOT NULL DEFAULT 0,
    sell_price INTEGER NOT NULL DEFAULT 0,
    heal INTEGER,
    effect TEXT,
    custom INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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

    UNIQUE (player_id, badge_id)
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

CREATE TABLE IF NOT EXISTS evolution_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    from_species TEXT NOT NULL,
    to_species TEXT NOT NULL,

    method TEXT NOT NULL DEFAULT 'level',

    condition_level INTEGER,
    condition_item TEXT,
    condition_friendship INTEGER,
    condition_time TEXT,
    condition_location TEXT,
    condition_held_item TEXT,

    description TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (from_species, to_species, method)
);

CREATE INDEX IF NOT EXISTS idx_evolution_from_species
ON evolution_rules(from_species);

CREATE INDEX IF NOT EXISTS idx_evolution_to_species
ON evolution_rules(to_species);

CREATE TABLE IF NOT EXISTS pvp_matches (
    match_id TEXT PRIMARY KEY,

    player1_id INTEGER NOT NULL,
    player2_id INTEGER NOT NULL,

    status TEXT NOT NULL DEFAULT 'active',

    winner_id INTEGER,
    loser_id INTEGER,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,

    FOREIGN KEY (player1_id)
        REFERENCES players(id)
        ON DELETE CASCADE,

    FOREIGN KEY (player2_id)
        REFERENCES players(id)
        ON DELETE CASCADE,

    FOREIGN KEY (winner_id)
        REFERENCES players(id)
        ON DELETE SET NULL,

    FOREIGN KEY (loser_id)
        REFERENCES players(id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS pvp_stats (
    player_id INTEGER PRIMARY KEY,

    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    total_matches INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pvp_matches_player1
ON pvp_matches(player1_id);

CREATE INDEX IF NOT EXISTS idx_pvp_matches_player2
ON pvp_matches(player2_id);

CREATE INDEX IF NOT EXISTS idx_pvp_matches_status
ON pvp_matches(status);

CREATE INDEX IF NOT EXISTS idx_players_role_id
ON players(role_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_owner
ON pokemon(owner_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_species
ON pokemon(species_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_unique_id
ON pokemon(unique_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_variant
ON pokemon(variant);

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
# PARTY SCHEMA
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

    CHECK (slot >= 1),
    CHECK (slot <= 6),

    UNIQUE (player_id, slot)
);

CREATE INDEX IF NOT EXISTS idx_party_player
ON party(player_id);

CREATE INDEX IF NOT EXISTS idx_party_pokemon
ON party(pokemon_id);

CREATE INDEX IF NOT EXISTS idx_party_player_slot
ON party(player_id, slot);
"""


# =============================================================================
# PC SCHEMA
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

    CHECK (slot >= 1),
    CHECK (slot <= 30),

    UNIQUE (player_id, page, slot)
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


# =============================================================================
# ROLE PERMISSIONS
# =============================================================================

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


# Backwards-compatible aliases.
_table_exists = table_exists
_column_exists = column_exists


# =============================================================================
# PARTY SCHEMA
# =============================================================================

def ensure_party_schema(
    db: sqlite3.Connection | None = None,
) -> None:
    """
    Ensure the Party table exists.

    Can be called either as:

        ensure_party_schema()

    or:

        ensure_party_schema(db)
    """

    owns_connection = db is None

    if owns_connection:
        db = get_connection()

    try:
        db.executescript(
            PARTY_SCHEMA
        )

        if owns_connection:
            db.commit()

    finally:
        if owns_connection:
            db.close()


# =============================================================================
# PC SCHEMA
# =============================================================================

def ensure_pc_schema(
    db: sqlite3.Connection | None = None,
) -> None:
    """
    Ensure the PC table exists.

    Can be called either as:

        ensure_pc_schema()

    or:

        ensure_pc_schema(db)
    """

    owns_connection = db is None

    if owns_connection:
        db = get_connection()

    try:
        db.executescript(
            PC_SCHEMA
        )

        if owns_connection:
            db.commit()

    finally:
        if owns_connection:
            db.close()


# =============================================================================
# STORAGE SCHEMA
# =============================================================================

def _ensure_storage_schema(
    db: sqlite3.Connection,
) -> None:
    db.executescript(
        PARTY_SCHEMA
    )

    db.executescript(
        PC_SCHEMA
    )


# =============================================================================
# STORAGE LOOKUPS
# =============================================================================

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

    for slot in range(
        1,
        MAX_PARTY_SIZE + 1,
    ):
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

        for slot in range(
            1,
            PC_SLOTS_PER_PAGE + 1,
        ):
            if (
                page,
                slot,
            ) not in occupied:
                return page, slot

        page += 1


# =============================================================================
# PUT POKÉMON IN PC
# =============================================================================

def _put_in_pc(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> bool:
    """
    Put a Pokémon into the first available PC slot.

    This function refuses to:

        - duplicate a PC record
        - put a Party Pokémon into PC
        - move a Pokémon belonging to another player
        - create a record for a nonexistent Pokémon
    """

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

    pokemon = db.execute(
        """
        SELECT owner_id
        FROM pokemon
        WHERE id = ?
        LIMIT 1
        """,
        (pokemon_id,),
    ).fetchone()

    if pokemon is None:
        return False

    if int(
        pokemon["owner_id"]
    ) != int(player_id):
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
    Migrate the old pokemon.is_active Party system.

    Final invariant:

        Every owned Pokémon must be in exactly one place:

            Party
            OR
            PC

        Never both.
        Never neither.
    """

    if not table_exists(
        db,
        "pokemon",
    ):
        return

    _ensure_storage_schema(
        db
    )

    has_is_active = column_exists(
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

    # -------------------------------------------------------------------------
    # Legacy active Pokémon -> Party
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

            if party_count >= MAX_PARTY_SIZE:
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

                if party_count >= MAX_PARTY_SIZE:
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

                for slot in range(
                    1,
                    MAX_PARTY_SIZE + 1,
                ):
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
    # Everything not in Party -> PC
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
    # Remove legacy is_active.
    #
    # If SQLite cannot perform the operation, we leave the column physically
    # present. Application code still does NOT use it.
    # -------------------------------------------------------------------------

    if has_is_active:

        try:
            db.execute(
                """
                ALTER TABLE pokemon
                DROP COLUMN is_active
                """
            )

        except sqlite3.OperationalError:
            pass


# =============================================================================
# REBUILD LEGACY POKÉMON TABLES SAFELY INTO NEW SCHEMA
# =============================================================================

def _compute_stats_for_migration(
    species_id: str,
    level: int,
    species_map: dict[str, dict] | None = None,
) -> dict[str, int]:
    """Compute baseline stats for a Pokémon when rebuilding tables."""
    level = max(1, min(100, int(level)))
    base_stats = {
        "hp": 50,
        "attack": 50,
        "defense": 50,
        "sp_attack": 50,
        "sp_defense": 50,
        "speed": 50,
    }

    if species_map:
        s = species_map.get(str(species_id).lower(), {})
        possible = s.get("base_stats") or s.get("stats")
        if isinstance(possible, dict):
            for k in base_stats:
                if k in possible:
                    try:
                        base_stats[k] = max(1, int(possible[k]))
                    except (TypeError, ValueError):
                        pass

    hp = max(1, ((2 * base_stats["hp"] * level) // 100) + level + 10)
    return {
        "hp": hp,
        "attack": max(1, ((2 * base_stats["attack"] * level) // 100) + 5),
        "defense": max(1, ((2 * base_stats["defense"] * level) // 100) + 5),
        "sp_attack": max(1, ((2 * base_stats["sp_attack"] * level) // 100) + 5),
        "sp_defense": max(1, ((2 * base_stats["sp_defense"] * level) // 100) + 5),
        "speed": max(1, ((2 * base_stats["speed"] * level) // 100) + 5),
    }


def rebuild_legacy_pokemon_tables(
    db: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Safely rebuild legacy Pokémon tables (pokemon, pokemon_stats, pokemon_moves)
    into the new strict schema.

    - Strips legacy columns (is_active, nature, status, hp_iv, attack_iv, etc.)
    - Clamps and sanitizes values to satisfy CHECK constraints (e.g. level between 1 and 100)
    - Computes and populates actual stat values (hp, attack, defense, sp_attack, sp_defense, speed)
    - Preserves all Pokémon IDs, relationships, moves, and storage positions
    - Checks foreign key integrity
    """
    owns_connection = db is None

    if owns_connection:
        db = get_connection()

    try:
        if not table_exists(db, "pokemon"):
            return {
                "rebuilt_pokemon": False,
                "rebuilt_stats": False,
                "rebuilt_moves": False,
            }

        # 1. Inspect pokemon table
        pokemon_cols = [
            r["name"]
            for r in db.execute("PRAGMA table_info(pokemon)").fetchall()
        ]
        has_legacy_cols = any(
            c in pokemon_cols
            for c in ("is_active", "nature", "status")
        )
        row_sql = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='pokemon'"
        ).fetchone()
        pokemon_sql = row_sql[0] if row_sql else ""
        missing_checks = (
            "CHECK (level >= 1)" not in pokemon_sql
            or "CHECK (level <= 100)" not in pokemon_sql
        )
        needs_pokemon_rebuild = has_legacy_cols or missing_checks

        # 2. Inspect pokemon_stats table
        has_stats_table = table_exists(db, "pokemon_stats")
        stats_cols = (
            [r["name"] for r in db.execute("PRAGMA table_info(pokemon_stats)").fetchall()]
            if has_stats_table
            else []
        )
        has_all_stats = all(s in stats_cols for s in STAT_NAMES)
        has_legacy_iv_ev = any(
            c.endswith("_iv") or c.endswith("_ev")
            for c in stats_cols
        )
        needs_stats_rebuild = (not has_stats_table) or (not has_all_stats) or has_legacy_iv_ev

        # 3. Inspect pokemon_moves table
        has_moves_table = table_exists(db, "pokemon_moves")
        moves_row = (
            db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='pokemon_moves'"
            ).fetchone()
            if has_moves_table
            else None
        )
        moves_sql = moves_row[0] if moves_row else ""
        needs_moves_rebuild = (not has_moves_table) or ("CHECK (slot >= 1)" not in moves_sql)

        if not (needs_pokemon_rebuild or needs_stats_rebuild or needs_moves_rebuild):
            return {
                "rebuilt_pokemon": False,
                "rebuilt_stats": False,
                "rebuilt_moves": False,
            }

        # If legacy is_active exists, migrate storage before table rebuild
        if "is_active" in pokemon_cols:
            _migrate_pokemon_storage(db)

        # Load species map for stats calculation
        species_raw = load_json("pokemon.json")
        species_map = {}
        if isinstance(species_raw, list):
            for s in species_raw:
                if isinstance(s, dict) and "id" in s:
                    species_map[str(s["id"]).lower()] = s

        # Turn foreign keys off during table rebuild
        db.execute("PRAGMA foreign_keys = OFF")

        rebuilt_pokemon = False
        rebuilt_stats = False
        rebuilt_moves = False

        # --- Rebuild pokemon ---
        if needs_pokemon_rebuild:
            pokemon_rows = db.execute("SELECT * FROM pokemon ORDER BY id").fetchall()

            db.execute(
                """
                CREATE TABLE _new_pokemon (
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
                    FOREIGN KEY (owner_id)
                        REFERENCES players(id)
                        ON DELETE CASCADE,
                    CHECK (level >= 1),
                    CHECK (level <= 100),
                    CHECK (experience >= 0),
                    CHECK (shiny IN (0, 1)),
                    CHECK (current_hp >= 0),
                    CHECK (max_hp >= 1)
                )
                """
            )

            for p in pokemon_rows:
                r = dict(p)
                lvl = max(1, min(100, int(r.get("level") or 5)))
                exp = max(0, int(r.get("experience") or 0))
                shiny = 1 if r.get("shiny") else 0
                gender = str(r.get("gender") or "unknown").lower()
                if gender not in ("male", "female", "genderless", "unknown"):
                    gender = "unknown"
                variant = str(r.get("variant") or "normal")
                max_hp = max(1, int(r.get("max_hp") or 1))
                cur_hp = max(0, min(max_hp, int(r.get("current_hp") if r.get("current_hp") is not None else max_hp)))
                created_at = str(r.get("created_at") or "CURRENT_TIMESTAMP")

                db.execute(
                    """
                    INSERT INTO _new_pokemon (
                        id, unique_id, owner_id, species_id, nickname,
                        level, experience, gender, shiny, variant,
                        current_hp, max_hp, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(r["id"]),
                        str(r["unique_id"]),
                        int(r["owner_id"]),
                        str(r["species_id"]),
                        r.get("nickname"),
                        lvl, exp, gender, shiny, variant,
                        cur_hp, max_hp, created_at,
                    ),
                )

            db.execute("DROP TABLE pokemon")
            db.execute("ALTER TABLE _new_pokemon RENAME TO pokemon")
            db.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_owner ON pokemon(owner_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_species ON pokemon(species_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_unique_id ON pokemon(unique_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_variant ON pokemon(variant)")
            rebuilt_pokemon = True

        # --- Rebuild pokemon_stats ---
        if needs_stats_rebuild:
            old_stats = {}
            if has_stats_table:
                try:
                    for r in db.execute("SELECT * FROM pokemon_stats").fetchall():
                        d = dict(r)
                        old_stats[int(d["pokemon_id"])] = d
                except Exception:
                    pass

            db.execute(
                """
                CREATE TABLE _new_pokemon_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pokemon_id INTEGER NOT NULL UNIQUE,
                    hp INTEGER NOT NULL DEFAULT 1,
                    attack INTEGER NOT NULL DEFAULT 1,
                    defense INTEGER NOT NULL DEFAULT 1,
                    sp_attack INTEGER NOT NULL DEFAULT 1,
                    sp_defense INTEGER NOT NULL DEFAULT 1,
                    speed INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY (pokemon_id)
                        REFERENCES pokemon(id)
                        ON DELETE CASCADE
                )
                """
            )

            for p in db.execute("SELECT id, species_id, level FROM pokemon").fetchall():
                pid = int(p["id"])
                computed = _compute_stats_for_migration(p["species_id"], p["level"], species_map)
                prev = old_stats.get(pid, {})
                hp = int(prev.get("hp") or computed["hp"])
                atk = int(prev.get("attack") or computed["attack"])
                defe = int(prev.get("defense") or computed["defense"])
                spa = int(prev.get("sp_attack") or computed["sp_attack"])
                spd = int(prev.get("sp_defense") or computed["sp_defense"])
                spe = int(prev.get("speed") or computed["speed"])

                db.execute(
                    """
                    INSERT INTO _new_pokemon_stats (
                        pokemon_id, hp, attack, defense, sp_attack, sp_defense, speed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (pid, hp, atk, defe, spa, spd, spe),
                )

            db.execute("DROP TABLE IF EXISTS pokemon_stats")
            db.execute("ALTER TABLE _new_pokemon_stats RENAME TO pokemon_stats")
            rebuilt_stats = True

        # --- Rebuild pokemon_moves ---
        if needs_moves_rebuild:
            old_moves = []
            if has_moves_table:
                try:
                    old_moves = db.execute("SELECT * FROM pokemon_moves").fetchall()
                except Exception:
                    pass

            db.execute(
                """
                CREATE TABLE _new_pokemon_moves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pokemon_id INTEGER NOT NULL,
                    move_id TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    current_pp INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (pokemon_id)
                        REFERENCES pokemon(id)
                        ON DELETE CASCADE,
                    UNIQUE (pokemon_id, slot),
                    CHECK (slot >= 1),
                    CHECK (slot <= 4),
                    CHECK (current_pp >= 0)
                )
                """
            )

            for m in old_moves:
                d = dict(m)
                slot = max(1, min(4, int(d.get("slot") or 1)))
                pp = max(0, int(d.get("current_pp") or 0))
                db.execute(
                    """
                    INSERT OR IGNORE INTO _new_pokemon_moves (
                        pokemon_id, move_id, slot, current_pp
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (int(d["pokemon_id"]), str(d["move_id"]), slot, pp),
                )

            db.execute("DROP TABLE IF EXISTS pokemon_moves")
            db.execute("ALTER TABLE _new_pokemon_moves RENAME TO pokemon_moves")
            db.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_moves_pokemon ON pokemon_moves(pokemon_id)")
            rebuilt_moves = True

        # Verify foreign keys
        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations after rebuild: {violations}")

        if owns_connection:
            db.commit()

        db.execute("PRAGMA foreign_keys = ON")

        # Storage cleanup / repair
        repair_pokemon_storage(db)

        return {
            "rebuilt_pokemon": rebuilt_pokemon,
            "rebuilt_stats": rebuilt_stats,
            "rebuilt_moves": rebuilt_moves,
        }

    finally:
        if owns_connection:
            db.close()


# Backwards compatibility aliases
def _remove_legacy_pokemon_columns(
    db: sqlite3.Connection,
) -> None:
    pass


def _remove_legacy_iv_ev_columns(
    db: sqlite3.Connection,
) -> None:
    pass


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


# =============================================================================
# PERMISSION SEEDING
# =============================================================================

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


# =============================================================================
# ROLE/PERMISSION RELATIONSHIPS
# =============================================================================

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


# =============================================================================
# PLAYER ROLE REPAIR
# =============================================================================

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
            "Controls server maintenance mode.",
        ),
        (
            "registration_enabled",
            "true",
            "Controls whether new player registrations are allowed.",
        ),
        (
            "daily_promo_enabled",
            "true",
            "Controls daily promotional Pokémon.",
        ),
    ]

    for (
        setting_name,
        setting_value,
        description,
    ) in settings:

        db.execute(
            """
            INSERT INTO settings
            (
                setting_name,
                setting_value,
                description
            )
            VALUES (?, ?, ?)

            ON CONFLICT(setting_name)
            DO UPDATE SET
                description = excluded.description
            """,
            (
                setting_name,
                setting_value,
                description,
            ),
        )


# =============================================================================
# EVOLUTION SEEDING
# =============================================================================

def _seed_evolution_rules(
    db: sqlite3.Connection,
) -> None:
    """Seed basic evolution rules into the database."""

    evolution_rules = [
        # Kanto starters
        ("bulbasaur", "ivysaur", "level", 16, None, None, None, None, None, "Level 16 evolution"),
        ("ivysaur", "venusaur", "level", 32, None, None, None, None, None, "Level 32 evolution"),
        ("charmander", "charmeleon", "level", 16, None, None, None, None, None, "Level 16 evolution"),
        ("charmeleon", "charizard", "level", 36, None, None, None, None, None, "Level 36 evolution"),
        ("squirtle", "wartortle", "level", 16, None, None, None, None, None, "Level 16 evolution"),
        ("wartortle", "blastoise", "level", 36, None, None, None, None, None, "Level 36 evolution"),

        # Stone evolutions
        ("pikachu", "raichu", "item", None, "thunder_stone", None, None, None, None, "Thunder Stone evolution"),
        ("eevee", "flareon", "item", None, "fire_stone", None, None, None, None, "Fire Stone evolution"),
        ("eevee", "vaporeon", "item", None, "water_stone", None, None, None, None, "Water Stone evolution"),
        ("eevee", "jolteon", "item", None, "thunder_stone", None, None, None, None, "Thunder Stone evolution"),
    ]

    for (
        from_species,
        to_species,
        method,
        condition_level,
        condition_item,
        condition_friendship,
        condition_time,
        condition_location,
        condition_held_item,
        description,
    ) in evolution_rules:

        db.execute(
            """
            INSERT OR IGNORE INTO evolution_rules
            (
                from_species,
                to_species,
                method,
                condition_level,
                condition_item,
                condition_friendship,
                condition_time,
                condition_location,
                condition_held_item,
                description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                from_species,
                to_species,
                method,
                condition_level,
                condition_item,
                condition_friendship,
                condition_time,
                condition_location,
                condition_held_item,
                description,
            ),
        )


# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

def init_db() -> None:
    """
    Initialize and migrate the Krampus RPG database.

    Safe to call repeatedly.
    """

    with get_connection() as db:

        # ---------------------------------------------------------------------
        # Base schema.
        # ---------------------------------------------------------------------

        db.executescript(
            SCHEMA
        )

        # ---------------------------------------------------------------------
        # Roles.
        # ---------------------------------------------------------------------

        _seed_roles(
            db
        )

        _migrate_players_role(
            db
        )

        # ---------------------------------------------------------------------
        # Permissions.
        # ---------------------------------------------------------------------

        _seed_permissions(
            db
        )

        _seed_role_permissions(
            db
        )

        # ---------------------------------------------------------------------
        # Repair player roles.
        # ---------------------------------------------------------------------

        _repair_existing_players(
            db
        )

        # ---------------------------------------------------------------------
        # Party / PC.
        # ---------------------------------------------------------------------

        _ensure_storage_schema(
            db
        )

        # ---------------------------------------------------------------------
        # Migrate old Party system.
        # ---------------------------------------------------------------------

        _migrate_pokemon_storage(
            db
        )

        # ---------------------------------------------------------------------
        # Rebuild legacy Pokémon tables safely into the new schema.
        # ---------------------------------------------------------------------

        rebuild_legacy_pokemon_tables(
            db
        )

        # ---------------------------------------------------------------------
        # Settings.
        # ---------------------------------------------------------------------

        _seed_default_settings(
            db
        )

        # ---------------------------------------------------------------------
        # Evolution rules.
        # ---------------------------------------------------------------------

        _seed_evolution_rules(
            db
        )

        db.commit()


# =============================================================================
# JSON LOADING
# =============================================================================

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

    with get_connection() as db:

        if isinstance(
            quests,
            list,
        ):

            for quest in quests:

                if not isinstance(
                    quest,
                    dict,
                ):
                    continue

                quest_id = quest.get(
                    "id"
                )

                if not quest_id:
                    continue

                db.execute(
                    """
                    INSERT INTO quests
                    (
                        id,
                        name,
                        description,
                        reward_money,
                        reward_item,
                        reward_quantity
                    )
                    VALUES (?, ?, ?, ?, ?, ?)

                    ON CONFLICT(id)
                    DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        reward_money = excluded.reward_money,
                        reward_item = excluded.reward_item,
                        reward_quantity = excluded.reward_quantity
                    """,
                    (
                        str(quest_id),
                        str(
                            quest.get(
                                "name",
                                "",
                            )
                        ),
                        str(
                            quest.get(
                                "description",
                                "",
                            )
                        ),
                        int(
                            quest.get(
                                "reward_money",
                                0,
                            )
                            or 0
                        ),
                        quest.get(
                            "reward_item"
                        ),
                        int(
                            quest.get(
                                "reward_quantity",
                                0,
                            )
                            or 0
                        ),
                    ),
                )

        db.commit()


# =============================================================================
# STORAGE REPAIR
# =============================================================================

def repair_pokemon_storage(
    db: sqlite3.Connection | None = None,
) -> dict:
    """
    Repair Pokémon that are not assigned to Party or PC, or have ownership mismatches.

    Rules:
        Party Pokémon stay in Party (max 6 per player; excess moves to PC).
        PC Pokémon stay in PC.
        Orphaned Pokémon are moved to PC.
        Pokémon in both are removed from PC.
        Pokémon stored under another player are moved to true owner's PC.
    """
    owns_connection = db is None

    if owns_connection:
        db = get_connection()

    repaired = 0
    already_stored = 0
    conflicts_fixed = 0

    try:
        _ensure_storage_schema(db)

        # ---------------------------------------------------------------------
        # Remove storage records for nonexistent Pokémon.
        # ---------------------------------------------------------------------
        db.execute(
            """
            DELETE FROM party
            WHERE pokemon_id NOT IN (
                SELECT id
                FROM pokemon
            )
            """
        )

        db.execute(
            """
            DELETE FROM pc_storage
            WHERE pokemon_id NOT IN (
                SELECT id
                FROM pokemon
            )
            """
        )

        # ---------------------------------------------------------------------
        # Fix storage owner mismatches (storage player_id != pokemon.owner_id).
        # ---------------------------------------------------------------------
        mismatched_party = db.execute(
            """
            DELETE FROM party
            WHERE id IN (
                SELECT pt.id
                FROM party pt
                JOIN pokemon p ON p.id = pt.pokemon_id
                WHERE pt.player_id != p.owner_id
            )
            """
        )
        conflicts_fixed += mismatched_party.rowcount

        mismatched_pc = db.execute(
            """
            DELETE FROM pc_storage
            WHERE id IN (
                SELECT pc.id
                FROM pc_storage pc
                JOIN pokemon p ON p.id = pc.pokemon_id
                WHERE pc.player_id != p.owner_id
            )
            """
        )
        conflicts_fixed += mismatched_pc.rowcount

        # ---------------------------------------------------------------------
        # Party takes priority if a Pokémon somehow exists in both.
        # ---------------------------------------------------------------------
        cursor = db.execute(
            """
            DELETE FROM pc_storage
            WHERE pokemon_id IN (
                SELECT pokemon_id
                FROM party
            )
            """
        )
        conflicts_fixed += cursor.rowcount

        # ---------------------------------------------------------------------
        # Move excess party Pokémon (> 6) to PC.
        # ---------------------------------------------------------------------
        party_players = db.execute(
            "SELECT DISTINCT player_id FROM party"
        ).fetchall()

        for p_row in party_players:
            pid = int(p_row["player_id"])
            p_slots = db.execute(
                "SELECT pokemon_id, slot FROM party WHERE player_id = ? ORDER BY slot",
                (pid,),
            ).fetchall()
            if len(p_slots) > MAX_PARTY_SIZE:
                for excess in p_slots[MAX_PARTY_SIZE:]:
                    x_id = int(excess["pokemon_id"])
                    db.execute("DELETE FROM party WHERE pokemon_id = ?", (x_id,))
                    _put_in_pc(db, pid, x_id)
                    repaired += 1

        # ---------------------------------------------------------------------
        # Find every owned Pokémon and ensure it is stored.
        # ---------------------------------------------------------------------
        pokemon_rows = db.execute(
            """
            SELECT
                id,
                owner_id
            FROM pokemon
            ORDER BY id
            """
        ).fetchall()

        for pokemon in pokemon_rows:
            pokemon_id = int(pokemon["id"])
            owner_id = int(pokemon["owner_id"])

            in_party = _pokemon_in_party(db, pokemon_id)
            in_pc = _pokemon_in_pc(db, pokemon_id)

            if in_party or in_pc:
                already_stored += 1
                continue

            if _put_in_pc(db, owner_id, pokemon_id):
                repaired += 1

        if owns_connection:
            db.commit()

        return {
            "repaired": repaired,
            "already_stored": already_stored,
            "conflicts_fixed": conflicts_fixed,
        }

    finally:
        if owns_connection:
            db.close()


# =============================================================================
# STORAGE LOCATION
# =============================================================================

def get_pokemon_storage_location(
    pokemon_id: int,
) -> dict | None:
    """
    Return the authoritative storage location of a Pokémon.
    """

    with get_connection() as db:

        party = db.execute(
            """
            SELECT
                player_id,
                slot
            FROM party
            WHERE pokemon_id = ?
            LIMIT 1
            """,
            (pokemon_id,),
        ).fetchone()

        if party is not None:

            return {
                "location": "party",
                "player_id": int(
                    party["player_id"]
                ),
                "slot": int(
                    party["slot"]
                ),
            }

        pc = db.execute(
            """
            SELECT
                player_id,
                page,
                slot
            FROM pc_storage
            WHERE pokemon_id = ?
            LIMIT 1
            """,
            (pokemon_id,),
        ).fetchone()

        if pc is not None:

            return {
                "location": "pc",
                "player_id": int(
                    pc["player_id"]
                ),
                "page": int(
                    pc["page"]
                ),
                "slot": int(
                    pc["slot"]
                ),
            }

    return None


# =============================================================================
# COUNTS
# =============================================================================

def get_party_count(
    player_id: int,
) -> int:

    with get_connection() as db:

        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM party
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        return int(
            row["count"]
        )


def get_pc_count(
    player_id: int,
) -> int:

    with get_connection() as db:

        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pc_storage
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        return int(
            row["count"]
        )


def get_owned_pokemon_count(
    player_id: int,
) -> int:

    with get_connection() as db:

        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM pokemon
            WHERE owner_id = ?
            """,
            (player_id,),
        ).fetchone()

        return int(
            row["count"]
        )


# =============================================================================
# STORAGE INVARIANT CHECK
# =============================================================================

def verify_storage_invariant(
    player_id: int | None = None,
    db: sqlite3.Connection | None = None,
) -> list[dict]:
    """
    Find Pokémon that violate the Party/PC ownership invariant.

    A valid Pokémon must be:

        Party
        OR
        PC

    and must never be:

        both
        neither
        owned by one player but stored under another.
    """

    problems: list[dict] = []
    owns_connection = db is None

    if owns_connection:
        db = get_connection()

    try:
        if player_id is None:

            pokemon_rows = db.execute(
                """
                SELECT
                    id,
                    owner_id
                FROM pokemon
                ORDER BY id
                """
            ).fetchall()

        else:

            pokemon_rows = db.execute(
                """
                SELECT
                    id,
                    owner_id
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

            owner_id = int(
                pokemon["owner_id"]
            )

            party_rows = db.execute(
                """
                SELECT player_id
                FROM party
                WHERE pokemon_id = ?
                """,
                (pokemon_id,),
            ).fetchall()

            pc_rows = db.execute(
                """
                SELECT player_id
                FROM pc_storage
                WHERE pokemon_id = ?
                """,
                (pokemon_id,),
            ).fetchall()

            storage_count = (
                len(party_rows)
                + len(pc_rows)
            )

            if storage_count == 0:

                problems.append(
                    {
                        "pokemon_id": pokemon_id,
                        "owner_id": owner_id,
                        "problem": "not_in_party_or_pc",
                    }
                )

                continue

            if storage_count > 1:

                problems.append(
                    {
                        "pokemon_id": pokemon_id,
                        "owner_id": owner_id,
                        "problem": "multiple_storage_records",
                    }
                )

                continue

            if party_rows:

                storage_player_id = int(
                    party_rows[0]["player_id"]
                )

            else:

                storage_player_id = int(
                    pc_rows[0]["player_id"]
                )

            if storage_player_id != owner_id:

                problems.append(
                    {
                        "pokemon_id": pokemon_id,
                        "owner_id": owner_id,
                        "storage_player_id": storage_player_id,
                        "problem": "storage_owner_mismatch",
                    }
                )

        if player_id is None:
            party_counts = db.execute(
                "SELECT player_id, COUNT(*) AS cnt FROM party GROUP BY player_id"
            ).fetchall()
        else:
            party_counts = db.execute(
                "SELECT player_id, COUNT(*) AS cnt FROM party WHERE player_id = ? GROUP BY player_id",
                (player_id,),
            ).fetchall()

        for pc_row in party_counts:
            if int(pc_row["cnt"]) > MAX_PARTY_SIZE:
                problems.append(
                    {
                        "player_id": int(pc_row["player_id"]),
                        "party_count": int(pc_row["cnt"]),
                        "problem": "party_exceeds_maximum",
                    }
                )

        return problems

    finally:
        if owns_connection:
            db.close()