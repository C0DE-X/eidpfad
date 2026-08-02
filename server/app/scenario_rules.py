from __future__ import annotations

"""Authoritative, serialisable scenario objective rules.

The game state deliberately stores this module's runtime data below ``world``.  Old
saves therefore remain loadable and no parallel, non-persisted in-memory state is
introduced.  ``GameEngine`` only has to call the lifecycle hooks documented on
``ScenarioRules``.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import RuleViolation
from .game_state import MAX_ACTION_POINTS, GameState


RUNTIME_KEY = "scenario_runtime"
CONSEQUENCES_KEY = "campaign_consequences"


@dataclass(frozen=True)
class ObjectiveDefinition:
    kind: str
    title: str
    description: str
    counter: str
    maximum: int


OBJECTIVES: dict[str, ObjectiveDefinition] = {
    "ambush": ObjectiveDefinition(
        "survive_opening",
        "Den ersten Ansturm überstehen",
        "Überlebt den angekündigten Eröffnungsangriff und besiegt alle Gegner.",
        "opening_round",
        1,
    ),
    "raid": ObjectiveDefinition(
        "contain_threat",
        "Den Überfall eindämmen",
        "Besiegt alle Wellen, bevor die Bedrohung sechs erreicht.",
        "threat",
        6,
    ),
    "village": ObjectiveDefinition(
        "protect_target",
        "Die Dorfbewohner schützen",
        "Mindestens ein Lebenspunkt der Dorfbewohner muss erhalten bleiben.",
        "protected_hp",
        12,
    ),
    "caravan": ObjectiveDefinition(
        "protect_target",
        "Die Karawane eskortieren",
        "Mindestens ein Lebenspunkt der Karawane muss erhalten bleiben.",
        "protected_hp",
        15,
    ),
    "hunt": ObjectiveDefinition(
        "prepare_hunt",
        "Die Beute stellen",
        "Spielt in Runde eins eine Vorbereitungskarte, bevor die Beute flieht.",
        "prepared",
        1,
    ),
    "ruin": ObjectiveDefinition(
        "contain_curse",
        "Den Fluch eindämmen",
        "Besiegt alle Gegner, bevor die Fluchgefahr sechs erreicht.",
        "curse",
        6,
    ),
    "country_boss": ObjectiveDefinition(
        "defeat_all",
        "Den Länderboss bezwingen",
        "Besiegt Elite und Länderboss.",
        "defeated",
        2,
    ),
    "final_boss": ObjectiveDefinition(
        "defeat_all",
        "Die Weltennaht schließen",
        "Erfüllt den Bossvertrag und besiegt alle Ziele.",
        "defeated",
        2,
    ),
}


def objective_definition(kind: str) -> ObjectiveDefinition:
    try:
        return OBJECTIVES[kind]
    except KeyError as exc:
        raise RuleViolation(f"Unsupported scenario kind: {kind}") from exc


class ScenarioRules:
    """Lifecycle rules for scenario objectives and persistent consequences."""

    @classmethod
    def initialize(cls, state: GameState) -> list[dict[str, Any]]:
        scenario = state.scenario
        existing = state.world.get(RUNTIME_KEY)
        if isinstance(existing, dict) and existing.get("scenario_id") == scenario.get("id"):
            return []

        definition = objective_definition(str(scenario["kind"]))
        difficulty = max(1, int(scenario.get("difficulty", 1)))
        maximum = definition.maximum
        if definition.kind == "protect_target":
            maximum += min(6, difficulty // 2)

        runtime: dict[str, Any] = {
            "version": 1,
            "scenario_id": str(scenario["id"]),
            "scenario_kind": str(scenario["kind"]),
            "status": "active",
            "objective": {
                "kind": definition.kind,
                "title": definition.title,
                "description": definition.description,
                "counter": definition.counter,
                "current": maximum if definition.kind == "protect_target" else 0,
                "maximum": maximum,
            },
            "rounds_survived": 0,
            "enemies_defeated": 0,
            "prepared_by": [],
            "failure_reason": None,
        }
        if scenario["kind"] == "village":
            runtime["protected_targets"] = {
                "objective:villagers": {
                    "id": "objective:villagers",
                    "name": "Dorfbewohner",
                    "hp": maximum,
                    "max_hp": maximum,
                    "side": "objective",
                }
            }
        elif scenario["kind"] == "caravan":
            runtime["protected_targets"] = {
                "objective:caravan": {
                    "id": "objective:caravan",
                    "name": "Karawane",
                    "hp": maximum,
                    "max_hp": maximum,
                    "side": "objective",
                }
            }
        else:
            runtime["protected_targets"] = {}

        state.world[RUNTIME_KEY] = runtime
        return [{"type": "scenario_objective_started", "objective": deepcopy(runtime["objective"])}]

    @staticmethod
    def runtime(state: GameState) -> dict[str, Any]:
        runtime = state.world.get(RUNTIME_KEY)
        if not isinstance(runtime, dict) or runtime.get("scenario_id") != state.scenario.get("id"):
            raise RuleViolation("Scenario objective has not been initialized")
        return runtime

    @classmethod
    def client_view(cls, state: GameState) -> dict[str, Any]:
        runtime = cls.runtime(state)
        return deepcopy(
            {
                "status": runtime["status"],
                "objective": runtime["objective"],
                "protected_targets": runtime["protected_targets"],
                "failure_reason": runtime["failure_reason"],
            }
        )

    @classmethod
    def record_card(
        cls,
        state: GameState,
        actor_id: str,
        card: Mapping[str, Any],
        target_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        runtime = cls.runtime(state)
        if runtime["status"] != "active":
            return []
        kind = runtime["scenario_kind"]
        events: list[dict[str, Any]] = []

        # A hunt requires an actual first-round preparation action, not a label.
        if kind == "hunt" and state.round_number == 1 and card.get("phase") == "utility":
            if actor_id not in runtime["prepared_by"]:
                runtime["prepared_by"].append(actor_id)
            runtime["objective"]["current"] = 1
            events.append({"type": "hunt_prepared", "player": actor_id})

        # Cleanse/warding utility is a deliberate way to manage the ruin clock.
        if kind == "ruin":
            cleansing = sum(
                int(effect.get("amount", 1))
                for effect in card.get("effects", ())
                if effect.get("type") in {"cleanse", "ward_objective"}
            )
            if cleansing:
                before = int(runtime["objective"]["current"])
                runtime["objective"]["current"] = max(0, before - cleansing)
                events.append(
                    {
                        "type": "curse_reduced",
                        "player": actor_id,
                        "amount": before - runtime["objective"]["current"],
                    }
                )

        # Healing may explicitly target a protect objective. It never happens by
        # accident when the player intended to heal their partner.
        targets = target_ids or []
        protected = runtime["protected_targets"]
        for target_id in targets:
            target = protected.get(target_id)
            if target is None:
                continue
            healing = sum(
                int(effect.get("amount", 0))
                for effect in card.get("effects", ())
                if effect.get("type") in {"heal_ally", "heal_all", "heal_objective"}
            )
            if healing:
                before = int(target["hp"])
                target["hp"] = min(int(target["max_hp"]), before + healing)
                runtime["objective"]["current"] = int(target["hp"])
                events.append(
                    {
                        "type": "objective_healed",
                        "target": target_id,
                        "amount": int(target["hp"]) - before,
                    }
                )
        return events

    @classmethod
    def record_enemy_attack(cls, state: GameState, unblocked_hits: int) -> list[dict[str, Any]]:
        runtime = cls.runtime(state)
        if runtime["status"] != "active" or runtime["scenario_kind"] not in {"village", "caravan"}:
            return []
        # Collateral is bounded but real. A perfect block protects the objective.
        damage = max(0, int(unblocked_hits))
        if damage == 0:
            return []
        target = next(iter(runtime["protected_targets"].values()))
        target["hp"] = max(0, int(target["hp"]) - damage)
        runtime["objective"]["current"] = int(target["hp"])
        events = [{"type": "objective_damaged", "target": target["id"], "amount": damage, "hp": target["hp"]}]
        if target["hp"] <= 0:
            events.extend(cls._fail(state, runtime, "protected_target_destroyed"))
        return events

    @classmethod
    def record_round_started(cls, state: GameState) -> list[dict[str, Any]]:
        runtime = cls.runtime(state)
        if runtime["status"] != "active":
            return []
        runtime["rounds_survived"] = max(int(runtime["rounds_survived"]), state.round_number - 1)
        kind = runtime["scenario_kind"]
        events: list[dict[str, Any]] = []

        if kind == "ambush" and state.round_number >= 2 and runtime["objective"]["current"] == 0:
            runtime["objective"]["current"] = 1
            events.append({"type": "opening_assault_survived"})
        elif kind == "raid" and state.round_number >= 2:
            runtime["objective"]["current"] += 1
            events.append({"type": "threat_changed", "value": runtime["objective"]["current"]})
            if runtime["objective"]["current"] >= runtime["objective"]["maximum"]:
                events.extend(cls._fail(state, runtime, "raid_overrun"))
        elif kind == "hunt" and state.round_number >= 2 and not runtime["prepared_by"]:
            events.extend(cls._fail(state, runtime, "quarry_escaped"))
        elif kind == "ruin" and state.round_number >= 2:
            runtime["objective"]["current"] += 1
            events.append({"type": "curse_changed", "value": runtime["objective"]["current"]})
            if runtime["objective"]["current"] >= runtime["objective"]["maximum"]:
                events.extend(cls._fail(state, runtime, "curse_consumed_party"))
        return events

    @classmethod
    def record_player_fallen(cls, state: GameState, player_id: str) -> list[dict[str, Any]]:
        runtime = cls.runtime(state)
        if runtime["scenario_kind"] == "ambush" and state.round_number == 1:
            return cls._fail(state, runtime, f"opening_assault_felled:{player_id}")
        return []

    @classmethod
    def record_enemy_defeated(cls, state: GameState, remaining_enemies: int) -> list[dict[str, Any]]:
        runtime = cls.runtime(state)
        if runtime["status"] != "active":
            return []
        runtime["enemies_defeated"] += 1
        events = [
            {
                "type": "scenario_progress",
                "enemies_defeated": runtime["enemies_defeated"],
                "remaining_enemies": max(0, int(remaining_enemies)),
            }
        ]
        if remaining_enemies > 0:
            return events

        kind = runtime["scenario_kind"]
        requirements_met = (
            kind != "ambush" or runtime["objective"]["current"] >= 1 or state.round_number == 1
        ) and (kind != "hunt" or bool(runtime["prepared_by"]))
        if requirements_met:
            runtime["status"] = "succeeded"
            events.append({"type": "scenario_objective_succeeded", "objective": runtime["objective"]["kind"]})
            events.extend(cls._persist_consequence(state, "success"))
        else:
            events.extend(cls._fail(state, runtime, "objective_requirements_not_met"))
        return events

    @classmethod
    def assert_completion_allowed(cls, state: GameState) -> None:
        status = cls.runtime(state)["status"]
        if status != "succeeded":
            raise RuleViolation(f"Scenario cannot complete while objective is {status}")

    @staticmethod
    def ambush_attack_dice_bonus(state: GameState) -> int:
        runtime = ScenarioRules.runtime(state)
        return 1 if runtime["scenario_kind"] == "ambush" and state.round_number == 1 else 0

    @staticmethod
    def hunt_utility_bonus(state: GameState, actor_id: str) -> int:
        runtime = ScenarioRules.runtime(state)
        return 1 if runtime["scenario_kind"] == "hunt" and state.round_number == 1 and actor_id in runtime["prepared_by"] else 0

    @staticmethod
    def ruin_loot_rarity_bonus(state: GameState) -> int:
        runtime = ScenarioRules.runtime(state)
        return 1 if runtime["scenario_kind"] == "ruin" and runtime["status"] == "succeeded" else 0

    @classmethod
    def _fail(cls, state: GameState, runtime: dict[str, Any], reason: str) -> list[dict[str, Any]]:
        if runtime["status"] == "failed":
            return []
        runtime["status"] = "failed"
        runtime["failure_reason"] = reason
        events = [{"type": "scenario_objective_failed", "reason": reason}]
        events.extend(cls._persist_consequence(state, "failure"))
        return events

    @classmethod
    def _persist_consequence(cls, state: GameState, outcome: str) -> list[dict[str, Any]]:
        consequences = state.world.setdefault(CONSEQUENCES_KEY, [])
        scenario_id = str(state.scenario["id"])
        if any(entry.get("scenario_id") == scenario_id for entry in consequences):
            return []
        entry = {
            "scenario_id": scenario_id,
            "country_id": state.scenario.get("country_id"),
            "kind": state.scenario["kind"],
            "outcome": outcome,
            "faction_reputation": 1 if outcome == "success" and state.scenario["kind"] in {"village", "caravan"} else 0,
            "unresolved_problem": outcome != "success",
        }
        consequences.append(entry)
        return [{"type": "campaign_consequence_recorded", "consequence": deepcopy(entry)}]


class WaveTransitionRules:
    """Normalize a newly spawned wave after an end-of-round DoT/trap kill.

    Mid-turn weapon kills intentionally keep the current phase and action points.
    Only deaths while ``_finish_round`` is resolving use this reset.
    """

    @staticmethod
    def after_round_resolution(state: GameState) -> list[dict[str, Any]]:
        for player in state.players.values():
            player.action_points = MAX_ACTION_POINTS
            player.guard = 0
            player.bonus_block_dice = 0
            player.played_weapon_this_round = False
        state.round_number += 1
        state.starter_index = (state.starter_index + 1) % len(state.turn_order)
        state.phase_index = 0
        state.active_slot = 0
        state.passed_players.clear()
        return [
            {"type": "wave_transition_completed", "enemy": state.enemy.enemy_id},
            {
                "type": "round_started",
                "round": state.round_number,
                "phase": state.phase,
                "active_player": state.active_player,
            },
        ]
