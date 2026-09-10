from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


# Make the Server package available when this script
# is run directly from the KrampusRPG project root.
PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from Server.database import get_connection, init_db


USERNAME = "Goldisduck"


def delete_player(username: str) -> None:
    username = username.strip()

    if not username:
        raise ValueError("Username is required.")

    init_db()

    with get_connection() as db:
        player = db.execute(
            """
            SELECT
                id,
                username,
                display_name,
                role_id
            FROM players
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

        if player is None:
            print()
            print(f"Player '{username}' was not found.")
            print()
            return

        print()
        print("=== PLAYER FOUND ===")
        print()
        print(f"ID:           {player['id']}")
        print(f"Username:     {player['username']}")
        print(f"Display Name: {player['display_name']}")
        print(f"Role ID:      {player['role_id']}")
        print()

        confirmation = input(
            f"Type DELETE to permanently delete '{username}': "
        ).strip()

        if confirmation != "DELETE":
            print()
            print("Deletion cancelled.")
            print()
            return

        player_id = player["id"]

        # Remove player progress first.
        db.execute(
            """
            DELETE FROM player_progress
            WHERE player_id = ?
            """,
            (player_id,),
        )

        # Remove owned Pokémon if this table exists.
        try:
            db.execute(
                """
                DELETE FROM player_pokemon
                WHERE player_id = ?
                """,
                (player_id,),
            )
        except sqlite3.OperationalError:
            pass

        # Finally remove the player.
        cursor = db.execute(
            """
            DELETE FROM players
            WHERE id = ?
            """,
            (player_id,),
        )

        if cursor.rowcount != 1:
            db.rollback()
            raise RuntimeError(
                "Player deletion failed. Database changes were rolled back."
            )

        db.commit()

        print()
        print("==============================")
        print("PLAYER DELETED SUCCESSFULLY")
        print("==============================")
        print()
        print(f"Username: {username}")
        print(f"Player ID: {player_id}")
        print()


if __name__ == "__main__":
    try:
        delete_player(USERNAME)

    except (ValueError, sqlite3.Error, RuntimeError) as exc:
        print()
        print(f"Error: {exc}")
        print()
        raise SystemExit(1)