"""
Krampus RPG Profile Ribbon System

Profile ribbons are visual profile decorations.

IMPORTANT:
    Ribbons do NOT grant permissions.

    The existing role/permission system remains authoritative.

Current automatic role ribbons:
    moderator
    administration
    webmaster

Current player-award ribbons:
    beta_tester
    sponsor
    artist

Additional ribbons can be added to RIBBON_DEFINITIONS without
changing the profile template.
"""

from __future__ import annotations

from typing import Any


# ============================================================
# RIBBON DEFINITIONS
# ============================================================

RIBBON_DEFINITIONS: dict[str, dict[str, Any]] = {
    "beta_tester": {
        "id": "beta_tester",
        "name": "Beta Tester",
        "filename": "beta-tester.jpg",
        "source": "badge",
        "badge_id": "beta_tester",
        "order": 10,
    },

    "administration": {
        "id": "administration",
        "name": "Administration",
        "filename": "administration.jpg",
        "source": "role",
        "role": "admin",
        "order": 20,
    },

    "moderator": {
        "id": "moderator",
        "name": "Moderator",
        "filename": "moderator.jpg",
        "source": "role",
        "role": "moderator",
        "order": 30,
    },

    "webmaster": {
        "id": "webmaster",
        "name": "Webmaster",
        "filename": "webmaster.jpg",
        "source": "role",
        "role": "webmaster",
        "order": 40,
    },

    "sponsor": {
        "id": "sponsor",
        "name": "Sponsor",
        "filename": "sponsor.jpg",
        "source": "badge",
        "badge_id": "sponsor",
        "order": 50,
    },

    "artist": {
        "id": "artist",
        "name": "Artist",
        "filename": "artist.jpg",
        "source": "badge",
        "badge_id": "artist",
        "order": 60,
    },
}


# ============================================================
# BADGE ID ALIASES
# ============================================================
#
# These allow the ribbon system to recognize common existing
# naming variations if badges were created manually.
# ============================================================

BADGE_ALIASES: dict[str, set[str]] = {
    "beta_tester": {
        "beta_tester",
        "beta-tester",
        "beta tester",
    },

    "sponsor": {
        "sponsor",
    },

    "artist": {
        "artist",
    },
}


# ============================================================
# ROLE ALIASES
# ============================================================

ROLE_ALIASES: dict[str, set[str]] = {
    "administration": {
        "admin",
        "administration",
    },

    "moderator": {
        "moderator",
    },

    "webmaster": {
        "webmaster",
    },
}


# ============================================================
# RIBBON IMAGE PATH
# ============================================================

RIBBON_STATIC_DIRECTORY = "badges/ribbons"


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_badge_id(
    badge_id: Any,
) -> str:
    """
    Normalize a badge identifier for comparison.
    """

    if badge_id is None:
        return ""

    return str(
        badge_id
    ).strip().lower()


def normalize_role(
    role_name: Any,
) -> str:
    """
    Normalize a role name for comparison.
    """

    if role_name is None:
        return ""

    return str(
        role_name
    ).strip().lower()


# ============================================================
# BADGE MATCHING
# ============================================================

def badge_matches_ribbon(
    badge_id: Any,
    ribbon_id: str,
) -> bool:
    """
    Return True if a stored badge ID activates a ribbon.
    """

    normalized_badge = normalize_badge_id(
        badge_id
    )

    aliases = BADGE_ALIASES.get(
        ribbon_id,
        set(),
    )

    return normalized_badge in {
        normalize_badge_id(alias)
        for alias in aliases
    }


# ============================================================
# ROLE MATCHING
# ============================================================

def role_matches_ribbon(
    role_name: Any,
    ribbon_id: str,
) -> bool:
    """
    Return True if a player's role activates a ribbon.
    """

    normalized_role = normalize_role(
        role_name
    )

    aliases = ROLE_ALIASES.get(
        ribbon_id,
        set(),
    )

    return normalized_role in {
        normalize_role(alias)
        for alias in aliases
    }


# ============================================================
# LOAD PLAYER RIBBONS
# ============================================================

def get_player_ribbons(
    db,
    player_id: int,
) -> list[dict[str, Any]]:
    """
    Build the complete list of ribbons for a player.

    Role ribbons are derived from the player's actual database
    role.

    Award ribbons are derived from the existing badges table.

    Multiple ribbons can be active simultaneously.
    """

    # --------------------------------------------------------
    # Get player's role.
    # --------------------------------------------------------

    player_row = db.execute(
        """
        SELECT
            r.name AS role_name
        FROM players p
        LEFT JOIN roles r
            ON p.role_id = r.id
        WHERE p.id = ?
        """,
        (
            player_id,
        ),
    ).fetchone()

    role_name = ""

    if player_row is not None:
        role_name = player_row["role_name"] or ""

    # --------------------------------------------------------
    # Get player's awarded badges.
    # --------------------------------------------------------

    badge_rows = db.execute(
        """
        SELECT badge_id
        FROM badges
        WHERE player_id = ?
        ORDER BY earned_at ASC, id ASC
        """,
        (
            player_id,
        ),
    ).fetchall()

    badge_ids = {
        normalize_badge_id(
            row["badge_id"]
        )
        for row in badge_rows
        if row["badge_id"]
    }

    # --------------------------------------------------------
    # Build active ribbon list.
    # --------------------------------------------------------

    ribbons: list[dict[str, Any]] = []

    for ribbon_id, definition in RIBBON_DEFINITIONS.items():

        source = definition.get(
            "source"
        )

        active = False

        # ----------------------------------------------------
        # ROLE RIBBON
        # ----------------------------------------------------

        if source == "role":

            active = role_matches_ribbon(
                role_name,
                ribbon_id,
            )

        # ----------------------------------------------------
        # BADGE RIBBON
        # ----------------------------------------------------

        elif source == "badge":

            aliases = BADGE_ALIASES.get(
                ribbon_id,
                set(),
            )

            normalized_aliases = {
                normalize_badge_id(alias)
                for alias in aliases
            }

            active = bool(
                badge_ids.intersection(
                    normalized_aliases
                )
            )

        if not active:
            continue

        ribbons.append(
            {
                "id": definition["id"],
                "name": definition["name"],
                "filename": definition["filename"],
                "static_path": (
                    f"{RIBBON_STATIC_DIRECTORY}/"
                    f"{definition['filename']}"
                ),
                "order": definition.get(
                    "order",
                    999,
                ),
            }
        )

    ribbons.sort(
        key=lambda ribbon: (
            ribbon["order"],
            ribbon["name"].lower(),
        )
    )

    return ribbons