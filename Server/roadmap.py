"""
Krampus RPG Development Roadmap

Database-backed Kanban-style development roadmap used by:

- The public /roadmap page (players see milestones, cards, progress).
- The Webmaster-only admin editor (full card/task management).

Data model:

- roadmap_milestones: top-level feature areas (Foundation, Pokémon
  System, Battle System, ...). Each has a sort order, description and
  the progress shown on the roadmap is computed from its cards.
- roadmap_cards: individual feature cards ("Pokémon Core", "Catching",
  ...). Each belongs to a milestone, has a status column (backlog /
  planned / in_development / testing / completed), priority, sprint,
  assignee, and a checklist of tasks.
- roadmap_tasks: checklist items on a card. Card progress is
  done_tasks / total_tasks.
"""

from __future__ import annotations

from typing import Any

from .database import get_connection


# ============================================================
# CONSTANTS
# ============================================================

STATUS_BACKLOG = "backlog"
STATUS_PLANNED = "planned"
STATUS_IN_DEVELOPMENT = "in_development"
STATUS_TESTING = "testing"
STATUS_COMPLETED = "completed"

CARD_STATUSES = (
    STATUS_BACKLOG,
    STATUS_PLANNED,
    STATUS_IN_DEVELOPMENT,
    STATUS_TESTING,
    STATUS_COMPLETED,
)

STATUS_LABELS = {
    STATUS_BACKLOG: "Backlog",
    STATUS_PLANNED: "Planned",
    STATUS_IN_DEVELOPMENT: "In Development",
    STATUS_TESTING: "Testing",
    STATUS_COMPLETED: "Completed",
}

PRIORITY_CRITICAL = "critical"
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

CARD_PRIORITIES = (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)


# ============================================================
# SCHEMA
# ============================================================

ROADMAP_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS roadmap_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roadmap_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'backlog',
    priority TEXT NOT NULL DEFAULT 'medium',
    sprint TEXT NOT NULL DEFAULT '',
    assignee TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (milestone_id)
        REFERENCES roadmap_milestones(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS roadmap_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (card_id)
        REFERENCES roadmap_cards(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_roadmap_cards_milestone
ON roadmap_cards(milestone_id);

CREATE INDEX IF NOT EXISTS idx_roadmap_tasks_card
ON roadmap_tasks(card_id);
"""


def ensure_roadmap_tables() -> None:
    """Create the roadmap tables if they do not exist."""

    with get_connection() as db:
        db.executescript(ROADMAP_TABLE_SCHEMA)
        db.commit()


# ============================================================
# MILESTONES
# ============================================================

def get_milestones() -> list[dict[str, Any]]:
    """Return all milestones ordered by sort_order, with card counts."""

    ensure_roadmap_tables()

    with get_connection() as db:
        rows = db.execute(
            """
            SELECT
                m.id,
                m.name,
                m.description,
                m.sort_order,
                (
                    SELECT COUNT(*)
                    FROM roadmap_cards c
                    WHERE c.milestone_id = m.id
                ) AS card_count
            FROM roadmap_milestones m
            ORDER BY
                m.sort_order ASC,
                m.id ASC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_milestone(milestone_id: int) -> dict[str, Any] | None:
    """Return one milestone by id, or None."""

    ensure_roadmap_tables()

    with get_connection() as db:
        row = db.execute(
            """
            SELECT *
            FROM roadmap_milestones
            WHERE id = ?
            """,
            (milestone_id,),
        ).fetchone()

    return dict(row) if row else None


def create_milestone(
    name: str,
    description: str = "",
    sort_order: int | None = None,
) -> int:
    """
    Create a milestone. Raises ValueError on invalid input or duplicate
    name.
    """

    name = str(name or "").strip()

    if not name:
        raise ValueError("Milestone name is required.")

    if len(name) > 100:
        raise ValueError("Milestone name is too long (max 100).")

    with get_connection() as db:
        existing = db.execute(
            """
            SELECT id
            FROM roadmap_milestones
            WHERE name = ?
            """,
            (name,),
        ).fetchone()

        if existing:
            raise ValueError(
                f"A milestone named {name!r} already exists."
            )

        if sort_order is None:
            row = db.execute(
                """
                SELECT COALESCE(MAX(sort_order), 0) + 1 AS next
                FROM roadmap_milestones
                """
            ).fetchone()
            sort_order = int(row["next"])

        cursor = db.execute(
            """
            INSERT INTO roadmap_milestones
                (name, description, sort_order)
            VALUES (?, ?, ?)
            """,
            (name, str(description or "").strip(), int(sort_order)),
        )
        db.commit()

        return int(cursor.lastrowid)


def update_milestone(
    milestone_id: int,
    name: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
) -> bool:
    """Update editable milestone fields. Returns False if not found."""

    ensure_roadmap_tables()

    assignments: list[str] = []
    values: list[Any] = []

    if name is not None:
        name = str(name).strip()

        if not name:
            raise ValueError("Milestone name cannot be empty.")

        if len(name) > 100:
            raise ValueError("Milestone name is too long (max 100).")

        with get_connection() as db:
            duplicate = db.execute(
                """
                SELECT id
                FROM roadmap_milestones
                WHERE name = ? AND id != ?
                """,
                (name, milestone_id),
            ).fetchone()

        if duplicate:
            raise ValueError(
                f"A milestone named {name!r} already exists."
            )

        assignments.append("name = ?")
        values.append(name)

    if description is not None:
        assignments.append("description = ?")
        values.append(str(description).strip())

    if sort_order is not None:
        assignments.append("sort_order = ?")
        values.append(int(sort_order))

    if not assignments:
        return True

    assignments.append("updated_at = CURRENT_TIMESTAMP")

    with get_connection() as db:
        cursor = db.execute(
            f"""
            UPDATE roadmap_milestones
            SET {", ".join(assignments)}
            WHERE id = ?
            """,
            (*values, milestone_id),
        )
        db.commit()

        return cursor.rowcount > 0


def delete_milestone(milestone_id: int) -> bool:
    """Delete a milestone along with its cards and tasks."""

    ensure_roadmap_tables()

    with get_connection() as db:
        card_ids = [
            int(row["id"])
            for row in db.execute(
                """
                SELECT id
                FROM roadmap_cards
                WHERE milestone_id = ?
                """,
                (milestone_id,),
            ).fetchall()
        ]

        for card_id in card_ids:
            db.execute(
                "DELETE FROM roadmap_tasks WHERE card_id = ?",
                (card_id,),
            )

        db.execute(
            "DELETE FROM roadmap_cards WHERE milestone_id = ?",
            (milestone_id,),
        )

        cursor = db.execute(
            "DELETE FROM roadmap_milestones WHERE id = ?",
            (milestone_id,),
        )
        db.commit()

        return cursor.rowcount > 0


# ============================================================
# CARDS
# ============================================================

def _normalize_status(status: Any) -> str:
    status = str(status or STATUS_BACKLOG).strip().lower()

    if status not in CARD_STATUSES:
        raise ValueError(f"Invalid card status: {status!r}")

    return status


def _normalize_priority(priority: Any) -> str:
    priority = str(priority or PRIORITY_MEDIUM).strip().lower()

    if priority not in CARD_PRIORITIES:
        raise ValueError(f"Invalid card priority: {priority!r}")

    return priority


def get_card(card_id: int) -> dict[str, Any] | None:
    """Return one card with its tasks, or None."""

    ensure_roadmap_tables()

    with get_connection() as db:
        row = db.execute(
            """
            SELECT
                c.*,
                m.name AS milestone_name
            FROM roadmap_cards c
            JOIN roadmap_milestones m
                ON m.id = c.milestone_id
            WHERE c.id = ?
            """,
            (card_id,),
        ).fetchone()

        if row is None:
            return None

        card = dict(row)

        tasks = db.execute(
            """
            SELECT *
            FROM roadmap_tasks
            WHERE card_id = ?
            ORDER BY
                sort_order ASC,
                id ASC
            """,
            (card_id,),
        ).fetchall()

    card["tasks"] = [dict(task) for task in tasks]
    card["done_tasks"] = sum(
        1 for task in card["tasks"] if task["done"]
    )
    card["total_tasks"] = len(card["tasks"])

    return card


def get_board() -> dict[str, Any]:
    """
    Return the full board: milestones (ordered) with their cards
    (ordered), each card including its checklist and progress.
    """

    ensure_roadmap_tables()

    with get_connection() as db:
        milestones = [
            dict(row)
            for row in db.execute(
                """
                SELECT *
                FROM roadmap_milestones
                ORDER BY
                    sort_order ASC,
                    id ASC
                """
            ).fetchall()
        ]

        cards = [
            dict(row)
            for row in db.execute(
                """
                SELECT *
                FROM roadmap_cards
                ORDER BY
                    sort_order ASC,
                    id ASC
                """
            ).fetchall()
        ]

        tasks = [
            dict(row)
            for row in db.execute(
                """
                SELECT *
                FROM roadmap_tasks
                ORDER BY
                    sort_order ASC,
                    id ASC
                """
            ).fetchall()
        ]

    tasks_by_card: dict[int, list[dict[str, Any]]] = {}
    for task in tasks:
        tasks_by_card.setdefault(int(task["card_id"]), []).append(task)

    cards_by_milestone: dict[int, list[dict[str, Any]]] = {}
    for card in cards:
        card_id = int(card["id"])
        card_tasks = tasks_by_card.get(card_id, [])
        card["tasks"] = card_tasks
        card["done_tasks"] = sum(1 for t in card_tasks if t["done"])
        card["total_tasks"] = len(card_tasks)

        cards_by_milestone.setdefault(
            int(card["milestone_id"]), []
        ).append(card)

    for milestone in milestones:
        milestone_cards = cards_by_milestone.get(int(milestone["id"]), [])
        milestone["cards"] = milestone_cards
        milestone["card_count"] = len(milestone_cards)

        total_done = sum(c["done_tasks"] for c in milestone_cards)
        total_tasks = sum(c["total_tasks"] for c in milestone_cards)

        completed_cards = sum(
            1 for c in milestone_cards
            if c["status"] == STATUS_COMPLETED
        )

        if total_tasks:
            milestone["progress"] = round(100 * total_done / total_tasks)
        elif milestone_cards and completed_cards == len(milestone_cards):
            milestone["progress"] = 100
        else:
            milestone["progress"] = 0

    return {
        "milestones": milestones,
        "statuses": CARD_STATUSES,
        "status_labels": STATUS_LABELS,
    }


def create_card(
    milestone_id: int,
    title: str,
    description: str = "",
    status: str = STATUS_BACKLOG,
    priority: str = PRIORITY_MEDIUM,
    sprint: str = "",
    assignee: str = "",
    sort_order: int | None = None,
) -> int:
    """
    Create a card. Raises ValueError on invalid input or unknown
    milestone.
    """

    title = str(title or "").strip()

    if not title:
        raise ValueError("Card title is required.")

    if len(title) > 120:
        raise ValueError("Card title is too long (max 120).")

    status = _normalize_status(status)
    priority = _normalize_priority(priority)

    with get_connection() as db:
        milestone = db.execute(
            """
            SELECT id
            FROM roadmap_milestones
            WHERE id = ?
            """,
            (milestone_id,),
        ).fetchone()

        if milestone is None:
            raise ValueError("Unknown milestone.")

        if sort_order is None:
            row = db.execute(
                """
                SELECT COALESCE(MAX(sort_order), 0) + 1 AS next
                FROM roadmap_cards
                WHERE milestone_id = ?
                """,
                (milestone_id,),
            ).fetchone()
            sort_order = int(row["next"])

        cursor = db.execute(
            """
            INSERT INTO roadmap_cards
                (
                    milestone_id,
                    title,
                    description,
                    status,
                    priority,
                    sprint,
                    assignee,
                    sort_order
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(milestone_id),
                title,
                str(description or "").strip(),
                status,
                priority,
                str(sprint or "").strip()[:60],
                str(assignee or "").strip()[:60],
                int(sort_order),
            ),
        )
        db.commit()

        return int(cursor.lastrowid)


def update_card(
    card_id: int,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    sprint: str | None = None,
    assignee: str | None = None,
    sort_order: int | None = None,
    milestone_id: int | None = None,
) -> bool:
    """Update editable card fields. Returns False if not found."""

    ensure_roadmap_tables()

    assignments: list[str] = []
    values: list[Any] = []

    if title is not None:
        title = str(title).strip()

        if not title:
            raise ValueError("Card title cannot be empty.")

        if len(title) > 120:
            raise ValueError("Card title is too long (max 120).")

        assignments.append("title = ?")
        values.append(title)

    if description is not None:
        assignments.append("description = ?")
        values.append(str(description).strip())

    if status is not None:
        assignments.append("status = ?")
        values.append(_normalize_status(status))

    if priority is not None:
        assignments.append("priority = ?")
        values.append(_normalize_priority(priority))

    if sprint is not None:
        assignments.append("sprint = ?")
        values.append(str(sprint).strip()[:60])

    if assignee is not None:
        assignments.append("assignee = ?")
        values.append(str(assignee).strip()[:60])

    if sort_order is not None:
        assignments.append("sort_order = ?")
        values.append(int(sort_order))

    if milestone_id is not None:
        with get_connection() as db:
            milestone = db.execute(
                """
                SELECT id
                FROM roadmap_milestones
                WHERE id = ?
                """,
                (int(milestone_id),),
            ).fetchone()

        if milestone is None:
            raise ValueError("Unknown milestone.")

        assignments.append("milestone_id = ?")
        values.append(int(milestone_id))

    if not assignments:
        return True

    assignments.append("updated_at = CURRENT_TIMESTAMP")

    with get_connection() as db:
        cursor = db.execute(
            f"""
            UPDATE roadmap_cards
            SET {", ".join(assignments)}
            WHERE id = ?
            """,
            (*values, card_id),
        )
        db.commit()

        return cursor.rowcount > 0


def delete_card(card_id: int) -> bool:
    """Delete a card and its tasks."""

    ensure_roadmap_tables()

    with get_connection() as db:
        db.execute(
            "DELETE FROM roadmap_tasks WHERE card_id = ?",
            (card_id,),
        )

        cursor = db.execute(
            "DELETE FROM roadmap_cards WHERE id = ?",
            (card_id,),
        )
        db.commit()

        return cursor.rowcount > 0


def move_card(card_id: int, status: str) -> bool:
    """
    Move a card to another Kanban column (status). Returns False if the
    card does not exist; raises ValueError on an invalid status.
    """

    status = _normalize_status(status)

    ensure_roadmap_tables()

    with get_connection() as db:
        cursor = db.execute(
            """
            UPDATE roadmap_cards
            SET status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, card_id),
        )
        db.commit()

        return cursor.rowcount > 0


# ============================================================
# TASKS
# ============================================================

def create_task(
    card_id: int,
    label: str,
    done: bool = False,
) -> int:
    """
    Add a checklist item to a card. Raises ValueError on invalid input
    or unknown card.
    """

    label = str(label or "").strip()

    if not label:
        raise ValueError("Task label is required.")

    if len(label) > 200:
        raise ValueError("Task label is too long (max 200).")

    with get_connection() as db:
        card = db.execute(
            """
            SELECT id
            FROM roadmap_cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()

        if card is None:
            raise ValueError("Unknown card.")

        row = db.execute(
            """
            SELECT COALESCE(MAX(sort_order), 0) + 1 AS next
            FROM roadmap_tasks
            WHERE card_id = ?
            """,
            (card_id,),
        ).fetchone()

        cursor = db.execute(
            """
            INSERT INTO roadmap_tasks
                (card_id, label, done, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(card_id),
                label,
                1 if done else 0,
                int(row["next"]),
            ),
        )
        db.commit()

        return int(cursor.lastrowid)


def update_task(
    task_id: int,
    label: str | None = None,
    done: bool | None = None,
) -> bool:
    """Update a checklist item. Returns False if not found."""

    ensure_roadmap_tables()

    assignments: list[str] = []
    values: list[Any] = []

    if label is not None:
        label = str(label).strip()

        if not label:
            raise ValueError("Task label cannot be empty.")

        if len(label) > 200:
            raise ValueError("Task label is too long (max 200).")

        assignments.append("label = ?")
        values.append(label)

    if done is not None:
        assignments.append("done = ?")
        values.append(1 if done else 0)

    if not assignments:
        return True

    with get_connection() as db:
        cursor = db.execute(
            f"""
            UPDATE roadmap_tasks
            SET {", ".join(assignments)}
            WHERE id = ?
            """,
            (*values, task_id),
        )
        db.commit()

        return cursor.rowcount > 0


def delete_task(task_id: int) -> bool:
    """Delete a checklist item."""

    ensure_roadmap_tables()

    with get_connection() as db:
        cursor = db.execute(
            "DELETE FROM roadmap_tasks WHERE id = ?",
            (task_id,),
        )
        db.commit()

        return cursor.rowcount > 0


# ============================================================
# SEED
# ============================================================

def seed_roadmap(force: bool = False) -> None:
    """
    Seed the initial Krampus RPG roadmap. Runs only when the board is
    empty (or force=True, used by tests to reset to the canonical seed).
    """

    ensure_roadmap_tables()

    with get_connection() as db:
        existing = db.execute(
            "SELECT COUNT(*) AS n FROM roadmap_milestones"
        ).fetchone()

    if int(existing["n"]) > 0 and not force:
        return

    if force:
        with get_connection() as db:
            db.execute("DELETE FROM roadmap_tasks")
            db.execute("DELETE FROM roadmap_cards")
            db.execute("DELETE FROM roadmap_milestones")
            db.commit()

    # (name, description, cards)
    # Each card: (title, status, priority, sprint, assignee, tasks)
    # Tasks: (label, done)
    ROADMAP_SEED: list[tuple[str, str, list[tuple]]] = [
        (
            "Foundation",
            "Core systems the whole game is built on.",
            [
                (
                    "Accounts",
                    STATUS_COMPLETED,
                    PRIORITY_CRITICAL,
                    "Foundation Sprint 1",
                    "Webmaster",
                    [
                        ("Registration & login", True),
                        ("Session handling", True),
                        ("Player profiles", True),
                    ],
                ),
                (
                    "Party System",
                    STATUS_COMPLETED,
                    PRIORITY_CRITICAL,
                    "Foundation Sprint 1",
                    "Webmaster",
                    [
                        ("Party of up to 6", True),
                        ("PC storage (30 per page)", True),
                        ("Move/swap/withdraw", True),
                    ],
                ),
                (
                    "Pokémon Database",
                    STATUS_IN_DEVELOPMENT,
                    PRIORITY_CRITICAL,
                    "Foundation Sprint 2",
                    "Webmaster",
                    [
                        ("Species schema", True),
                        ("Pokémon IDs", True),
                        ("Base stats", True),
                        ("Types", True),
                        ("Abilities", True),
                        ("Evolution data", True),
                        ("Move learnsets", False),
                    ],
                ),
                (
                    "UI",
                    STATUS_TESTING,
                    PRIORITY_HIGH,
                    "Foundation Sprint 2",
                    "Webmaster",
                    [
                        ("PC panel", True),
                        ("Details panel", True),
                        ("Responsive layout", False),
                    ],
                ),
            ],
        ),
        (
            "Pokémon System",
            "Everything about catching, raising and evolving Pokémon.",
            [
                (
                    "Catching",
                    STATUS_TESTING,
                    PRIORITY_HIGH,
                    "Pokémon Sprint 1",
                    "Webmaster",
                    [
                        ("Encounter generation", True),
                        ("Ball types & catch rates", False),
                        ("Catch animation/flow", False),
                    ],
                ),
                (
                    "Evolution",
                    STATUS_COMPLETED,
                    PRIORITY_HIGH,
                    "Foundation Sprint 2",
                    "Webmaster",
                    [
                        ("Level-up evolutions", True),
                        ("Stone evolutions", True),
                        ("Evolution UI in PC panel", True),
                    ],
                ),
                (
                    "Breeding",
                    STATUS_BACKLOG,
                    PRIORITY_LOW,
                    "",
                    "",
                    [],
                ),
                (
                    "Trading",
                    STATUS_BACKLOG,
                    PRIORITY_LOW,
                    "",
                    "",
                    [],
                ),
            ],
        ),
        (
            "Battle System",
            "Turn-based battles, gyms and player combat.",
            [
                (
                    "Battle",
                    STATUS_PLANNED,
                    PRIORITY_CRITICAL,
                    "Battle Sprint 1",
                    "Webmaster",
                    [
                        ("Battle engine design", False),
                        ("Damage formula", False),
                        ("Type effectiveness", False),
                    ],
                ),
                (
                    "PvP",
                    STATUS_BACKLOG,
                    PRIORITY_MEDIUM,
                    "",
                    "",
                    [],
                ),
                (
                    "Gyms",
                    STATUS_BACKLOG,
                    PRIORITY_MEDIUM,
                    "",
                    "",
                    [],
                ),
            ],
        ),
        (
            "World",
            "The world of Krampus: regions, towns and dungeons.",
            [
                (
                    "World Map",
                    STATUS_IN_DEVELOPMENT,
                    PRIORITY_HIGH,
                    "World Sprint 1",
                    "Webmaster",
                    [
                        ("Region data model", True),
                        ("Area encounters", True),
                        ("Map UI", False),
                    ],
                ),
                (
                    "Quests",
                    STATUS_BACKLOG,
                    PRIORITY_MEDIUM,
                    "",
                    "",
                    [],
                ),
                (
                    "Mining",
                    STATUS_BACKLOG,
                    PRIORITY_LOW,
                    "",
                    "",
                    [],
                ),
                (
                    "Achievements",
                    STATUS_BACKLOG,
                    PRIORITY_LOW,
                    "",
                    "",
                    [],
                ),
            ],
        ),
        (
            "Multiplayer",
            "Player interaction: chat, marketplace, leaderboards.",
            [
                (
                    "Marketplace",
                    STATUS_PLANNED,
                    PRIORITY_MEDIUM,
                    "",
                    "",
                    [],
                ),
                (
                    "Chat",
                    STATUS_BACKLOG,
                    PRIORITY_LOW,
                    "",
                    "",
                    [],
                ),
                (
                    "Leaderboards",
                    STATUS_BACKLOG,
                    PRIORITY_LOW,
                    "",
                    "",
                    [],
                ),
            ],
        ),
    ]

    for name, description, cards in ROADMAP_SEED:
        milestone_id = create_milestone(name, description)
        for (
            title,
            status,
            priority,
            sprint,
            assignee,
            tasks,
        ) in cards:
            card_id = create_card(
                milestone_id=milestone_id,
                title=title,
                status=status,
                priority=priority,
                sprint=sprint,
                assignee=assignee,
            )

            for label, done in tasks:
                create_task(card_id, label, done=bool(done))
