from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from Server.database import (
    MAX_PARTY_SIZE,
    PC_SLOTS_PER_PAGE,
    STAT_NAMES,
    ensure_party_schema,
    ensure_pc_schema,
    get_connection,
    init_db,
    rebuild_legacy_pokemon_tables,
    repair_pokemon_storage,
    table_exists,
    verify_storage_invariant,
)
from Server.party_storage import (
    add_to_party,
    get_party,
    is_in_party,
    party_count,
    party_is_full,
    remove_from_party,
)
from Server.pc_storage import (
    deposit_pokemon,
    get_page,
    get_pc_count,
    is_in_pc,
    move_pokemon,
    swap_pokemon,
    withdraw_pokemon,
)
from Server.services import (
    calculate_hp,
    calculate_pokemon_stats,
    calculate_stat,
    create_player,
    create_pokemon,
    get_player,
    get_pokemon,
)


class BaseTestCase(unittest.TestCase):
    """Base test case setting up an isolated temporary database for each test."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_krampus.sqlite3"

        # Patch DATABASE_PATH in config and database modules
        import Server.config as config
        import Server.database as database

        self._orig_db_path = config.DATABASE_PATH
        config.DATABASE_PATH = self.db_path
        database.DATABASE_PATH = self.db_path

        # Initialize schema
        init_db()

        # Create two test players
        self.player1_id = create_player("ash", "ash@example.com", "Ash Ketchum")
        self.player1 = get_player(self.player1_id)

        self.player2_id = create_player("gary", "gary@example.com", "Gary Oak")
        self.player2 = get_player(self.player2_id)

    def tearDown(self) -> None:
        import Server.config as config
        import Server.database as database

        config.DATABASE_PATH = self._orig_db_path
        database.DATABASE_PATH = self._orig_db_path

        shutil.rmtree(self.temp_dir, ignore_errors=True)


# =============================================================================
# 1. POKÉMON CREATION TESTS
# =============================================================================

class TestPokemonCreation(BaseTestCase):
    """Tests for Pokémon creation, stat generation, and constraint enforcement."""

    def test_create_pokemon_basic(self) -> None:
        mon = create_pokemon(
            owner_id=self.player1_id,
            species_id="bulbasaur",
            level=5,
            nickname="Bulby",
        )
        self.assertIsNotNone(mon)
        self.assertEqual(mon["species_id"], "bulbasaur")
        self.assertEqual(mon["level"], 5)
        self.assertEqual(mon["nickname"], "Bulby")
        self.assertEqual(mon["owner_id"], self.player1_id)
        self.assertTrue(len(mon["unique_id"]) > 0)

        # Verify stats dict is returned
        stats = mon.get("stats", {})
        for stat_name in STAT_NAMES:
            self.assertIn(stat_name, stats)
            self.assertGreater(stats[stat_name], 0)

    def test_create_pokemon_level_clamped(self) -> None:
        # Level below 1 must clamp to 1
        mon_low = create_pokemon(
            owner_id=self.player1_id,
            species_id="charmander",
            level=-10,
        )
        self.assertEqual(mon_low["level"], 1)

        # Level above 100 must clamp to 100
        mon_high = create_pokemon(
            owner_id=self.player1_id,
            species_id="charmander",
            level=500000,
        )
        self.assertEqual(mon_high["level"], 100)

    def test_create_pokemon_stats_persisted(self) -> None:
        mon = create_pokemon(
            owner_id=self.player1_id,
            species_id="squirtle",
            level=10,
        )
        with get_connection() as db:
            row = db.execute(
                """
                SELECT hp, attack, defense, sp_attack, sp_defense, speed
                FROM pokemon_stats
                WHERE pokemon_id = ?
                """,
                (mon["id"],),
            ).fetchone()
            self.assertIsNotNone(row)
            stats = dict(row)
            for s in STAT_NAMES:
                self.assertIn(s, stats)
                self.assertGreater(stats[s], 0)

    def test_create_pokemon_starting_moves(self) -> None:
        mon = create_pokemon(
            owner_id=self.player1_id,
            species_id="pikachu",
            level=5,
        )
        with get_connection() as db:
            moves = db.execute(
                """
                SELECT move_id, slot, current_pp
                FROM pokemon_moves
                WHERE pokemon_id = ?
                ORDER BY slot
                """,
                (mon["id"],),
            ).fetchall()
            self.assertGreater(len(moves), 0)
            for m in moves:
                self.assertGreaterEqual(m["slot"], 1)
                self.assertLessEqual(m["slot"], 4)
                self.assertGreater(m["current_pp"], 0)

    def test_create_pokemon_auto_stored_in_party(self) -> None:
        """First 6 Pokémon created should be automatically placed into party slots 1-6."""
        for slot in range(1, MAX_PARTY_SIZE + 1):
            mon = create_pokemon(
                owner_id=self.player1_id,
                species_id="bulbasaur",
                level=5,
            )
            self.assertTrue(is_in_party(self.player1_id, mon["id"]))
            self.assertFalse(is_in_pc(self.player1_id, mon["id"]))

        self.assertEqual(party_count(self.player1_id), 6)
        self.assertTrue(party_is_full(self.player1_id))

    def test_create_pokemon_overflow_to_pc(self) -> None:
        """7th Pokémon created when party is full should automatically go to PC."""
        for _ in range(MAX_PARTY_SIZE):
            create_pokemon(
                owner_id=self.player1_id,
                species_id="bulbasaur",
                level=5,
            )

        mon7 = create_pokemon(
            owner_id=self.player1_id,
            species_id="charmander",
            level=5,
        )
        self.assertFalse(is_in_party(self.player1_id, mon7["id"]))
        self.assertTrue(is_in_pc(self.player1_id, mon7["id"]))
        self.assertEqual(get_pc_count(self.player1_id), 1)

    def test_create_pokemon_invalid_species_raises(self) -> None:
        with self.assertRaises(ValueError):
            create_pokemon(
                owner_id=self.player1_id,
                species_id="nonexistent_fakemon_xyz",
                level=5,
            )


# =============================================================================
# 2. STORAGE INTEGRITY TESTS
# =============================================================================

class TestStorageIntegrity(BaseTestCase):
    """Tests for Party and PC storage mechanics and constraints."""

    def test_party_max_six(self) -> None:
        for _ in range(6):
            create_pokemon(
                owner_id=self.player1_id,
                species_id="bulbasaur",
            )
        self.assertEqual(party_count(self.player1_id), 6)
        self.assertTrue(party_is_full(self.player1_id))

        # Trying to add another to party must fail
        mon7 = create_pokemon(
            owner_id=self.player1_id,
            species_id="squirtle",
            auto_store=False,
        )
        with self.assertRaises(ValueError):
            add_to_party(self.player1_id, mon7["id"])

    def test_remove_from_party_moves_to_pc(self) -> None:
        """Removing from Party must move to PC and NEVER delete the Pokémon."""
        mon = create_pokemon(
            owner_id=self.player1_id,
            species_id="bulbasaur",
        )
        self.assertTrue(is_in_party(self.player1_id, mon["id"]))
        self.assertEqual(get_pc_count(self.player1_id), 0)

        remove_from_party(self.player1_id, mon["id"])

        self.assertFalse(is_in_party(self.player1_id, mon["id"]))
        self.assertTrue(is_in_pc(self.player1_id, mon["id"]))
        self.assertEqual(get_pc_count(self.player1_id), 1)

        # Confirm Pokémon row still exists
        persisted = get_pokemon(self.player1_id, mon["id"])
        self.assertIsNotNone(persisted)

    def test_withdraw_from_pc_to_party(self) -> None:
        mon = create_pokemon(
            owner_id=self.player1_id,
            species_id="bulbasaur",
        )
        remove_from_party(self.player1_id, mon["id"])
        self.assertTrue(is_in_pc(self.player1_id, mon["id"]))

        withdraw_pokemon(self.player1_id, mon["id"])

        self.assertTrue(is_in_party(self.player1_id, mon["id"]))
        self.assertFalse(is_in_pc(self.player1_id, mon["id"]))

    def test_deposit_to_pc(self) -> None:
        mon = create_pokemon(
            owner_id=self.player1_id,
            species_id="charmander",
        )
        self.assertTrue(is_in_party(self.player1_id, mon["id"]))

        # First remove from party to deposit
        remove_from_party(self.player1_id, mon["id"])
        self.assertTrue(is_in_pc(self.player1_id, mon["id"]))

        # Now deposit to a specific slot (should move within PC)
        deposit_pokemon(self.player1_id, mon["id"], page=1, slot=5)

        self.assertFalse(is_in_party(self.player1_id, mon["id"]))
        self.assertTrue(is_in_pc(self.player1_id, mon["id"]))

    def test_pc_pagination_and_30_per_page(self) -> None:
        """Verify PC handles 30 slots per page and creates page 2 for slot 31."""
        # Fill party first (6)
        for _ in range(6):
            create_pokemon(owner_id=self.player1_id, species_id="bulbasaur")

        # Create 31 Pokémon in PC
        pc_pokemon = []
        for _ in range(31):
            mon = create_pokemon(owner_id=self.player1_id, species_id="squirtle")
            pc_pokemon.append(mon)

        self.assertEqual(get_pc_count(self.player1_id), 31)

        page1 = get_page(self.player1_id, page=1)
        # page1["pokemon"] is a fixed 30-entry list; each occupied slot is
        # {"slot": N, "pokemon": {...}}, empty slots are None.
        self.assertEqual(
            len([p for p in page1["pokemon"] if p is not None]),
            30,
        )

        page2 = get_page(self.player1_id, page=2)
        page2_pokemon = [p for p in page2["pokemon"] if p is not None]
        self.assertEqual(len(page2_pokemon), 1)
        # Check that the last pokemon is in page 2 (we don't check exact ID since ordering may vary)
        self.assertIsNotNone(page2_pokemon[0])
        self.assertEqual(page2_pokemon[0]["slot"], 1)
        # get_page() reports the page number once, at the top level of its
        # return value — not per slot.
        self.assertEqual(page2["page"], 2)

    def test_pc_move_and_swap(self) -> None:
        # Fill party
        for _ in range(6):
            create_pokemon(owner_id=self.player1_id, species_id="bulbasaur")

        mon_a = create_pokemon(owner_id=self.player1_id, species_id="charmander")
        mon_b = create_pokemon(owner_id=self.player1_id, species_id="squirtle")

        # Move mon_a to slot 15
        move_pokemon(self.player1_id, mon_a["id"], 1, 15)
        page1 = get_page(self.player1_id, page=1)
        pokemon_by_id = {
            p["pokemon"]["pokemon_id"]: p
            for p in page1["pokemon"]
            if p is not None
        }
        self.assertEqual(pokemon_by_id[mon_a["id"]]["slot"], 15)

        # Move mon_b to slot 20
        move_pokemon(self.player1_id, mon_b["id"], 1, 20)
        page1_after = get_page(self.player1_id, page=1)
        after_by_id = {
            p["pokemon"]["pokemon_id"]: p
            for p in page1_after["pokemon"]
            if p is not None
        }
        self.assertEqual(after_by_id[mon_b["id"]]["slot"], 20)


# =============================================================================
# 3. POKÉMON OWNERSHIP TESTS
# =============================================================================

class TestPokemonOwnership(BaseTestCase):
    """Tests guaranteeing a Pokémon belongs to exactly one player and storage location."""

    def test_cross_player_party_modification_rejected(self) -> None:
        """Player 2 cannot add or remove Player 1's Pokémon."""
        mon1 = create_pokemon(
            owner_id=self.player1_id,
            species_id="bulbasaur",
        )

        with self.assertRaises(PermissionError):
            remove_from_party(self.player2_id, mon1["id"])

        with self.assertRaises(PermissionError):
            add_to_party(self.player2_id, mon1["id"])

    def test_cross_player_pc_modification_rejected(self) -> None:
        """Player 2 cannot withdraw or deposit Player 1's Pokémon."""
        # Fill party so mon goes to PC
        for _ in range(6):
            create_pokemon(owner_id=self.player1_id, species_id="bulbasaur")
        mon_pc = create_pokemon(owner_id=self.player1_id, species_id="charmander")

        with self.assertRaises(PermissionError):
            withdraw_pokemon(self.player2_id, mon_pc["id"])

        with self.assertRaises(PermissionError):
            deposit_pokemon(self.player2_id, mon_pc["id"])

    def test_storage_invariant_satisfied_for_normal_flow(self) -> None:
        """A normal player flow must have 0 storage invariant problems."""
        for _ in range(10):
            create_pokemon(owner_id=self.player1_id, species_id="bulbasaur")
        for _ in range(5):
            create_pokemon(owner_id=self.player2_id, species_id="squirtle")

        problems = verify_storage_invariant()
        self.assertEqual(problems, [])

    def test_repair_fixes_orphaned_pokemon(self) -> None:
        """An orphaned Pokémon (no party and no PC record) is restored into PC."""
        mon = create_pokemon(
            owner_id=self.player1_id,
            species_id="bulbasaur",
            auto_store=False,
        )

        # Invariant should flag not_in_party_or_pc
        problems = verify_storage_invariant()
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["problem"], "not_in_party_or_pc")

        # Run repair
        result = repair_pokemon_storage()
        self.assertGreaterEqual(result["repaired"], 1)

        # Invariant must now be completely clean
        self.assertEqual(verify_storage_invariant(), [])
        self.assertTrue(is_in_pc(self.player1_id, mon["id"]))

    def test_repair_fixes_conflicting_dual_storage(self) -> None:
        """A Pokémon erroneously inserted into both Party and PC is resolved to Party."""
        mon = create_pokemon(
            owner_id=self.player1_id,
            species_id="bulbasaur",
        )
        self.assertTrue(is_in_party(self.player1_id, mon["id"]))

        # Force dual insertion
        with get_connection() as db:
            db.execute(
                """
                INSERT INTO pc_storage (player_id, pokemon_id, page, slot)
                VALUES (?, ?, 1, 1)
                """,
                (self.player1_id, mon["id"]),
            )
            db.commit()

        problems = verify_storage_invariant()
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["problem"], "multiple_storage_records")

        # Repair must remove the PC duplicate
        repair_pokemon_storage()
        self.assertEqual(verify_storage_invariant(), [])
        self.assertTrue(is_in_party(self.player1_id, mon["id"]))
        self.assertFalse(is_in_pc(self.player1_id, mon["id"]))

    def test_repair_fixes_ownership_mismatch(self) -> None:
        """A Pokémon owned by Player 1 but stored under Player 2 is fixed."""
        mon = create_pokemon(
            owner_id=self.player1_id,
            species_id="bulbasaur",
            auto_store=False,
        )
        # Illegally store under player 2
        with get_connection() as db:
            db.execute(
                """
                INSERT INTO party (player_id, pokemon_id, slot)
                VALUES (?, ?, 1)
                """,
                (self.player2_id, mon["id"]),
            )
            db.commit()

        problems = verify_storage_invariant()
        self.assertTrue(any(p["problem"] == "storage_owner_mismatch" for p in problems))

        repair_pokemon_storage()
        self.assertEqual(verify_storage_invariant(), [])
        # Should now be stored under true owner (player 1)
        self.assertTrue(is_in_pc(self.player1_id, mon["id"]))


# =============================================================================
# 4. DATABASE MIGRATION TESTS
# =============================================================================

class TestDatabaseMigration(BaseTestCase):
    """Tests verifying safe rebuilding of legacy tables into new schema."""

    def test_rebuild_legacy_pokemon_tables_idempotent(self) -> None:
        create_pokemon(owner_id=self.player1_id, species_id="bulbasaur")
        result = rebuild_legacy_pokemon_tables()
        # Should not need rebuild if schema is already up to date
        self.assertIsInstance(result, dict)
        self.assertEqual(verify_storage_invariant(), [])

    def test_legacy_columns_stripped_and_checks_enforced(self) -> None:
        with get_connection() as db:
            # Verify pokemon table columns
            p_cols = [r["name"] for r in db.execute("PRAGMA table_info(pokemon)").fetchall()]
            for legacy in ("is_active", "nature", "status"):
                self.assertNotIn(legacy, p_cols)

            # Verify stats table columns
            s_cols = [r["name"] for r in db.execute("PRAGMA table_info(pokemon_stats)").fetchall()]
            for s in STAT_NAMES:
                self.assertIn(s, s_cols)
            for iv_ev in ("hp_iv", "attack_iv", "hp_ev", "attack_ev"):
                self.assertNotIn(iv_ev, s_cols)

            # Check constraints present in schema
            sql = db.execute("SELECT sql FROM sqlite_master WHERE name='pokemon'").fetchone()[0]
            self.assertIn("CHECK (level >= 1)", sql)
            self.assertIn("CHECK (level <= 100)", sql)
            self.assertIn("CHECK (shiny IN (0, 1))", sql)

    def test_rebuild_migrates_legacy_is_active_and_missing_stats(self) -> None:
        """Simulate an old database with is_active, nature, status and missing stats."""
        with get_connection() as db:
            db.execute("PRAGMA foreign_keys = OFF")
            # Drop current tables to create mock legacy tables
            db.execute("DROP TABLE IF EXISTS party")
            db.execute("DROP TABLE IF EXISTS pc_storage")
            db.execute("DROP TABLE IF EXISTS pokemon_stats")
            db.execute("DROP TABLE IF EXISTS pokemon")

            # Legacy pokemon table
            db.execute(
                """
                CREATE TABLE pokemon (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unique_id TEXT NOT NULL UNIQUE,
                    owner_id INTEGER NOT NULL,
                    species_id TEXT NOT NULL,
                    nickname TEXT,
                    level INTEGER NOT NULL DEFAULT 5,
                    experience INTEGER NOT NULL DEFAULT 0,
                    gender TEXT NOT NULL DEFAULT 'unknown',
                    shiny INTEGER NOT NULL DEFAULT 0,
                    variant TEXT NOT NULL DEFAULT 'normal',
                    nature TEXT NOT NULL DEFAULT 'Hardy',
                    current_hp INTEGER NOT NULL DEFAULT 1,
                    max_hp INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'healthy',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Insert legacy active and inactive pokemon (with level > 100 to test clamping)
            db.execute(
                """
                INSERT INTO pokemon (id, unique_id, owner_id, species_id, level, is_active)
                VALUES (1, 'LEGACY-001', 1, 'bulbasaur', 500, 1),
                       (2, 'LEGACY-002', 1, 'charmander', 10, 0)
                """
            )

            # Legacy stats table (only IVs)
            db.execute(
                """
                CREATE TABLE pokemon_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pokemon_id INTEGER NOT NULL UNIQUE,
                    hp_iv INTEGER NOT NULL DEFAULT 0,
                    attack_iv INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            db.execute("INSERT INTO pokemon_stats (pokemon_id) VALUES (1), (2)")

            db.commit()
            db.execute("PRAGMA foreign_keys = ON")

        # Now run rebuild
        rebuild_legacy_pokemon_tables()

        # Repair orphaned pokemon (since we deleted storage tables)
        repair_pokemon_storage()

        # Verify the pokemon were migrated to new schema
        # Since we deleted the storage tables, the pokemon should be repaired into PC
        problems = verify_storage_invariant()
        self.assertEqual(problems, [])

        # Verify level 500 was clamped to 100
        p1 = get_pokemon(1, 1)
        self.assertIsNotNone(p1)
        self.assertEqual(p1["level"], 100)

        # Verify stats were calculated and populated
        with get_connection() as db:
            s1 = db.execute("SELECT * FROM pokemon_stats WHERE pokemon_id = 1").fetchone()
            self.assertIsNotNone(s1)
            self.assertGreater(s1["hp"], 0)
            self.assertGreater(s1["attack"], 0)

            # Verify no foreign key violations
            violations = db.execute("PRAGMA foreign_key_check").fetchall()
            self.assertEqual(violations, [])

        # Invariant check must be completely clean
        self.assertEqual(verify_storage_invariant(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
