"""
Krampus RPG News System

Database-backed news articles used by the player dashboard and the
Webmaster-only administrative news editor.
"""

from __future__ import annotations

from typing import Any

from .database import get_connection


NEWS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    author_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (author_id)
        REFERENCES players(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_news_posts_published
ON news_posts(published);

CREATE INDEX IF NOT EXISTS idx_news_posts_created_at
ON news_posts(created_at);
"""


def ensure_news_table() -> None:
    """Create the news table and indexes if they do not exist."""

    with get_connection() as db:
        db.executescript(NEWS_TABLE_SCHEMA)
        db.commit()


def get_published_news(
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return published news articles, newest first."""

    ensure_news_table()

    try:
        limit = max(
            1,
            min(
                int(limit),
                100,
            ),
        )
    except (TypeError, ValueError):
        limit = 20

    with get_connection() as db:
        rows = db.execute(
            """
            SELECT
                n.id,
                n.title,
                n.content,
                n.author_id,
                n.created_at,
                n.updated_at,
                n.published,
                COALESCE(
                    p.display_name,
                    p.username
                ) AS author_name
            FROM news_posts n
            LEFT JOIN players p
                ON p.id = n.author_id
            WHERE n.published = 1
            ORDER BY
                n.created_at DESC,
                n.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_all_news() -> list[dict[str, Any]]:
    """Return all news articles for the Webmaster editor."""

    ensure_news_table()

    with get_connection() as db:
        rows = db.execute(
            """
            SELECT
                n.id,
                n.title,
                n.content,
                n.author_id,
                n.created_at,
                n.updated_at,
                n.published,
                COALESCE(
                    p.display_name,
                    p.username
                ) AS author_name
            FROM news_posts n
            LEFT JOIN players p
                ON p.id = n.author_id
            ORDER BY
                n.created_at DESC,
                n.id DESC
            """
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_news_post(
    post_id: int,
) -> dict[str, Any] | None:
    """Return one news article by ID."""

    ensure_news_table()

    with get_connection() as db:
        row = db.execute(
            """
            SELECT
                n.id,
                n.title,
                n.content,
                n.author_id,
                n.created_at,
                n.updated_at,
                n.published,
                COALESCE(
                    p.display_name,
                    p.username
                ) AS author_name
            FROM news_posts n
            LEFT JOIN players p
                ON p.id = n.author_id
            WHERE n.id = ?
            """,
            (post_id,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def create_news_post(
    title: str,
    content: str,
    author_id: int,
    published: bool = False,
) -> int:
    """Create a news article and return its ID."""

    ensure_news_table()

    title = title.strip()
    content = content.strip()

    if not title:
        raise ValueError(
            "A news title is required."
        )

    if not content:
        raise ValueError(
            "News content is required."
        )

    with get_connection() as db:
        cursor = db.execute(
            """
            INSERT INTO news_posts
            (
                title,
                content,
                author_id,
                published
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                title,
                content,
                author_id,
                1 if published else 0,
            ),
        )

        db.commit()

        return int(cursor.lastrowid)


def update_news_post(
    post_id: int,
    title: str,
    content: str,
    published: bool,
) -> bool:
    """Update an existing news article."""

    ensure_news_table()

    title = title.strip()
    content = content.strip()

    if not title:
        raise ValueError(
            "A news title is required."
        )

    if not content:
        raise ValueError(
            "News content is required."
        )

    with get_connection() as db:
        cursor = db.execute(
            """
            UPDATE news_posts
            SET
                title = ?,
                content = ?,
                published = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                title,
                content,
                1 if published else 0,
                post_id,
            ),
        )

        db.commit()

        return cursor.rowcount > 0


def delete_news_post(
    post_id: int,
) -> bool:
    """Delete a news article."""

    ensure_news_table()

    with get_connection() as db:
        cursor = db.execute(
            """
            DELETE FROM news_posts
            WHERE id = ?
            """,
            (post_id,),
        )

        db.commit()

        return cursor.rowcount > 0