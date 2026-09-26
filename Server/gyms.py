"""
Krampus RPG Gyms

Gym challenges built on the shared battle engine. Each gym has a
leader with a fixed team; beating a leader awards a badge (stored in
the existing badges table), money, and progression toward gyms that
require earlier badges.

Gym battles run through Server/battle_store.py (server-authoritative
state, party HP synced back on finish) — the same flow as the Battle
Arena, just with a fixed opponent team and a badge on the line.

The admin CRUD (create_gym / update_gym / set_gym_team / delete_gym)
writes Data/gyms.json atomically (temp file + os.replace), mirroring
Server/world_config.py. Reads go straight to disk every call so admin
edits are live immediately with no restart. Validation guarantees bad
data never reaches the live file: species must exist in the catalog,
non-normal variants must resolve, teams are 1-6 members, and levels
are uncapped (>= 1).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any

from .config import DATA_DIR
from .database import get_connection

GYMS_PATH = DATA_DIR / "gyms.json"

# Allowed gym types (display strings, not battle mechanics).
GYM_TYPES = (
    "normal",
    "fire",
    "water",
    "electric",
    "grass",
    "ice",
    "fighting",
    "poison",
    "ground",
    "flying",
    "psychic",
    "bug",
    "rock",
    "ghost",
    "dragon",
    "dark",
    "steel",
    "fairy",
)

MAX_GYM_TEAM_SIZE = 6


# ============================================================
# LOADING
# ============================================================

def load_gyms_document() -> dict[str, Any]:
    """
    Load the raw gyms.json document with normalized wrapper keys.

    Always a fresh copy from disk: admin edits apply on the very next
    request with no restart, and callers can mutate the result and
    pass it back to save_gyms_document().
    """

    if not GYMS_PATH.exists():
        return {"gyms": [], "badges": {}}

    try:
        with GYMS_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        data = {}

    if not isinstance(data, dict):
        data = {}

    if not isinstance(data.get("gyms"), list):
        data["gyms"] = []

    if not isinstance(data.get("badges"), dict):
        data["badges"] = {}

    return data


def save_gyms_document(document: dict[str, Any]) -> None:
    """
    Atomically write the gyms document back to Data/gyms.json
    (temp file + os.replace, mirroring world_config.save_areas_document).
    """

    GYMS_PATH.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        dir=str(GYMS_PATH.parent),
        suffix=".tmp",
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(document, file, indent=2, ensure_ascii=False)
            file.write("\n")

        os.replace(temp_path, GYMS_PATH)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

        raise


def get_gyms() -> list[dict[str, Any]]:
    """All gyms in definition order."""

    gyms = load_gyms_document().get("gyms")
    return [g for g in gyms if isinstance(g, dict)] if isinstance(gyms, list) else []


def get_gym(gym_id: str) -> dict[str, Any] | None:
    wanted = str(gym_id).strip().lower()

    for gym in get_gyms():
        if str(gym.get("id", "")).lower() == wanted:
            return gym

    return None


def get_badge_definitions() -> dict[str, dict[str, Any]]:
    return load_gyms_document().get("badges") or {}


# ============================================================
# VALIDATION HELPERS
# ============================================================

def slugify_gym_id(name: str) -> str:
    """Turn a gym/badge name into a URL-safe snake_case id."""

    slug = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(name).strip().lower(),
    ).strip("_")

    return slug or "gym"


def _parse_level(value: Any, default: int = 1) -> int:
    """
    Levels have no upper cap (a gym leader may sit at 99999999);
    only the >= 1 floor is enforced.
    """

    try:
        level = int(value)
    except (TypeError, ValueError):
        return default

    return max(1, level)


def _parse_required_badges(value: Any) -> int:
    try:
        required = int(value)
    except (TypeError, ValueError):
        return 0

    return max(0, min(8, required))


def _parse_money(value: Any) -> int:
    try:
        money = int(value)
    except (TypeError, ValueError):
        return 0

    return max(0, min(999_999_999, money))


def _clean_variant(value: Any) -> str:
    """Normalize a variant string; empty collapses to "normal"."""

    variant = str(value or "").strip().lower()

    return variant if variant else "normal"


def _clean_species(value: Any, context: str) -> str:
    """Require a species that exists in the live catalog."""

    from .services import get_species

    species_id = str(value or "").strip().lower()

    if not species_id:
        raise ValueError(f"{context} is missing a species.")

    if get_species(species_id) is None:
        raise ValueError(f"{context}: unknown species '{species_id}'.")

    return species_id


def _clean_team(value: Any) -> list[dict[str, Any]]:
    """
    Validate a full gym team: 1-6 members, each with a real species
    and (when non-normal) a resolvable variant. Raises ValueError on
    any problem so nothing is written.
    """

    from .services import get_variant

    if not isinstance(value, list):
        raise ValueError("Team must be a list of members.")

    if not (1 <= len(value) <= MAX_GYM_TEAM_SIZE):
        raise ValueError(
            f"A gym team needs 1 to {MAX_GYM_TEAM_SIZE} members."
        )

    team: list[dict[str, Any]] = []

    for index, member in enumerate(value, start=1):
        if not isinstance(member, dict):
            raise ValueError(f"Team member #{index} is malformed.")

        species_id = _clean_species(member.get("species"), f"Team member #{index}")
        level = _parse_level(member.get("level"), 5)
        variant = _clean_variant(member.get("variant"))

        if variant != "normal" and get_variant(variant) is None:
            raise ValueError(
                f"Team member #{index}: unknown variant "
                f"'{variant}' for {species_id}."
            )

        entry: dict[str, Any] = {
            "species": species_id,
            "level": level,
        }

        if variant != "normal":
            entry["variant"] = variant

        team.append(entry)

    return team


def _badge_definition(
    badge_id: str,
    badge_name: str,
    leader: str,
    gym_name: str,
) -> dict[str, str]:
    return {
        "id": badge_id,
        "name": badge_name,
        "description": (
            f"Awarded for defeating {leader or gym_name}."
        ),
    }


def _find_in_document(
    document: dict[str, Any],
    gym_id: str,
) -> dict[str, Any] | None:
    """
    Look a gym up inside this same document instance — a second
    load_gyms_document() returns a different copy, and mutating that
    one would be silently lost.
    """

    wanted = str(gym_id).strip().lower()

    for candidate in document["gyms"]:
        if str(candidate.get("id", "")).lower() == wanted:
            return candidate

    return None


# ============================================================
# ADMIN CRUD
# ============================================================

def create_gym(
    name: str,
    leader: str = "",
    leader_title: str = "",
    gym_type: str = "normal",
    region: str = "hollyhollow",
    leader_intro: str = "",
    leader_defeat: str = "",
    badge_name: str = "",
    required_badges: int = 0,
    money_reward: int = 0,
    team: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Create a new gym plus its badge definition. Raises ValueError on
    bad input or a duplicate id; nothing is written unless the whole
    gym (including the team) validates.
    """

    name = str(name).strip()

    if not name:
        raise ValueError("Gym name is required.")

    gym_id = slugify_gym_id(name)

    if get_gym(gym_id) is not None:
        raise ValueError(f"A gym with id '{gym_id}' already exists.")

    badge_name = str(badge_name).strip()

    if not badge_name:
        raise ValueError("Badge name is required.")

    badge_id = slugify_gym_id(badge_name)
    cleaned_team = _clean_team(list(team or []))
    leader = str(leader).strip()

    gym: dict[str, Any] = {
        "id": gym_id,
        "name": name,
        "region": str(region).strip() or "hollyhollow",
        "type": gym_type if gym_type in GYM_TYPES else "normal",
        "leader": leader,
        "leader_title": str(leader_title).strip(),
        "leader_intro": str(leader_intro).strip(),
        "leader_defeat": str(leader_defeat).strip(),
        "badge": badge_id,
        "required_badges": _parse_required_badges(required_badges),
        "rewards": {"money": _parse_money(money_reward)},
        "team": cleaned_team,
    }

    document = load_gyms_document()
    document["gyms"].append(gym)
    document["badges"][badge_id] = _badge_definition(
        badge_id,
        badge_name,
        leader,
        name,
    )

    save_gyms_document(document)

    return gym


def update_gym(
    gym_id: str,
    *,
    name: str | None = None,
    leader: str | None = None,
    leader_title: str | None = None,
    gym_type: str | None = None,
    region: str | None = None,
    leader_intro: str | None = None,
    leader_defeat: str | None = None,
    badge_name: str | None = None,
    required_badges: Any = None,
    money_reward: Any = None,
) -> dict[str, Any]:
    """
    Update a gym's display fields (id is immutable). Editing the badge
    name renames the badge definition in place — the badge id stays
    stable so badges players already hold keep resolving.
    """

    document = load_gyms_document()
    gym = _find_in_document(document, gym_id)

    if gym is None:
        raise ValueError("Gym not found.")

    if name is not None:
        name = str(name).strip()

        if not name:
            raise ValueError("Gym name cannot be empty.")

        gym["name"] = name

    if leader is not None:
        gym["leader"] = str(leader).strip()

    if leader_title is not None:
        gym["leader_title"] = str(leader_title).strip()

    if gym_type is not None and gym_type in GYM_TYPES:
        gym["type"] = gym_type

    if region is not None:
        region = str(region).strip()

        if region:
            gym["region"] = region

    if leader_intro is not None:
        gym["leader_intro"] = str(leader_intro).strip()

    if leader_defeat is not None:
        gym["leader_defeat"] = str(leader_defeat).strip()

    if badge_name is not None:
        badge_name = str(badge_name).strip()

        if not badge_name:
            raise ValueError("Badge name cannot be empty.")

        # The id stays stable (player-held badges reference it); only
        # the display name is renamed.
        badge_id = str(gym.get("badge") or "") or slugify_gym_id(badge_name)
        gym["badge"] = badge_id

        previous = dict(document["badges"].get(badge_id) or {})
        previous.update({"id": badge_id, "name": badge_name})

        if not previous.get("description"):
            previous["description"] = _badge_definition(
                badge_id,
                badge_name,
                str(gym.get("leader") or ""),
                str(gym.get("name") or ""),
            )["description"]

        document["badges"][badge_id] = previous

    if required_badges is not None:
        gym["required_badges"] = _parse_required_badges(required_badges)

    if money_reward is not None:
        gym["rewards"] = {
            **(gym.get("rewards") or {}),
            "money": _parse_money(money_reward),
        }

    save_gyms_document(document)

    return gym


def set_gym_team(
    gym_id: str,
    team: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace a gym's whole team with a validated list."""

    document = load_gyms_document()
    gym = _find_in_document(document, gym_id)

    if gym is None:
        raise ValueError("Gym not found.")

    gym["team"] = _clean_team(team)

    save_gyms_document(document)

    return gym


def delete_gym(gym_id: str) -> dict[str, Any] | None:
    """
    Remove a gym. Its badge definition is removed too — unless another
    gym still references the same badge id. Returns the removed gym,
    or None when the id is unknown.
    """

    document = load_gyms_document()
    wanted = str(gym_id).strip().lower()

    for index, candidate in enumerate(document["gyms"]):
        if str(candidate.get("id", "")).lower() == wanted:
            removed = document["gyms"].pop(index)
            badge_id = str(removed.get("badge") or "")

            if badge_id and not any(
                str(g.get("badge") or "") == badge_id
                for g in document["gyms"]
            ):
                document["badges"].pop(badge_id, None)

            save_gyms_document(document)

            return removed

    return None


# ============================================================
# PLAYER BADGE STATE
# ============================================================

def get_player_badges(player_id: int) -> list[str]:
    """Badge ids the player has earned (from the existing badges table)."""

    with get_connection() as db:
        rows = db.execute(
            "SELECT badge_id FROM badges WHERE player_id = ?",
            (player_id,),
        ).fetchall()

    return [str(row["badge_id"]) for row in rows]


def has_badge(player_id: int, badge_id: str) -> bool:
    return badge_id in get_player_badges(player_id)


def gym_available(gym: dict[str, Any], player_id: int) -> tuple[bool, str | None]:
    """
    (available, lock_reason): a gym is challengeable when the player
    holds at least required_badges gym badges.
    """

    required = int(gym.get("required_badges") or 0)

    if required <= 0:
        return True, None

    badge_defs = get_badge_definitions()
    gym_badges_held = sum(
        1
        for badge_id in get_player_badges(player_id)
        if badge_id in badge_defs
    )

    if gym_badges_held >= required:
        return True, None

    return False, (
        f"Requires {required} gym badges "
        f"(you have {gym_badges_held})."
    )


# ============================================================
# CHALLENGE + AWARD
# ============================================================

def start_gym_battle(player_id: int, gym_id: str) -> dict[str, Any]:
    """
    Start a battle against a gym leader's team. Raises ValueError for
    unknown/locked gyms or missing prerequisites.
    """

    from . import battle_store

    gym = get_gym(gym_id)

    if gym is None:
        raise ValueError("Unknown gym.")

    available, reason = gym_available(gym, player_id)

    if not available:
        raise ValueError(reason or "This gym is locked.")

    battle = battle_store.start_trainer_battle(
        player_id,
        list(gym.get("team") or []),
    )

    # Tag the battle context as a gym challenge so awarding only
    # happens for gym battles won.
    _tag_battle_context(
        battle["battle_id"],
        {
            "gym_id": gym["id"],
            "badge": gym.get("badge"),
        },
    )

    return battle


def _tag_battle_context(battle_id: int, extra: dict[str, Any]) -> None:
    """Merge extra keys into the stored battle's context JSON."""

    with get_connection() as db:
        row = db.execute(
            "SELECT context FROM battles WHERE id = ?",
            (battle_id,),
        ).fetchone()

        if row is None:
            return

        try:
            context = json.loads(row["context"] or "{}")
        except json.JSONDecodeError:
            context = {}

        context.update(extra)

        db.execute(
            "UPDATE battles SET context = ? WHERE id = ?",
            (json.dumps(context), battle_id),
        )
        db.commit()


def read_battle_context(battle_id: int) -> dict[str, Any]:
    with get_connection() as db:
        row = db.execute(
            "SELECT context FROM battles WHERE id = ?",
            (battle_id,),
        ).fetchone()

    if row is None:
        return {}

    try:
        return json.loads(row["context"] or "{}")
    except json.JSONDecodeError:
        return {}


def award_gym_victory(player_id: int, battle_id: int) -> dict[str, Any] | None:
    """
    Check a finished gym battle and award badge + money exactly once.
    Returns an award summary, or None when nothing was awarded
    (not a gym battle, not won, or already awarded).
    """

    with get_connection() as db:
        row = db.execute(
            """
            SELECT status, winner, context
            FROM battles
            WHERE id = ? AND player_id = ?
            """,
            (battle_id, player_id),
        ).fetchone()

    if row is None or row["status"] != "finished" or row["winner"] != "player":
        return None

    context = read_battle_context(battle_id)
    gym_id = context.get("gym_id")

    if not gym_id:
        return None

    gym = get_gym(str(gym_id))

    if gym is None:
        return None

    badge_id = str(gym.get("badge") or "")
    awarded_badge = False
    money = int((gym.get("rewards") or {}).get("money") or 0)

    with get_connection() as db:
        # Badge (idempotent via the badges table's uniqueness per player)
        if badge_id:
            existing = db.execute(
                """
                SELECT 1 FROM badges
                WHERE player_id = ? AND badge_id = ?
                """,
                (player_id, badge_id),
            ).fetchone()

            if existing is None:
                db.execute(
                    """
                    INSERT INTO badges (player_id, badge_id)
                    VALUES (?, ?)
                    """,
                    (player_id, badge_id),
                )
                awarded_badge = True

        if money > 0:
            db.execute(
                """
                UPDATE player_progress
                SET money = money + ?
                WHERE player_id = ?
                """,
                (money, player_id),
            )

        db.commit()

    return {
        "gym": gym["name"],
        "leader": gym.get("leader"),
        "badge": badge_id if awarded_badge else None,
        "badge_name": (
            get_badge_definitions().get(badge_id, {}).get("name", badge_id)
            if badge_id
            else None
        ),
        "money": money,
        "leader_defeat": gym.get("leader_defeat"),
    }
