import json
import unittest
from pathlib import Path

from app.campaign_runtime import CampaignRuntime
from app.boss_contract import BossContract
from app.content import CardCatalog, EnemyCatalog, ItemCatalog


ROOT = Path(__file__).resolve().parents[2]
CARDS = CardCatalog(ROOT / "shared" / "cards.json")
ITEMS = ItemCatalog(ROOT / "shared" / "items.json")
ENEMIES = EnemyCatalog(ROOT / "shared" / "enemies.json")
LOADOUTS = {
    "p1": {"weapon": "axe", "magic": "ember"},
    "p2": {"weapon": "bow", "magic": "rune"},
}


def new_runtime(seed: int = 17) -> CampaignRuntime:
    return CampaignRuntime.new(
        campaign_id="campaign-test",
        seed=seed,
        loadouts=LOADOUTS,
        cards=CARDS,
        items=ITEMS,
        enemies=ENEMIES,
        campaign_length="expedition",
        world_tier=1,
    )


def finish_active_cinematics(runtime: CampaignRuntime) -> None:
    while runtime.cinematics.state.active is not None:
        cinematic_id = runtime.cinematics.state.active.cinematic_id
        runtime.cinematic_ack("p1", cinematic_id)
        runtime.cinematic_ack("p2", cinematic_id)


class CampaignRuntimeTests(unittest.TestCase):
    def test_new_campaign_is_media_gated_and_restore_is_viewer_safe(self) -> None:
        runtime = new_runtime()
        self.assertTrue(runtime.client_view("p1")["cinematics"]["gameplay_blocked"])
        finish_active_cinematics(runtime)
        restored = CampaignRuntime.restore(
            runtime.campaign_id,
            runtime.export(),
            cards=CARDS,
            items=ITEMS,
            enemies=ENEMIES,
            fallback_loadouts=LOADOUTS,
        )
        self.assertFalse(restored.client_view("p2")["cinematics"]["gameplay_blocked"])
        self.assertEqual(restored.export(), runtime.export())

    def test_final_contract_postgame_and_new_game_plus_are_one_closed_flow(self) -> None:
        runtime = new_runtime(29)
        finish_active_cinematics(runtime)
        runtime.game.state.scenario_index = len(runtime.game.state.world["route"]) - 1
        runtime.game.state.scenario_selected_id = runtime.game.state.world["route"][-1]["id"]
        runtime.game._start_scenario_encounter()
        runtime._ensure_final_contract()
        contract = runtime.boss_contract
        self.assertIsNotNone(contract)
        self.assertEqual(contract.active_targets, ("oath_gate",))

        # Oversized damage may advance exactly one contract stage, never skip it.
        runtime.game._apply_target_damage(["oath_gate"], 999)
        self.assertEqual(contract.state.stage, "wardens")
        for stage_targets in (
            list(contract.active_targets),
            list(contract.state.anchors),
            list(contract.state.armor_parts),
        ):
            for target_id in stage_targets:
                runtime.game._apply_target_damage([target_id], 999)
        self.assertEqual(contract.state.stage, "torn_world")
        for _ in range(3):
            runtime.game._apply_target_damage(["throneless"], 999)
        self.assertEqual(contract.state.stage, "final_oath")
        self.assertGreaterEqual(contract.state.oath_power, 12)

        # Ensure each player owns an eligible, distinct legacy choice.
        eligible = [
            item["id"] for item in ITEMS.items.values()
            if item["rarity"] in {"exceptional", "legendary", "unique"}
        ]
        runtime.game.state.players["p1"].inventory.append(eligible[0])
        runtime.game.state.players["p2"].inventory.append(eligible[1])

        for _attempt in range(12):
            for player in runtime.game.state.players.values():
                player.action_points = 5
            runtime.commit_final_oath("p1")
            events = runtime.commit_final_oath("p2")
            if any(event.get("success") for event in events if event.get("type") == "final_oath_resolved"):
                break
        self.assertTrue(contract.state.completed)
        self.assertIsNotNone(runtime.postgame)
        finish_active_cinematics(runtime)

        runtime.submit_ending("p1", "seal")
        runtime.submit_ending("p2", "seal")
        finish_active_cinematics(runtime)
        option1 = runtime.postgame.public_view("p1")["legacy_options"][0]
        option2 = runtime.postgame.public_view("p2")["legacy_options"][0]
        runtime.select_legacy("p1", option1)
        runtime.select_legacy("p2", option2)
        finish_active_cinematics(runtime)
        runtime.confirm_new_game_plus("p1")
        events = runtime.confirm_new_game_plus("p2")
        self.assertTrue(any(event["type"] == "new_game_plus_ready" for event in events))

        before_tier = runtime.game.state.world_tier
        events = runtime.start_new_game_plus()
        self.assertEqual(runtime.game.state.world_tier, before_tier + 1)
        self.assertIsNone(runtime.boss_contract)
        self.assertIsNone(runtime.postgame)
        self.assertTrue(any(event["type"] == "new_game_plus_started" for event in events))
        self.assertIn(option1, runtime.game.state.players["p1"].inventory)

    def test_history_and_checkpoint_exports_remain_bounded(self) -> None:
        runtime = new_runtime()
        finish_active_cinematics(runtime)
        runtime.game._record([{"type": "audit", "index": index} for index in range(2_000)])
        self.assertEqual(len(runtime.game.state.history), 500)
        encoded = json.dumps(runtime.export())
        self.assertLess(len(encoded), 2_000_000)
        self.assertNotIn('"checkpoint": {"seed"', json.dumps(runtime.game.state.checkpoint))

    def test_failed_final_oath_restores_a_playable_retry(self) -> None:
        runtime = new_runtime(4404)
        finish_active_cinematics(runtime)
        runtime.boss_contract = BossContract.new(4404, ("p1", "p2"), world_tier=2)
        runtime.game.attach_boss_contract(runtime.boss_contract)
        contract = runtime.boss_contract
        for _stage in range(4):
            for target_id in tuple(contract.active_targets):
                contract.apply_damage(target_id, 100_000, bypass_armor=True)
        for _arena in range(3):
            contract.apply_damage("throneless", 100_000)
        self.assertEqual(contract.state.stage, "final_oath")

        runtime.commit_final_oath("p1")
        events = runtime.commit_final_oath("p2")
        resolution = next(event for event in events if event["type"] == "final_oath_resolved")
        self.assertFalse(resolution["success"])
        self.assertTrue(any(event["type"] == "final_oath_retry_ready" for event in events))
        self.assertEqual(runtime.game.state.players["p1"].action_points, 5)
        self.assertEqual(runtime.game.state.players["p2"].action_points, 5)

    def test_boss_objectives_receive_runtime_status_and_trap_damage(self) -> None:
        runtime = new_runtime(73)
        finish_active_cinematics(runtime)
        runtime.boss_contract = BossContract.new(73, ("p1", "p2"), world_tier=1)
        runtime.game.attach_boss_contract(runtime.boss_contract)
        runtime.game._sync_boss_targets()
        target = runtime.game.state.world["combat_runtime"]["targets"]["oath_gate"]
        target["statuses"] = {"burning": 3, "trap_dice": 2}
        hp_before = runtime.boss_contract.state.gate.hp

        events = runtime.game._enemy_phase()

        self.assertLess(runtime.boss_contract.state.gate.hp, hp_before)
        self.assertTrue(any(event["type"] == "status_damage" for event in events))
        synced = runtime.game.state.world["combat_runtime"]["targets"]["oath_gate"]
        self.assertEqual(synced["statuses"].get("burning"), 2)

    def test_final_contract_normalizes_persisted_scenario_consequences(self) -> None:
        runtime = new_runtime(101)
        finish_active_cinematics(runtime)
        runtime.game.state.scenario_index = len(runtime.game.state.world["route"]) - 1
        runtime.game.state.scenario_selected_id = runtime.game.state.world["route"][-1]["id"]
        runtime.game.state.world["campaign_consequences"] = [
            {
                "scenario_id": "lost-caravan", "country_id": "nebelmark",
                "kind": "caravan", "unresolved_problem": True,
            },
            {
                "scenario_id": "saved-village", "country_id": "dornwall",
                "kind": "village", "unresolved_problem": False,
            },
        ]

        runtime._ensure_final_contract()

        self.assertEqual(
            runtime.boss_contract.state.unresolved_problems,
            ["nebelmark:caravan:lost-caravan"],
        )

    def test_entering_final_oath_opens_a_fresh_shared_action_window(self) -> None:
        runtime = new_runtime(303)
        finish_active_cinematics(runtime)
        for player in runtime.game.state.players.values():
            player.action_points = 1

        events = runtime._after_game_events([
            {"type": "boss_stage_changed", "stage": "final_oath"}
        ])

        self.assertTrue(any(event["type"] == "final_oath_ready" for event in events))
        self.assertTrue(all(player.action_points == 5 for player in runtime.game.state.players.values()))

    def test_card_riders_expire_cleanly_after_destroying_the_last_stage_target(self) -> None:
        runtime = new_runtime(404)
        finish_active_cinematics(runtime)
        runtime.boss_contract = BossContract.new(404, ("p1", "p2"), world_tier=1)
        runtime.game.attach_boss_contract(runtime.boss_contract)
        contract = runtime.boss_contract
        for target_id in tuple(contract.active_targets):
            contract.apply_damage(target_id, 100_000, bypass_armor=True)
        for target_id in tuple(contract.active_targets):
            contract.apply_damage(target_id, 100_000, bypass_armor=True)
        self.assertEqual(contract.state.stage, "anchors")
        for target_id in tuple(contract.active_targets)[:-1]:
            contract.apply_damage(target_id, 100_000, bypass_armor=True)
        runtime.game._sync_boss_targets()
        final_anchor = contract.active_targets[0]
        runtime.game._apply_target_damage([final_anchor], 100_000, bypass_armor=True)

        events: list[dict] = []
        runtime.game._apply_effect(
            runtime.game.state.players["p1"],
            {"id": "test_card"},
            {"type": "enemy_status", "status": "burning", "amount": 2},
            [final_anchor],
            events,
        )

        self.assertEqual(events, [])
        self.assertEqual(contract.state.stage, "armored_form")


if __name__ == "__main__":
    unittest.main()
