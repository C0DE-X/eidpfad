from __future__ import annotations

import copy
import hashlib
import random
from dataclasses import asdict
from typing import Any

from .boss_contract import BossContract, FINAL_OATH_CARD_ID, filter_progression_rewards
from .combat_actions import (
    CooperationRules,
    EffectRules,
    IntentRules,
    ReactionRules,
    StatusRules,
    TalentRules,
    TargetRules,
    combat_client_view,
)
from .content import CardCatalog, EnemyCatalog, ItemCatalog, RARITY_RANK
from .dice import MAX_DICE, roll_d12
from .errors import RuleViolation
from .game_state import MAX_ACTION_POINTS, PHASES, EnemyState, GameState, PlayerState
from .scenario_rules import ScenarioRules, WaveTransitionRules
from .world_generator import generate_world
from .weather_rules import WeatherRules


HISTORY_LIMIT = 500


class GameEngine:
    def __init__(
        self,
        state: GameState,
        catalog: CardCatalog | None = None,
        items: ItemCatalog | None = None,
        enemies: EnemyCatalog | None = None,
    ) -> None:
        self.state = state
        self.catalog = catalog or CardCatalog()
        self.items = items or ItemCatalog()
        self.enemies = enemies or EnemyCatalog()
        self.boss_contract: BossContract | None = None

    @classmethod
    def new(
        cls,
        seed: int,
        loadouts: dict[str, dict[str, str]],
        catalog: CardCatalog | None = None,
        items: ItemCatalog | None = None,
        campaign_length: str = "fieldzug",
        world_tier: int = 1,
        enemies: EnemyCatalog | None = None,
    ) -> GameEngine:
        if len(loadouts) not in {1, 2}:
            raise RuleViolation("Eidpfad requires one or two players")
        card_catalog = catalog or CardCatalog()
        item_catalog = items or ItemCatalog()
        enemy_catalog = enemies or EnemyCatalog()
        rng = random.Random(seed)
        players: dict[str, PlayerState] = {}
        for profile_id, loadout in loadouts.items():
            deck = card_catalog.starter_deck(loadout["weapon"], loadout["magic"])
            rng.shuffle(deck)
            starting_weapon = item_catalog.STARTING_WEAPONS[loadout["weapon"]]
            players[profile_id] = PlayerState(
                profile_id=profile_id,
                weapon=loadout["weapon"],
                magic=loadout["magic"],
                deck=deck,
                inventory=[starting_weapon, "travel_leathers"],
                equipment={"weapon": starting_weapon, "armor": "travel_leathers"},
            )

        world = generate_world(seed, campaign_length, world_tier, enemy_catalog)
        state = GameState(
            seed=seed,
            players=players,
            turn_order=list(loadouts),
            campaign_length=campaign_length,
            world_tier=world_tier,
            world=world,
        )
        state.scenario_selected_id = str(state.world["route"][0]["id"])
        engine = cls(state, card_catalog, item_catalog, enemy_catalog)
        engine._start_scenario_encounter()
        for player in state.players.values():
            engine._draw(player, 5)
            engine._apply_equipment_passives(player)
        engine.save_checkpoint()
        return engine

    @classmethod
    def restore(
        cls,
        value: dict[str, Any],
        catalog: CardCatalog | None = None,
        items: ItemCatalog | None = None,
        enemies: EnemyCatalog | None = None,
    ) -> GameEngine:
        engine = cls(GameState.from_dict(value), catalog, items, enemies)
        engine._ensure_runtime()
        return engine

    def export(self) -> dict[str, Any]:
        return asdict(self.state)

    def attach_boss_contract(self, contract: BossContract) -> None:
        """Attach the authoritative final-boss state machine to this engine instance."""

        if set(contract.state.player_ids) != set(self.state.players):
            raise RuleViolation("Boss-contract players do not match the campaign")
        self.boss_contract = contract
        self.state.world["boss_contract_active"] = True
        self._sync_boss_targets()

    def client_view(self) -> dict[str, Any]:
        state = self.export()
        state.pop("checkpoint", None)
        state.pop("history", None)
        state.pop("roll_index", None)
        state["phase"] = self.state.phase
        state["active_player"] = self.state.active_player
        state["scenario"] = copy.deepcopy(self.state.scenario)
        state["available_scenarios"] = copy.deepcopy(self.state.available_scenarios)
        state["scenario_objective"] = ScenarioRules.client_view(self.state)
        state["weather_effect"] = WeatherRules.client_view(str(self.state.scenario.get("weather", "")))
        state["combat"] = combat_client_view(self.state)
        visible_cards = {
            card_id
            for player in self.state.players.values()
            for card_id in player.hand + player.discard + player.exhausted
        }
        visible_items = {
            item_id
            for player in self.state.players.values()
            for item_id in player.inventory
        } | set(self.state.pending_loot)
        state["card_definitions"] = {
            card_id: self.catalog.get(card_id) for card_id in sorted(visible_cards)
        }
        state["item_definitions"] = {
            item_id: self.items.get(item_id) for item_id in sorted(visible_items)
        }
        return state

    def save_checkpoint(self) -> None:
        self.state.checkpoint = copy.deepcopy(self.state.snapshot())
        self._record([
            {"type": "checkpoint", "scenario": self.state.scenario_index, "round": self.state.round_number}
        ])

    def _record(self, events: list[dict[str, Any]]) -> None:
        self.state.history.extend(copy.deepcopy(events))
        if len(self.state.history) > HISTORY_LIMIT:
            del self.state.history[:-HISTORY_LIMIT]

    def play_card(
        self,
        actor_id: str,
        card_id: str,
        target_id: str | None = None,
        target_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_runtime()
        self._require_action(actor_id)
        player = self.state.players[actor_id]
        if card_id not in player.hand:
            raise RuleViolation("The card is not in the player's hand")

        card = self.catalog.get(card_id)
        if card_id == FINAL_OATH_CARD_ID:
            raise RuleViolation("Der letzte Eid is resolved by the shared boss contract")
        explicit_targets = list(target_ids or ([target_id] if target_id else []))
        if card["kind"] == "reaction":
            raise RuleViolation("Reaction cards can only be played in an open reaction window")
        if card["kind"] == "cooperation":
            if len(self.state.players) == 1:
                return self._resolve_card(actor_id, card, explicit_targets, cooperative=True)
            events = CooperationRules.propose(
                self.state, actor_id, card_id, self.catalog, explicit_targets
            )
            self._record(events)
            return events
        return self._resolve_card(actor_id, card, explicit_targets)

    def _resolve_card(
        self,
        actor_id: str,
        card: dict[str, Any],
        target_ids: list[str] | None = None,
        *,
        ignore_phase: bool = False,
        cooperative: bool = False,
        record: bool = True,
    ) -> list[dict[str, Any]]:
        player = self.state.players[actor_id]
        card_id = str(card["id"])
        if card_id not in player.hand:
            raise RuleViolation("The card is not in the player's hand")
        if card["phase"] != self.state.phase:
            if not ignore_phase:
                raise RuleViolation(f"This card can only be played during {card['phase']}")
        cost = int(card["action_point_cost"])
        if player.action_points < cost:
            raise RuleViolation("Not enough action points")

        self._sync_primary_target()
        selected = TargetRules.select(
            self.state,
            actor_id,
            card,
            target_ids or (
                [self._default_enemy_target()]
                if TargetRules.targeting(card)["side"] == "enemy"
                else None
            ),
        )

        player.action_points -= cost
        player.hand.remove(card_id)
        events: list[dict[str, Any]] = [
            {
                "type": "card_played",
                "actor": actor_id,
                "card": card_id,
                "phase": self.state.phase,
                "action_points_left": player.action_points,
                "target_ids": selected,
                "cooperative": cooperative,
            }
        ]
        if cooperative:
            combo = sum(StatusRules.weapon_combo_bonus(member) for member in self.state.players.values())
            if combo:
                player.statuses["coordinated"] = player.statuses.get("coordinated", 0) + combo
        exhaust = False
        for effect in card["effects"]:
            exhaust = self._apply_effect(player, card, effect, selected, events) or exhaust
            if any(event["type"] == "rollback" for event in events):
                if record:
                    self._record(events)
                return events

        events.extend(ScenarioRules.record_card(self.state, actor_id, card, selected))

        if card["kind"] == "weapon":
            player.played_weapon_this_round = True
        (player.exhausted if exhaust else player.discard).append(card_id)
        self._draw(player, 1)

        events.extend(self._resolve_combat_defeats(end_of_round=False))
        if record:
            self._record(events)
        return events

    def confirm_cooperation(self, actor_id: str, accepted: bool) -> list[dict[str, Any]]:
        events = CooperationRules.respond(self.state, actor_id, accepted)
        if not accepted:
            CooperationRules.clear_rejected(self.state)
            self._record(events)
            return events
        if not any(event["type"] == "cooperation_confirmed" for event in events):
            self._record(events)
            return events
        action = CooperationRules.consume(self.state)
        partner = self.state.players[actor_id]
        if partner.action_points < 1:
            raise RuleViolation("The confirming partner needs one action point")
        partner.action_points -= 1
        events.append({
            "type": "action_points_spent", "player": actor_id,
            "amount": 1, "action_points_left": partner.action_points,
        })
        resolved = self._resolve_card(
            str(action["actor"]), self.catalog.get(str(action["card_id"])),
            list(action["target_ids"]), cooperative=True, record=False,
        )
        events.extend(resolved)
        self._record(events)
        return events

    def pass_phase(self, actor_id: str) -> list[dict[str, Any]]:
        self._require_action(actor_id)
        self.state.passed_players.append(actor_id)
        events: list[dict[str, Any]] = [
            {"type": "player_passed", "actor": actor_id, "phase": self.state.phase}
        ]

        if len(self.state.passed_players) < len(self.state.turn_order):
            self.state.active_slot += 1
            events.append({"type": "active_player_changed", "player": self.state.active_player})
        elif self.state.phase_index + 1 < len(PHASES):
            self.state.phase_index += 1
            self.state.active_slot = 0
            self.state.passed_players.clear()
            events.append(
                {
                    "type": "phase_changed",
                    "phase": self.state.phase,
                    "active_player": self.state.active_player,
                }
            )
        else:
            if self._reaction_available():
                events.extend(IntentRules.announce(self.state))
                events.extend(ReactionRules.open(self.state))
            else:
                events.extend(self._finish_round())

        self._record(events)
        return events

    def react(
        self,
        actor_id: str,
        card_id: str | None,
        target_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        events = ReactionRules.respond(
            self.state, actor_id, card_id, self.catalog, target_ids
        )
        if any(event["type"] == "reaction_window_ready" for event in events):
            for reaction in ReactionRules.consume(self.state):
                events.extend(
                    self._resolve_card(
                        str(reaction["actor"]),
                        self.catalog.get(str(reaction["card_id"])),
                        list(reaction.get("target_ids", [])),
                        ignore_phase=True,
                        record=False,
                    )
                )
            events.extend(self._finish_round())
        self._record(events)
        return events

    def _reaction_available(self) -> bool:
        for player in self.state.players.values():
            for card_id in player.hand:
                card = self.catalog.get(card_id)
                if card.get("kind") == "reaction" and player.action_points >= int(card["action_point_cost"]):
                    return True
        return False

    def claim_loot(self, actor_id: str, item_id: str) -> list[dict[str, Any]]:
        if actor_id not in self.state.players:
            raise RuleViolation("Unknown player")
        if item_id not in self.state.pending_loot:
            raise RuleViolation("This item is not available")
        if actor_id in self.state.loot_claims:
            raise RuleViolation("This player already claimed an item")

        player = self.state.players[actor_id]
        item = self.items.get(item_id)
        player.inventory.append(item_id)
        self.state.pending_loot.remove(item_id)
        self.state.loot_claims[actor_id] = item_id
        equipped = False
        events = [
            {
                "type": "loot_claimed",
                "player": actor_id,
                "item": item_id,
                "rarity": item["rarity"],
                "equipped": equipped,
            }
        ]

        if len(self.state.loot_claims) == len(self.state.players):
            self.state.pending_loot.clear()
            self.state.loot_claims.clear()
            if self.state.scenario_index + 1 >= len(self.state.world["route"]):
                self.state.campaign_complete = True
                events.append({"type": "campaign_completed", "world_tier": self.state.world_tier})
            else:
                self.state.scenario_index += 1
                self.state.round_number = 1
                self.state.phase_index = 0
                self.state.starter_index = 0
                self.state.active_slot = 0
                self.state.passed_players.clear()
                self.state.scenario_votes.clear()
                if len(self.state.available_scenarios) > 1:
                    self.state.awaiting_scenario_choice = True
                    self.state.scenario_selected_id = ""
                    events.append({
                        "type": "scenario_choice_required",
                        "options": copy.deepcopy(self.state.available_scenarios),
                    })
                else:
                    self.state.scenario_selected_id = str(self.state.available_scenarios[0]["id"])
                    self._start_scenario_encounter()
                    events.append(
                        {
                            "type": "scenario_started",
                            "scenario": copy.deepcopy(self.state.scenario),
                            "enemy": asdict(self.state.enemy),
                            "remaining_enemies": len(self.state.enemy_queue),
                        }
                    )
                    self.save_checkpoint()

        self._record(events)
        return events

    def choose_scenario(self, actor_id: str, scenario_id: str) -> list[dict[str, Any]]:
        if actor_id not in self.state.players:
            raise RuleViolation("Unknown player")
        if not self.state.awaiting_scenario_choice:
            raise RuleViolation("No scenario choice is pending")
        legal = {str(option["id"]) for option in self.state.available_scenarios}
        if scenario_id not in legal:
            raise RuleViolation("This scenario is not available")
        self.state.scenario_votes[actor_id] = scenario_id
        events: list[dict[str, Any]] = [{
            "type": "scenario_vote_recorded", "player": actor_id,
            "voted_players": sorted(self.state.scenario_votes),
        }]
        if len(self.state.scenario_votes) == len(self.state.players):
            choices = set(self.state.scenario_votes.values())
            if len(choices) != 1:
                self.state.scenario_votes.clear()
                events.append({"type": "scenario_consensus_required"})
            else:
                self.state.scenario_selected_id = choices.pop()
                self.state.awaiting_scenario_choice = False
                self.state.scenario_votes.clear()
                self._start_scenario_encounter()
                self.save_checkpoint()
                events.append({
                    "type": "scenario_started", "scenario": copy.deepcopy(self.state.scenario),
                    "enemy": asdict(self.state.enemy),
                    "remaining_enemies": len(self.state.enemy_queue),
                })
        self._record(events)
        return events

    def equip_item(self, actor_id: str, item_id: str) -> list[dict[str, Any]]:
        if actor_id not in self.state.players:
            raise RuleViolation("Unknown player")
        if not self.state.pending_loot and not self.state.awaiting_scenario_choice:
            raise RuleViolation("Equipment can only be changed between scenarios")
        player = self.state.players[actor_id]
        if item_id not in player.inventory:
            raise RuleViolation("The item is not in this player's inventory")
        item = self.items.get(item_id)
        if item.get("weapon_school") not in (None, player.weapon):
            raise RuleViolation("This character cannot equip the item")
        slot = str(item["slot"])
        if slot == "talisman":
            slot = "talisman_1" if "talisman_1" not in player.equipment else "talisman_2"
        old_id = player.equipment.get(slot)
        if old_id == item_id:
            return []
        if old_id:
            self._remove_granted_card(player, self.items.get(old_id).get("granted_card"))
        player.equipment[slot] = item_id
        granted_card = item.get("granted_card")
        if granted_card and granted_card in self.catalog.cards:
            known = player.hand + player.deck + player.discard + player.exhausted
            if granted_card not in known:
                player.discard.append(granted_card)
        self._apply_equipment_passives(player)
        events = [{
            "type": "item_equipped", "player": actor_id, "item": item_id,
            "slot": slot, "replaced": old_id,
        }]
        self._record(events)
        return events

    def perform_scenario_action(self, actor_id: str, action: str) -> list[dict[str, Any]]:
        """Resolve an always-reachable objective action independent of card draw."""

        self._require_action(actor_id)
        runtime = self.state.world.get("scenario_runtime", {})
        if action != "prepare_hunt" or runtime.get("scenario_kind") != "hunt":
            raise RuleViolation("This scenario action is not available")
        if self.state.phase != "utility" or self.state.round_number != 1:
            raise RuleViolation("The hunt must be prepared in utility during round one")
        player = self.state.players[actor_id]
        if player.action_points < 1:
            raise RuleViolation("Preparing the hunt requires one action point")
        player.action_points -= 1
        events = [{
            "type": "scenario_action_performed",
            "action": action,
            "player": actor_id,
            "action_points_left": player.action_points,
        }]
        events.extend(ScenarioRules.record_card(
            self.state,
            actor_id,
            {"id": "scenario_prepare_hunt", "phase": "utility", "effects": []},
            [],
        ))
        self._record(events)
        return events

    def apply_player_damage(self, player_id: str, amount: int) -> list[dict[str, Any]]:
        player = self.state.players[player_id]
        absorbed = min(player.guard, amount)
        player.guard -= absorbed
        damage = max(0, amount - absorbed)
        player.hp -= damage
        events = [
            {"type": "player_damaged", "player": player_id, "amount": damage, "absorbed": absorbed}
        ]

        if player.hp <= 0 and player.statuses.get("last_oath", 0) > 0:
            player.statuses.pop("last_oath", None)
            player.hp = 1
            events.append({"type": "last_oath_triggered", "player": player_id})
        elif player.hp <= 0:
            events.extend(ScenarioRules.record_player_fallen(self.state, player_id))
            events.append(self._rollback(player_id))
        return events

    def _require_action(self, actor_id: str) -> None:
        if self.state.campaign_complete:
            raise RuleViolation("The campaign is complete")
        if self.state.pending_loot:
            raise RuleViolation("Loot must be claimed before the next scenario")
        if self.state.awaiting_scenario_choice:
            raise RuleViolation("Both players must choose the next scenario")
        if actor_id not in self.state.players:
            raise RuleViolation("Unknown player")
        runtime = self.state.world.get("combat_runtime", {})
        if runtime.get("reaction_window") is not None:
            raise RuleViolation("The reaction window must be resolved first")
        if runtime.get("coop_action") is not None:
            raise RuleViolation("The cooperation proposal must be resolved first")
        if actor_id != self.state.active_player:
            raise RuleViolation("It is not this player's action")

    def _apply_effect(
        self,
        player: PlayerState,
        card: dict[str, Any],
        effect: dict[str, Any],
        target_ids: list[str],
        events: list[dict[str, Any]],
    ) -> bool:
        effect_type = effect["type"]
        amount = int(effect.get("amount", 0))

        if effect_type == "dice_attack":
            hits, _ = self._roll_check(player, effect, "hit", events, use_weapon=True)
            for target_id in target_ids:
                target = self._target_definition(target_id)
                blocks, _ = self._roll_pool(
                    target_id,
                    int(target.get("block_dice", 0)) + int(target.get("statuses", {}).get("guard_bonus", 0)),
                    int(target.get("block_threshold", 8)),
                    "block",
                    events,
                )
                unblocked_hits = max(0, hits - blocks)
                weapon_bonus = self._bonuses(player).get("damage_per_hit", 0)
                damage = unblocked_hits * (int(effect.get("damage_per_success", 0)) + weapon_bonus)
                armor_break = unblocked_hits * int(effect.get("armor_per_success", 0))
                block_break = unblocked_hits * int(self._bonuses(player).get("block_break", 0))
                if armor_break:
                    events.extend(self._apply_armor_break([target_id], armor_break))
                if block_break:
                    removed = min(int(target.get("block_dice", 0)), block_break)
                    target["block_dice"] = int(target.get("block_dice", 0)) - removed
                    events.append({"type": "block_dice_broken", "target": target_id, "amount": removed})
                events.extend(self._apply_target_damage([target_id], damage))
                acid_charges = player.statuses.get("acid_charges", 0)
                if acid_charges and unblocked_hits and self._target_is_live(target_id):
                    used = min(acid_charges, unblocked_hits)
                    player.statuses["acid_charges"] -= used
                    target["block_threshold"] = min(12, int(target.get("block_threshold", 8)) + used)
                    events.append({"type": "acid_triggered", "target": target_id, "charges": used})
                events.append(
                    {
                        "type": "attack_resolved", "target": target_id,
                        "hits": hits, "blocks": blocks,
                        "unblocked_hits": unblocked_hits, "damage": damage,
                    }
                )
        elif effect_type == "dice_magic_damage":
            successes, _ = self._roll_check(player, effect, "magic", events, use_magic=True)
            for target_id in target_ids:
                target = self._target_definition(target_id)
                wards, _ = self._roll_pool(
                    target_id, int(target.get("ward_dice", 0)),
                    int(target.get("ward_threshold", 9)), "ward", events,
                )
                remaining = max(0, successes - wards)
                damage = remaining * int(effect.get("damage_per_success", 0))
                events.extend(self._apply_target_damage([target_id], damage, bypass_armor=True))
                if remaining and effect.get("status") and self._target_is_live(target_id):
                    status = str(effect["status"])
                    statuses = target.setdefault("statuses", {})
                    statuses[status] = statuses.get(status, 0) + amount
                    events.append({"type": "enemy_status", "target": target_id, "status": status, "amount": amount})
                events.append(
                    {"type": "magic_resolved", "target": target_id, "successes": successes, "wards": wards, "damage": damage}
                )
        elif effect_type == "armor_break":
            events.extend(self._apply_armor_break(
                [target_id for target_id in target_ids if self._target_is_live(target_id)], amount
            ))
        elif effect_type == "enemy_status":
            for target_id in target_ids:
                if not self._target_is_live(target_id):
                    continue
                target = self._target_definition(target_id)
                status = str(effect["status"])
                statuses = target.setdefault("statuses", {})
                statuses[status] = statuses.get(status, 0) + amount
                events.append({"type": "enemy_status", "target": target_id, "status": status, "amount": amount})
        elif effect_type == "add_block_dice_self":
            player.bonus_block_dice += amount
            events.append({"type": "block_dice_added", "target": player.profile_id, "amount": amount})
        elif effect_type == "add_block_dice_ally":
            ally = self._ally(player.profile_id)
            ally.bonus_block_dice += amount
            events.append({"type": "block_dice_added", "target": ally.profile_id, "amount": amount})
        elif effect_type == "add_block_dice_all":
            for target in self.state.players.values():
                target.bonus_block_dice += amount
            events.append({"type": "team_block_dice_added", "amount": amount})
        elif effect_type == "self_status":
            player.statuses[str(effect["status"])] = amount
        elif effect_type == "team_status":
            for target in self.state.players.values():
                target.statuses[str(effect["status"])] = amount
        elif effect_type == "self_damage":
            events.extend(self.apply_player_damage(player.profile_id, amount))
        elif effect_type == "heal_self":
            events.extend(EffectRules.heal(self.state, player.profile_id, [player.profile_id], amount, self._bonuses(player)))
        elif effect_type == "heal_ally":
            ally_ids = [target for target in target_ids if target in self.state.players]
            events.extend(EffectRules.heal(self.state, player.profile_id, ally_ids or [self._ally(player.profile_id).profile_id], amount, self._bonuses(player)))
        elif effect_type == "heal_all":
            events.extend(EffectRules.heal(self.state, player.profile_id, list(self.state.players), amount, self._bonuses(player)))
        elif effect_type == "regeneration":
            player.statuses["regeneration"] = amount
            player.statuses["regeneration_rounds"] = int(effect.get("rounds", 2))
        elif effect_type == "apply_weapon_coating":
            player.statuses["acid_charges"] = amount
            events.append({"type": "weapon_coated", "coating": "acid", "charges": amount})
        elif effect_type == "set_trap":
            for target_id in target_ids:
                if not self._target_is_live(target_id):
                    continue
                target = self._target_definition(target_id)
                target.setdefault("statuses", {})["trap_dice"] = amount
                events.append({"type": "trap_set", "target": target_id, "dice": amount})
        elif effect_type == "draw_cards":
            before = len(player.hand)
            self._draw(player, amount)
            events.append({"type": "cards_drawn", "player": player.profile_id, "amount": len(player.hand) - before})
        elif effect_type == "gain_action_points":
            before = player.action_points
            player.action_points = min(MAX_ACTION_POINTS, player.action_points + amount)
            events.append({"type": "action_points_gained", "player": player.profile_id, "amount": player.action_points - before})
        elif effect_type == "guard_self":
            player.guard += amount
            events.append({"type": "guard_gained", "player": player.profile_id, "amount": amount})
        elif effect_type == "cleanse":
            negative = ("poisoned", "burning", "bleeding", "weakened", "bound")
            removed = next((status for status in negative if player.statuses.pop(status, None) is not None), None)
            events.append({"type": "status_cleansed", "player": player.profile_id, "status": removed})
        elif effect_type == "exhaust":
            return True
        return False

    def _roll_check(
        self,
        player: PlayerState,
        effect: dict[str, Any],
        purpose: str,
        events: list[dict[str, Any]],
        *,
        use_weapon: bool = False,
        use_magic: bool = False,
    ) -> tuple[int, int]:
        bonuses = self._bonuses(player)
        count = int(effect.get("count", 1))
        count += int(player.talents.get(f"{purpose}_dice", 0))
        # After repeated checkpoint retries the party gains a bounded resolve bonus.
        # This prevents deterministic dice timelines from turning a legal campaign
        # into an endless rollback loop while preserving the first attempts unchanged.
        count += int(player.statuses.get("resolve_dice", 0))
        count += WeatherRules.player_dice(
            str(self.state.scenario.get("weather", "")), purpose, player
        )
        status_modifier, status_events = StatusRules.consume_player_roll_penalty(player, purpose)
        count += status_modifier
        events.extend(status_events)
        if use_weapon:
            count += int(bonuses.get("attack_dice", 0))
            count += min(1, self.state.enemy.statuses.pop("marked", 0))
            count += player.statuses.pop("coordinated", 0)
            count += player.statuses.pop("fury", 0)
            if player.statuses.pop("final_oath", 0):
                count += 2
                ally = self._ally(player.profile_id)
                count += 2 if ally.statuses.pop("final_oath", 0) else 0
        if use_magic:
            count += int(bonuses.get("magic_dice", 0))
            count += player.statuses.pop("arcane_link", 0)
        count += player.statuses.pop("oath_power", 0)
        count -= player.statuses.pop("weakened", 0)
        threshold = int(effect.get("threshold", 7))
        threshold += int(bonuses.get("hit_threshold_modifier", 0)) if use_weapon else 0
        if use_weapon and "bog_shroud" in self.state.enemy.traits and self.state.round_number == 1:
            threshold += 1
        if use_magic and "prismatic_ward" in self.state.enemy.traits:
            threshold += 1
        if player.statuses.pop("aimed", 0) > 0:
            threshold -= 1
        critical_min = int(bonuses.get("critical_min", 12))
        return self._roll_pool(
            player.profile_id,
            min(MAX_DICE, max(0, count)),
            min(12, max(2, threshold)),
            purpose,
            events,
            critical_min,
        )

    def _roll_pool(
        self,
        actor_id: str,
        count: int,
        threshold: int,
        purpose: str,
        events: list[dict[str, Any]],
        critical_min: int = 12,
    ) -> tuple[int, int]:
        # A rollback must not replay an identical losing dice timeline forever.
        retry_seed = self.state.seed + self.state.rollback_count * 1_000_003
        result = roll_d12(retry_seed, self.state.roll_index, count, threshold, critical_min)
        self.state.roll_index += 1
        events.append(
            {
                "type": "dice_rolled",
                "actor": actor_id,
                "purpose": purpose,
                "sides": 12,
                **result,
            }
        )
        return int(result["successes"]), int(result["criticals"])

    def _damage_enemy(self, amount: int, events: list[dict[str, Any]], bypass_armor: bool = False) -> None:
        """Compatibility helper for tools and focused tests using the primary target."""
        exposed = self.state.enemy.statuses.pop("exposed", 0)
        total = max(0, amount + (2 if exposed else 0))
        self._sync_primary_target()
        events.extend(self._apply_target_damage(
            [self._default_enemy_target()], total, bypass_armor=bypass_armor
        ))
        self._update_boss_phase(events)

    def _finish_round(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = [{"type": "round_resolving", "round": self.state.round_number}]
        events.extend(self._enemy_phase())
        if any(event["type"] == "rollback" for event in events):
            return events
        defeat_events = self._resolve_combat_defeats(end_of_round=True)
        events.extend(defeat_events)
        if self.state.pending_loot or self.state.campaign_complete:
            return events
        if any(event["type"] == "enemy_spawned" for event in defeat_events):
            upkeep = self._player_upkeep()
            events.extend(upkeep)
            if any(event["type"] == "rollback" for event in upkeep):
                return events
            events.extend(WaveTransitionRules.after_round_resolution(self.state))
            events.extend(ScenarioRules.record_round_started(self.state))
            if any(event["type"] == "scenario_objective_failed" for event in events):
                events.append(self._rollback(self.state.active_player))
                return events
            events.extend(IntentRules.announce(self.state))
            return events

        upkeep = self._player_upkeep()
        events.extend(upkeep)
        if any(event["type"] == "rollback" for event in upkeep):
            return events
        for player in self.state.players.values():
            player.action_points = MAX_ACTION_POINTS
            player.guard = 0
            player.bonus_block_dice = 0
            player.played_weapon_this_round = False
        self.state.round_number += 1
        self.state.starter_index = (self.state.starter_index + 1) % len(self.state.turn_order)
        self.state.phase_index = 0
        self.state.active_slot = 0
        self.state.passed_players.clear()
        events.append(
            {
                "type": "round_started",
                "round": self.state.round_number,
                "phase": self.state.phase,
                "active_player": self.state.active_player,
            }
        )
        events.extend(ScenarioRules.record_round_started(self.state))
        if any(event["type"] == "scenario_objective_failed" for event in events):
            events.append(self._rollback(self.state.active_player))
            return events
        events.extend(IntentRules.announce(self.state))
        return events

    def _player_upkeep(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for player in self.state.players.values():
            for status in ("burning", "bleeding", "poisoned"):
                amount = player.statuses.get(status, 0)
                if amount:
                    events.extend(self.apply_player_damage(player.profile_id, amount))
                    player.statuses[status] = max(0, amount - 1)
                    events.append({"type": "player_status_damage", "player": player.profile_id, "status": status, "amount": amount})
                    if any(event["type"] == "rollback" for event in events):
                        return events
            if player.statuses.get("regeneration_rounds", 0) > 0:
                events.extend(EffectRules.heal(
                    self.state, player.profile_id, [player.profile_id],
                    player.statuses.get("regeneration", 0), self._bonuses(player),
                ))
                player.statuses["regeneration_rounds"] -= 1
        return events

    def _enemy_phase(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = [{"type": "enemy_phase"}]
        if self.boss_contract is not None:
            events.extend(self._boss_target_upkeep())
            self._sync_boss_targets()
            if not self.boss_contract.active_targets:
                return events
        else:
            for status in ("burning", "bleeding"):
                amount = self.state.enemy.statuses.get(status, 0)
                if amount:
                    self.state.enemy.hp = max(0, self.state.enemy.hp - amount)
                    self.state.enemy.statuses[status] = max(0, amount - 1)
                    events.append({"type": "status_damage", "status": status, "amount": amount})
                    self._update_boss_phase(events)
            trap_dice = self.state.enemy.statuses.pop("trap_dice", 0)
            if trap_dice:
                successes, _ = self._roll_pool("team_trap", trap_dice, 7, "trap", events)
                self._damage_enemy(successes * 2, events, bypass_armor=True)
        if self.state.enemy.hp <= 0:
            TargetRules.sync_primary(self.state)
            return events

        threshold_penalty = self.state.enemy.statuses.pop("weakened", 0)
        bound_penalty = self.state.enemy.statuses.pop("bound", 0)
        announced = self.state.world.get("combat_runtime", {}).get("announced_intent")
        if announced and announced.get("intent") not in (self.state.enemy.intents or ["strike"]):
            self.state.world["combat_runtime"]["announced_intent"] = None
        try:
            announcement = IntentRules.consume(self.state)
        except RuleViolation:
            events.extend(IntentRules.announce(self.state))
            announcement = IntentRules.consume(self.state)
        intent = str(announcement["intent"])
        events.append({"type": "enemy_intent", "enemy": self.state.enemy.enemy_id, "intent": intent})
        self.state.enemy.statuses.pop("guard_bonus", None)
        if intent == "guard":
            self.state.enemy.statuses["guard_bonus"] = 1
        targets = list(announcement["targets"])
        for player_id in targets:
            regional_attack = 1 if ("tidal_pressure" in self.state.enemy.traits and intent == "advance") or ("storm_charge" in self.state.enemy.traits and intent == "pressure") else 0
            enemy_hits, _ = self._roll_pool(
                self.state.enemy.enemy_id,
                max(0, self.state.enemy.attack_dice + (1 if intent == "pressure" else 0) + regional_attack + WeatherRules.enemy_dice(str(self.state.scenario.get("weather", ""))) + ScenarioRules.ambush_attack_dice_bonus(self.state) + (self.boss_contract.boss_attack_bonus if self.boss_contract else 0) - bound_penalty),
                min(12, self.state.enemy.hit_threshold + threshold_penalty - (1 if intent == "advance" else 0)),
                "enemy_hit",
                events,
            )
            player = self.state.players[player_id]
            bonuses = self._bonuses(player)
            block_dice = int(bonuses.get("block_dice", 0)) + player.bonus_block_dice
            block_threshold = int(bonuses.get("block_threshold", 8))
            player_blocks, _ = self._roll_pool(
                player_id,
                block_dice,
                block_threshold,
                "player_block",
                events,
            )
            unblocked_hits = max(0, enemy_hits - player_blocks)
            if intent == "hex" and unblocked_hits:
                unblocked_hits = EffectRules.resolve_player_ward(
                    player, unblocked_hits, bonuses, self._roll_pool, events
                )
            damage = unblocked_hits * (self.state.enemy.damage_per_hit + (1 if intent == "strike" else 0))
            events.append(
                {
                    "type": "enemy_attack_resolved",
                    "target": player_id,
                    "hits": enemy_hits,
                    "blocks": player_blocks,
                    "damage": damage,
                }
            )
            damage_events = self.apply_player_damage(player_id, damage)
            events.extend(damage_events)
            events.extend(StatusRules.apply_enemy_hit(self.state.enemy, player, intent, unblocked_hits))
            events.extend(ScenarioRules.record_enemy_attack(self.state, unblocked_hits))
            if any(event["type"] == "scenario_objective_failed" for event in events):
                events.append(self._rollback(player_id))
                return events
            if "thorn_rebuke" in self.state.enemy.traits and player_blocks:
                events.append({"type": "thorn_rebuke", "player": player_id, "amount": 1})
                events.extend(self.apply_player_damage(player_id, 1))
            if any(event["type"] == "rollback" for event in damage_events):
                break
        self._sync_primary_target()
        return events

    def _boss_target_upkeep(self) -> list[dict[str, Any]]:
        """Resolve damage-over-time and traps on every live final-boss objective."""

        if self.boss_contract is None:
            return []
        events: list[dict[str, Any]] = []
        runtime = self.state.world.get("combat_runtime", {}).get("targets", {})
        for target_id in list(self.boss_contract.active_targets):
            target = runtime.get(target_id)
            if not target:
                continue
            statuses = target.setdefault("statuses", {})
            for status in ("burning", "bleeding"):
                amount = int(statuses.get(status, 0))
                if not amount or target_id not in self.boss_contract.active_targets:
                    continue
                statuses[status] = max(0, amount - 1)
                events.append({"type": "status_damage", "target": target_id, "status": status, "amount": amount})
                events.extend(self._apply_target_damage([target_id], amount, bypass_armor=True))
            trap_dice = int(statuses.pop("trap_dice", 0))
            if trap_dice and target_id in self.boss_contract.active_targets:
                successes, _ = self._roll_pool(f"team_trap:{target_id}", trap_dice, 7, "trap", events)
                events.extend(self._apply_target_damage([target_id], successes * 2, bypass_armor=True))
        return events

    def _complete_scenario(self) -> list[dict[str, Any]]:
        scenario = self.state.scenario
        for player in self.state.players.values():
            player.hp = player.max_hp
            player.action_points = MAX_ACTION_POINTS
            player.guard = 0
            player.bonus_block_dice = 0
            player.statuses.clear()
            player.played_weapon_this_round = False
            self._apply_equipment_passives(player)
        minimum = "legendary" if scenario["is_final"] else "exceptional" if scenario["is_boss"] else "normal"
        self.state.pending_loot = self._generate_loot(minimum, 3)
        self.state.loot_claims.clear()
        events = self._grant_progression()
        events.extend([
            {"type": "scenario_completed", "scenario": copy.deepcopy(scenario), "party_healed": True},
            {
                "type": "loot_offered",
                "items": [self.items.get(item_id) for item_id in self.state.pending_loot],
            },
        ])
        return events

    def _grant_progression(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for player in self.state.players.values():
            player.experience += 1
            threshold = max(2, player.character_level * 2)
            if player.experience >= threshold and player.character_level < 30:
                player.experience -= threshold
                player.character_level += 1
                events.append({"type": "character_level_gained", "player": player.profile_id, "level": player.character_level})
                available_talents = [
                    talent_id for talent_id in TalentRules.TALENTS
                    if not player.talents.get(f"unlocked:{talent_id}")
                ]
                if available_talents:
                    events.append(TalentRules.unlock(player, available_talents[0]))
            known = set(player.hand + player.deck + player.discard + player.exhausted)
            candidates = [
                card for card in self.catalog.cards.values()
                if card["id"] not in known
                and card.get("school") in {player.weapon, player.magic, "universal"}
                and int(card.get("unlock_level", 1)) <= self.state.scenario_index + 3
                and card["id"] in filter_progression_rewards([card["id"]])
            ]
            if not candidates:
                candidates = [
                    card for card in self.catalog.cards.values()
                    if card["id"] not in known
                    and card.get("school") in {player.weapon, player.magic, "universal"}
                    and card["id"] in filter_progression_rewards([card["id"]])
                ]
            if not candidates:
                player.mastery_points += 1
                events.append({"type": "mastery_gained", "player": player.profile_id, "mastery_points": player.mastery_points})
                continue
            material = f"unlock:{self.state.seed}:{self.state.scenario_index}:{player.profile_id}".encode()
            index = int.from_bytes(hashlib.sha256(material).digest()[:4], "big") % len(candidates)
            card_id = sorted(candidates, key=lambda card: card["id"])[index]["id"]
            player.discard.append(card_id)
            events.append({"type": "card_unlocked", "player": player.profile_id, "card": card_id})
        return events

    def _grant_progression_cards(self) -> list[dict[str, Any]]:
        """Backward-compatible alias used by old tools."""
        return self._grant_progression()

    def _generate_loot(self, minimum_rarity: str, count: int) -> list[str]:
        minimum_rank = min(
            len(RARITY_RANK) - 1,
            RARITY_RANK[minimum_rarity] + ScenarioRules.ruin_loot_rarity_bonus(self.state),
        )
        owned = {item_id for player in self.state.players.values() for item_id in player.inventory}
        current_country = self.state.scenario["country_id"]
        available = [item for item in self.items.items.values() if item["id"] not in owned]
        guaranteed = [item for item in available if RARITY_RANK[item["rarity"]] >= minimum_rank]
        if not guaranteed:
            guaranteed = available
        material = f"loot:{self.state.seed}:{self.state.scenario_index}:{self.state.world_tier}".encode()
        rng = random.Random(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))
        result = [rng.choice(guaranteed)["id"]]
        weighted: list[str] = []
        for item in available:
            rank = RARITY_RANK[item["rarity"]]
            weight = int(item.get("drop_weight", max(1, 8 - rank)))
            if item.get("country_affinity") == current_country:
                weight *= 3
            if item.get("weapon_school") in {player.weapon for player in self.state.players.values()}:
                weight *= 2
            weighted.extend([item["id"]] * max(1, weight))
        while len(result) < count:
            candidate = rng.choice(weighted)
            if candidate not in result:
                result.append(candidate)
        return result

    def _start_scenario_encounter(self) -> None:
        encounters = list(self.state.scenario.get("encounters", ()))
        if not encounters:
            raise RuleViolation(f"Scenario {self.state.scenario.get('id')} has no enemies")
        group_size = 1 if self.state.scenario.get("is_boss") else min(2, len(encounters))
        active = [self._enemy_from_catalog(enemy_id, self.state.scenario) for enemy_id in encounters[:group_size]]
        self.state.enemy = active[0]
        self.state.enemy_queue = encounters[group_size:]
        self.state.defeated_enemies.clear()
        ScenarioRules.initialize(self.state)
        TargetRules.initialize(self.state, active)
        IntentRules.announce(self.state)

    def _resolve_enemy_defeat(self) -> list[dict[str, Any]]:
        return self._resolve_combat_defeats(end_of_round=False)

    def _resolve_combat_defeats(self, *, end_of_round: bool) -> list[dict[str, Any]]:
        del end_of_round  # The caller owns the round reset; defeat resolution is shared.
        if self.boss_contract is not None:
            # Stage advancement and defeat are exclusively owned by BossContract.
            self._sync_boss_targets()
            return []
        runtime = self.state.world.get("combat_runtime", {})
        targets: dict[str, dict[str, Any]] = runtime.get("targets", {})
        events: list[dict[str, Any]] = []
        newly_defeated = [
            target_id for target_id, target in targets.items()
            if not target.get("alive", int(target.get("hp", 0)) > 0)
            and target_id not in self.state.defeated_enemies
        ]
        living = [target for target in targets.values() if target.get("alive", int(target.get("hp", 0)) > 0)]
        for index, target_id in enumerate(newly_defeated):
            self.state.defeated_enemies.append(target_id)
            if not any(event.get("type") == "enemy_defeated" and event.get("enemy") == target_id for event in events):
                events.append({"type": "enemy_defeated", "enemy": target_id})
            remaining = len(living) + len(self.state.enemy_queue) + len(newly_defeated) - index - 1
            events.extend(ScenarioRules.record_enemy_defeated(self.state, remaining))

        if living:
            if self.state.enemy.hp <= 0:
                self.state.enemy = self._enemy_state_from_target(living[0])
            return events
        if not newly_defeated:
            return events
        if self.state.enemy_queue:
            group_size = 1 if self.state.scenario.get("is_boss") else min(2, len(self.state.enemy_queue))
            next_ids = self.state.enemy_queue[:group_size]
            del self.state.enemy_queue[:group_size]
            active = [self._enemy_from_catalog(enemy_id, self.state.scenario) for enemy_id in next_ids]
            self.state.enemy = active[0]
            TargetRules.initialize(self.state, active)
            IntentRules.announce(self.state)
            events.append({
                "type": "enemy_spawned", "enemy": asdict(self.state.enemy),
                "enemies": [asdict(enemy) for enemy in active],
                "remaining_enemies": len(self.state.enemy_queue),
            })
            return events
        ScenarioRules.assert_completion_allowed(self.state)
        if not (self.state.scenario.get("is_final") and self.state.world.get("boss_contract_active")):
            events.extend(self._complete_scenario())
        return events

    def _ensure_runtime(self) -> None:
        if self.boss_contract is not None:
            self._sync_boss_targets()
            return
        scenario_runtime = self.state.world.get("scenario_runtime")
        if not isinstance(scenario_runtime, dict) or scenario_runtime.get("scenario_id") != self.state.scenario.get("id"):
            ScenarioRules.initialize(self.state)
            TargetRules.initialize(self.state, [self.state.enemy])
            IntentRules.announce(self.state)
            return
        if not isinstance(self.state.world.get("combat_runtime"), dict):
            TargetRules.initialize(self.state, [self.state.enemy])
            IntentRules.announce(self.state)

    def _target_definition(self, target_id: str) -> dict[str, Any]:
        try:
            return self.state.world["combat_runtime"]["targets"][target_id]
        except KeyError as exc:
            raise RuleViolation(f"Unknown combat target: {target_id}") from exc

    def _target_is_live(self, target_id: str) -> bool:
        target = self.state.world.get("combat_runtime", {}).get("targets", {}).get(target_id)
        return isinstance(target, dict) and int(target.get("hp", 0)) > 0

    def _default_enemy_target(self) -> str:
        if self.boss_contract is not None:
            active = self.boss_contract.active_targets
            if not active:
                raise RuleViolation("The final encounter has no vulnerable target")
            return str(active[0])
        return self.state.enemy.enemy_id

    def _sync_primary_target(self) -> None:
        if self.boss_contract is not None:
            self._sync_boss_targets()
        else:
            TargetRules.sync_primary(self.state)

    def _apply_target_damage(
        self,
        target_ids: list[str],
        amount: int,
        *,
        bypass_armor: bool = False,
    ) -> list[dict[str, Any]]:
        if self.boss_contract is None:
            events: list[dict[str, Any]] = []
            for target_id in target_ids:
                target = self._target_definition(target_id)
                adjusted = amount
                if (
                    "phase_shift" in target.get("traits", [])
                    and int(target.setdefault("statuses", {}).get("phase_shift_round", 0)) != self.state.round_number
                    and amount > 0
                ):
                    target["statuses"]["phase_shift_round"] = self.state.round_number
                    if target_id == self.state.enemy.enemy_id:
                        self.state.enemy.statuses["phase_shift_round"] = self.state.round_number
                    adjusted = (amount + 1) // 2
                    events.append({
                        "type": "phase_shift_triggered", "target": target_id,
                        "prevented": amount - adjusted,
                    })
                events.extend(TargetRules.damage(
                    self.state, [target_id], adjusted, bypass_armor=bypass_armor
                ))
            return events
        events: list[dict[str, Any]] = []
        for target_id in target_ids:
            events.extend(self.boss_contract.apply_damage(
                target_id, amount, bypass_armor=bypass_armor
            ))
        self._sync_boss_targets()
        return events

    def _apply_armor_break(self, target_ids: list[str], amount: int) -> list[dict[str, Any]]:
        if self.boss_contract is None:
            return TargetRules.armor_break(self.state, target_ids, amount)
        events: list[dict[str, Any]] = []
        for target_id in target_ids:
            events.extend(self.boss_contract.break_armor(target_id, amount))
        self._sync_boss_targets()
        return events

    def _sync_boss_targets(self) -> None:
        if self.boss_contract is None:
            return
        view = self.boss_contract.public_view()
        definitions: dict[str, dict[str, Any]] = {}
        for group_name in ("wardens", "anchors", "armor_parts"):
            definitions.update(view.get(group_name, {}))
        definitions[str(view["gate"]["id"])] = view["gate"]
        if "throneless" in self.boss_contract.active_targets:
            definitions["throneless"] = {
                "id": "throneless",
                "name": (view.get("sovereign") or {}).get("name", "Der Thronlose"),
                "hp": view["boss_hp"],
                "max_hp": view["boss_max_hp"],
                "armor": 0,
            }
        previous = self.state.world.get("combat_runtime", {}).get("targets", {})
        targets: list[dict[str, Any]] = []
        for target_id in self.boss_contract.active_targets:
            source = definitions[target_id]
            old = previous.get(target_id, {})
            model = (
                self.state.enemy.model if target_id == "throneless"
                else f"res://assets/models/props/{target_id}.glb"
            )
            targets.append({
                "id": target_id,
                "enemy_id": target_id,
                "name": source.get("name", target_id),
                "hp": int(source.get("hp", 1)),
                "max_hp": int(source.get("max_hp", source.get("hp", 1))),
                "armor": int(source.get("armor", 0)),
                "block_dice": 0,
                "block_threshold": 8,
                "ward_dice": 0,
                "ward_threshold": 9,
                "statuses": copy.deepcopy(old.get("statuses", {})),
                "boss": True,
                "final_boss": True,
                "art": self.state.enemy.art,
                "model": model,
            })
        if targets:
            TargetRules.initialize(self.state, targets)
        else:
            runtime = self.state.world.setdefault("combat_runtime", {})
            runtime["targets"] = {}

    @staticmethod
    def _enemy_state_from_target(target: dict[str, Any]) -> EnemyState:
        fields = EnemyState.__dataclass_fields__
        payload = {key: copy.deepcopy(value) for key, value in target.items() if key in fields}
        payload["enemy_id"] = str(target.get("enemy_id") or target.get("id"))
        return EnemyState(**payload)

    def _enemy_for_scenario(self, scenario: dict[str, Any]) -> EnemyState:
        """Return the first regional enemy; retained for tools and old saves."""
        encounters = scenario.get("encounters", ())
        if not encounters:
            raise RuleViolation(f"Scenario {scenario.get('id')} has no enemies")
        return self._enemy_from_catalog(encounters[0], scenario)

    def _enemy_from_catalog(self, enemy_id: str, scenario: dict[str, Any]) -> EnemyState:
        definition = self.enemies.get(enemy_id)
        stats = definition["stats"]
        difficulty = int(scenario["difficulty"])
        scaling = 1.0 + max(0, difficulty - 1) * 0.12 + max(0, self.state.world_tier - 1) * 0.15
        traits = list(definition["traits"])
        hp = max(1, round(int(stats["hp"]) * scaling * (1.12 if "grave_resolve" in traits else 1.0)))
        armor = int(stats["armor"]) + difficulty // 3 + (2 if "salt_armor" in traits else 0) + (1 if "ember_skin" in traits else 0)
        ward_dice = min(MAX_DICE, int(stats["ward_dice"]) + difficulty // 6 + (1 if "prismatic_ward" in traits or "rift_shift" in traits else 0))
        block_dice = min(MAX_DICE, int(stats["block_dice"]) + difficulty // 5 + (1 if "thorn_rebuke" in traits else 0))
        block_threshold = 7 if "moon_veil" in traits else int(stats["block_threshold"])
        return EnemyState(
            enemy_id=enemy_id, name=definition["name"], role=definition["role"], hp=hp, max_hp=hp,
            armor=armor,
            block_dice=block_dice,
            block_threshold=block_threshold,
            ward_dice=ward_dice,
            ward_threshold=int(stats["ward_threshold"]),
            attack_dice=min(MAX_DICE, int(stats["attack_dice"]) + difficulty // 4),
            hit_threshold=int(stats["hit_threshold"]),
            damage_per_hit=int(stats["damage_per_hit"]) + difficulty // 5,
            elite=bool(definition.get("elite")), boss=bool(definition["boss"]),
            final_boss=bool(definition.get("final_boss")), traits=traits,
            intents=list(definition["intents"]), intent=str(definition["intents"][0]), art=str(definition["art"]),
            model=str(definition["model"]),
            body_family=str(definition.get("body_family", "humanoid")),
            animation_set=str(definition.get("animation_set", "combat_humanoid")),
            scale=float(definition.get("scale", 1.0)),
            voice_profile=str(definition.get("voice_profile", f"enemy_{definition['role']}")),
        )

    def _update_boss_phase(self, events: list[dict[str, Any]]) -> None:
        enemy = self.state.enemy
        if not enemy.boss or enemy.hp <= 0:
            return
        fraction = enemy.hp / enemy.max_hp
        new_phase = 4 if enemy.final_boss and fraction <= 0.25 else 3 if fraction <= 0.5 else 2 if fraction <= 0.75 else 1
        if new_phase > enemy.boss_phase:
            enemy.boss_phase = new_phase
            enemy.attack_dice = min(MAX_DICE, enemy.attack_dice + 1)
            events.append({"type": "boss_phase_changed", "phase": new_phase})
            if enemy.final_boss and new_phase == 4:
                for player in self.state.players.values():
                    known = player.hand + player.deck + player.discard + player.exhausted
                    if "der_letzte_eid" not in known:
                        player.hand.append("der_letzte_eid")
                events.append({"type": "final_oath_unlocked"})

    def _bonuses(self, player: PlayerState) -> dict[str, int]:
        result: dict[str, int] = {}
        for item_id in player.equipment.values():
            for key, value in self.items.get(item_id).get("bonuses", {}).items():
                if key in {"block_threshold", "critical_min"}:
                    result[key] = min(result.get(key, int(value)), int(value))
                else:
                    result[key] = result.get(key, 0) + int(value)
        return result

    def _apply_equipment_passives(self, player: PlayerState) -> None:
        if self._bonuses(player).get("last_oath", 0):
            player.statuses["last_oath"] = 1

    def _equip_if_upgrade(self, player: PlayerState, item: dict[str, Any]) -> bool:
        slot = item["slot"]
        if slot == "talisman":
            slot = "talisman_1" if "talisman_1" not in player.equipment else "talisman_2"
        old_id = player.equipment.get(slot)
        if old_id is not None:
            old = self.items.get(old_id)
            if RARITY_RANK[item["rarity"]] <= RARITY_RANK[old["rarity"]]:
                return False
        if item.get("weapon_school") not in (None, player.weapon):
            return False
        if old_id is not None:
            self._remove_granted_card(player, self.items.get(old_id).get("granted_card"))
        player.equipment[slot] = item["id"]
        granted_card = item.get("granted_card")
        if granted_card and granted_card in self.catalog.cards:
            known_cards = player.hand + player.deck + player.discard + player.exhausted
            if granted_card not in known_cards:
                player.discard.append(granted_card)
        self._apply_equipment_passives(player)
        return True

    @staticmethod
    def _remove_granted_card(player: PlayerState, card_id: str | None) -> None:
        if not card_id:
            return
        for pile in (player.hand, player.deck, player.discard, player.exhausted):
            while card_id in pile:
                pile.remove(card_id)

    def _rollback(self, fallen_player: str) -> dict[str, Any]:
        if not self.state.checkpoint:
            raise RuleViolation("No checkpoint is available")
        previous_count = self.state.rollback_count
        previous_history = list(self.state.history)
        checkpoint = copy.deepcopy(self.state.checkpoint)
        restored = GameState.from_dict(checkpoint)
        restored.checkpoint = copy.deepcopy(checkpoint)
        restored.rollback_count = previous_count + 1
        restored.history = previous_history[-HISTORY_LIMIT:]
        attempts = copy.deepcopy(self.state.world.get("scenario_attempts", {}))
        scenario_id = str(self.state.scenario.get("id", self.state.scenario_index))
        attempts[scenario_id] = int(attempts.get(scenario_id, 1)) + 1
        restored.world["scenario_attempts"] = attempts
        resolve_bonus = min(3, int(attempts[scenario_id]) // 2)
        for player in restored.players.values():
            player.statuses["resolve_dice"] = resolve_bonus
        self.state = restored
        return {
            "type": "rollback",
            "fallen_player": fallen_player,
            "checkpoint_scenario": restored.scenario_index,
            "scenario_attempt": attempts[scenario_id],
            "resolve_dice": resolve_bonus,
        }

    def _draw(self, player: PlayerState, amount: int) -> None:
        for _ in range(amount):
            if not player.deck and player.discard:
                player.deck = list(reversed(player.discard))
                player.discard.clear()
            if player.deck:
                player.hand.append(player.deck.pop())

    def _ally(self, player_id: str) -> PlayerState:
        return next((player for key, player in self.state.players.items() if key != player_id), self.state.players[player_id])
