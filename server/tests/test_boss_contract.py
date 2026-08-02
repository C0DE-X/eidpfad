import unittest

from app.boss_contract import (
    FINAL_OATH_CARD_ID,
    STAGE_ANCHORS,
    STAGE_ARMORED_FORM,
    STAGE_DEFEATED,
    STAGE_FINAL_OATH,
    STAGE_TORN_WORLD,
    STAGE_WARDENS,
    BossContract,
    filter_progression_rewards,
)
from app.errors import RuleViolation


class BossContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = BossContract.new(
            991,
            ("player-one", "player-two"),
            world_tier=2,
            unresolved_problems=("abandoned_caravan", "cursed_village"),
        )

    def destroy_all_active_targets(self) -> None:
        for target_id in tuple(self.contract.active_targets):
            self.contract.apply_damage(target_id, 10_000, bypass_armor=True)

    def reach_torn_world(self) -> None:
        self.destroy_all_active_targets()
        self.assertEqual(self.contract.state.stage, STAGE_WARDENS)
        self.destroy_all_active_targets()
        self.assertEqual(self.contract.state.stage, STAGE_ANCHORS)
        self.destroy_all_active_targets()
        self.assertEqual(self.contract.state.stage, STAGE_ARMORED_FORM)
        self.destroy_all_active_targets()
        self.assertEqual(self.contract.state.stage, STAGE_TORN_WORLD)

    def reach_final_oath(self) -> None:
        self.reach_torn_world()
        # One damage packet can cross one arena floor, never several.
        for expected_arena in (1, 2):
            self.contract.apply_damage("throneless", 100_000)
            self.assertEqual(self.contract.state.arena_index, expected_arena)
            self.assertEqual(self.contract.state.stage, STAGE_TORN_WORLD)
        self.contract.apply_damage("throneless", 100_000)
        self.assertEqual(self.contract.state.stage, STAGE_FINAL_OATH)

    def test_hidden_sovereign_is_deterministic_and_revealed_at_armored_form(self) -> None:
        second = BossContract.new(991, ("player-one", "player-two"), world_tier=2)
        self.assertEqual(self.contract.state.sovereign_id, second.state.sovereign_id)
        self.assertIsNone(self.contract.public_view()["sovereign"])

        clue_id = self.contract.sovereign["clues"][0]
        self.contract.discover_clue(clue_id)
        self.assertEqual(self.contract.public_view()["revealed_clues"], [clue_id])
        with self.assertRaises(RuleViolation):
            self.contract.discover_clue("wrong_clue")

        self.destroy_all_active_targets()
        self.destroy_all_active_targets()
        self.destroy_all_active_targets()
        self.assertEqual(self.contract.state.stage, STAGE_ARMORED_FORM)
        self.assertEqual(self.contract.public_view()["sovereign"]["id"], self.contract.state.sovereign_id)

    def test_objectives_are_addressable_and_stages_cannot_be_skipped(self) -> None:
        with self.assertRaises(RuleViolation):
            self.contract.apply_damage("anchor_origin", 100)

        events = self.contract.apply_damage("oath_gate", 100_000, bypass_armor=True)
        self.assertEqual(self.contract.state.stage, STAGE_WARDENS)
        self.assertIn("boss_stage_changed", [event["type"] for event in events])
        self.assertEqual(len(self.contract.active_targets), 2)

        first_warden = self.contract.active_targets[0]
        self.contract.apply_damage(first_warden, 100_000, bypass_armor=True)
        self.assertEqual(self.contract.state.stage, STAGE_WARDENS)
        self.assertEqual(len(self.contract.active_targets), 1)

    def test_armor_parts_must_be_destroyed_before_boss_can_be_damaged(self) -> None:
        self.destroy_all_active_targets()
        self.destroy_all_active_targets()
        self.destroy_all_active_targets()
        self.assertEqual(self.contract.state.stage, STAGE_ARMORED_FORM)
        self.assertEqual(len(self.contract.active_targets), 4)
        with self.assertRaises(RuleViolation):
            self.contract.apply_damage("throneless", 999)

        self.destroy_all_active_targets()
        self.assertEqual(self.contract.state.stage, STAGE_TORN_WORLD)
        self.assertEqual(self.contract.active_targets, ("throneless",))

    def test_massive_boss_damage_stops_at_every_arena_and_one_hp(self) -> None:
        self.reach_torn_world()
        expected_floors = (
            self.contract.state.boss_max_hp * 2 // 3,
            self.contract.state.boss_max_hp // 3,
            1,
        )
        for index, floor in enumerate(expected_floors):
            self.contract.apply_damage("throneless", 1_000_000)
            self.assertEqual(self.contract.state.boss_hp, floor)
            if index < 2:
                self.assertFalse(self.contract.state.completed)
                self.assertEqual(self.contract.state.stage, STAGE_TORN_WORLD)

        self.assertEqual(self.contract.state.stage, STAGE_FINAL_OATH)
        self.assertFalse(self.contract.state.completed)
        self.assertNotIn("throneless", self.contract.active_targets)
        with self.assertRaises(RuleViolation):
            self.contract.apply_damage("throneless", 1)

    def test_final_oath_requires_five_ap_and_both_independent_pools(self) -> None:
        self.reach_final_oath()
        self.assertGreaterEqual(self.contract.state.oath_power, 12)
        with self.assertRaises(RuleViolation):
            self.contract.commit_final_oath(
                "player-one", available_action_points=4
            )

        first = self.contract.commit_final_oath(
            "player-one", available_action_points=5
        )
        self.assertEqual(first[-1]["type"], "final_oath_contribution_locked")
        self.assertFalse(self.contract.state.completed)
        with self.assertRaises(RuleViolation):
            self.contract.commit_final_oath(
                "player-one", available_action_points=5
            )

        second = self.contract.commit_final_oath(
            "player-two", available_action_points=5
        )
        resolution = second[-1]
        self.assertEqual(resolution["type"], "final_oath_resolved")
        self.assertTrue(resolution["success"])
        self.assertEqual(resolution["dice_count"], 12)  # Deliberately above the normal 8-die cap.
        self.assertEqual(self.contract.state.stage, STAGE_DEFEATED)
        self.assertEqual(self.contract.state.boss_hp, 0)
        self.assertTrue(self.contract.state.completed)

    def test_failed_joint_oath_can_be_retried_but_raises_threat(self) -> None:
        self.contract = BossContract.new(4404, ("player-one", "player-two"), world_tier=2)
        self.reach_final_oath()
        threat_before = self.contract.state.threat
        self.contract.commit_final_oath(
            "player-one", available_action_points=5
        )
        events = self.contract.commit_final_oath(
            "player-two", available_action_points=5
        )
        self.assertFalse(events[-1]["success"])
        self.assertEqual(self.contract.state.final_oath_contributions, {})
        self.assertEqual(self.contract.state.final_oath_attempt, 2)
        self.assertGreaterEqual(self.contract.state.threat, threat_before)

    def test_threat_and_problem_echoes_change_boss_pressure(self) -> None:
        base = self.contract.boss_attack_bonus
        self.contract.end_round()
        self.contract.end_round()
        self.contract.end_round()
        self.assertGreater(self.contract.boss_attack_bonus, base)
        self.assertEqual(
            self.contract.public_view()["unresolved_problem_echoes"],
            ["abandoned_caravan", "cursed_village"],
        )
        threat = self.contract.state.threat
        self.contract.reduce_threat(2)
        self.assertEqual(self.contract.state.threat, max(0, threat - 2))

    def test_final_oath_is_reserved_from_normal_progression_and_card_play(self) -> None:
        self.assertEqual(
            filter_progression_rewards(["kreuzschnitt", FINAL_OATH_CARD_ID, "feldverband"]),
            ["kreuzschnitt", "feldverband"],
        )
        with self.assertRaises(RuleViolation):
            self.contract.validate_normal_card(FINAL_OATH_CARD_ID)
        self.contract.validate_normal_card("kreuzschnitt")

    def test_export_restore_preserves_every_boss_gate(self) -> None:
        self.destroy_all_active_targets()
        first_warden = self.contract.active_targets[0]
        self.contract.apply_damage(first_warden, 7)
        restored = BossContract.restore(self.contract.export())
        self.assertEqual(restored.export(), self.contract.export())
        self.assertEqual(restored.public_view(), self.contract.public_view())


if __name__ == "__main__":
    unittest.main()
