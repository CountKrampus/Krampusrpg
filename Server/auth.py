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
