"""
Regression tests for quest line sections (Team Krampus / Side
Stories) and quest line chain locks on the Story Adventure hub.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from Server.app import create_app
import Server.config as config
import Server.database as database
from Server.database import init_db, seed_database
from Server.services import create_player

from Server import quest_chain
from Server.story_battle import complete_quest


class TestQuestlineSections(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "quest_sections_test.sqlite3"

        self._orig_db_path = config.DATABASE_PATH
        config.DATABASE_PATH = self.db_path
        database.DATABASE_PATH = self.db_path

        init_db()
        seed_database()

        self.player_id = create_player(
            "quester", "quester@example.com", "Quest Tester"
        )

        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._orig_db_path
        database.DATABASE_PATH = self._orig_db_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------

    def _completed(self) -> set[str]:
        return quest_chain.get_player_completed_quest_ids(self.player_id)

    def _sections(self) -> list[dict]:
        sections = quest_chain.group_questlines_by_section(
            quest_chain.list_questlines()
        )
        quest_chain.apply_questline_chain_locks(sections, self._completed())
        return sections

    def _line(self, questline_id: str) -> dict:
        for section in self._sections():
            for manifest in section["questlines"]:
                if manifest["id"] == questline_id:
                    return manifest
        raise AssertionError(f"questline {questline_id} not found")

    def _complete(self, questline_id: str, quest_id: str) -> None:
        summary = complete_quest(self.player_id, questline_id, quest_id)
        assert summary is not None, f"{quest_id} was not completable"

    # --------------------------------------------------------
    # SECTIONS
    # --------------------------------------------------------

    def test_saga_questlines_share_one_team_krampus_section(self) -> None:
        sections = self._sections()
        labels = {s["label"] for s in sections}

        self.assertIn("Team Krampus", labels)
        self.assertIn("Side Stories", labels)

        saga = next(
            s for s in sections if s["label"] == "Team Krampus"
        )
        saga_ids = [m["id"] for m in saga["questlines"]]

        # All three saga quest lines live under one banner, in order.
        self.assertEqual(
            saga_ids, ["team_krampus", "the_six_bells", "the_winterheart"]
        )

        side = next(
            s for s in sections if s["label"] == "Side Stories"
        )
        self.assertEqual(
            [m["id"] for m in side["questlines"]], ["lantern_registry"]
        )

    def test_no_quests_are_lost_in_grouping(self) -> None:
        sections = self._sections()
        total = sum(
            m["line_total"]
            for s in sections
            for m in s["questlines"]
        )
        # 12 + 12 + 13 + 6 — every quest survives the regrouping.
        self.assertEqual(total, 43)

    # --------------------------------------------------------
    # CHAIN LOCKS
    # --------------------------------------------------------

    def test_everything_after_first_line_is_locked_initially(self) -> None:
        self.assertFalse(self._line("team_krampus")["line_locked"])
        self.assertTrue(self._line("the_six_bells")["line_locked"])
        self.assertTrue(self._line("the_winterheart")["line_locked"])
        self.assertTrue(self._line("lantern_registry")["line_locked"])

    def test_chain_unlocks_only_after_full_completion(self) -> None:
        # 11 of 12 is not enough.
        for i in range(1, 12):
            self._complete("team_krampus", f"tk_{i:03d}")
        self.assertTrue(self._line("the_six_bells")["line_locked"])

        # The twelfth quest opens the next line.
        self._complete("team_krampus", "tk_012")
        self.assertFalse(self._line("the_six_bells")["line_locked"])

        # …but nothing beyond it.
        self.assertTrue(self._line("the_winterheart")["line_locked"])
        self.assertTrue(self._line("lantern_registry")["line_locked"])

    def test_lock_reason_names_the_blocking_questline(self) -> None:
        locked, reason = quest_chain.is_questline_locked(
            "the_six_bells", self._completed()
        )
        self.assertTrue(locked)
        self.assertIsNotNone(reason)
        self.assertIn("Krampus Conspiracy", reason)

    # --------------------------------------------------------
    # SERVER-SIDE GUARDS
    # --------------------------------------------------------

    def test_locked_questline_page_redirects_to_hub(self) -> None:
        with self.client.session_transaction() as session:
            session["player_id"] = self.player_id

        response = self.client.get(
            "/story-adventure/quest/lantern_registry/lr_001",
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/story-adventure", response.headers["Location"])

    def test_quest_pages_viewable_by_guests_and_players(self) -> None:
        # Guests can read quest pages (battles require login).
        response = self.client.get(
            "/story-adventure/quest/team_krampus/tk_001"
        )
        self.assertEqual(response.status_code, 200)

        # Logged in: first questline is unlocked, page renders.
        with self.client.session_transaction() as session:
            session["player_id"] = self.player_id

        response = self.client.get(
            "/story-adventure/quest/team_krampus/tk_001"
        )
        self.assertEqual(response.status_code, 200)

    def test_hub_renders_sections_and_lock_cards(self) -> None:
        response = self.client.get("/story-adventure")
        self.assertEqual(response.status_code, 200)

        body = response.get_data(as_text=True)
        self.assertIn("Team Krampus", body)
        self.assertIn("Side Stories", body)

        # Guests (and fresh players) see three locked quest lines.
        self.assertEqual(body.count("story-line-locked"), 3)

        # Only the current line auto-expands.
        self.assertEqual(body.count("is-open"), 1)


if __name__ == "__main__":
    unittest.main()
