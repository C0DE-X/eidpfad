from __future__ import annotations

"""Composable combat rules for targeting, intents, reactions and cooperation.

This module is intentionally independent from ``GameEngine``.  Every pending action
is persisted below ``GameState.world`` so reconnects cannot silently skip a reaction
or cooperation confirmation.
"""

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Mapping, Sequence

from .errors import RuleViolation
from .game_state import GameState, PlayerState


RUNTIME_KEY = "combat_runtime"

AREA_CARD_IDS = {
    "tausend_schnitte",
    "sturm_des_henkers",
    "pfeilregen",
    "sonnenhagel",
    "bolzenhagel",
    "salve",
    "feuersturm",
    "mondlose_nacht",
    "purpurflut",
}


def _runtime(state: GameState) -> dict[str, Any]:
    value = state.world.setdefault(
        RUNTIME_KEY,
        {"version": 1, "targets": {}, "announced_intent": None, "reaction_window": None, "coop_action": None},
    )
    if not isinstance(value, dict):
        raise RuleViolation("Combat runtime is malformed")
    return value


def combat_client_view(state: GameState) -> dict[str, Any]:
    """Return reconnect-safe combat UI state without exposing hidden hand data."""
    runtime = _runtime(state)
    reaction = runtime.get("reaction_window")
    cooperation = runtime.get("coop_action")
    return {
        "targets": TargetRules.client_view(state),
        "announced_intent": deepcopy(runtime.get("announced_intent")),
        "reaction_window": None
        if reaction is None
        else {
            "status": reaction["status"],
            "round": reaction["round"],
            "intent": deepcopy(reaction["intent"]),
            "responders": list(reaction["responders"]),
            "responded": list(reaction["responses"]),
        },
        "cooperation": None
        if cooperation is None
        else {
            "status": cooperation["status"],
            "actor": cooperation["actor"],
            "partners": list(cooperation["partners"]),
            "confirmed_by": list(cooperation["confirmations"]),
            "card_id": cooperation["card_id"],
            "target_ids": list(cooperation["target_ids"]),
        },
    }


def _as_target(value: Any) -> dict[str, Any]:
    target = asdict(value) if is_dataclass(value) else deepcopy(dict(value))
    enemy_id = str(target.get("enemy_id") or target.get("id") or "")
    if not enemy_id:
        raise RuleViolation("A combat target needs an id")
    target["id"] = enemy_id
    target["enemy_id"] = enemy_id
    target["side"] = "enemy"
    target["alive"] = int(target.get("hp", 0)) > 0
    return target


class TargetRules:
    @staticmethod
    def initialize(state: GameState, enemies: Sequence[Any]) -> list[dict[str, Any]]:
        if not enemies:
            raise RuleViolation("An encounter needs at least one target")
        converted = [_as_target(enemy) for enemy in enemies]
        targets = {target["id"]: target for target in converted}
        if len(targets) != len(converted):
            raise RuleViolation("Combat target ids must be unique")
        _runtime(state)["targets"] = targets
        return [{"type": "combat_targets_changed", "targets": TargetRules.client_view(state)}]

    @staticmethod
    def sync_primary(state: GameState) -> None:
        runtime = _runtime(state)
        primary = _as_target(state.enemy)
        runtime["targets"][primary["id"]] = primary

    @staticmethod
    def client_view(state: GameState) -> list[dict[str, Any]]:
        result = []
        for target in _runtime(state)["targets"].values():
            if target.get("alive", int(target.get("hp", 0)) > 0):
                result.append(deepcopy(target))
        return sorted(result, key=lambda value: value["id"])

    @staticmethod
    def targeting(card: Mapping[str, Any]) -> dict[str, Any]:
        explicit = card.get("targeting")
        if isinstance(explicit, Mapping):
            return {
                "side": str(explicit.get("side", "enemy")),
                "minimum": int(explicit.get("minimum", 1)),
                "maximum": int(explicit.get("maximum", 1)),
            }
        effect_types = {str(effect.get("type")) for effect in card.get("effects", ())}
        if effect_types & {"heal_all", "add_block_dice_all", "team_status"}:
            return {"side": "team", "minimum": 0, "maximum": 0}
        if effect_types & {"heal_ally", "add_block_dice_ally"}:
            return {"side": "ally", "minimum": 1, "maximum": 1}
        if effect_types & {"dice_attack", "dice_magic_damage", "enemy_status", "armor_break", "set_trap"}:
            return {
                "side": "enemy",
                "minimum": 1,
                "maximum": 3 if card.get("id") in AREA_CARD_IDS else 1,
            }
        return {"side": "self", "minimum": 0, "maximum": 0}

    @classmethod
    def select(
        cls,
        state: GameState,
        actor_id: str,
        card: Mapping[str, Any],
        target_ids: str | Sequence[str] | None,
    ) -> list[str]:
        rule = cls.targeting(card)
        if rule["side"] in {"self", "team"}:
            if target_ids not in (None, "", []):
                raise RuleViolation(f"{rule['side']} cards do not accept explicit targets")
            return [actor_id] if rule["side"] == "self" else list(state.turn_order)
        if rule["side"] == "ally":
            legal = [player_id for player_id in state.turn_order if player_id != actor_id]
            if not legal:
                legal = [actor_id]
        elif rule["side"] == "objective":
            legal = list(state.world.get("scenario_runtime", {}).get("protected_targets", {}))
        else:
            legal = [target["id"] for target in cls.client_view(state)]

        if isinstance(target_ids, str):
            selected = [target_ids] if target_ids else []
        else:
            selected = list(target_ids or [])
        if not selected and len(legal) == 1 and rule["minimum"] == 1:
            selected = legal
        if len(selected) != len(set(selected)):
            raise RuleViolation("Targets must be unique")
        if not rule["minimum"] <= len(selected) <= rule["maximum"]:
            raise RuleViolation(
                f"Card requires {rule['minimum']}..{rule['maximum']} targets, got {len(selected)}"
            )
        unknown = set(selected) - set(legal)
        if unknown:
            raise RuleViolation(f"Illegal targets: {sorted(unknown)}")
        return selected

    @staticmethod
    def damage(
        state: GameState,
        target_ids: Sequence[str],
        amount: int,
        *,
        bypass_armor: bool = False,
    ) -> list[dict[str, Any]]:
        runtime = _runtime(state)
        events: list[dict[str, Any]] = []
        for target_id in target_ids:
            try:
                target = runtime["targets"][target_id]
            except KeyError as exc:
                raise RuleViolation(f"Unknown combat target: {target_id}") from exc
            if not target.get("alive", True):
                raise RuleViolation(f"Target is already defeated: {target_id}")
            total = max(0, int(amount))
            absorbed = 0 if bypass_armor else min(int(target.get("armor", 0)), total)
            if not bypass_armor:
                target["armor"] = int(target.get("armor", 0)) - absorbed
            damage = total - absorbed
            target["hp"] = max(0, int(target["hp"]) - damage)
            target["alive"] = target["hp"] > 0
            if target_id == state.enemy.enemy_id:
                state.enemy.hp = int(target["hp"])
                state.enemy.armor = int(target.get("armor", 0))
            events.append(
                {"type": "enemy_damaged", "target": target_id, "amount": damage, "absorbed": absorbed}
            )
            if not target["alive"]:
                events.append({"type": "enemy_defeated", "enemy": target_id})
        return events

    @staticmethod
    def armor_break(state: GameState, target_ids: Sequence[str], amount: int) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for target_id in target_ids:
            target = _runtime(state)["targets"].get(target_id)
            if target is None:
                raise RuleViolation(f"Unknown combat target: {target_id}")
            if not target.get("alive", True):
                # A previous effect of the same already-validated card may have
                # defeated the target. Later armor-break riders resolve as a no-op.
                events.append({"type": "armor_broken", "target": target_id, "amount": 0})
                continue
            removed = min(int(target.get("armor", 0)), max(0, int(amount)))
            target["armor"] -= removed
            if target_id == state.enemy.enemy_id:
                state.enemy.armor = int(target["armor"])
            events.append({"type": "armor_broken", "target": target_id, "amount": removed})
        return events


class IntentRules:
    @staticmethod
    def announce(state: GameState) -> list[dict[str, Any]]:
        runtime = _runtime(state)
        current = runtime.get("announced_intent")
        if current and current.get("round") == state.round_number and current.get("enemy") == state.enemy.enemy_id:
            return []
        intents = state.enemy.intents or ["strike"]
        intent = intents[(state.round_number - 1) % len(intents)]
        targets = (
            list(state.turn_order)
            if state.enemy.final_boss or intent == "pressure"
            else [state.turn_order[(state.round_number - 1) % len(state.turn_order)]]
        )
        status_preview = StatusRules.statuses_for_hit(state.enemy.role, state.enemy.traits, intent)
        announcement = {
            "enemy": state.enemy.enemy_id,
            "round": state.round_number,
            "intent": intent,
            "targets": targets,
            "attack_dice": state.enemy.attack_dice + (1 if intent == "pressure" else 0),
            "hit_threshold": max(2, state.enemy.hit_threshold - (1 if intent == "advance" else 0)),
            "damage_per_hit": state.enemy.damage_per_hit + (1 if intent == "strike" else 0),
            "statuses_on_hit": status_preview,
        }
        state.enemy.intent = intent
        runtime["announced_intent"] = announcement
        return [{"type": "enemy_intent_announced", **deepcopy(announcement)}]

    @staticmethod
    def require_announced(state: GameState) -> dict[str, Any]:
        announcement = _runtime(state).get("announced_intent")
        if not announcement or announcement.get("round") != state.round_number or announcement.get("enemy") != state.enemy.enemy_id:
            raise RuleViolation("Enemy intent must be announced before it resolves")
        return deepcopy(announcement)

    @staticmethod
    def consume(state: GameState) -> dict[str, Any]:
        announcement = IntentRules.require_announced(state)
        _runtime(state)["announced_intent"] = None
        return announcement


class ReactionRules:
    @staticmethod
    def open(state: GameState) -> list[dict[str, Any]]:
        runtime = _runtime(state)
        if runtime.get("reaction_window") is not None:
            raise RuleViolation("A reaction window is already open")
        intent = IntentRules.require_announced(state)
        window = {
            "status": "open",
            "round": state.round_number,
            "intent": intent,
            "responders": list(state.turn_order),
            "responses": {},
        }
        runtime["reaction_window"] = window
        return [{"type": "reaction_window_opened", "intent": deepcopy(intent), "responders": list(state.turn_order)}]

    @staticmethod
    def respond(
        state: GameState,
        actor_id: str,
        card_id: str | None,
        catalog: Any,
        target_ids: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        window = _runtime(state).get("reaction_window")
        if not window or window["status"] != "open":
            raise RuleViolation("No reaction window is open")
        if actor_id not in window["responders"]:
            raise RuleViolation("This player cannot react")
        if actor_id in window["responses"]:
            raise RuleViolation("This player already responded")
        response: dict[str, Any] = {"kind": "pass"}
        if card_id is not None:
            card = catalog.get(card_id)
            player = state.players[actor_id]
            if card.get("kind") != "reaction":
                raise RuleViolation("Only reaction cards can be played in a reaction window")
            if card_id not in player.hand:
                raise RuleViolation("The reaction card is not in the player's hand")
            if player.action_points < int(card["action_point_cost"]):
                raise RuleViolation("Not enough action points for reaction")
            response = {
                "kind": "play_card",
                "card_id": card_id,
                "target_ids": list(target_ids or []),
                "cost": int(card["action_point_cost"]),
            }
        window["responses"][actor_id] = response
        events = [{"type": "reaction_recorded", "player": actor_id, "reaction": response["kind"]}]
        if len(window["responses"]) == len(window["responders"]):
            window["status"] = "ready"
            events.append({"type": "reaction_window_ready"})
        return events

    @staticmethod
    def consume(state: GameState) -> list[dict[str, Any]]:
        runtime = _runtime(state)
        window = runtime.get("reaction_window")
        if not window or window["status"] != "ready":
            raise RuleViolation("All players must respond before reactions resolve")
        reactions = [
            {"actor": actor, **deepcopy(response)}
            for actor, response in window["responses"].items()
            if response["kind"] == "play_card"
        ]
        runtime["reaction_window"] = None
        return reactions


class CooperationRules:
    @staticmethod
    def propose(
        state: GameState,
        actor_id: str,
        card_id: str,
        catalog: Any,
        target_ids: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        runtime = _runtime(state)
        if runtime.get("coop_action") is not None:
            raise RuleViolation("Another cooperation action is pending")
        card = catalog.get(card_id)
        if card.get("kind") != "cooperation":
            raise RuleViolation("This is not a cooperation card")
        player = state.players.get(actor_id)
        if player is None or card_id not in player.hand:
            raise RuleViolation("The cooperation card is not in the player's hand")
        if player.action_points < int(card["action_point_cost"]):
            raise RuleViolation("Not enough action points")
        partners = [player_id for player_id in state.turn_order if player_id != actor_id]
        if any(state.players[partner_id].action_points < 1 for partner_id in partners):
            raise RuleViolation("Every cooperation partner needs one action point")
        action = {
            "status": "pending",
            "actor": actor_id,
            "partners": partners,
            "confirmations": {},
            "card_id": card_id,
            "target_ids": list(target_ids or []),
            "cost": int(card["action_point_cost"]),
        }
        runtime["coop_action"] = action
        return [
            {
                "type": "cooperation_proposed",
                "actor": actor_id,
                "partners": partners,
                "card": card_id,
                "target_ids": list(target_ids or []),
            }
        ]

    @staticmethod
    def respond(state: GameState, actor_id: str, accepted: bool) -> list[dict[str, Any]]:
        action = _runtime(state).get("coop_action")
        if not action or action["status"] != "pending":
            raise RuleViolation("No cooperation action is pending")
        if actor_id not in action["partners"]:
            raise RuleViolation("Only the partner can confirm this action")
        if actor_id in action["confirmations"]:
            raise RuleViolation("This player already responded")
        action["confirmations"][actor_id] = bool(accepted)
        if not accepted:
            action["status"] = "rejected"
            return [{"type": "cooperation_rejected", "player": actor_id, "card": action["card_id"]}]
        if len(action["confirmations"]) == len(action["partners"]):
            action["status"] = "confirmed"
            return [{"type": "cooperation_confirmed", "players": [action["actor"], *action["partners"]], "card": action["card_id"]}]
        return [{"type": "cooperation_response_recorded", "player": actor_id}]

    @staticmethod
    def consume(state: GameState) -> dict[str, Any]:
        runtime = _runtime(state)
        action = runtime.get("coop_action")
        if not action or action["status"] != "confirmed":
            raise RuleViolation("Cooperation must be confirmed before resolution")
        result = deepcopy(action)
        runtime["coop_action"] = None
        return result

    @staticmethod
    def clear_rejected(state: GameState) -> None:
        action = _runtime(state).get("coop_action")
        if action and action["status"] == "rejected":
            _runtime(state)["coop_action"] = None


class StatusRules:
    @staticmethod
    def statuses_for_hit(role: str, traits: Sequence[str], intent: str) -> list[str]:
        statuses: list[str] = []
        if intent == "hex" or "drowned_hex" in traits:
            statuses.append("weakened")
        if "frost_bite" in traits or "root_bind" in traits:
            statuses.append("bound")
        if "sun_scorch" in traits:
            statuses.append("burning")
        # These two paths existed on players but had no producer.
        if role == "assassin":
            statuses.append("bleeding")
        if role == "controller" and intent in {"hex", "pressure"}:
            statuses.append("poisoned")
        return list(dict.fromkeys(statuses))

    @classmethod
    def apply_enemy_hit(cls, enemy: Any, player: PlayerState, intent: str, unblocked_hits: int) -> list[dict[str, Any]]:
        if unblocked_hits <= 0:
            return []
        events: list[dict[str, Any]] = []
        for status in cls.statuses_for_hit(enemy.role, enemy.traits, intent):
            amount = 1
            player.statuses[status] = player.statuses.get(status, 0) + amount
            events.append({"type": "player_status", "player": player.profile_id, "status": status, "amount": amount})
        return events

    @staticmethod
    def consume_player_roll_penalty(player: PlayerState, purpose: str) -> tuple[int, list[dict[str, Any]]]:
        if purpose not in {"hit", "magic", "ward"}:
            return 0, []
        amount = max(0, int(player.statuses.pop("bound", 0)))
        if amount == 0:
            return 0, []
        penalty = min(2, amount)
        return -penalty, [{"type": "status_consumed", "player": player.profile_id, "status": "bound", "dice_modifier": -penalty}]

    @staticmethod
    def weapon_combo_bonus(player: PlayerState) -> int:
        """Make ``played_weapon_this_round`` a real cooperative combo input."""
        return 1 if player.played_weapon_this_round else 0


class EffectRules:
    @staticmethod
    def heal(
        state: GameState,
        source_id: str,
        target_ids: Sequence[str],
        amount: int,
        source_bonuses: Mapping[str, int],
    ) -> list[dict[str, Any]]:
        if source_id not in state.players:
            raise RuleViolation("Unknown healing source")
        total = max(0, int(amount) + int(source_bonuses.get("healing", 0)))
        events: list[dict[str, Any]] = []
        for target_id in target_ids:
            try:
                player = state.players[target_id]
            except KeyError as exc:
                raise RuleViolation(f"Unknown healing target: {target_id}") from exc
            before = player.hp
            player.hp = min(player.max_hp, player.hp + total)
            events.append(
                {
                    "type": "player_healed",
                    "source": source_id,
                    "player": target_id,
                    "amount": player.hp - before,
                }
            )
        return events

    @staticmethod
    def resolve_player_ward(
        player: PlayerState,
        successes: int,
        bonuses: Mapping[str, int],
        roll_pool: Callable[[str, int, int, str, list[dict[str, Any]]], tuple[int, int]],
        events: list[dict[str, Any]],
    ) -> int:
        dice = max(0, int(bonuses.get("ward_dice", 0)) + int(player.talents.get("ward_dice", 0)))
        wards, _ = roll_pool(player.profile_id, dice, 8, "player_ward", events)
        remaining = max(0, int(successes) - wards)
        events.append(
            {"type": "player_ward_resolved", "player": player.profile_id, "successes": successes, "wards": wards, "remaining": remaining}
        )
        return remaining


class TalentRules:
    TALENTS = {
        "weapon_training": ("hit_dice", 1),
        "arcane_training": ("magic_dice", 1),
        "ward_training": ("ward_dice", 1),
    }

    @classmethod
    def unlock(cls, player: PlayerState, talent_id: str) -> dict[str, Any]:
        try:
            stat, amount = cls.TALENTS[talent_id]
        except KeyError as exc:
            raise RuleViolation(f"Unknown talent: {talent_id}") from exc
        if player.talents.get(f"unlocked:{talent_id}"):
            raise RuleViolation("Talent is already unlocked")
        player.talents[f"unlocked:{talent_id}"] = 1
        player.talents[stat] = player.talents.get(stat, 0) + amount
        return {"type": "talent_unlocked", "player": player.profile_id, "talent": talent_id, "bonus": {stat: amount}}
