import unittest

from app.boss_contract import STAGE_TORN_WORLD, BossContract
from app.cinematic_progress import CinematicProgress
from app.errors import RuleViolation
from app.postgame import (
    ENDING_BIND,
    ENDING_DESTROY,
    ENDING_DOMINATE,
    ENDING_SEAL,
    PHASE_ENDING_VOTE,
    PHASE_LEGACY_SELECTION,
    PHASE_NEW_GAME_PLUS,
    Postgame,
    character_levels_after_campaign,
    eligible_legacy_items,
)


class PostgameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.postgame = Postgame.new(
            seed=4404,
            campaign_length="saga",
            completed_world_tier=3,
            player_ids=("player-one", "player-two"),
            legacy_options={
                "player-one": ("ember_crown", "duelist_hooks"),
                "player-two": ("moon_armor", "rune_axe"),
            },
            character_levels={"player-one": 8, "player-two": 9},
        )

    def agree_on_ending(self) -> None:
        self.postgame.submit_ending("player-one", ENDING_SEAL)
        events = self.postgame.submit_ending("player-two", ENDING_SEAL)
        self.assertEqual(events[-1]["type"], "ending_resolved")

    def choose_legacies(self) -> None:
        self.agree_on_ending()
        self.postgame.select_legacy("player-one", "ember_crown")
        self.postgame.select_legacy("player-two", "moon_armor")

    def complete_postgame(self) -> None:
        self.choose_legacies()
        self.postgame.confirm_new_game_plus("player-one")
        self.postgame.confirm_new_game_plus("player-two")

    def test_ending_votes_are_simultaneous_and_hidden_until_both_lock(self) -> None:
        events = self.postgame.submit_ending("player-one", ENDING_DESTROY)
        self.assertEqual(events, [{
            "type": "ending_choice_locked",
            "player": "player-one",
            "vote_round": 1,
        }])
        other_view = self.postgame.public_view("player-two")
        self.assertEqual(other_view["ending_vote_locked_players"], ["player-one"])
        self.assertNotIn("ending_votes", other_view)
        self.assertIsNone(other_view["ending_result"])

        events = self.postgame.submit_ending("player-two", ENDING_DESTROY)
        self.assertEqual(events[-1]["choice"], ENDING_DESTROY)
        self.assertEqual(self.postgame.state.phase, PHASE_LEGACY_SELECTION)

    def test_disagreement_reveals_both_choices_and_starts_fresh_vote(self) -> None:
        self.postgame.submit_ending("player-one", ENDING_SEAL)
        events = self.postgame.submit_ending("player-two", ENDING_BIND)
        self.assertEqual(events[-1]["type"], "ending_consensus_required")
        self.assertEqual(
            events[-1]["choices"],
            {"player-one": ENDING_SEAL, "player-two": ENDING_BIND},
        )
        self.assertEqual(self.postgame.state.phase, PHASE_ENDING_VOTE)
        self.assertEqual(self.postgame.state.vote_round, 2)
        self.assertEqual(self.postgame.state.ending_votes, {})

        self.postgame.submit_ending("player-two", ENDING_BIND)
        self.postgame.submit_ending("player-one", ENDING_BIND)
        self.assertEqual(self.postgame.state.ending_result, ENDING_BIND)

    def test_one_player_cannot_override_or_submit_twice(self) -> None:
        self.postgame.submit_ending("player-one", ENDING_SEAL)
        with self.assertRaises(RuleViolation):
            self.postgame.submit_ending("player-one", ENDING_DESTROY)
        self.assertEqual(self.postgame.state.phase, PHASE_ENDING_VOTE)

    def test_legacy_must_be_an_owned_eligible_choice_and_both_select(self) -> None:
        self.agree_on_ending()
        with self.assertRaises(RuleViolation):
            self.postgame.select_legacy("player-one", "moon_armor")

        first = self.postgame.select_legacy("player-one", "ember_crown")
        self.assertEqual(first[-1]["type"], "legacy_item_locked")
        self.assertEqual(self.postgame.state.phase, PHASE_LEGACY_SELECTION)
        events = self.postgame.select_legacy("player-two", "moon_armor")
        self.assertEqual(events[-1]["type"], "legacy_transfer_ready")
        self.assertEqual(self.postgame.state.phase, PHASE_NEW_GAME_PLUS)
        self.assertEqual(self.postgame.state.next_world_tier, 4)
        self.assertIsNotNone(self.postgame.state.next_seed)

    def test_new_game_plus_requires_both_confirmations_and_transfers_legacy(self) -> None:
        self.choose_legacies()
        first = self.postgame.confirm_new_game_plus("player-one")
        self.assertEqual(first[-1]["type"], "new_game_plus_confirmed")
        self.assertFalse(self.postgame.state.completed)

        second = self.postgame.confirm_new_game_plus("player-two")
        ready = second[-1]
        self.assertEqual(ready["type"], "new_game_plus_ready")
        self.assertEqual(ready["world_tier"], 4)
        self.assertEqual(ready["legacy_items"]["player-one"]["item_id"], "ember_crown")
        self.assertEqual(ready["legacy_items"]["player-two"]["item_id"], "moon_armor")
        self.assertEqual(ready["character_levels"], {"player-one": 12, "player-two": 13})
        self.assertTrue(self.postgame.state.completed)

    def test_meta_progress_is_reconnect_and_retry_idempotent(self) -> None:
        self.complete_postgame()
        first = self.postgame.meta_progress_for(
            "player-one", {"campaign_wins": 2, "endings": [ENDING_BIND]}
        )
        self.assertEqual(first["campaign_wins"], 3)
        self.assertEqual(first["endings"], [ENDING_BIND, ENDING_SEAL])
        self.assertEqual(first["highest_world_tier"], 4)
        self.assertEqual(first["legacy_vault"][0]["item_id"], "ember_crown")

        retry = self.postgame.meta_progress_for("player-one", first)
        self.assertEqual(retry, first)

    def test_next_world_seed_is_deterministic_and_changes_with_legacy(self) -> None:
        self.choose_legacies()
        seed = self.postgame.state.next_seed
        restored = Postgame.restore(self.postgame.export())
        self.assertEqual(restored.state.next_seed, seed)
        self.assertEqual(restored.export(), self.postgame.export())

        other = Postgame.new(
            seed=4404,
            campaign_length="saga",
            completed_world_tier=3,
            player_ids=("player-one", "player-two"),
            legacy_options={
                "player-one": ("ember_crown", "duelist_hooks"),
                "player-two": ("moon_armor", "rune_axe"),
            },
            character_levels={"player-one": 8, "player-two": 9},
        )
        other.submit_ending("player-one", ENDING_SEAL)
        other.submit_ending("player-two", ENDING_SEAL)
        other.select_legacy("player-one", "duelist_hooks")
        other.select_legacy("player-two", "moon_armor")
        self.assertNotEqual(other.state.next_seed, seed)

    def test_eligible_legacy_filter_and_bounded_character_levels(self) -> None:
        choices = eligible_legacy_items(
            {
                "p1": ("common", "legend", "legend", "forbidden", "missing"),
                "p2": ("exceptional",),
            },
            {
                "common": {"rarity": "common"},
                "legend": {"rarity": "legendary"},
                "forbidden": {"rarity": "unique", "legacy_eligible": False},
                "exceptional": {"rarity": "exceptional"},
            },
        )
        self.assertEqual(choices, {"p1": ["legend"], "p2": ["exceptional"]})
        self.assertEqual(
            character_levels_after_campaign({"p1": 29, "p2": 1}, "saga", 7),
            {"p1": 30, "p2": 6},
        )


class CinematicProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.progress = CinematicProgress.new("campaign-a", ("p1", "p2"))

    def test_blocking_cinematic_waits_for_both_and_does_not_replay(self) -> None:
        started = self.progress.request("final_gate_intro", "boss:gate")
        self.assertEqual(started[-1]["type"], "cinematic_started")
        self.assertTrue(self.progress.public_view()["gameplay_blocked"])

        first = self.progress.acknowledge("p1", "final_gate_intro")
        self.assertEqual(first[-1]["type"], "cinematic_acknowledged")
        self.assertTrue(self.progress.public_view()["gameplay_blocked"])

        second = self.progress.acknowledge("p2", "final_gate_intro", skipped=True)
        self.assertEqual(second[-1]["type"], "cinematic_completed")
        self.assertEqual(second[-1]["skipped_players"], ["p2"])
        self.assertFalse(self.progress.public_view()["gameplay_blocked"])
        self.assertEqual(self.progress.request("final_gate_intro", "boss:gate"), [])

    def test_reconnect_restore_keeps_active_acks_per_campaign(self) -> None:
        self.progress.request("boss_reveal", "boss:armored")
        self.progress.acknowledge("p1", "boss_reveal")
        restored = CinematicProgress.restore(self.progress.export())
        self.assertEqual(restored.public_view()["active"]["acknowledged_players"], ["p1"])
        events = restored.acknowledge("p2", "boss_reveal")
        self.assertEqual(events[-1]["type"], "cinematic_completed")

        other_campaign = CinematicProgress.new("campaign-b", ("p1", "p2"))
        self.assertTrue(other_campaign.request("boss_reveal", "boss:armored"))

    def test_ack_retries_are_idempotent_and_other_cinematic_is_blocked(self) -> None:
        self.progress.request("travel", "world:departure")
        self.progress.acknowledge("p1", "travel")
        self.assertEqual(self.progress.acknowledge("p1", "travel"), [])
        with self.assertRaises(RuleViolation):
            self.progress.request("boss", "boss:intro")


class BossToNewGamePlusFlowTests(unittest.TestCase):
    def test_shared_boss_finish_flows_through_ending_and_legacy_into_next_world(self) -> None:
        boss = BossContract.new(991, ("p1", "p2"), world_tier=1)
        while boss.state.stage != STAGE_TORN_WORLD:
            for target_id in tuple(boss.active_targets):
                boss.apply_damage(target_id, 100_000, bypass_armor=True)
        for _ in range(3):
            boss.apply_damage("throneless", 100_000)
        boss.commit_final_oath("p1", available_action_points=5)
        boss.commit_final_oath("p2", available_action_points=5)
        self.assertTrue(boss.state.completed)

        postgame = Postgame.new(
            seed=991,
            campaign_length="expedition",
            completed_world_tier=1,
            player_ids=("p1", "p2"),
            legacy_options={"p1": ("legacy_blade",), "p2": ("legacy_ward",)},
            character_levels={"p1": 4, "p2": 4},
        )
        postgame.submit_ending("p1", ENDING_DOMINATE)
        postgame.submit_ending("p2", ENDING_DOMINATE)
        postgame.select_legacy("p1", "legacy_blade")
        postgame.select_legacy("p2", "legacy_ward")
        postgame.confirm_new_game_plus("p1")
        events = postgame.confirm_new_game_plus("p2")

        self.assertEqual(events[-1]["type"], "new_game_plus_ready")
        self.assertEqual(events[-1]["ending"], ENDING_DOMINATE)
        self.assertEqual(events[-1]["world_tier"], 2)
        self.assertEqual(events[-1]["legacy_items"]["p1"]["item_id"], "legacy_blade")


if __name__ == "__main__":
    unittest.main()
