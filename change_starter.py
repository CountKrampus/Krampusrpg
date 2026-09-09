from __future__ import annotations

import json
import sqlite3
from pathlib import Path


# ============================================================
# KRAMPUS RPG - CHANGE STARTER
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent

DATABASE_PATH = (
    PROJECT_DIR
    / "instance"
    / "krampus_rpg.sqlite3"
)

DATA_DIR = (
    PROJECT_DIR
    / "Data"
)

SPRITES_DIR = (
    PROJECT_DIR
    / "Web"
    / "static"
    / "sprites"
)


# ============================================================
# VARIANT FUNCTIONS
# ============================================================

def get_all_variants() -> list[dict[str, str]]:
    """Load the master variant list from Data/variants.json."""

    variants_file = DATA_DIR / "variants.json"

    if not variants_file.exists():
        return []

    try:
        with variants_file.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    variants: list[dict[str, str]] = []

    for item in data:

        if not isinstance(item, dict):
            continue

        variant_id = str(
            item.get("id", "")
        ).strip()

        name = str(
            item.get("name", variant_id)
        ).strip()

        suffix = str(
            item.get("suffix", "")
        ).strip()

        if not variant_id:
            continue

        variants.append(
            {
                "id": variant_id,
                "name": name,
                "suffix": suffix,
            }
        )

    return variants


# ============================================================
# POKEMON FUNCTIONS
# ============================================================

def get_available_pokemon() -> list[str]:
    """
    Find all Pokémon folders in the variants directory.

    These folders are used to determine which Pokémon have
    custom variant sprites available.
    """

    variants_dir = (
        SPRITES_DIR
        / "variants"
    )

    if not variants_dir.exists():
        return []

    return sorted(
        folder.name
        for folder in variants_dir.iterdir()
        if folder.is_dir()
    )


# ============================================================
# SPRITE FUNCTIONS
# ============================================================

def find_sprite(
    pokemon: str,
    variant: str,
) -> Path | None:
    """
    Find the actual game sprite.

    Game naming convention:

        <pokemon>-<variant>.png

    Normal sprites use:

        <pokemon>.png

    Example:

        gastly.png
        gastly-undead.png
        gastly-ruby.png
    """

    pokemon = pokemon.lower().strip()
    variant = variant.lower().strip()

    # --------------------------------------------------------
    # Normal variant
    # --------------------------------------------------------

    if variant == "normal":

        possible_files = [
            SPRITES_DIR / f"{pokemon}.png",
            SPRITES_DIR / f"{pokemon}-normal.png",
        ]

    # --------------------------------------------------------
    # Other variants
    # --------------------------------------------------------

    else:

        possible_files = [
            SPRITES_DIR / f"{pokemon}-{variant}.png"
        ]

    for file in possible_files:

        if file.is_file():
            return file

    return None


def variant_has_sprite(
    pokemon: str,
    variant: str,
) -> bool:
    """Check whether a Pokémon has a sprite for a variant."""

    return find_sprite(
        pokemon,
        variant,
    ) is not None


# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def get_player(
    db: sqlite3.Connection,
) -> sqlite3.Row | None:
    """Get the first player."""

    return db.execute(
        """
        SELECT *
        FROM players
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()


def get_starter(
    db: sqlite3.Connection,
    player_id: int,
) -> sqlite3.Row | None:
    """Get the player's first Pokémon."""

    return db.execute(
        """
        SELECT *
        FROM pokemon
        WHERE owner_id = ?
        ORDER BY id
        LIMIT 1
        """,
        (player_id,),
    ).fetchone()


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print()
    print("=" * 60)
    print(" KRAMPUS RPG - CHANGE STARTER")
    print("=" * 60)
    print()

    # --------------------------------------------------------
    # Check database
    # --------------------------------------------------------

    if not DATABASE_PATH.exists():

        print("ERROR: Database was not found.")
        print()
        print("Expected:")
        print(DATABASE_PATH)
        print()

        input("Press Enter to exit...")
        return

    print("Database found:")
    print(DATABASE_PATH)
    print()

    # --------------------------------------------------------
    # Check variant file
    # --------------------------------------------------------

    variants_file = (
        DATA_DIR
        / "variants.json"
    )

    if not variants_file.exists():

        print("ERROR: Variant file was not found.")
        print()
        print("Expected:")
        print(variants_file)
        print()

        input("Press Enter to exit...")
        return

    # --------------------------------------------------------
    # Check sprite directory
    # --------------------------------------------------------

    if not SPRITES_DIR.exists():

        print("ERROR: Sprite directory was not found.")
        print()
        print("Expected:")
        print(SPRITES_DIR)
        print()

        input("Press Enter to exit...")
        return

    # --------------------------------------------------------
    # Load variants
    # --------------------------------------------------------

    all_variants = get_all_variants()

    if not all_variants:

        print("ERROR: No variants were found.")
        print()
        print("Expected:")
        print(variants_file)
        print()

        input("Press Enter to exit...")
        return

    # --------------------------------------------------------
    # Connect
    # --------------------------------------------------------

    db = sqlite3.connect(
        DATABASE_PATH
    )

    db.row_factory = sqlite3.Row

    try:

        # ----------------------------------------------------
        # Player
        # ----------------------------------------------------

        player = get_player(db)

        if player is None:

            print("ERROR: No players were found.")
            print()

            input("Press Enter to exit...")
            return

        player_id = int(
            player["id"]
        )

        print("PLAYER")
        print("-" * 60)
        print(
            f"Name : {player['display_name']}"
        )
        print(
            f"ID   : {player_id}"
        )
        print()

        # ----------------------------------------------------
        # Current starter
        # ----------------------------------------------------

        starter = get_starter(
            db,
            player_id,
        )

        if starter is None:

            print(
                "ERROR: This player does not have a Pokémon."
            )
            print()

            input("Press Enter to exit...")
            return

        print("CURRENT STARTER")
        print("-" * 60)
        print(
            f"Database ID : {starter['id']}"
        )
        print(
            f"Species ID  : {starter['species_id']}"
        )
        print(
            f"Level       : {starter['level']}"
        )
        print(
            f"Nickname    : "
            f"{starter['nickname'] or '(none)'}"
        )
        print(
            f"Shiny       : "
            f"{'Yes' if starter['shiny'] else 'No'}"
        )
        print(
            f"Variant     : {starter['variant']}"
        )
        print()

        # ----------------------------------------------------
        # Pokémon list
        # ----------------------------------------------------

        pokemon_list = get_available_pokemon()

        if not pokemon_list:

            print(
                "ERROR: No Pokémon folders were found in:"
            )
            print(
                SPRITES_DIR / "variants"
            )
            print()

            input("Press Enter to exit...")
            return

        print("AVAILABLE POKÉMON")
        print("-" * 60)

        for number, pokemon in enumerate(
            pokemon_list,
            start=1,
        ):

            print(
                f"{number:3}. {pokemon}"
            )

        print()
        print(
            "Enter the Pokémon number or type its name."
        )
        print()

        pokemon_input = input(
            "Pokémon: "
        ).strip()

        if not pokemon_input:

            print("Cancelled.")
            return

        # ----------------------------------------------------
        # Pokémon selection
        # ----------------------------------------------------

        if pokemon_input.isdigit():

            number = int(
                pokemon_input
            )

            if (
                number < 1
                or number > len(pokemon_list)
            ):

                print(
                    "ERROR: Invalid Pokémon number."
                )

                input(
                    "Press Enter to exit..."
                )

                return

            pokemon = pokemon_list[
                number - 1
            ]

        else:

            matches = [
                name
                for name in pokemon_list
                if name.lower()
                == pokemon_input.lower()
            ]

            if not matches:

                print()
                print(
                    f"ERROR: Pokémon "
                    f"'{pokemon_input}' was not found."
                )
                print()

                input(
                    "Press Enter to exit..."
                )

                return

            pokemon = matches[0]

        # ----------------------------------------------------
        # Variant list
        # ----------------------------------------------------

        print()
        print(
            f"AVAILABLE VARIANTS FOR "
            f"{pokemon.upper()}"
        )
        print("-" * 60)

        available_variants: list[dict[str, str]] = []

        for variant_data in all_variants:

            variant_id = variant_data["id"]
            variant_name = variant_data["name"]

            sprite = find_sprite(
                pokemon,
                variant_id,
            )

            if sprite is None:
                continue

            available_variants.append(
                variant_data
            )

        if not available_variants:

            print()
            print(
                f"ERROR: No sprites were found for "
                f"{pokemon}."
            )
            print()

            input(
                "Press Enter to exit..."
            )

            return

        for number, variant_data in enumerate(
            available_variants,
            start=1,
        ):

            variant_id = variant_data["id"]
            variant_name = variant_data["name"]

            print(
                f"{number:3}. "
                f"{variant_name} "
                f"({variant_id})"
            )

        print()

        variant_input = input(
            "Variant: "
        ).strip()

        if not variant_input:

            print("Cancelled.")
            return

        # ----------------------------------------------------
        # Variant selection
        # ----------------------------------------------------

        if variant_input.isdigit():

            number = int(
                variant_input
            )

            if (
                number < 1
                or number > len(available_variants)
            ):

                print(
                    "ERROR: Invalid variant number."
                )

                input(
                    "Press Enter to exit..."
                )

                return

            selected_variant = (
                available_variants[number - 1]
            )

        else:

            matches = [
                item
                for item in available_variants
                if (
                    item["id"].lower()
                    == variant_input.lower()
                    or
                    item["name"].lower()
                    == variant_input.lower()
                )
            ]

            if not matches:

                print()
                print(
                    f"ERROR: Variant "
                    f"'{variant_input}' does not exist "
                    f"for {pokemon}."
                )
                print()

                input(
                    "Press Enter to exit..."
                )

                return

            selected_variant = matches[0]

        variant = selected_variant["id"]

        # ----------------------------------------------------
        # Find sprite
        # ----------------------------------------------------

        sprite = find_sprite(
            pokemon,
            variant,
        )

        if sprite is None:

            print()
            print(
                "ERROR: Sprite file was not found."
            )
            print()

            input(
                "Press Enter to exit..."
            )

            return

        # ----------------------------------------------------
        # Confirmation
        # ----------------------------------------------------

        print()
        print("=" * 60)
        print(" CHANGE PREVIEW")
        print("=" * 60)
        print()

        print(
            f"Player       : "
            f"{player['display_name']}"
        )

        print()

        print("CURRENT")
        print(
            f"  Species ID : "
            f"{starter['species_id']}"
        )
        print(
            f"  Variant    : "
            f"{starter['variant']}"
        )

        print()

        print("NEW")
        print(
            f"  Pokémon    : "
            f"{pokemon}"
        )
        print(
            f"  Variant    : "
            f"{selected_variant['name']} "
            f"({variant})"
        )

        print()

        print("SPRITE")
        print(
            f"  {sprite}"
        )

        print()

        print(
            "The existing Pokémon record will be preserved."
        )

        print()

        print("Preserved:")
        print("  • Level")
        print("  • Experience")
        print("  • IVs")
        print("  • EVs")
        print("  • Nature")
        print("  • Gender")
        print("  • Nickname")
        print("  • Shiny status")
        print("  • Pokémon database ID")

        print()

        confirmation = input(
            "Change starter? [y/N]: "
        ).strip().lower()

        if confirmation not in {
            "y",
            "yes",
        }:

            print()
            print(
                "Cancelled. No changes were made."
            )

            return

        # ----------------------------------------------------
        # Update
        # ----------------------------------------------------

        db.execute(
            """
            UPDATE pokemon
            SET
                species_id = ?,
                variant = ?
            WHERE id = ?
              AND owner_id = ?
            """,
            (
                pokemon,
                variant,
                int(starter["id"]),
                player_id,
            ),
        )

        db.commit()

        # ----------------------------------------------------
        # Verify
        # ----------------------------------------------------

        updated = db.execute(
            """
            SELECT *
            FROM pokemon
            WHERE id = ?
              AND owner_id = ?
            """,
            (
                int(starter["id"]),
                player_id,
            ),
        ).fetchone()

        print()
        print("=" * 60)
        print(" SUCCESS")
        print("=" * 60)
        print()

        print(
            f"Starter is now: "
            f"{updated['species_id']} "
            f"({updated['variant']})"
        )

        print()

        print("Sprite:")
        print(sprite)

        print()

        print(
            "No other Pokémon data was changed."
        )

        print()

    except sqlite3.Error as error:

        print()
        print("=" * 60)
        print(" DATABASE ERROR")
        print("=" * 60)
        print()
        print(error)
        print()

    finally:

        db.close()

    input(
        "Press Enter to exit..."
    )


if __name__ == "__main__":
    main()