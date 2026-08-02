#!/usr/bin/env python3
"""Play one complete authoritative campaign through ending, legacy and NG+."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.campaign_runtime import CampaignRuntime  # noqa: E402
from app.content import CardCatalog, EnemyCatalog, ItemCatalog  # noqa: E402


AREA_CARDS = {
    "tausend_schnitte", "sturm_des_henkers", "pfeilregen", "sonnenhagel",
    "bolzenhagel", "salve", "feuersturm", "mondlose_nacht", "purpurflut",
}
HOST = "p1"
PARTNER = "p2"


class ReleaseBot:
    def __init__(
        self,
        seed: int,
        campaign_length: str,
        action_limit: int,
        game_mode: str,
        host_weapon: str = "longsword",
        partner_weapon: str = "bow",
    ) -> None:
        self.cards = CardCatalog(ROOT / "shared" / "cards.json")
        self.items = ItemCatalog(ROOT / "shared" / "items.json")
        self.enemies = EnemyCatalog(ROOT / "shared" / "enemies.json")
        self.player_ids = (HOST,) if game_mode == "singleplayer" else (HOST, PARTNER)
        loadouts = {HOST: {"weapon": host_weapon, "magic": "ember"}}
        if game_mode == "multiplayer":
            loadouts[PARTNER] = {"weapon": partner_weapon, "magic": "rune"}
        self.runtime = CampaignRuntime.new(
            campaign_id=f"release-playtest-{seed}",
            seed=seed,
            loadouts=loadouts,
            cards=self.cards,
            items=self.items,
            enemies=self.enemies,
            campaign_length=campaign_length,
            world_tier=1,
            game_mode=game_mode,
        )
        self.action_limit = action_limit
        self.actions = 0
        self.events: Counter[str] = Counter()
        self.completed_scenarios: set[str] = set()
        self.boss_stages: set[str] = set()

    def take(self, events: list[dict[str, Any]]) -> None:
        self.actions += 1
        for event in events:
            event_type = str(event.get("type", "unknown"))
            self.events[event_type] += 1
            if event_type == "scenario_completed":
                self.completed_scenarios.add(str(event.get("scenario", event.get("scenario_id", self.runtime.game.state.scenario.get("id", "")))))
            if event_type == "boss_stage_changed":
                self.boss_stages.add(str(event.get("stage", "")))

    def clear_media(self) -> None:
        while self.runtime.cinematics.state.active is not None:
            cinematic_id = self.runtime.cinematics.state.active.cinematic_id
            for player_id in self.player_ids:
                active = self.runtime.cinematics.state.active
                if active is not None and player_id not in active.acknowledged_players:
                    self.take(self.runtime.cinematic_ack(player_id, cinematic_id))

    def run(self) -> dict[str, Any]:
        original_scenario_count = len(self.runtime.game.state.world["route"])
        while self.actions < self.action_limit:
            self.clear_media()
            if self._postgame_action():
                if self.runtime.game.state.world_tier == 2 and self.runtime.postgame is None:
                    break
                continue
            if self._final_oath_action() or self._protocol_window_action() or self._between_scenario_action():
                continue
            self._combat_action()
        else:
            raise RuntimeError(f"Virtual playthrough exceeded {self.action_limit} actions")

        required_stages = {"wardens", "anchors", "armored_form", "torn_world", "final_oath", "defeated"}
        if self.runtime.game.state.world_tier != 2:
            raise RuntimeError("New Game+ did not start")
        if self.events["ending_resolved"] != 1 or self.events["legacy_transfer_ready"] != 1:
            raise RuntimeError("Postgame did not resolve exactly once")
        # The defeated transition is represented by final_oath_resolved rather than a
        # boss_stage_changed event, so verify it through its dedicated event.
        observed = self.boss_stages | ({"defeated"} if self.events["final_oath_resolved"] else set())
        if not required_stages <= observed:
            raise RuntimeError(f"Boss stages missing: {sorted(required_stages - observed)}")
        return {
            "status": "complete",
            "seed": int(self.runtime.game.state.seed),
            "campaign_length": self.runtime.game.state.world.get("campaign_length", "unknown"),
            "game_mode": self.runtime.game_mode,
            "actions": self.actions,
            "scenario_count": original_scenario_count,
            "scenario_completions": self.events["scenario_completed"],
            "rollbacks": self.events["rollback"],
            "boss_stages": sorted(observed),
            "final_oath_attempts": self.events["final_oath_resolved"],
            "cinematics_completed": self.events["cinematic_completed"],
            "ending": "seal",
            "legacy_transfer": self.events["legacy_transfer_ready"] == 1,
            "new_world_tier": self.runtime.game.state.world_tier,
        }

    def _postgame_action(self) -> bool:
        postgame = self.runtime.postgame
        if postgame is None:
            return False
        if postgame.state.phase == "ending_vote":
            for player_id in self.player_ids:
                if player_id not in postgame.state.ending_votes:
                    self.take(self.runtime.submit_ending(player_id, "seal"))
        elif postgame.state.phase == "legacy_selection":
            for player_id in self.player_ids:
                if player_id not in postgame.state.legacy_selections:
                    self.take(self.runtime.select_legacy(player_id, postgame.state.legacy_options[player_id][0]))
        elif postgame.state.phase == "new_game_plus":
            for player_id in self.player_ids:
                if player_id not in postgame.state.new_game_confirmations:
                    self.take(self.runtime.confirm_new_game_plus(player_id))
        elif postgame.state.phase == "complete":
            self.take(self.runtime.start_new_game_plus())
            self.clear_media()
        return True

    def _final_oath_action(self) -> bool:
        contract = self.runtime.boss_contract
        if contract is None or contract.state.stage != "final_oath":
            return False
        for player_id in self.player_ids:
            if player_id not in contract.state.final_oath_contributions:
                self.take(self.runtime.commit_final_oath(player_id))
        return True

    def _protocol_window_action(self) -> bool:
        combat = self.runtime.game.state.world.get("combat_runtime", {})
        cooperation = combat.get("coop_action")
        if cooperation is not None:
            self.take(self.runtime.confirm_cooperation(str(cooperation["partners"][0]), True))
            return True
        reaction = combat.get("reaction_window")
        if reaction is not None:
            for player_id in reaction["responders"]:
                if player_id not in reaction["responses"]:
                    self.take(self.runtime.react(str(player_id), None, None))
            return True
        return False

    def _between_scenario_action(self) -> bool:
        state = self.runtime.game.state
        if state.awaiting_scenario_choice:
            scenario_id = str(state.available_scenarios[0]["id"])
            for player_id in self.player_ids:
                if player_id not in state.scenario_votes:
                    self.take(self.runtime.choose_scenario(player_id, scenario_id))
            return True
        if state.pending_loot:
            for player_id in self.player_ids:
                if player_id not in state.loot_claims and state.pending_loot:
                    self.take(self.runtime.claim_loot(player_id, state.pending_loot[0]))
            return True
        return False

    def _combat_action(self) -> None:
        game = self.runtime.game
        state = game.state
        player = state.players[state.active_player]
        objective = state.world.get("scenario_runtime", {}).get("objective", {})
        if (
            objective.get("kind") == "prepare_hunt"
            and objective.get("current", 0) < 1
            and state.phase == "utility"
            and player.action_points >= 1
        ):
            self.take(self.runtime.perform_scenario_action(player.profile_id, "prepare_hunt"))
            return

        playable = [
            card_id for card_id in player.hand
            if self.cards.get(card_id)["phase"] == state.phase
            and self.cards.get(card_id)["action_point_cost"] <= player.action_points
            and self.cards.get(card_id).get("kind") != "reaction"
        ]
        reserve = 2 if state.phase == "attack" else 1 if state.phase == "magic" else 0
        needs_hunt_preparation = (
            objective.get("kind") == "prepare_hunt"
            and objective.get("current", 0) < 1
            and state.round_number == 1
            and state.phase != "utility"
        )
        if needs_hunt_preparation:
            reserve = max(reserve, 1)
        playable = [
            card_id for card_id in playable
            if player.action_points - self.cards.get(card_id)["action_point_cost"] >= reserve
        ]
        allies = [value for key, value in state.players.items() if key != player.profile_id]
        if allies:
            playable = [
                card_id for card_id in playable
                if self.cards.get(card_id).get("kind") != "cooperation" or allies[0].action_points >= 1
            ]
        playable.sort(
            key=lambda card_id: any(
                effect["type"] in {"dice_attack", "dice_magic_damage"}
                for effect in self.cards.get(card_id)["effects"]
            ),
            reverse=True,
        )
        if not playable:
            self.take(self.runtime.pass_phase(player.profile_id))
            return

        card_id = playable[0]
        card = self.cards.get(card_id)
        effect_types = {effect["type"] for effect in card["effects"]}
        target_ids: list[str] | None = None
        if effect_types & {"dice_attack", "dice_magic_damage", "enemy_status", "armor_break", "set_trap"}:
            living = [target["id"] for target in game.client_view()["combat"]["targets"]]
            target_ids = living[:3 if card_id in AREA_CARDS else 1]
        self.take(self.runtime.play_card(player.profile_id, card_id, target_ids=target_ids))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--campaign-length", choices=("expedition", "fieldzug", "saga"), default="expedition")
    parser.add_argument("--game-mode", choices=("singleplayer", "multiplayer"), default="multiplayer")
    parser.add_argument("--host-weapon", choices=("dual_blades", "axe", "bow", "crossbow", "longsword"), default="longsword")
    parser.add_argument("--partner-weapon", choices=("dual_blades", "axe", "bow", "crossbow", "longsword"), default="bow")
    parser.add_argument("--action-limit", type=int, default=25_000)
    args = parser.parse_args()
    report = ReleaseBot(
        args.seed,
        args.campaign_length,
        args.action_limit,
        args.game_mode,
        args.host_weapon,
        args.partner_weapon,
    ).run()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
