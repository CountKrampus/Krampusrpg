from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


# ============================================================
# PROJECT PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent


# ============================================================
# IMPORT PROJECT CODE
# ============================================================

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from Server.database import get_connection, init_db, seed_database
from Server.party_storage import (
    MAX_PARTY_SIZE,
    ensure_party_schema,
)
from Server.pc_storage import (
    ensure_pc_schema,
    first_empty_slot,
)


# ============================================================
# DEFAULT STARTERS
# ============================================================

DEFAULT_STARTERS = {
    "bulbasaur": "Bulbasaur",
    "charmander": "Charmander",
    "squirtle": "Squirtle",
}


# ============================================================
# HELPERS
# ============================================================

def normalize_species(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def get_player(
    db: sqlite3.Connection,
    username: str,
):
    return db.execute(
        """
        SELECT *
        FROM players
        WHERE LOWER(username) = LOWER(?)
        LIMIT 1
        """,
        (username,),
    ).fetchone()


def get_pokemon_species(
    db: sqlite3.Connection,
) -> list[str]:
    """
    Read starter species from Data/pokemon.json through the
    existing project data system when possible.

    This function falls back to the original three starters.
    """

    try:
        from Server.services import get_all_species

        species = get_all_species()

        result = []

        for entry in species:
            if not isinstance(entry, dict):
                continue

            species_id = entry.get("id")

            if species_id is None:
                species_id = entry.get("species_id")

            name = entry.get("name")

            if species_id is not None:
                result.append(str(species_id))

            elif name:
                result.append(
                    normalize_species(str(name))
                )

        if result:
            return result

    except Exception:
        pass

    return list(DEFAULT_STARTERS.keys())


def pokemon_exists(
    db: sqlite3.Connection,
    player_id: int,
) -> bool:
    row = db.execute(
        """
        SELECT 1
        FROM pokemon
        WHERE owner_id = ?
        LIMIT 1
        """,
        (player_id,),
    ).fetchone()

    return row is not None


def get_existing_pokemon(
    db: sqlite3.Connection,
    player_id: int,
):
    """
    Return all Pokémon currently owned by the player.

    This intentionally does NOT use pokemon.is_active.
    """

    rows = db.execute(
        """
        SELECT
            id,
            unique_id,
            species_id,
            nickname,
            level,
            experience,
            gender,
            shiny,
            variant,
            nature,
            current_hp,
            max_hp,
            status
        FROM pokemon
        WHERE owner_id = ?
        ORDER BY id
        """,
        (player_id,),
    ).fetchall()

    return rows


def get_party_pokemon(
    db: sqlite3.Connection,
    player_id: int,
):
    return db.execute(
        """
        SELECT
            p.id,
            p.unique_id,
            p.species_id,
            p.nickname,
            p.level,
            p.experience,
            p.gender,
            p.shiny,
            p.variant,
            p.current_hp,
            p.max_hp,
            party.slot
        FROM party
        INNER JOIN pokemon p
            ON p.id = party.pokemon_id
        WHERE party.player_id = ?
        ORDER BY party.slot
        """,
        (player_id,),
    ).fetchall()


def get_pc_pokemon(
    db: sqlite3.Connection,
    player_id: int,
):
    return db.execute(
        """
        SELECT
            p.id,
            p.unique_id,
            p.species_id,
            p.nickname,
            p.level,
            p.experience,
            p.gender,
            p.shiny,
            p.variant,
            p.current_hp,
            p.max_hp,
            pc.page,
            pc.slot
        FROM pc_storage pc
        INNER JOIN pokemon p
            ON p.id = pc.pokemon_id
        WHERE pc.player_id = ?
        ORDER BY pc.page, pc.slot
        """,
        (player_id,),
    ).fetchall()


def get_pokemon_location(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> str:
    party = db.execute(
        """
        SELECT 1
        FROM party
        WHERE player_id = ?
          AND pokemon_id = ?
        LIMIT 1
        """,
        (
            player_id,
            pokemon_id,
        ),
    ).fetchone()

    if party:
        return "party"

    pc = db.execute(
        """
        SELECT 1
        FROM pc_storage
        WHERE player_id = ?
          AND pokemon_id = ?
        LIMIT 1
        """,
        (
            player_id,
            pokemon_id,
        ),
    ).fetchone()

    if pc:
        return "pc"

    return "unassigned"


def add_pokemon_to_party(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> int:
    """
    Add an existing Pokémon to the first open Party slot.

    This is the new Party system.
    """

    current_count = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM party
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()

    if int(current_count["total"]) >= MAX_PARTY_SIZE:
        raise ValueError(
            "The player's party is already full."
        )

    occupied = {
        int(row["slot"])
        for row in db.execute(
            """
            SELECT slot
            FROM party
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchall()
    }

    party_slot = next(
        (
            slot
            for slot in range(
                1,
                MAX_PARTY_SIZE + 1,
            )
            if slot not in occupied
        ),
        None,
    )

    if party_slot is None:
        raise ValueError(
            "No Party slot is available."
        )

    existing = db.execute(
        """
        SELECT 1
        FROM party
        WHERE player_id = ?
          AND pokemon_id = ?
        LIMIT 1
        """,
        (
            player_id,
            pokemon_id,
        ),
    ).fetchone()

    if existing:
        return party_slot

    db.execute(
        """
        INSERT INTO party
        (
            player_id,
            pokemon_id,
            slot
        )
        VALUES (?, ?, ?)
        """,
        (
            player_id,
            pokemon_id,
            party_slot,
        ),
    )

    return party_slot


def add_pokemon_to_pc(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> tuple[int, int]:
    """
    Put an owned Pokémon into the first available PC slot.
    """

    existing = db.execute(
        """
        SELECT page, slot
        FROM pc_storage
        WHERE player_id = ?
          AND pokemon_id = ?
        LIMIT 1
        """,
        (
            player_id,
            pokemon_id,
        ),
    ).fetchone()

    if existing:
        return (
            int(existing["page"]),
            int(existing["slot"]),
        )

    page, slot = first_empty_slot(
        db,
        player_id,
    )

    db.execute(
        """
        INSERT INTO pc_storage
        (
            player_id,
            pokemon_id,
            page,
            slot
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            player_id,
            pokemon_id,
            page,
            slot,
        ),
    )

    return page, slot


def remove_from_party(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> None:
    """
    Move a Pokémon from Party to PC.

    This is deliberately implemented here as a safety measure
    for the recovery script. Nothing is deleted.
    """

    party_row = db.execute(
        """
        SELECT slot
        FROM party
        WHERE player_id = ?
          AND pokemon_id = ?
        LIMIT 1
        """,
        (
            player_id,
            pokemon_id,
        ),
    ).fetchone()

    if party_row is None:
        return

    page, slot = add_pokemon_to_pc(
        db,
        player_id,
        pokemon_id,
    )

    db.execute(
        """
        DELETE FROM party
        WHERE player_id = ?
          AND pokemon_id = ?
        """,
        (
            player_id,
            pokemon_id,
        ),
    )

    print(
        f"  Moved Pokémon #{pokemon_id} "
        f"from Party to PC page {page}, slot {slot}."
    )


def remove_from_pc(
    db: sqlite3.Connection,
    player_id: int,
    pokemon_id: int,
) -> None:
    db.execute(
        """
        DELETE FROM pc_storage
        WHERE player_id = ?
          AND pokemon_id = ?
        """,
        (
            player_id,
            pokemon_id,
        ),
    )


# ============================================================
# CREATE NEW STARTER
# ============================================================

def create_new_starter(
    player_id: int,
    species_id: str,
    level: int = 5,
) -> int:
    """
    Create a completely new starter using the project's
    normal Pokémon creation system.

    The Pokémon is immediately placed in Party.
    """

    from Server.services import create_pokemon

    pokemon = create_pokemon(
        owner_id=player_id,
        species_id=species_id,
        level=level,
        shiny=False,
        variant="normal",
        nickname=None,
    )

    if not pokemon:
        raise RuntimeError(
            "The Pokémon could not be created."
        )

    if isinstance(pokemon, dict):
        pokemon_id = pokemon.get("id")

        if pokemon_id is None:
            pokemon_id = pokemon.get("pokemon_id")
    else:
        pokemon_id = None

    if pokemon_id is None:
        raise RuntimeError(
            "The Pokémon was created but its database ID "
            "could not be determined."
        )

    pokemon_id = int(pokemon_id)

    with get_connection() as db:
        ensure_party_schema(db)
        ensure_pc_schema(db)

        add_pokemon_to_party(
            db,
            player_id,
            pokemon_id,
        )

        db.commit()

    return pokemon_id


# ============================================================
# RECOVER LOST STARTER
# ============================================================

def recover_starter(
    username: str,
    species_id: str,
    level: int = 5,
) -> None:
    """
    Recover a starter for an existing player.

    If the player still has Pokémon, they are preserved.

    If the player has an existing Party, the new starter is added
    to the Party if there is room.

    If the Party is full, the starter is safely placed into PC.
    """

    species_id = normalize_species(
        species_id
    )

    with get_connection() as db:
        ensure_party_schema(db)
        ensure_pc_schema(db)

        player = get_player(
            db,
            username,
        )

        if player is None:
            raise ValueError(
                f"Player '{username}' was not found."
            )

        player_id = int(player["id"])

        print()
        print("=" * 60)
        print("KRAMPUS RPG - STARTER RECOVERY")
        print("=" * 60)
        print()
        print(
            f"Player: {player['username']}"
        )
        print(
            f"Starter: {species_id}"
        )
        print(
            f"Level: {level}"
        )
        print()

        existing = get_existing_pokemon(
            db,
            player_id,
        )

        print(
            f"Existing Pokémon: {len(existing)}"
        )

        party = get_party_pokemon(
            db,
            player_id,
        )

        pc = get_pc_pokemon(
            db,
            player_id,
        )

        print(
            f"Party Pokémon: {len(party)}"
        )
        print(
            f"PC Pokémon: {len(pc)}"
        )
        print()

        # ----------------------------------------------------
        # If the requested species already exists, restore it
        # instead of creating a duplicate.
        # ----------------------------------------------------

        existing_starter = db.execute(
            """
            SELECT id
            FROM pokemon
            WHERE owner_id = ?
              AND LOWER(CAST(species_id AS TEXT)) = ?
            ORDER BY id
            LIMIT 1
            """,
            (
                player_id,
                species_id,
            ),
        ).fetchone()

        if existing_starter is not None:
            pokemon_id = int(
                existing_starter["id"]
            )

            location = get_pokemon_location(
                db,
                player_id,
                pokemon_id,
            )

            print(
                f"Existing {species_id} found "
                f"(Pokémon #{pokemon_id})."
            )
            print(
                f"Current location: {location}"
            )

            if location == "party":
                print(
                    "Starter is already in the Party."
                )

                db.commit()

                print()
                print("Nothing needed to be changed.")
                print()

                return

            if location == "pc":
                remove_from_pc(
                    db,
                    player_id,
                    pokemon_id,
                )

                try:
                    party_slot = add_pokemon_to_party(
                        db,
                        player_id,
                        pokemon_id,
                    )

                    db.commit()

                    print(
                        f"Restored existing starter "
                        f"to Party slot {party_slot}."
                    )

                    print()
                    print("Starter recovery complete.")
                    print()

                    return

                except ValueError:
                    # Party is full. Put it back in PC.
                    add_pokemon_to_pc(
                        db,
                        player_id,
                        pokemon_id,
                    )

                    db.commit()

                    print(
                        "Party is full."
                    )
                    print(
                        "Existing starter was kept safely "
                        "in the PC."
                    )

                    print()
                    print("Recovery complete.")
                    print()

                    return

            if location == "unassigned":
                try:
                    party_slot = add_pokemon_to_party(
                        db,
                        player_id,
                        pokemon_id,
                    )

                    db.commit()

                    print(
                        f"Restored existing starter "
                        f"to Party slot {party_slot}."
                    )

                    print()
                    print("Starter recovery complete.")
                    print()

                    return

                except ValueError:
                    page, slot = add_pokemon_to_pc(
                        db,
                        player_id,
                        pokemon_id,
                    )

                    db.commit()

                    print(
                        "Party is full."
                    )
                    print(
                        f"Starter placed in PC "
                        f"page {page}, slot {slot}."
                    )

                    print()
                    print("Recovery complete.")
                    print()

                    return

        # ----------------------------------------------------
        # No existing starter was found.
        # Create a new one.
        # ----------------------------------------------------

        print(
            "No existing starter was found."
        )
        print(
            "Creating a new starter..."
        )
        print()

        from Server.services import create_pokemon

        pokemon = create_pokemon(
            owner_id=player_id,
            species_id=species_id,
            level=level,
            shiny=False,
            variant="normal",
            nickname=None,
        )

        if not pokemon:
            raise RuntimeError(
                "Starter creation failed."
            )

        pokemon_id = None

        if isinstance(pokemon, dict):
            pokemon_id = pokemon.get("id")

            if pokemon_id is None:
                pokemon_id = pokemon.get(
                    "pokemon_id"
                )

        if pokemon_id is None:
            # Safely locate the newly-created Pokémon.
            row = db.execute(
                """
                SELECT id
                FROM pokemon
                WHERE owner_id = ?
                  AND CAST(species_id AS TEXT) = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    player_id,
                    species_id,
                ),
            ).fetchone()

            if row is None:
                db.rollback()

                raise RuntimeError(
                    "Starter was created but could not "
                    "be located."
                )

            pokemon_id = int(
                row["id"]
            )

        pokemon_id = int(
            pokemon_id
        )

        # ----------------------------------------------------
        # Put starter into Party if possible.
        # Otherwise PC.
        # ----------------------------------------------------

        try:
            party_slot = add_pokemon_to_party(
                db,
                player_id,
                pokemon_id,
            )

            db.commit()

            print(
                f"New starter created: "
                f"{species_id}"
            )
            print(
                f"Pokémon ID: {pokemon_id}"
            )
            print(
                f"Party slot: {party_slot}"
            )

        except ValueError:
            page, slot = add_pokemon_to_pc(
                db,
                player_id,
                pokemon_id,
            )

            db.commit()

            print(
                f"New starter created: "
                f"{species_id}"
            )
            print(
                f"Pokémon ID: {pokemon_id}"
            )
            print(
                f"Party is full."
            )
            print(
                f"Starter placed in PC "
                f"page {page}, slot {slot}."
            )

        print()
        print("Starter recovery complete.")
        print()


# ============================================================
# SHOW PLAYER STORAGE
# ============================================================

def show_player(
    username: str,
) -> None:
    with get_connection() as db:
        ensure_party_schema(db)
        ensure_pc_schema(db)

        player = get_player(
            db,
            username,
        )

        if player is None:
            raise ValueError(
                f"Player '{username}' was not found."
            )

        player_id = int(player["id"])

        party = get_party_pokemon(
            db,
            player_id,
        )

        pc = get_pc_pokemon(
            db,
            player_id,
        )

        all_pokemon = get_existing_pokemon(
            db,
            player_id,
        )

        print()
        print("=" * 60)
        print("PLAYER STORAGE")
        print("=" * 60)
        print()
        print(
            f"Player: {player['username']}"
        )
        print(
            f"Total Pokémon: {len(all_pokemon)}"
        )
        print()

        print("PARTY")
        print("-" * 60)

        if not party:
            print(
                "  Party is empty."
            )
        else:
            for pokemon in party:
                print(
                    f"  Slot {pokemon['slot']}: "
                    f"#{pokemon['id']} "
                    f"{pokemon['species_id']} "
                    f"Lv.{pokemon['level']}"
                )

        print()

        print("PC")
        print("-" * 60)

        if not pc:
            print(
                "  PC is empty."
            )
        else:
            for pokemon in pc:
                print(
                    f"  Page {pokemon['page']} "
                    f"Slot {pokemon['slot']}: "
                    f"#{pokemon['id']} "
                    f"{pokemon['species_id']} "
                    f"Lv.{pokemon['level']}"
                )

        print()


# ============================================================
# COMMAND LINE
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Krampus RPG starter recovery/change utility."
        )
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    recover_parser = subparsers.add_parser(
        "recover",
        help="Recover or create a starter.",
    )

    recover_parser.add_argument(
        "username",
        help="Player username.",
    )

    recover_parser.add_argument(
        "starter",
        choices=sorted(
            DEFAULT_STARTERS.keys()
        ),
        help="Starter Pokémon.",
    )

    recover_parser.add_argument(
        "--level",
        type=int,
        default=5,
        help="Starter level. Default: 5.",
    )

    show_parser = subparsers.add_parser(
        "show",
        help="Show the player's Party and PC.",
    )

    show_parser.add_argument(
        "username",
        help="Player username.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        # Make sure the current database structure exists.
        init_db()
        seed_database()

        if args.command == "recover":
            recover_starter(
                username=args.username,
                species_id=args.starter,
                level=max(
                    1,
                    int(args.level),
                ),
            )

        elif args.command == "show":
            show_player(
                username=args.username,
            )

        return 0

    except KeyboardInterrupt:
        print()
        print(
            "Operation cancelled."
        )
        return 1

    except Exception as exc:
        print()
        print(
            "ERROR:"
        )
        print(
            str(exc)
        )
        print()

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )