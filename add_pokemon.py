from __future__ import annotations

import argparse
import secrets
import sqlite3
import sys
from pathlib import Path


# =============================================================================
# PROJECT PATH
# =============================================================================

ROOT_DIR = Path(__file__).resolve().parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from Server.database import get_connection
from Server.party_storage import add_to_party
from Server.pc_storage import deposit_pokemon


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_LEVEL = 5
DEFAULT_VARIANT = "normal"

VALID_GENDERS = {
    "male",
    "female",
    "genderless",
}


# =============================================================================
# HELPERS
# =============================================================================

def generate_unique_id() -> str:
    """Generate a unique Pokémon identifier."""
    return secrets.token_hex(12)


def find_player(
    db: sqlite3.Connection,
    username: str,
) -> sqlite3.Row | None:
    """Find a player by username."""
    return db.execute(
        """
        SELECT id, username
        FROM players
        WHERE username = ?
        LIMIT 1
        """,
        (username,),
    ).fetchone()


def find_species(
    db: sqlite3.Connection,
    value: str,
) -> sqlite3.Row | None:
    """
    Find a Pokémon species by:

        - numeric species ID
        - exact name
        - exact National Dex number
    """

    # Numeric lookup.
    if value.isdigit():
        number = int(value)

        row = db.execute(
            """
            SELECT *
            FROM pokemon_species
            WHERE id = ?
               OR national_dex = ?
            LIMIT 1
            """,
            (
                number,
                number,
            ),
        ).fetchone()

        if row is not None:
            return row

    # Name lookup.
    return db.execute(
        """
        SELECT *
        FROM pokemon_species
        WHERE LOWER(name) = LOWER(?)
        LIMIT 1
        """,
        (value,),
    ).fetchone()


def get_base_hp(
    species: sqlite3.Row,
) -> int:
    """Read the species base HP from the catalog."""

    try:
        return max(
            1,
            int(species["base_hp"]),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        return 50


def calculate_max_hp(
    species: sqlite3.Row,
    level: int,
) -> int:
    """
    Krampus RPG HP calculation.

    No IVs, EVs, or Nature.
    """

    base_hp = get_base_hp(species)

    return max(
        1,
        ((2 * base_hp * level) // 100)
        + level
        + 10,
    )


def validate_gender(
    gender: str | None,
) -> str | None:
    if gender is None:
        return None

    gender = gender.lower()

    if gender not in VALID_GENDERS:
        raise ValueError(
            "Gender must be male, female, or genderless."
        )

    return gender


def create_pokemon(
    username: str,
    species_value: str,
    level: int,
    nickname: str | None,
    gender: str | None,
    shiny: bool,
    variant: str,
) -> tuple[int, int]:
    """
    Create a Pokémon for a player.

    Returns:
        (player_id, pokemon_id)
    """

    if level < 1:
        raise ValueError(
            "Level must be at least 1."
        )

    if level > 100:
        raise ValueError(
            "Level cannot exceed 100."
        )

    gender = validate_gender(gender)

    variant = (
        variant.strip()
        if variant
        else DEFAULT_VARIANT
    )

    with get_connection() as db:
        # ---------------------------------------------------------------------
        # Player
        # ---------------------------------------------------------------------

        player = find_player(
            db,
            username,
        )

        if player is None:
            raise ValueError(
                f"Player '{username}' does not exist."
            )

        player_id = int(
            player["id"]
        )

        # ---------------------------------------------------------------------
        # Species
        # ---------------------------------------------------------------------

        species = find_species(
            db,
            species_value,
        )

        if species is None:
            raise ValueError(
                f"Pokémon species '{species_value}' was not found."
            )

        species_id = int(
            species["id"]
        )

        species_name = str(
            species["name"]
        )

        # ---------------------------------------------------------------------
        # Gender
        # ---------------------------------------------------------------------

        if gender is None:
            try:
                gender_rate = int(
                    species["gender_rate"]
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                gender_rate = -1

            if gender_rate == -1:
                gender = "genderless"

            elif gender_rate == 0:
                gender = "male"

            elif gender_rate == 8:
                gender = "female"

            else:
                # Simple 50/50 fallback for the admin utility.
                gender = (
                    "male"
                    if secrets.randbelow(2) == 0
                    else "female"
                )

        # ---------------------------------------------------------------------
        # HP
        # ---------------------------------------------------------------------

        max_hp = calculate_max_hp(
            species,
            level,
        )

        # ---------------------------------------------------------------------
        # Create Pokémon
        # ---------------------------------------------------------------------

        unique_id = generate_unique_id()

        cursor = db.execute(
            """
            INSERT INTO pokemon
            (
                unique_id,
                owner_id,
                species_id,
                nickname,
                level,
                experience,
                gender,
                shiny,
                variant,
                current_hp,
                max_hp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unique_id,
                player_id,
                species_id,
                nickname,
                level,
                0,
                gender,
                1 if shiny else 0,
                variant,
                max_hp,
                max_hp,
            ),
        )

        pokemon_id = int(
            cursor.lastrowid
        )

        db.commit()

        return player_id, pokemon_id, species_name


# =============================================================================
# STORAGE
# =============================================================================

def put_pokemon_in_party(
    player_id: int,
    pokemon_id: int,
) -> dict:
    """Put the Pokémon into the first available Party slot."""

    return add_to_party(
        player_id,
        pokemon_id,
    )


def put_pokemon_in_pc(
    player_id: int,
    pokemon_id: int,
) -> dict:
    """Put the Pokémon into the first available PC slot."""

    return deposit_pokemon(
        player_id,
        pokemon_id,
    )


# =============================================================================
# COMMAND
# =============================================================================

def add_pokemon(
    username: str,
    species: str,
    destination: str,
    level: int,
    nickname: str | None,
    gender: str | None,
    shiny: bool,
    variant: str,
) -> None:

    player_id, pokemon_id, species_name = create_pokemon(
        username=username,
        species_value=species,
        level=level,
        nickname=nickname,
        gender=gender,
        shiny=shiny,
        variant=variant,
    )

    try:
        if destination == "party":
            result = put_pokemon_in_party(
                player_id,
                pokemon_id,
            )

            slot = result.get(
                "slot",
                "?",
            )

            print()
            print("Pokémon added successfully.")
            print(f"Player:   {username}")
            print(f"Pokémon:  {species_name}")
            print(f"ID:       {pokemon_id}")
            print(f"Level:    {level}")
            print(f"Variant:  {variant}")
            print(f"Shiny:    {'Yes' if shiny else 'No'}")
            print(f"Gender:   {gender}")
            print(f"Party:    Slot {slot}")
            print()

        else:
            result = put_pokemon_in_pc(
                player_id,
                pokemon_id,
            )

            page = result.get(
                "page",
                "?",
            )

            slot = result.get(
                "slot",
                "?",
            )

            print()
            print("Pokémon added successfully.")
            print(f"Player:   {username}")
            print(f"Pokémon:  {species_name}")
            print(f"ID:       {pokemon_id}")
            print(f"Level:    {level}")
            print(f"Variant:  {variant}")
            print(f"Shiny:    {'Yes' if shiny else 'No'}")
            print(f"Gender:   {gender}")
            print(f"PC:       Page {page}, Slot {slot}")
            print()

    except Exception:
        # If storage placement fails after Pokémon creation,
        # remove the newly-created Pokémon so we don't leave
        # an unassigned Pokémon in the database.
        with get_connection() as db:
            db.execute(
                """
                DELETE FROM pokemon
                WHERE id = ?
                  AND owner_id = ?
                """,
                (
                    pokemon_id,
                    player_id,
                ),
            )

            db.commit()

        raise


# =============================================================================
# ARGUMENT PARSER
# =============================================================================

def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Add a Pokémon directly to a Krampus RPG "
            "player's Party or PC."
        )
    )

    parser.add_argument(
        "username",
        help="Player username.",
    )

    parser.add_argument(
        "pokemon",
        help=(
            "Pokémon species name or species ID."
        ),
    )

    parser.add_argument(
        "destination",
        choices=(
            "party",
            "pc",
            "box",
        ),
        help=(
            "Where to place the Pokémon: "
            "party or pc/box."
        ),
    )

    parser.add_argument(
        "--level",
        type=int,
        default=DEFAULT_LEVEL,
        help=f"Pokémon level. Default: {DEFAULT_LEVEL}",
    )

    parser.add_argument(
        "--nickname",
        default=None,
        help="Optional Pokémon nickname.",
    )

    parser.add_argument(
        "--gender",
        choices=(
            "male",
            "female",
            "genderless",
        ),
        default=None,
        help="Optional gender.",
    )

    parser.add_argument(
        "--shiny",
        action="store_true",
        help="Create the Pokémon as shiny.",
    )

    parser.add_argument(
        "--variant",
        default=DEFAULT_VARIANT,
        help=(
            "Krampus variant. "
            f"Default: {DEFAULT_VARIANT}"
        ),
    )

    return parser


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:

    parser = build_parser()

    args = parser.parse_args()

    destination = args.destination

    if destination == "box":
        destination = "pc"

    try:
        add_pokemon(
            username=args.username,
            species=args.pokemon,
            destination=destination,
            level=args.level,
            nickname=args.nickname,
            gender=args.gender,
            shiny=args.shiny,
            variant=args.variant,
        )

        return 0

    except PermissionError as exc:
        print()
        print(f"ERROR: {exc}")
        print()
        return 1

    except ValueError as exc:
        print()
        print(f"ERROR: {exc}")
        print()
        return 1

    except sqlite3.IntegrityError as exc:
        print()
        print(
            "ERROR: Database rejected the Pokémon."
        )
        print(exc)
        print()
        return 1

    except Exception as exc:
        print()
        print(
            "ERROR: Unexpected error while adding Pokémon."
        )
        print(exc)
        print()
        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )