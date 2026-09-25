"""
Krampus RPG Quest Battle Progress Table
=======================================

Created alongside the story battle engine: tracks which individual
quest battle steps a player has defeated, so multi-battle quests
unlock step by step.
"""

from __future__ import annotations

from .database import get_connection


_SCHEMA = """
CREATE TABLE IF NOT EXISTS player_quest_battles (
    player_id    INTEGER NOT NULL,
    questline    TEXT NOT NULL,
    quest_id     TEXT NOT NULL,
    battle_index INTEGER NOT NULL,

    defeated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (player_id, questline, quest_id, battle_index),

    FOREIGN KEY (player_id)
        REFERENCES players(id)
        ON DELETE CASCADE
);
"""


def ensure_quest_battle_schema() -> None:
    with get_connection() as db:
        db.executescript(_SCHEMA)
        db.commit()
