from __future__ import annotations

import argparse
import getpass
import sqlite3

from ..auth import create_password
from ..database import get_connection, init_db


# Role IDs from Server/database.py
PLAYER_ROLE_ID = 1
MODERATOR_ROLE_ID = 2
EVENT_STAFF_ROLE_ID = 3
ADMIN_ROLE_ID = 4
WEBMASTER_ROLE_ID = 5


def find_player(
    db: sqlite3.Connection,
    username: str,
):
    return db.execute(
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


def create_webmaster(
    username: str,
    password: str,
    display_name: str | None = None,
) -> int:
    """
    Create a new webmaster account.

    This function is intended for initial server setup.
    It does not modify an existing account unless the
    account is explicitly promoted with promote_webmaster().
    """

    username = username.strip()

    if not username:
        raise ValueError("Username is required.")

    if len(username) < 3:
        raise ValueError(
            "Username must contain at least 3 characters."
        )

    if len(password) < 6:
        raise ValueError(
            "Password must contain at least 6 characters."
        )

    display_name = (
        display_name.strip()
        if display_name
        else username
    )

    init_db()

    with get_connection() as db:
        existing = find_player(
            db,
            username,
        )

        if existing is not None:
            raise ValueError(
                f"Username '{username}' already exists."
            )

        cursor = db.execute(
            """
            INSERT INTO players
            (
                username,
                password_hash,
                display_name,
                role_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                username,
                create_password(password),
                display_name,
                WEBMASTER_ROLE_ID,
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

    return int(player_id)


def promote_webmaster(
    username: str,
) -> int:
    """
    Promote an existing account to webmaster.

    Returns the player ID.
    """

    username = username.strip()

    if not username:
        raise ValueError("Username is required.")

    init_db()

    with get_connection() as db:
        player = find_player(
            db,
            username,
        )

        if player is None:
            raise ValueError(
                f"Player '{username}' does not exist."
            )

        db.execute(
            """
            UPDATE players
            SET role_id = ?
            WHERE id = ?
            """,
            (
                WEBMASTER_ROLE_ID,
                player["id"],
            ),
        )

        db.commit()

        return int(player["id"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Krampus RPG webmaster account setup."
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    create_parser = subparsers.add_parser(
        "create",
        help="Create a new webmaster account.",
    )

    create_parser.add_argument(
        "username",
        help="Username for the webmaster account.",
    )

    create_parser.add_argument(
        "--display-name",
        default=None,
        help="Optional display name.",
    )

    promote_parser = subparsers.add_parser(
        "promote",
        help="Promote an existing account to webmaster.",
    )

    promote_parser.add_argument(
        "username",
        help="Existing username to promote.",
    )

    args = parser.parse_args()

    if args.command == "create":
        print()
        print("=== Krampus RPG Webmaster Setup ===")
        print()

        password = getpass.getpass(
            "Webmaster password: "
        )

        confirm_password = getpass.getpass(
            "Confirm password: "
        )

        if password != confirm_password:
            print("Passwords do not match.")
            raise SystemExit(1)

        try:
            player_id = create_webmaster(
                username=args.username,
                password=password,
                display_name=args.display_name,
            )
        except (ValueError, sqlite3.Error) as exc:
            print(f"Error: {exc}")
            raise SystemExit(1)

        print()
        print("Webmaster account created successfully.")
        print(f"Player ID: {player_id}")
        print(f"Username: {args.username}")
        print("Role: webmaster")
        print()

    elif args.command == "promote":
        print()
        print("=== Krampus RPG Webmaster Promotion ===")
        print()

        try:
            player_id = promote_webmaster(
                args.username,
            )
        except (ValueError, sqlite3.Error) as exc:
            print(f"Error: {exc}")
            raise SystemExit(1)

        print()
        print("Account promoted successfully.")
        print(f"Player ID: {player_id}")
        print(f"Username: {args.username}")
        print("Role: webmaster")
        print()


if __name__ == "__main__":
    main()