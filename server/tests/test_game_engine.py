import unittest
from pathlib import Path

from app.content import EnemyCatalog
from app.game_engine import CardCatalog, GameEngine, ItemCatalog, RuleViolation
from app.world_generator import generate_world


ROOT = Path(__file__).resolve().parents[2]
CATALOG = CardCatalog(ROOT / "shared" / "cards.json")
ITEMS = ItemCatalog(ROOT / "shared" / "items.json")
ENEMIES = EnemyCatalog(ROOT / "shared" / "enemies.json")




class GameEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = GameEngine.new(
            seed=42,
            loadouts={
                "player-one": {"weapon": "dual_blades", "magic": "ember"},
                "player-two": {"weapon": "axe", "magic": "rune"},
            },
            catalog=CATALOG,
            items=ITEMS,
            campaign_length="expedition",
        )

    def test_only_active_player_can_act(self) -> None:
        self.engine.state.players["player-two"].hand = ["eisenbrecher"]
        with self.assertRaises(RuleViolation):
            self.engine.play_card("player-two", "eisenbrecher")

    def test_card_consumes_action_points_and_moves_to_discard(self) -> None:
        player = self.engine.state.players["player-one"]
        player.hand = ["kreuzschnitt"]
        player.deck = ["sehnenhieb"]
        self.engine.state.enemy.block_dice = 0

        events = self.engine.play_card("player-one", "kreuzschnitt")

        self.assertEqual(player.action_points, 4)
        self.assertIn("kreuzschnitt", player.discard)
        self.assertIn("sehnenhieb", player.hand)
        self.assertEqual([event["purpose"] for event in events if event["type"] == "dice_rolled"], ["hit", "block"])

    def test_card_must_match_current_phase(self) -> None:
        self.engine.state.players["player-one"].hand = ["feldverband"]
        with self.assertRaises(RuleViolation):
            self.engine.play_card("player-one", "feldverband")

    def test_both_players_pass_before_phase_changes(self) -> None:
        first = self.engine.state.active_player
        second = next(player for player in self.engine.state.turn_order if player != first)

        first_events = self.engine.pass_phase(first)
        self.assertEqual(self.engine.state.phase, "attack")
        self.assertEqual(first_events[-1]["type"], "active_player_changed")

        second_events = self.engine.pass_phase(second)
        self.assertEqual(self.engine.state.phase, "defense")
        self.assertEqual(second_events[-1]["type"], "phase_changed")

    def test_action_points_persist_across_phases_and_reset_next_round(self) -> None:
        player = self.engine.state.players["player-one"]
        player.hand = ["kreuzschnitt"]
        self.engine.state.enemy.block_dice = 0
        self.engine.play_card("player-one", "kreuzschnitt")
        self.assertEqual(player.action_points, 4)

        for _phase in range(4):
            if self.engine.state.phase == "attack":
                self.engine.pass_phase("player-one")
                self.engine.pass_phase("player-two")
            else:
                first = self.engine.state.active_player
                second = next(value for value in self.engine.state.turn_order if value != first)
                self.engine.pass_phase(first)
                self.engine.pass_phase(second)
            if self.engine.state.round_number == 2:
                break

        self.assertEqual(self.engine.state.round_number, 2)
        self.assertEqual(player.action_points, 5)
        self.assertEqual(self.engine.state.phase, "attack")

    def test_weapon_and_talent_increase_attack_dice(self) -> None:
        player = self.engine.state.players["player-one"]
        player.inventory.append("duelist_hooks")
        player.equipment["weapon"] = "duelist_hooks"
        player.talents["hit_dice"] = 1
        player.hand = ["kreuzschnitt"]
        self.engine.state.enemy.block_dice = 0

        events = self.engine.play_card("player-one", "kreuzschnitt")
        hit_roll = next(event for event in events if event.get("purpose") == "hit")
        expected = 3 + ITEMS.get("duelist_hooks")["bonuses"]["attack_dice"] + 1
        self.assertEqual(len(hit_roll["values"]), expected)

    def test_marked_enemy_adds_one_die_and_consumes_mark(self) -> None:
        player = self.engine.state.players["player-one"]
        player.hand = ["kreuzschnitt"]
        self.engine.state.enemy.block_dice = 0
        self.engine.state.enemy.statuses["marked"] = 1

        events = self.engine.play_card("player-one", "kreuzschnitt")

        hit_roll = next(event for event in events if event.get("purpose") == "hit")
        self.assertEqual(len(hit_roll["values"]), 4)
        self.assertNotIn("marked", self.engine.state.enemy.statuses)

    def test_player_death_restores_both_players_to_scenario_checkpoint(self) -> None:
        self.engine.state.players["player-one"].hp = 2
        self.engine.state.players["player-two"].hp = 11

        events = self.engine.apply_player_damage("player-one", 10)

        self.assertEqual(events[-1]["type"], "rollback")
        self.assertEqual(self.engine.state.players["player-one"].hp, 30)
        self.assertEqual(self.engine.state.players["player-two"].hp, 30)
        self.assertEqual(self.engine.state.rollback_count, 1)

    def test_last_oath_prevents_one_rollback(self) -> None:
        player = self.engine.state.players["player-one"]
        player.statuses["last_oath"] = 1
        player.hp = 2

        events = self.engine.apply_player_damage("player-one", 10)

        self.assertEqual(player.hp, 1)
        self.assertEqual(events[-1]["type"], "last_oath_triggered")
        self.assertEqual(self.engine.state.rollback_count, 0)

    def test_dice_are_server_generated_and_reproducible(self) -> None:
        loadouts = {
            "archer": {"weapon": "bow", "magic": "ember"},
            "guardian": {"weapon": "axe", "magic": "rune"},
        }
        first = GameEngine.new(777, loadouts, CATALOG, ITEMS, "expedition")
        second = GameEngine.new(777, loadouts, CATALOG, ITEMS, "expedition")
        for engine in (first, second):
            engine.state.players["archer"].hand = ["jagdschuss"]
            engine.state.players["archer"].deck = ["ruhige_hand"]
            engine.state.enemy.block_dice = 0

        first_events = first.play_card("archer", "jagdschuss")
        second_events = second.play_card("archer", "jagdschuss")
        first_rolls = [event for event in first_events if event["type"] == "dice_rolled"]
        second_rolls = [event for event in second_events if event["type"] == "dice_rolled"]

        self.assertEqual(first_rolls, second_rolls)
        self.assertEqual([event["purpose"] for event in first_rolls], ["hit", "block"])
        self.assertTrue(all(event["sides"] == 12 for event in first_rolls))

    def test_export_restore_keeps_authoritative_state_and_client_metadata(self) -> None:
        restored = GameEngine.restore(self.engine.export(), CATALOG, ITEMS)
        self.assertEqual(restored.export(), self.engine.export())
        view = restored.client_view()
        self.assertEqual(view["phase"], "attack")
        self.assertEqual(view["active_player"], "player-one")
        self.assertEqual(view["scenario"]["index"], 0)
        self.assertTrue(view["card_definitions"])

    def test_scenario_victory_heals_party_and_offers_boss_loot(self) -> None:
        self.engine.state.scenario_index = 2
        self.engine.state.enemy = self.engine._enemy_for_scenario(self.engine.state.scenario)
        self.engine.state.enemy_queue.clear()
        self.engine.state.enemy.hp = 1
        self.engine.state.enemy.block_dice = 0
        self.engine.state.players["player-one"].hp = 7
        self.engine.state.players["player-one"].hand = ["kreuzschnitt"]

        events = self.engine.play_card("player-one", "kreuzschnitt")

        self.assertEqual(self.engine.state.players["player-one"].hp, 30)
        self.assertEqual(len(self.engine.state.pending_loot), 3)
        offered = next(event for event in events if event["type"] == "loot_offered")
        self.assertTrue(any(item["rarity"] in {"exceptional", "legendary", "unique"} for item in offered["items"]))

    def test_enemy_wave_advances_without_healing_or_loot(self) -> None:
        self.engine.state.scenario_index = 1
        self.engine.state.scenario_selected_id = self.engine.state.world["route"][1]["id"]
        self.engine._start_scenario_encounter()
        player = self.engine.state.players["player-one"]
        player.hp = 9
        self.assertTrue(self.engine.state.enemy_queue)
        for target in self.engine.state.world["combat_runtime"]["targets"].values():
            target["hp"] = 0
            target["alive"] = False
        self.engine.state.enemy.hp = 0

        events = self.engine._resolve_enemy_defeat()

        self.assertIn("enemy_spawned", [event["type"] for event in events])
        self.assertEqual(player.hp, 9)
        self.assertFalse(self.engine.state.pending_loot)

    def test_enemy_intent_changes_combat_profile(self) -> None:
        self.engine.state.enemy.intents = ["guard"]
        self.engine.state.enemy.attack_dice = 0
        before = self.engine.state.enemy.block_dice

        events = self.engine._enemy_phase()

        intent = next(event for event in events if event["type"] == "enemy_intent")
        self.assertEqual(intent["intent"], "guard")
        self.assertEqual(self.engine.state.enemy.block_dice, before)
        self.assertEqual(self.engine.state.enemy.statuses["guard_bonus"], 1)

    def test_physical_damage_is_absorbed_by_enemy_armor(self) -> None:
        events: list[dict] = []
        self.engine.state.enemy.hp = 20
        self.engine.state.enemy.armor = 3

        self.engine._damage_enemy(5, events)

        self.assertEqual(self.engine.state.enemy.hp, 18)
        self.assertEqual(self.engine.state.enemy.armor, 0)
        self.assertEqual(events[-1]["absorbed"], 3)

    def test_scenario_completion_unlocks_progression_cards(self) -> None:
        before = {key: len(player.discard) for key, player in self.engine.state.players.items()}

        events = self.engine._complete_scenario()

        unlocked = [event for event in events if event["type"] == "card_unlocked"]
        self.assertEqual(len(unlocked), 2)
        for key, player in self.engine.state.players.items():
            self.assertGreater(len(player.discard), before[key])

    def test_expedition_can_complete_with_baseline_strategy(self) -> None:
        for seed in range(3):
            engine = GameEngine.new(
                seed,
                {"p1": {"weapon": "axe", "magic": "ember"}, "p2": {"weapon": "bow", "magic": "rune"}},
                CATALOG, ITEMS, "expedition", 1, ENEMIES,
            )
            actions = 0
            while not engine.state.campaign_complete and actions < 15_000:
                actions += 1
                runtime = engine.state.world.get("combat_runtime", {})
                cooperation = runtime.get("coop_action")
                if cooperation is not None:
                    engine.confirm_cooperation(cooperation["partners"][0], True)
                    continue
                reaction = runtime.get("reaction_window")
                if reaction is not None:
                    for player_id in reaction["responders"]:
                        if player_id not in reaction["responses"]:
                            engine.react(player_id, None)
                    continue
                if engine.state.awaiting_scenario_choice:
                    scenario_id = engine.state.available_scenarios[0]["id"]
                    for player_id in engine.state.players:
                        engine.choose_scenario(player_id, scenario_id)
                    continue
                if engine.state.pending_loot:
                    for player_id in list(engine.state.players):
                        if player_id not in engine.state.loot_claims and engine.state.pending_loot:
                            engine.claim_loot(player_id, engine.state.pending_loot[0])
                    continue
                player = engine.state.players[engine.state.active_player]
                objective = engine.state.world.get("scenario_runtime", {}).get("objective", {})
                if (
                    objective.get("kind") == "prepare_hunt"
                    and objective.get("current", 0) < 1
                    and engine.state.phase == "utility"
                    and player.action_points >= 1
                ):
                    engine.perform_scenario_action(player.profile_id, "prepare_hunt")
                    continue
                playable = [
                    card_id for card_id in player.hand
                    if CATALOG.get(card_id)["phase"] == engine.state.phase
                    and CATALOG.get(card_id)["action_point_cost"] <= player.action_points
                    and CATALOG.get(card_id).get("kind") != "reaction"
                ]
                reserve = 2 if engine.state.phase == "attack" else 1 if engine.state.phase == "magic" else 0
                playable = [card_id for card_id in playable if player.action_points - CATALOG.get(card_id)["action_point_cost"] >= reserve]
                ally = next(value for key, value in engine.state.players.items() if key != player.profile_id)
                playable = [
                    card_id for card_id in playable
                    if CATALOG.get(card_id).get("kind") != "cooperation" or ally.action_points >= 1
                ]
                playable.sort(
                    key=lambda card_id: any(effect["type"] in {"dice_attack", "dice_magic_damage"} for effect in CATALOG.get(card_id)["effects"]),
                    reverse=True,
                )
                if playable:
                    card = CATALOG.get(playable[0])
                    effects = {effect["type"] for effect in card["effects"]}
                    target_ids = None
                    if effects & {"dice_attack", "dice_magic_damage", "enemy_status", "armor_break", "set_trap"}:
                        living = [target["id"] for target in engine.client_view()["combat"]["targets"]]
                        maximum = 3 if playable[0] in {"tausend_schnitte", "sturm_des_henkers", "pfeilregen", "sonnenhagel", "bolzenhagel", "salve", "feuersturm", "mondlose_nacht", "purpurflut"} else 1
                        target_ids = living[:maximum]
                    engine.play_card(player.profile_id, playable[0], target_ids=target_ids)
                else:
                    engine.pass_phase(player.profile_id)
            self.assertTrue(engine.state.campaign_complete, f"Seed {seed} did not complete after {actions} actions")

    def test_equipped_weapon_grants_its_card(self) -> None:
        player = self.engine.state.players["player-one"]
        player.hand.clear()
        player.deck.clear()
        player.discard.clear()
        player.exhausted.clear()
        item = ITEMS.get("erste_und_letzte_klinge")

        equipped = self.engine._equip_if_upgrade(player, item)

        self.assertTrue(equipped)
        self.assertIn(item["granted_card"], player.discard)

    def test_manual_equipment_changes_are_limited_to_scenario_breaks(self) -> None:
        player = self.engine.state.players["player-one"]
        item_id = next(
            item["id"] for item in ITEMS.items.values()
            if item.get("weapon_school") == "dual_blades" and item["id"] != player.equipment.get("weapon")
        )
        player.inventory.append(item_id)
        with self.assertRaises(RuleViolation):
            self.engine.equip_item("player-one", item_id)

        self.engine.state.pending_loot = ["break_marker"]
        events = self.engine.equip_item("player-one", item_id)
        self.assertEqual(events[-1]["type"], "item_equipped")
        self.assertEqual(player.equipment["weapon"], item_id)

    def test_both_players_claim_loot_before_next_scenario(self) -> None:
        self.engine.state.enemy.hp = 0
        self.engine._complete_scenario()
        first_item, second_item = self.engine.state.pending_loot[:2]

        self.engine.claim_loot("player-one", first_item)
        events = self.engine.claim_loot("player-two", second_item)

        self.assertEqual(self.engine.state.scenario_index, 1)
        self.assertFalse(self.engine.state.pending_loot)
        self.assertEqual(events[-1]["type"], "scenario_choice_required")
        scenario_id = self.engine.state.available_scenarios[0]["id"]
        self.engine.choose_scenario("player-one", scenario_id)
        events = self.engine.choose_scenario("player-two", scenario_id)
        self.assertEqual(events[-1]["type"], "scenario_started")
        self.assertEqual(self.engine.state.checkpoint["scenario_index"], 1)


class WorldGeneratorTests(unittest.TestCase):
    def test_world_is_deterministic_and_ends_at_weltennaht(self) -> None:
        first = generate_world(1234, "saga", 2)
        second = generate_world(1234, "saga", 2)
        self.assertEqual(first, second)
        self.assertEqual(len(first["countries"]), 13)
        self.assertEqual(len(first["route"]), 39)
        self.assertTrue(first["route"][-1]["is_final"])


class ContentTests(unittest.TestCase):
    def test_catalogs_have_full_content_and_all_six_rarities(self) -> None:
        self.assertGreaterEqual(len(CATALOG.cards), 120)
        self.assertGreaterEqual(len(ITEMS.items), 120)
        self.assertGreaterEqual(len(ENEMIES.enemies), 120)
        self.assertEqual({card["rarity"] for card in CATALOG.cards.values()}, {"normal", "rare", "enhanced", "exceptional", "legendary", "unique"})
        self.assertEqual({item["rarity"] for item in ITEMS.items.values()}, {"normal", "rare", "enhanced", "exceptional", "legendary", "unique"})

    def test_every_catalog_entry_has_an_existing_art_asset(self) -> None:
        for entry in list(CATALOG.cards.values()) + list(ITEMS.items.values()) + list(ENEMIES.enemies.values()):
            path = ROOT / "client" / entry["art"].removeprefix("res://")
            self.assertTrue(path.is_file(), path)

    def test_every_item_and_enemy_has_a_unique_existing_3d_model(self) -> None:
        entries = list(ITEMS.items.values()) + list(ENEMIES.enemies.values())
        models = [entry["model"] for entry in entries]
        self.assertEqual(len(models), len(set(models)))
        for model in models:
            path = ROOT / "client" / model.removeprefix("res://")
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.read_bytes()[:4], b"glTF")

    def test_each_country_has_ten_distinct_enemies_and_a_boss(self) -> None:
        for country in ENEMIES._by_country:
            regional = ENEMIES.for_country(country)
            self.assertGreaterEqual(len(regional), 10)
            self.assertEqual(len({enemy["name"] for enemy in regional}), len(regional))
            self.assertTrue(any(enemy["boss"] for enemy in regional))

    def test_every_loadout_has_cards_for_all_four_phases(self) -> None:
        for weapon in ("dual_blades", "axe", "bow", "crossbow"):
            for magic in ("rune", "ember", "veil", "blood"):
                deck = CATALOG.starter_deck(weapon, magic)
                phases = {CATALOG.get(card_id)["phase"] for card_id in deck}
                self.assertEqual(phases, {"attack", "defense", "magic", "utility"})

    def test_every_scenario_has_a_landmark_and_two_3d_props(self) -> None:
        world = generate_world(2468, "saga", 3, ENEMIES)
        for scenario in world["route"]:
            self.assertTrue(scenario["landmark_model"].endswith(".glb"))
            self.assertEqual(len(scenario["prop_models"]), 2)
            for resource_path in [scenario["landmark_model"], *scenario["prop_models"]]:
                path = ROOT / "client" / resource_path.removeprefix("res://")
                self.assertTrue(path.is_file(), path)


if __name__ == "__main__":
    unittest.main()
