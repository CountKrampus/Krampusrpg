"""
Gym admin CRUD, gym battle integration, and uncapped level tests.

Mirrors test_admin.py's isolation pattern: every test gets a temp
database and a temp Data/gyms.json so the live files are never
touched.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import Server.config as config
import Server.database as database
import Server.gyms as gyms
from Server.app import create_app
from Server.admin.bootstrap import create_webmaster
from Server.admin.services import ensure_admin_tables
from Server.database import init_db, seed_database
from Server.services import create_player, create_pokemon


class BaseGymTestCase(unittest.TestCase):
    """Isolated temp database + temp gyms.json for each test."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "gyms_test.sqlite3"
        self.gyms_path = Path(self.temp_dir) / "gyms.json"

        self._orig_db_path = config.DATABASE_PATH
        config.DATABASE_PATH = self.db_path
        database.DATABASE_PATH = self.db_path

        self._orig_gyms_path = gyms.GYMS_PATH
        gyms.GYMS_PATH = self.gyms_path

        init_db()
        seed_database()
        ensure_admin_tables()

        self.webmaster_id = create_webmaster(
            "webmaster_user", "password123", "Webmaster Test"
        )
        self.player_id = create_player(
            "tester", "tester@example.com", "Test Player"
        )

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._orig_db_path
        database.DATABASE_PATH = self._orig_db_path
        gyms.GYMS_PATH = self._orig_gyms_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _staff_client(self):
        app = create_app()
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        client = app.test_client()

        with client.session_transaction() as sess:
            sess["player_id"] = self.webmaster_id

        return client

    def _plain_client(self):
        app = create_app()
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        client = app.test_client()

        with client.session_transaction() as sess:
            sess["player_id"] = self.player_id

        return client


VALID_TEAM = [
    {"species": "pikachu", "level": 12},
    {"species": "charmander", "level": 14},
]


class TestGymCrud(BaseGymTestCase):
    """Direct service-layer CRUD round-trips on Data/gyms.json."""

    def test_create_gym_roundtrip_and_badge_definition(self) -> None:
        gym = gyms.create_gym(
            name="Ember Cavern Gym",
            leader="Blaine",
            leader_title="The Quiz Master",
            gym_type="fire",
            region="hollyhollow",
            leader_intro="Bring water.",
            leader_defeat="Well burned.",
            badge_name="Volcano Badge",
            required_badges=1,
            money_reward=2500,
            team=VALID_TEAM,
        )

        self.assertEqual(gym["id"], "ember_cavern_gym")
        self.assertEqual(gym["badge"], "volcano_badge")
        self.assertEqual(gym["rewards"]["money"], 2500)

        stored = gyms.get_gym("EMBER_CAVERN_GYM")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["leader"], "Blaine")
        self.assertEqual(stored["team"][0]["species"], "pikachu")

        badge = gyms.get_badge_definitions().get("volcano_badge")
        self.assertIsNotNone(badge)
        self.assertEqual(badge["name"], "Volcano Badge")
        self.assertIn("Blaine", badge["description"])

    def test_create_gym_duplicate_rejected(self) -> None:
        gyms.create_gym(
            name="Duplicate Gym",
            badge_name="Dup Badge",
            team=VALID_TEAM,
        )

        with self.assertRaises(ValueError):
            gyms.create_gym(
                name="Duplicate   Gym",  # same slug
                badge_name="Other Badge",
                team=VALID_TEAM,
            )

    def test_create_gym_unknown_species_rejected(self) -> None:
        with self.assertRaises(ValueError):
            gyms.create_gym(
                name="Bad Species Gym",
                badge_name="Bad Badge",
                team=[{"species": "not_a_pokemon", "level": 5}],
            )

    def test_create_gym_unknown_variant_rejected(self) -> None:
        with self.assertRaises(ValueError):
            gyms.create_gym(
                name="Bad Variant Gym",
                badge_name="Bad Badge",
                team=[
                    {
                        "species": "pikachu",
                        "level": 5,
                        "variant": "definitely_not_real",
                    }
                ],
            )

    def test_create_gym_team_size_enforced(self) -> None:
        with self.assertRaises(ValueError):
            gyms.create_gym(
                name="Empty Gym",
                badge_name="Empty Badge",
                team=[],
            )

        with self.assertRaises(ValueError):
            gyms.create_gym(
                name="Too Big Gym",
                badge_name="Big Badge",
                team=[
                    {"species": "pikachu", "level": n}
                    for n in range(1, 8)
                ],
            )

    def test_update_gym_fields_and_badge_rename(self) -> None:
        gyms.create_gym(
            name="Rename Gym",
            leader="Original",
            badge_name="Original Badge",
            money_reward=100,
            team=VALID_TEAM,
        )

        gyms.update_gym(
            "rename_gym",
            name="Renamed Gym",
            leader="Updated",
            gym_type="ghost",
            money_reward=4242,
            badge_name="Renamed Badge",
        )

        gym = gyms.get_gym("rename_gym")
        self.assertEqual(gym["name"], "Renamed Gym")
        self.assertEqual(gym["leader"], "Updated")
        self.assertEqual(gym["type"], "ghost")
        self.assertEqual(gym["rewards"]["money"], 4242)

        # Badge id stays stable so held badges keep resolving; only
        # the display name is renamed.
        self.assertEqual(gym["badge"], "original_badge")
        badge = gyms.get_badge_definitions()["original_badge"]
        self.assertEqual(badge["name"], "Renamed Badge")

    def test_set_gym_team_replaces_whole_team(self) -> None:
        gyms.create_gym(
            name="Team Gym",
            badge_name="Team Badge",
            team=VALID_TEAM,
        )

        new_team = [
            {"species": "bulbasaur", "level": 99999999},
            {"species": "squirtle", "level": 2, "variant": "ruby"},
        ]

        gyms.set_gym_team("team_gym", new_team)

        team = gyms.get_gym("team_gym")["team"]
        self.assertEqual(len(team), 2)
        self.assertEqual(team[0]["species"], "bulbasaur")
        self.assertEqual(team[1]["variant"], "ruby")

    def test_team_levels_are_uncapped(self) -> None:
        """The whole point: a gym leader may sit at level 99999999."""

        gym = gyms.create_gym(
            name="Uncapped Gym",
            badge_name="Uncapped Badge",
            team=[{"species": "pikachu", "level": 1}],
        )

        gyms.set_gym_team(
            gym["id"],
            [{"species": "froslass", "level": 99999999}],
        )

        member = gyms.get_gym("uncapped_gym")["team"][0]
        self.assertEqual(member["level"], 99999999)

    def test_delete_gym_removes_badge_unless_shared(self) -> None:
        gyms.create_gym(
            name="Doomed Gym",
            badge_name="Doomed Badge",
            team=VALID_TEAM,
        )
        gyms.create_gym(
            name="Keeper Gym",
            badge_name="Keeper Badge",
            team=VALID_TEAM,
        )

        removed = gyms.delete_gym("doomed_gym")
        self.assertIsNotNone(removed)
        self.assertEqual(removed["name"], "Doomed Gym")
        self.assertIsNone(gyms.get_gym("doomed_gym"))
        self.assertNotIn("doomed_badge", gyms.get_badge_definitions())

        # Unknown id is a silent no-op returning None.
        self.assertIsNone(gyms.delete_gym("nope_gym"))

        gyms.delete_gym("keeper_gym")
        self.assertNotIn("keeper_badge", gyms.get_badge_definitions())

    def test_changes_are_live_without_restart(self) -> None:
        """gyms.json writes apply on the very next read."""

        gyms.create_gym(
            name="Fresh Gym",
            badge_name="Fresh Badge",
            team=VALID_TEAM,
        )

        # The file on disk is valid JSON with the gym present.
        raw = json.loads(self.gyms_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [g["id"] for g in raw["gyms"]],
            ["fresh_gym"],
        )


class TestGymBattleIntegration(BaseGymTestCase):
    """Gym challenges still flow through the shared battle engine."""

    def setUp(self) -> None:
        super().setUp()

        # The player needs a party for battle_store.
        for species in ("pikachu", "charmander", "squirtle"):
            create_pokemon(
                owner_id=self.player_id,
                species_id=species,
                level=10,
            )

    def test_start_gym_battle_tags_context(self) -> None:
        gyms.create_gym(
            name="Battle Gym",
            badge_name="Battle Badge",
            money_reward=500,
            team=VALID_TEAM,
        )

        battle = gyms.start_gym_battle(self.player_id, "battle_gym")

        self.assertIn("battle_id", battle)

        context = gyms.read_battle_context(battle["battle_id"])
        self.assertEqual(context.get("gym_id"), "battle_gym")
        self.assertEqual(context.get("badge"), "battle_badge")

    def test_locked_gym_rejected(self) -> None:
        gyms.create_gym(
            name="Locked Gym",
            badge_name="Locked Badge",
            required_badges=1,
            team=VALID_TEAM,
        )

        with self.assertRaises(ValueError):
            gyms.start_gym_battle(self.player_id, "locked_gym")

    def test_unknown_gym_rejected(self) -> None:
        with self.assertRaises(ValueError):
            gyms.start_gym_battle(self.player_id, "ghost_gym")


class TestAdminGymRoutes(BaseGymTestCase):
    """The /admin/gyms pages: full CRUD round-trip via the forms."""

    CREATE_FORM = {
        "name": "Route Admin Gym",
        "leader": "Form Leader",
        "leader_title": "The Form Tester",
        "type": "electric",
        "region": "hollyhollow",
        "leader_intro": "Hello.",
        "leader_defeat": "Goodbye.",
        "badge_name": "Form Badge",
        "required_badges": "0",
        "money_reward": "1234",
        "team_species": ["pikachu", "", "charmander"],
        "team_level": ["20", "50", "30"],
        "team_variant": ["normal", "normal", "normal"],
    }

    def test_gyms_page_renders_for_staff(self) -> None:
        response = self._staff_client().get("/admin/gyms")
        self.assertEqual(response.status_code, 200)
        self.assertIn("New Gym", response.get_data(as_text=True))

    def test_plain_player_blocked(self) -> None:
        # A logged-in player without staff permission is forbidden;
        # anonymous visitors are redirected to login.
        response = self._plain_client().get("/admin/gyms")
        self.assertIn(response.status_code, (302, 403))

    def test_full_crud_roundtrip_via_forms(self) -> None:
        client = self._staff_client()

        # Create (empty spare row in the middle is skipped).
        response = client.post("/admin/gyms/create", data=self.CREATE_FORM)
        self.assertEqual(response.status_code, 302)

        gym = gyms.get_gym("route_admin_gym")
        self.assertIsNotNone(gym)
        self.assertEqual(
            [m["species"] for m in gym["team"]],
            ["pikachu", "charmander"],
        )
        self.assertIsNotNone(gyms.get_badge_definitions().get("form_badge"))

        # Edit details: rename badge display name + bump reward.
        response = client.post(
            "/admin/gyms/route_admin_gym/edit",
            data={
                "name": "Route Admin Gym",
                "leader": "Form Leader",
                "leader_title": "The Form Tester",
                "type": "electric",
                "region": "hollyhollow",
                "leader_intro": "Hello.",
                "leader_defeat": "Goodbye.",
                "badge_name": "Renamed Form Badge",
                "required_badges": "2",
                "money_reward": "9999",
            },
        )
        self.assertEqual(response.status_code, 302)

        gym = gyms.get_gym("route_admin_gym")
        self.assertEqual(gym["rewards"]["money"], 9999)
        self.assertEqual(gym["required_badges"], 2)
        self.assertEqual(
            gyms.get_badge_definitions()["form_badge"]["name"],
            "Renamed Form Badge",
        )

        # Replace the team, with an uncapped level.
        response = client.post(
            "/admin/gyms/route_admin_gym/team",
            data={
                "team_species": ["froslass"],
                "team_level": ["99999999"],
                "team_variant": ["normal"],
            },
        )
        self.assertEqual(response.status_code, 302)

        team = gyms.get_gym("route_admin_gym")["team"]
        self.assertEqual(len(team), 1)
        self.assertEqual(team[0]["level"], 99999999)

        # Delete (with the confirm prompt handled client-side).
        response = client.post("/admin/gyms/route_admin_gym/delete")
        self.assertEqual(response.status_code, 302)

        self.assertIsNone(gyms.get_gym("route_admin_gym"))
        self.assertNotIn("form_badge", gyms.get_badge_definitions())

    def test_duplicate_gym_rejected_via_form(self) -> None:
        client = self._staff_client()

        client.post("/admin/gyms/create", data=self.CREATE_FORM)

        response = client.post(
            "/admin/gyms/create",
            data={**self.CREATE_FORM, "name": "Route Admin Gym"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "already exists",
            response.get_data(as_text=True),
        )

    def test_unknown_species_rejected_via_form(self) -> None:
        response = self._staff_client().post(
            "/admin/gyms/create",
            data={
                **self.CREATE_FORM,
                "name": "Broken Species Gym",
                "badge_name": "Broken Badge",
                "team_species": ["missing_no"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "unknown species",
            response.get_data(as_text=True),
        )
        self.assertIsNone(gyms.get_gym("broken_species_gym"))


if __name__ == "__main__":
    unittest.main()
