import copy
import unittest
from pathlib import Path

from app.content import CardCatalog, EnemyCatalog, ItemCatalog
from app.errors import RuleViolation
from app.game_engine import GameEngine
from app.scenario_rules import ScenarioRules, WaveTransitionRules


ROOT = Path(__file__).resolve().parents[2]
CARDS = CardCatalog(ROOT / "shared" / "cards.json")
ITEMS = ItemCatalog(ROOT / "shared" / "items.json")
ENEMIES = EnemyCatalog(ROOT / "shared" / "enemies.json")


def new_engine() -> GameEngine:
    return GameEngine.new(
        123,
        {
            "p1": {"weapon": "axe", "magic": "ember"},
            "p2": {"weapon": "bow", "magic": "rune"},
        },
        CARDS,
        ITEMS,
        "expedition",
        1,
        ENEMIES,
    )


def set_kind(engine: GameEngine, kind: str) -> None:
    scenario = engine.state.world["route"][engine.state.scenario_index]
    scenario["id"] = f"test-{kind}"
    scenario["kind"] = kind
    scenario["is_boss"] = kind in {"country_boss", "final_boss"}
    scenario["is_final"] = kind == "final_boss"


class ScenarioRulesTests(unittest.TestCase):
    def test_all_six_regular_scenario_types_get_real_objectives(self) -> None:
        for kind in ("ambush", "raid", "village", "caravan", "hunt", "ruin"):
            with self.subTest(kind=kind):
                engine = new_engine()
                set_kind(engine, kind)
                events = ScenarioRules.initialize(engine.state)
                view = ScenarioRules.client_view(engine.state)
                self.assertEqual(events[0]["type"], "scenario_objective_started")
                self.assertEqual(view["status"], "active")
                self.assertTrue(view["objective"]["description"])
                self.assertIn("current", view["objective"])
                self.assertIn("maximum", view["objective"])

    def test_village_and_caravan_are_damageable_and_can_fail(self) -> None:
        for kind, target_id in (("village", "objective:villagers"), ("caravan", "objective:caravan")):
            with self.subTest(kind=kind):
                engine = new_engine()
                set_kind(engine, kind)
                ScenarioRules.initialize(engine.state)
                maximum = ScenarioRules.client_view(engine.state)["protected_targets"][target_id]["max_hp"]

                events = ScenarioRules.record_enemy_attack(engine.state, maximum)

                self.assertIn("scenario_objective_failed", [event["type"] for event in events])
                self.assertEqual(ScenarioRules.client_view(engine.state)["status"], "failed")
                self.assertTrue(engine.state.world["campaign_consequences"][0]["unresolved_problem"])
                with self.assertRaises(RuleViolation):
                    ScenarioRules.assert_completion_allowed(engine.state)

    def test_village_target_can_be_selected_and_healed(self) -> None:
        engine = new_engine()
        set_kind(engine, "village")
        ScenarioRules.initialize(engine.state)
        ScenarioRules.record_enemy_attack(engine.state, 4)
        before = ScenarioRules.client_view(engine.state)["objective"]["current"]
        card = {"phase": "utility", "effects": [{"type": "heal_objective", "amount": 3}]}

        events = ScenarioRules.record_card(engine.state, "p1", card, ["objective:villagers"])

        self.assertEqual(events[0]["type"], "objective_healed")
        self.assertEqual(ScenarioRules.client_view(engine.state)["objective"]["current"], before + 3)

    def test_raid_has_a_real_threat_loss_condition(self) -> None:
        engine = new_engine()
        set_kind(engine, "raid")
        ScenarioRules.initialize(engine.state)

        events = []
        for round_number in range(2, 8):
            engine.state.round_number = round_number
            events.extend(ScenarioRules.record_round_started(engine.state))

        self.assertEqual(ScenarioRules.client_view(engine.state)["status"], "failed")
        self.assertIn("scenario_objective_failed", [event["type"] for event in events])

    def test_hunt_requires_a_first_round_preparation_action(self) -> None:
        unprepared = new_engine()
        set_kind(unprepared, "hunt")
        ScenarioRules.initialize(unprepared.state)
        unprepared.state.round_number = 2
        events = ScenarioRules.record_round_started(unprepared.state)
        failed = next(event for event in events if event["type"] == "scenario_objective_failed")
        self.assertEqual(failed["reason"], "quarry_escaped")

        prepared = new_engine()
        set_kind(prepared, "hunt")
        ScenarioRules.initialize(prepared.state)
        ScenarioRules.record_card(prepared.state, "p1", {"phase": "utility", "effects": []})
        prepared.state.round_number = 2
        ScenarioRules.record_round_started(prepared.state)
        events = ScenarioRules.record_enemy_defeated(prepared.state, 0)
        self.assertIn("scenario_objective_succeeded", [event["type"] for event in events])
        ScenarioRules.assert_completion_allowed(prepared.state)

    def test_ruin_curse_is_managed_by_cleanse_and_changes_loot(self) -> None:
        engine = new_engine()
        set_kind(engine, "ruin")
        ScenarioRules.initialize(engine.state)
        for round_number in (2, 3, 4):
            engine.state.round_number = round_number
            ScenarioRules.record_round_started(engine.state)
        self.assertEqual(ScenarioRules.client_view(engine.state)["objective"]["current"], 3)

        events = ScenarioRules.record_card(
            engine.state,
            "p1",
            {"phase": "utility", "effects": [{"type": "cleanse", "amount": 2}]},
        )
        self.assertEqual(events[0]["amount"], 2)
        ScenarioRules.record_enemy_defeated(engine.state, 0)
        self.assertEqual(ScenarioRules.ruin_loot_rarity_bonus(engine.state), 1)

    def test_ambush_changes_opening_attack_and_fall_fails_objective(self) -> None:
        engine = new_engine()
        set_kind(engine, "ambush")
        ScenarioRules.initialize(engine.state)

        self.assertEqual(ScenarioRules.ambush_attack_dice_bonus(engine.state), 1)
        events = ScenarioRules.record_player_fallen(engine.state, "p1")
        failed = next(event for event in events if event["type"] == "scenario_objective_failed")
        self.assertEqual(failed["reason"], "opening_assault_felled:p1")

    def test_success_persists_campaign_consequence_and_survives_restore(self) -> None:
        engine = new_engine()
        set_kind(engine, "village")
        ScenarioRules.initialize(engine.state)
        ScenarioRules.record_enemy_defeated(engine.state, 0)

        restored = GameEngine.restore(engine.export(), CARDS, ITEMS, ENEMIES)
        consequence = restored.state.world["campaign_consequences"][0]
        self.assertEqual(consequence["outcome"], "success")
        self.assertEqual(consequence["faction_reputation"], 1)
        self.assertEqual(ScenarioRules.client_view(restored.state)["status"], "succeeded")


class WaveTransitionRulesTests(unittest.TestCase):
    def test_dot_or_trap_wave_kill_starts_a_clean_attack_round(self) -> None:
        engine = new_engine()
        state = engine.state
        old_round = state.round_number
        old_starter = state.starter_index
        state.phase_index = 3
        state.active_slot = 1
        state.passed_players[:] = state.turn_order
        for player in state.players.values():
            player.action_points = 0
            player.guard = 4
            player.bonus_block_dice = 2
            player.played_weapon_this_round = True

        events = WaveTransitionRules.after_round_resolution(state)

        self.assertEqual(state.phase, "attack")
        self.assertEqual(state.round_number, old_round + 1)
        self.assertEqual(state.starter_index, (old_starter + 1) % 2)
        self.assertEqual(state.active_slot, 0)
        self.assertEqual(state.passed_players, [])
        for player in state.players.values():
            self.assertEqual(player.action_points, 5)
            self.assertEqual(player.guard, 0)
            self.assertEqual(player.bonus_block_dice, 0)
            self.assertFalse(player.played_weapon_this_round)
        self.assertEqual(events[-1]["type"], "round_started")

    def test_wave_reset_is_round_resolution_only(self) -> None:
        """The integration hook is explicit so a mid-action kill cannot call it by accident."""
        self.assertFalse(hasattr(WaveTransitionRules, "after_card_resolution"))


if __name__ == "__main__":
    unittest.main()
