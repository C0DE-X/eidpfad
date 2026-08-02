import copy
import unittest
from pathlib import Path

from app.combat_actions import (
    CooperationRules,
    EffectRules,
    IntentRules,
    ReactionRules,
    StatusRules,
    TalentRules,
    TargetRules,
)
from app.content import CardCatalog, EnemyCatalog, ItemCatalog
from app.errors import RuleViolation
from app.game_engine import GameEngine


ROOT = Path(__file__).resolve().parents[2]
CARDS = CardCatalog(ROOT / "shared" / "cards.json")
ITEMS = ItemCatalog(ROOT / "shared" / "items.json")
ENEMIES = EnemyCatalog(ROOT / "shared" / "enemies.json")


def new_engine() -> GameEngine:
    return GameEngine.new(
        321,
        {
            "p1": {"weapon": "dual_blades", "magic": "ember"},
            "p2": {"weapon": "axe", "magic": "rune"},
        },
        CARDS,
        ITEMS,
        "expedition",
        1,
        ENEMIES,
    )


class TargetRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = new_engine()
        second = copy.deepcopy(self.engine.state.enemy)
        second.enemy_id += "-second"
        second.name += " II"
        self.second_id = second.enemy_id
        TargetRules.initialize(self.engine.state, [self.engine.state.enemy, second])

    def test_single_target_card_requires_an_explicit_choice_when_two_are_alive(self) -> None:
        card = CARDS.get("kreuzschnitt")
        with self.assertRaises(RuleViolation):
            TargetRules.select(self.engine.state, "p1", card, None)
        selected = TargetRules.select(self.engine.state, "p1", card, self.second_id)
        self.assertEqual(selected, [self.second_id])

    def test_area_card_accepts_multiple_unique_targets(self) -> None:
        card = CARDS.get("tausend_schnitte")
        ids = [self.engine.state.enemy.enemy_id, self.second_id]
        self.assertEqual(TargetRules.select(self.engine.state, "p1", card, ids), ids)
        with self.assertRaises(RuleViolation):
            TargetRules.select(self.engine.state, "p1", card, [ids[0], ids[0]])

    def test_damage_and_armor_break_apply_to_selected_targets_only(self) -> None:
        primary_id = self.engine.state.enemy.enemy_id
        before_primary = self.engine.state.enemy.hp
        second_before = next(target for target in TargetRules.client_view(self.engine.state) if target["id"] == self.second_id)["hp"]

        TargetRules.armor_break(self.engine.state, [self.second_id], 99)
        events = TargetRules.damage(self.engine.state, [self.second_id], 3)

        self.assertEqual(self.engine.state.enemy.hp, before_primary)
        second = next(target for target in TargetRules.client_view(self.engine.state) if target["id"] == self.second_id)
        self.assertEqual(second["hp"], second_before - 3)
        self.assertEqual(events[0]["target"], self.second_id)

    def test_team_and_ally_targeting_are_unambiguous(self) -> None:
        heal_ally = CARDS.get("feldverband")
        team = CARDS.get("wachposten")
        self.assertEqual(TargetRules.select(self.engine.state, "p1", heal_ally, "p2"), ["p2"])
        self.assertEqual(TargetRules.select(self.engine.state, "p1", team, None), ["p1", "p2"])


class IntentAndReactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = new_engine()
        # New encounters intentionally publish an intent immediately. These focused
        # rule tests start from an explicit pre-telegraph state.
        self.engine.state.world["combat_runtime"]["announced_intent"] = None

    def test_intent_is_announced_once_before_resolution_with_targets_and_numbers(self) -> None:
        self.engine.state.enemy.intents = ["pressure"]
        events = IntentRules.announce(self.engine.state)

        event = events[0]
        self.assertEqual(event["type"], "enemy_intent_announced")
        self.assertEqual(event["targets"], ["p1", "p2"])
        self.assertGreaterEqual(event["attack_dice"], self.engine.state.enemy.attack_dice + 1)
        self.assertEqual(IntentRules.announce(self.engine.state), [])
        self.assertEqual(IntentRules.require_announced(self.engine.state)["intent"], "pressure")

    def test_enemy_intent_cannot_resolve_without_telegraph(self) -> None:
        with self.assertRaises(RuleViolation):
            IntentRules.consume(self.engine.state)

    def test_reaction_window_requires_both_players_and_only_reaction_cards(self) -> None:
        IntentRules.announce(self.engine.state)
        ReactionRules.open(self.engine.state)
        self.engine.state.players["p1"].hand = ["blitzreflex", "gekreuzte_klingen"]

        with self.assertRaises(RuleViolation):
            ReactionRules.respond(self.engine.state, "p1", "gekreuzte_klingen", CARDS)
        ReactionRules.respond(self.engine.state, "p1", "blitzreflex", CARDS)
        with self.assertRaises(RuleViolation):
            ReactionRules.consume(self.engine.state)
        events = ReactionRules.respond(self.engine.state, "p2", None, CARDS)
        self.assertEqual(events[-1]["type"], "reaction_window_ready")

        reactions = ReactionRules.consume(self.engine.state)
        self.assertEqual(reactions[0]["card_id"], "blitzreflex")
        self.assertEqual(reactions[0]["actor"], "p1")

    def test_reaction_window_survives_export_restore(self) -> None:
        IntentRules.announce(self.engine.state)
        ReactionRules.open(self.engine.state)
        ReactionRules.respond(self.engine.state, "p1", None, CARDS)

        restored = GameEngine.restore(self.engine.export(), CARDS, ITEMS, ENEMIES)
        ReactionRules.respond(restored.state, "p2", None, CARDS)
        self.assertEqual(ReactionRules.consume(restored.state), [])


class CooperationRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = new_engine()
        self.engine.state.players["p1"].hand = ["blutsbruder"]

    def test_cooperation_does_not_resolve_without_partner_confirmation(self) -> None:
        events = CooperationRules.propose(self.engine.state, "p1", "blutsbruder", CARDS)
        self.assertEqual(events[0]["type"], "cooperation_proposed")
        with self.assertRaises(RuleViolation):
            CooperationRules.consume(self.engine.state)
        with self.assertRaises(RuleViolation):
            CooperationRules.respond(self.engine.state, "p1", True)

        events = CooperationRules.respond(self.engine.state, "p2", True)
        self.assertEqual(events[0]["type"], "cooperation_confirmed")
        action = CooperationRules.consume(self.engine.state)
        self.assertEqual(action["actor"], "p1")
        self.assertEqual(action["card_id"], "blutsbruder")

    def test_rejected_cooperation_can_be_cleared_without_spending_card(self) -> None:
        CooperationRules.propose(self.engine.state, "p1", "blutsbruder", CARDS)
        CooperationRules.respond(self.engine.state, "p2", False)
        CooperationRules.clear_rejected(self.engine.state)
        self.assertIn("blutsbruder", self.engine.state.players["p1"].hand)
        CooperationRules.propose(self.engine.state, "p1", "blutsbruder", CARDS)


class StatusAndEffectRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = new_engine()

    def test_assassin_and_controller_make_bleeding_and_poison_reachable(self) -> None:
        player = self.engine.state.players["p1"]
        enemy = self.engine.state.enemy
        enemy.role = "assassin"
        events = StatusRules.apply_enemy_hit(enemy, player, "strike", 1)
        self.assertIn("bleeding", player.statuses)
        self.assertIn("bleeding", [event["status"] for event in events])

        enemy.role = "controller"
        StatusRules.apply_enemy_hit(enemy, player, "pressure", 1)
        self.assertIn("poisoned", player.statuses)

    def test_bound_reduces_and_is_consumed_by_next_player_roll(self) -> None:
        player = self.engine.state.players["p1"]
        player.statuses["bound"] = 3
        modifier, events = StatusRules.consume_player_roll_penalty(player, "hit")
        self.assertEqual(modifier, -2)
        self.assertNotIn("bound", player.statuses)
        self.assertEqual(events[0]["type"], "status_consumed")

    def test_played_weapon_flag_contributes_to_cooperative_combo(self) -> None:
        player = self.engine.state.players["p1"]
        self.assertEqual(StatusRules.weapon_combo_bonus(player), 0)
        player.played_weapon_this_round = True
        self.assertEqual(StatusRules.weapon_combo_bonus(player), 1)

    def test_healing_bonus_comes_from_healer_not_target(self) -> None:
        healer = self.engine.state.players["p1"]
        target = self.engine.state.players["p2"]
        target.hp = 10
        events = EffectRules.heal(self.engine.state, healer.profile_id, [target.profile_id], 4, {"healing": 3})
        self.assertEqual(target.hp, 17)
        self.assertEqual(events[0]["source"], "p1")

    def test_player_ward_dice_are_rolled_and_reduce_incoming_magic(self) -> None:
        player = self.engine.state.players["p1"]
        events = []

        def fixed_roll(actor, count, threshold, purpose, output):
            self.assertEqual((actor, count, threshold, purpose), ("p1", 2, 8, "player_ward"))
            output.append({"type": "dice_rolled", "purpose": purpose})
            return 2, 0

        remaining = EffectRules.resolve_player_ward(player, 3, {"ward_dice": 2}, fixed_roll, events)
        self.assertEqual(remaining, 1)
        self.assertEqual(events[-1]["type"], "player_ward_resolved")

    def test_talents_have_an_authoritative_unlock_path(self) -> None:
        player = self.engine.state.players["p1"]
        event = TalentRules.unlock(player, "weapon_training")
        self.assertEqual(player.talents["hit_dice"], 1)
        self.assertEqual(event["type"], "talent_unlocked")
        with self.assertRaises(RuleViolation):
            TalentRules.unlock(player, "weapon_training")

    def test_direct_armor_break_and_team_heal_are_reachable_from_content(self) -> None:
        armor_effects = CARDS.get("riss_im_panzer")["effects"]
        healing_effects = CARDS.get("runenheilung")["effects"]
        self.assertIn("armor_break", [effect["type"] for effect in armor_effects])
        self.assertIn("heal_all", [effect["type"] for effect in healing_effects])


if __name__ == "__main__":
    unittest.main()
