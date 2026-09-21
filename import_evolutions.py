from __future__ import annotations

import csv
import sqlite3
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
DATABASE_PATH = ROOT_DIR / "instance" / "krampus_rpg.sqlite3"


def download_evolution_data():
    """Download evolution chain data from PokeAPI."""
    print("Downloading evolution chain data...")

    base_url = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv"

    files = {
        "evolution_chains": "evolution_chains.csv",
        "evolution_triggers": "evolution_triggers.csv",
    }

    data = {}

    for key, filename in files.items():
        url = f"{base_url}/{filename}"
        response = urllib.request.urlopen(url)
        content = response.read().decode('utf-8')
        reader = csv.DictReader(content.split('\n'))
        data[key] = [row for row in reader if row]

    return data


def build_species_lookup(db):
    """Build a lookup from species ID to species identifier."""
    species = db.execute("SELECT id, national_dex FROM pokemon_species").fetchall()
    return {int(row["national_dex"]): row["id"] for row in species if row["national_dex"]}


def build_trigger_lookup(trigger_data):
    """Build a lookup from trigger ID to trigger name."""
    return {int(row["id"]): row["identifier"] for row in trigger_data if row.get("id")}


def parse_evolution_chain(chain_data, species_lookup, trigger_lookup):
    """Parse evolution chain data into evolution rules."""
    evolution_rules = []

    for chain in chain_data:
        chain_id = int(chain.get("id", 0))
        if chain_id == 0:
            continue

        # Parse the chain data
        # The chain_id references the base species
        # We need to extract the evolution steps from the chain

        # For now, let's use a simpler approach
        # We'll look at the pokemon_species table for species that have evolution chains
        pass

    return evolution_rules


def import_evolutions_from_database(db):
    """
    Import evolutions by looking at species data.
    Since we have the full PokeAPI data imported, we can infer evolutions
    from the species information.
    """
    print("Importing evolution data from species catalog...")

    # Get all species with their national dex numbers
    species_data = db.execute("""
        SELECT id, national_dex, name
        FROM pokemon_species
        WHERE national_dex IS NOT NULL
        ORDER BY national_dex
    """).fetchall()

    # Known evolution stages (this is a simplified approach)
    # In a full implementation, this would come from the evolution_chains.csv data
    known_evolutions = []

    # First stage Pokemon (that evolve)
    first_stage = [
        "bulbasaur", "charmander", "squirtle", "caterpie", "weedle", "pidgey",
        "rattata", "spearow", "ekans", "pikachu", "sandshrew", "nidoran-f",
        "nidoran-m", "clefairy", "vulpix", "jigglypuff", "zubat", "oddish",
        "paras", "venonat", "diglett", "meowth", "psyduck", "mankey", "growlithe",
        "poliwag", "abra", "machop", "bellsprout", "tentacool", "geodude",
        "ponyta", "slowpoke", "magnemite", "farfetchd", "doduo", "seel",
        "grimer", "shellder", "gastly", "onix", "drowzee", "hypno", "krabby",
        "exeggcute", "cubone", "hitmonlee", "hitmonchan", "lickitung", "koffing",
        "rhyhorn", "chansey", "tangela", "kangaskhan", "horsea", "goldeen",
        "staryu", "mr-mime", "scyther", "jynx", "electabuzz", "magmar", "pinsir",
        "tauros", "magikarp", "lapras", "eevee", "porygon", "omanyte", "kabuto",
        "aerodactyl", "snorlax", "articuno", "zapdos", "moltres", "dratini",
        "mewtwo", "mew",
    ]

    # Map species to their evolutions (simplified - level-based only)
    evolution_map = {
        "bulbasaur": ("ivysaur", 16),
        "ivysaur": ("venusaur", 32),
        "charmander": ("charmeleon", 16),
        "charmeleon": ("charizard", 36),
        "squirtle": ("wartortle", 16),
        "wartortle": ("blastoise", 36),
        "caterpie": ("metapod", 7),
        "metapod": ("butterfree", 10),
        "weedle": ("kakuna", 7),
        "kakuna": ("beedrill", 10),
        "pidgey": ("pidgeotto", 18),
        "pidgeotto": ("pidgeot", 36),
        "rattata": ("raticate", 20),
        "spearow": ("fearow", 20),
        "ekans": ("arbok", 22),
        "pikachu": ("raichu", None),  # Stone evolution
        "sandshrew": ("sandslash", 22),
        "clefairy": ("clefable", None),  # Moon stone
        "vulpix": ("ninetales", None),  # Fire stone
        "jigglypuff": ("wigglytuff", None),  # Moon stone
        "zubat": ("golbat", 22),
        "oddish": ("gloom", 21),
        "gloom": ("vileplume", None),  # Leaf stone
        "paras": ("parasect", 24),
        "venonat": ("venomoth", 31),
        "diglett": ("dugtrio", 26),
        "meowth": ("persian", 28),
        "psyduck": ("golduck", 33),
        "mankey": ("primeape", 28),
        "growlithe": ("arcanine", None),  # Fire stone
        "poliwag": ("poliwhirl", 25),
        "poliwhirl": ("poliwrath", None),  # Water stone
        "abra": ("kadabra", 16),
        "kadabra": ("alakazam", None),  # Trade
        "machop": ("machoke", 28),
        "machoke": ("machamp", None),  # Trade
        "bellsprout": ("weepinbell", 21),
        "weepinbell": ("victreebel", None),  # Leaf stone
        "tentacool": ("tentacruel", 30),
        "geodude": ("graveler", 25),
        "graveler": ("golem", None),  # Trade
        "ponyta": ("rapidash", 40),
        "slowpoke": ("slowbro", None),  # Trade
        "magnemite": ("magneton", 30),
        "farfetchd": None,
        "doduo": ("dodrio", 31),
        "seel": ("dewgong", 34),
        "grimer": ("muk", 38),
        "shellder": ("cloyster", None),  # Water stone
        "gastly": ("haunter", 25),
        "haunter": ("gengar", None),  # Trade
        "onix": ("steelix", None),  # Trade with metal coat
        "drowzee": ("hypno", 26),
        "krabby": ("kingler", 28),
        "exeggcute": ("exeggutor", None),  # Leaf stone
        "cubone": ("marowak", 28),
        "hitmonlee": None,
        "hitmonchan": None,
        "lickitung": None,
        "koffing": ("weezing", 35),
        "rhyhorn": ("rhydon", 42),
        "chansey": None,
        "tangela": None,
        "kangaskhan": None,
        "horsea": ("seadra", 32),
        "goldeen": ("seaking", 33),
        "staryu": ("starmie", None),  # Water stone
        "mr-mime": None,
        "scyther": ("scizor", None),  # Trade with metal coat
        "jynx": None,
        "electabuzz": ("electivire", None),  # Trade with electrizer
        "magmar": ("magmortar", None),  # Trade with magmarizer
        "pinsir": None,
        "tauros": None,
        "magikarp": ("gyarados", 20),
        "lapras": None,
        "eevee": ("vaporeon", None),  # Water stone (multiple evolutions)
        "porygon": ("porygon2", None),  # Trade with upgrade
        "omanyte": ("omastar", 40),
        "kabuto": ("kabutops", 40),
        "aerodactyl": None,
        "snorlax": None,
        "articuno": None,
        "zapdos": None,
        "moltres": None,
        "dratini": ("dragonair", 30),
        "dragonair": ("dragonite", 55),
        "mewtwo": None,
        "mew": None,
    }

    # Add Eevee's other evolutions
    eevee_evolutions = [
        ("flareon", "fire_stone"),
        ("jolteon", "thunder_stone"),
        ("espeon", None),  # Happiness + day
        ("umbreon", None),  # Happiness + night
        ("leafeon", None),  # Level up near moss rock
        ("glaceon", None),  # Level up near ice rock
        ("sylveon", None),  # Fairy type + affection
    ]

    evolution_rules = []

    for from_species, evolution_data in evolution_map.items():
        if evolution_data is None:
            continue

        to_species, level = evolution_data

        # Check if both species exist in our database
        from_exists = db.execute(
            "SELECT 1 FROM pokemon_species WHERE id = ?",
            (from_species,)
        ).fetchone()

        to_exists = db.execute(
            "SELECT 1 FROM pokemon_species WHERE id = ?",
            (to_species,)
        ).fetchone()

        if not from_exists or not to_exists:
            continue

        if level is not None:
            # Level-based evolution
            evolution_rules.append({
                "from_species": from_species,
                "to_species": to_species,
                "method": "level",
                "condition_level": level,
                "condition_item": None,
                "condition_friendship": None,
                "condition_time": None,
                "condition_location": None,
                "condition_held_item": None,
                "description": f"Level {level} evolution"
            })
        else:
            # Item/other evolution
            # Determine the item based on species
            item_map = {
                "pikachu": "thunder_stone",
                "clefairy": "moon_stone",
                "vulpix": "fire_stone",
                "jigglypuff": "moon_stone",
                "growlithe": "fire_stone",
                "poliwhirl": "water_stone",
                "weepinbell": "leaf_stone",
                "shellder": "water_stone",
                "staryu": "water_stone",
                "exeggcute": "leaf_stone",
                "onix": "metal_coat",
                "gastly": None,  # Trade
                "graveler": None,  # Trade
                "slowpoke": None,  # Trade
                "haunter": None,  # Trade
                "machoke": None,  # Trade
                "kadabra": None,  # Trade,
                "scyther": "metal_coat",
                "electabuzz": "electrizer",
                "magmar": "magmarizer",
                "porygon": "upgrade",
                "dratini": None,  # Level based, handled above
            }

            item = item_map.get(from_species)
            if item is None:
                method = "trade"
            else:
                method = "item"

            evolution_rules.append({
                "from_species": from_species,
                "to_species": to_species,
                "method": method,
                "condition_level": None,
                "condition_item": item,
                "condition_friendship": None,
                "condition_time": None,
                "condition_location": None,
                "condition_held_item": None,
                "description": f"{method.title()} evolution"
            })

    # Add Eevee's multiple evolutions
    eevee_exists = db.execute("SELECT 1 FROM pokemon_species WHERE id = ?", ("eevee",)).fetchone()
    if eevee_exists:
        for to_species, item in eevee_evolutions:
            to_exists = db.execute("SELECT 1 FROM pokemon_species WHERE id = ?", (to_species,)).fetchone()
            if to_exists:
                if item:
                    method = "item"
                else:
                    method = "friendship"  # Simplified for complex evolutions

                evolution_rules.append({
                    "from_species": "eevee",
                    "to_species": to_species,
                    "method": method,
                    "condition_level": None,
                    "condition_item": item,
                    "condition_friendship": None if item else 220,
                    "condition_time": None,
                    "condition_location": None,
                    "condition_held_item": None,
                    "description": f"Eevee {to_species} evolution"
                })

    return evolution_rules


def main():
    print("=" * 60)
    print("EVOLUTION DATA IMPORT")
    print("=" * 60)
    print()

    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row

    try:
        # Clear existing evolution rules
        db.execute("DELETE FROM evolution_rules")
        db.commit()
        print("Cleared existing evolution rules")

        # Import evolutions from species data
        evolution_rules = import_evolutions_from_database(db)

        print(f"Found {len(evolution_rules)} evolution rules")

        # Insert evolution rules
        for rule in evolution_rules:
            db.execute("""
                INSERT INTO evolution_rules
                (from_species, to_species, method, condition_level, condition_item,
                 condition_friendship, condition_time, condition_location, condition_held_item, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rule["from_species"],
                rule["to_species"],
                rule["method"],
                rule["condition_level"],
                rule["condition_item"],
                rule["condition_friendship"],
                rule["condition_time"],
                rule["condition_location"],
                rule["condition_held_item"],
                rule["description"]
            ))

        db.commit()

        print(f"Imported {len(evolution_rules)} evolution rules")

        # Verify
        count = db.execute("SELECT COUNT(*) FROM evolution_rules").fetchone()[0]
        print(f"Total evolution rules in database: {count}")

        print()
        print("=" * 60)
        print("EVOLUTION IMPORT COMPLETE")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
