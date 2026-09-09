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
