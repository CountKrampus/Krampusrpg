from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from Server.app import create_app
from Server.config import SECRET_KEY
import Server.config as config
import Server.database as database
from Server.database import init_db, seed_database
from Server.admin.services import (
    ensure_admin_tables,
    get_dashboard_stats,
    admin_assign_pokemon,
    get_available_species,
    get_available_variants,
    search_players,
    get_player_details,
    create_report,
    get_reports,
    update_report_status,
    create_promo,
    get_promos,
    toggle_promo_active,
    create_event,
    get_events,
    toggle_event_active,
    get_all_settings,
    update_settings,
    get_database_diagnostics,
    run_database_integrity_check,
    create_database_backup,
)
from Server.admin.bootstrap import create_webmaster
from Server.services import create_player


class TestAdminSystem(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "admin_test.sqlite3"

        self._orig_db_path = config.DATABASE_PATH
        config.DATABASE_PATH = self.db_path
        database.DATABASE_PATH = self.db_path

        init_db()
        seed_database()
        ensure_admin_tables()

        # Create webmaster and test player
        self.webmaster_id = create_webmaster("webmaster_user", "password123", "Webmaster Test")
        self.player_id = create_player("tester", "tester@example.com", "Test Player")

        # Flask test app
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._orig_db_path
        database.DATABASE_PATH = self._orig_db_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dashboard_stats(self) -> None:
        stats = get_dashboard_stats()
        self.assertIn("players", stats)
        self.assertIn("pokemon", stats)
        self.assertIn("party_pokemon", stats)
        self.assertIn("pc_pokemon", stats)
        self.assertIn("open_reports", stats)
        self.assertIn("total_money", stats)
        self.assertGreaterEqual(stats["players"], 2)

    def test_admin_assign_pokemon_party_and_pc(self) -> None:
        """Verify directly assigning pokemon puts first 6 into party, and 7th into PC."""
        species = get_available_species()
        self.assertTrue(len(species) > 0)
        spec_id = species[0]["id"]

        variants = get_available_variants()
        self.assertTrue(len(variants) > 0)

        # Assign 6 Pokemon to player -> should all be in party
        for i in range(1, 7):
            res = admin_assign_pokemon(
                owner_id=self.player_id,
                species_id=spec_id,
                level=10 + i,
                shiny=(i == 1),
                variant="ruby",
                nickname=f"PartyMon{i}",
            )
            self.assertEqual(res["location"]["location"], "party")
            self.assertEqual(res["location"]["slot"], i)

        # 7th Pokemon should automatically go to PC
        res7 = admin_assign_pokemon(
            owner_id=self.player_id,
            species_id=spec_id,
            level=50,
            shiny=False,
            variant="normal",
            nickname="PCMon1",
        )
        self.assertEqual(res7["location"]["location"], "pc")

        # Verify details
        details = get_player_details(self.player_id)
        self.assertIsNotNone(details)
        self.assertEqual(details["party_count"], 6)
        self.assertEqual(details["pc_count"], 1)
        self.assertEqual(details["pokemon_count"], 7)

    def test_reports_management(self) -> None:
        report_id = create_report(
            reporter_id=self.webmaster_id,
            reported_player_id=self.player_id,
            reason="Test harassment",
            details="Test details here",
        )
        self.assertGreater(report_id, 0)

        reports = get_reports(status="open")
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["reason"], "Test harassment")

        # Update report status
        updated = update_report_status(
            report_id=report_id,
            status="resolved",
            staff_player_id=self.webmaster_id,
            resolution_notes="Resolved in testing",
        )
        self.assertTrue(updated)

        open_reports = get_reports(status="open")
        self.assertEqual(len(open_reports), 0)

        resolved_reports = get_reports(status="resolved")
        self.assertEqual(len(resolved_reports), 1)

    def test_promos_and_events(self) -> None:
        promo_id = create_promo(species_id="charmander", variant="ruby", level=20, active=True)
        self.assertGreater(promo_id, 0)
        promos = get_promos()
        self.assertEqual(len(promos), 1)

        toggle_promo_active(promo_id)
        promos_after = get_promos()
        self.assertEqual(promos_after[0]["active"], 0)

        event_id = create_event(name="Winter Blast", description="Cold weather tournament", active=True)
        self.assertGreater(event_id, 0)
        events = get_events()
        self.assertEqual(len(events), 1)

        toggle_event_active(event_id)
        events_after = get_events()
        self.assertEqual(events_after[0]["active"], 0)

    def test_settings_management(self) -> None:
        settings = get_all_settings()
        self.assertTrue(len(settings) > 0)

        update_settings({"exp_multiplier": "2.5", "maintenance_mode": "1"})
        updated_settings = {s["name"]: s["value"] for s in get_all_settings()}
        self.assertEqual(updated_settings["exp_multiplier"], "2.5")
        self.assertEqual(updated_settings["maintenance_mode"], "1")

    def test_database_diagnostics_and_backup(self) -> None:
        diag = get_database_diagnostics()
        self.assertIn("version", diag)
        self.assertIn("size_kb", diag)
        self.assertIn("tables", diag)
        self.assertGreater(diag["tables"]["players"], 0)

        check = run_database_integrity_check()
        self.assertEqual(check.lower(), "ok")

        backup_file = create_database_backup()
        self.assertTrue(backup_file.startswith("krampus_backup_"))

    def test_admin_routes_with_webmaster_session(self) -> None:
        with self.client.session_transaction() as sess:
            sess["player_id"] = self.webmaster_id

        # Access dashboard
        res = self.client.get("/admin/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Admin Dashboard", res.data)

        # Access players
        res = self.client.get("/admin/players")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Player Directory", res.data)

        # Access pokemon
        res = self.client.get("/admin/pokemon")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Assign Pok", res.data)

        # Direct assign pokemon via POST
        res = self.client.post(
            "/admin/pokemon/assign",
            data={
                "player_id": str(self.player_id),
                "species_id": "pikachu",
                "level": "25",
                "shiny": "1",
                "variant": "gold",
                "nickname": "GoldenSpark",
            },
            follow_redirects=True,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Successfully assigned", res.data)

        # Access database diagnostics
        res = self.client.get("/admin/database")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Database Administration", res.data)

        # Access site settings
        res = self.client.get("/admin/settings")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Site Settings", res.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
