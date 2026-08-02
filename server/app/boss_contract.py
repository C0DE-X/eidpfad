"""Authoritative contract for the final encounter at the Weltennaht.

The regular combat engine intentionally remains useful for ordinary encounters.  The
final encounter has stronger invariants though: objectives may not be skipped by a large
damage packet and the boss may only be defeated by a joint action.  This module owns
those invariants as a small, serialisable state machine.

Integration code should persist :meth:`BossContract.export` next to ``GameState`` and
route every final-encounter target action through :meth:`BossContract.apply_damage`.
``der_letzte_eid`` must never be sent through the ordinary card resolver; use
:meth:`BossContract.commit_final_oath` instead.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .dice import roll_d12
from .errors import RuleViolation


FINAL_OATH_CARD_ID = "der_letzte_eid"
FINAL_OATH_AP_COST = 5
FINAL_OATH_REQUIRED_POWER = 12
FINAL_OATH_REQUIRED_SUCCESSES = 6
MAX_OATH_POWER = 20
MAX_THREAT = 12

STAGE_GATE = "oath_gate"
STAGE_WARDENS = "wardens"
STAGE_ANCHORS = "anchors"
STAGE_ARMORED_FORM = "armored_form"
STAGE_TORN_WORLD = "torn_world"
STAGE_FINAL_OATH = "final_oath"
STAGE_DEFEATED = "defeated"

STAGES = (
    STAGE_GATE,
    STAGE_WARDENS,
    STAGE_ANCHORS,
    STAGE_ARMORED_FORM,
    STAGE_TORN_WORLD,
    STAGE_FINAL_OATH,
    STAGE_DEFEATED,
)


# Each identity has clues that describe behaviour rather than directly naming the boss.
# The selected id stays server-only until the armored form enters the arena.
THRONELESS: tuple[dict[str, Any], ...] = (
    {
        "id": "ash_regent",
        "name": "Der Aschenregent",
        "epithet": "Herr der verglühten Schwüre",
        "clues": ("warmer_throne", "cinder_seal", "breathless_choir"),
        "arena_order": ("ash", "rift", "frost"),
    },
    {
        "id": "mirror_queen",
        "name": "Die Spiegelkönigin",
        "epithet": "Das Antlitz hinter jedem Eid",
        "clues": ("silver_reflection", "borrowed_voice", "shattered_crown"),
        "arena_order": ("crystal", "night", "rift"),
    },
    {
        "id": "drowned_judge",
        "name": "Der Ertrunkene Richter",
        "epithet": "Wäger der namenlosen Schuld",
        "clues": ("salted_verdict", "wet_chains", "silent_bell"),
        "arena_order": ("sunken", "storm", "rift"),
    },
    {
        "id": "thorn_heir",
        "name": "Die Dornenerbin",
        "epithet": "Kind des ersten gebrochenen Bundes",
        "clues": ("blood_bloom", "rooted_blade", "green_scar"),
        "arena_order": ("thorn", "forest", "rift"),
    },
    {
        "id": "bone_pilgrim",
        "name": "Der Knochenpilger",
        "epithet": "Sammler der letzten Wege",
        "clues": ("ivory_footprint", "empty_reliquary", "grave_dust"),
        "arena_order": ("bone", "moor", "rift"),
    },
    {
        "id": "storm_exile",
        "name": "Die Sturmverbannte",
        "epithet": "Stimme jenseits des Himmels",
        "clues": ("forked_sigil", "still_thunder", "windless_banner"),
        "arena_order": ("storm", "coast", "rift"),
    },
)


@dataclass
class Objective:
    id: str
    name: str
    max_hp: int
    hp: int
    armor: int = 0

    @property
    def defeated(self) -> bool:
        return self.hp <= 0

    def damage(self, amount: int, *, bypass_armor: bool = False) -> tuple[int, int]:
        amount = max(0, int(amount))
        absorbed = 0 if bypass_armor else min(self.armor, amount)
        if not bypass_armor:
            self.armor -= absorbed
        dealt = min(self.hp, amount - absorbed)
        self.hp -= dealt
        return dealt, absorbed


@dataclass
class FinalOathContribution:
    actor_id: str
    action_points_spent: int
    dice_count: int
    values: list[int]
    threshold: int
    successes: int


@dataclass
class BossContractState:
    seed: int
    player_ids: list[str]
    sovereign_id: str
    stage: str = STAGE_GATE
    gate: Objective = field(
        default_factory=lambda: Objective("oath_gate", "Das Eidtor", 36, 36, 6)
    )
    wardens: dict[str, Objective] = field(default_factory=dict)
    anchors: dict[str, Objective] = field(default_factory=dict)
    armor_parts: dict[str, Objective] = field(default_factory=dict)
    boss_hp: int = 120
    boss_max_hp: int = 120
    arena_index: int = 0
    threat: int = 0
    oath_power: int = 0
    round_number: int = 1
    revealed_clues: list[str] = field(default_factory=list)
    unresolved_problems: list[str] = field(default_factory=list)
    final_oath_contributions: dict[str, FinalOathContribution] = field(default_factory=dict)
    final_oath_attempt: int = 1
    final_oath_roll_index: int = 0
    completed: bool = False


def _default_wardens(world_tier: int) -> dict[str, Objective]:
    hp = 28 + max(0, world_tier - 1) * 6
    return {
        "warden_memory": Objective("warden_memory", "Wächter der Erinnerung", hp, hp, 3),
        "warden_promise": Objective("warden_promise", "Wächter des Versprechens", hp, hp, 3),
    }


def _default_anchors(world_tier: int) -> dict[str, Objective]:
    hp = 24 + max(0, world_tier - 1) * 5
    return {
        "anchor_origin": Objective("anchor_origin", "Eidanker des Ursprungs", hp, hp, 2),
        "anchor_bond": Objective("anchor_bond", "Eidanker des Bundes", hp, hp, 2),
        "anchor_future": Objective("anchor_future", "Eidanker der Zukunft", hp, hp, 2),
    }


def _default_armor(world_tier: int) -> dict[str, Objective]:
    hp = 20 + max(0, world_tier - 1) * 4
    return {
        "armor_crown": Objective("armor_crown", "Namenlose Krone", hp, hp, 4),
        "armor_cuirass": Objective("armor_cuirass", "Panzer des Meineids", hp, hp, 5),
        "armor_gauntlet": Objective("armor_gauntlet", "Schwurbrecherfaust", hp, hp, 3),
        "armor_greaves": Objective("armor_greaves", "Beinschienen der Flucht", hp, hp, 3),
    }


def is_reserved_boss_card(card_id: str) -> bool:
    """Return whether a card is owned by the boss contract, not normal progression."""

    return card_id == FINAL_OATH_CARD_ID


def filter_progression_rewards(card_ids: Iterable[str]) -> list[str]:
    """Prevent the final card from being awarded by ordinary level progression."""

    return [card_id for card_id in card_ids if not is_reserved_boss_card(card_id)]


class BossContract:
    """Non-skippable final-boss state machine.

    Damage is target based.  Only the targets returned by :attr:`active_targets` are
    legal.  Boss hit points have hard floors at arena boundaries, so one oversized hit
    can advance at most one arena and can never kill the boss.
    """

    def __init__(self, state: BossContractState, *, world_tier: int = 1) -> None:
        if len(set(state.player_ids)) != 2:
            raise RuleViolation("The boss contract requires exactly two different players")
        if state.stage not in STAGES:
            raise RuleViolation(f"Unknown boss stage: {state.stage}")
        self.state = state
        self.world_tier = max(1, int(world_tier))

    @classmethod
    def new(
        cls,
        seed: int,
        player_ids: Iterable[str],
        *,
        world_tier: int = 1,
        unresolved_problems: Iterable[str] = (),
    ) -> "BossContract":
        players = list(player_ids)
        digest = hashlib.sha256(f"eidpfad-throneless:{seed}:{world_tier}".encode()).digest()
        sovereign = THRONELESS[int.from_bytes(digest[:4], "big") % len(THRONELESS)]
        boss_hp = 120 + max(0, world_tier - 1) * 24
        state = BossContractState(
            seed=int(seed),
            player_ids=players,
            sovereign_id=str(sovereign["id"]),
            gate=Objective("oath_gate", "Das Eidtor", 36 + (world_tier - 1) * 6, 36 + (world_tier - 1) * 6, 6 + world_tier - 1),
            wardens=_default_wardens(world_tier),
            anchors=_default_anchors(world_tier),
            armor_parts=_default_armor(world_tier),
            boss_hp=boss_hp,
            boss_max_hp=boss_hp,
            unresolved_problems=list(dict.fromkeys(unresolved_problems)),
        )
        return cls(state, world_tier=world_tier)

    @classmethod
    def restore(cls, value: dict[str, Any]) -> "BossContract":
        payload = copy.deepcopy(value)
        world_tier = int(payload.pop("world_tier", 1))
        payload["gate"] = Objective(**payload["gate"])
        for key in ("wardens", "anchors", "armor_parts"):
            payload[key] = {target_id: Objective(**target) for target_id, target in payload[key].items()}
        payload["final_oath_contributions"] = {
            player_id: FinalOathContribution(**contribution)
            for player_id, contribution in payload.get("final_oath_contributions", {}).items()
        }
        return cls(BossContractState(**payload), world_tier=world_tier)

    def export(self) -> dict[str, Any]:
        return {**asdict(self.state), "world_tier": self.world_tier}

    @property
    def sovereign(self) -> dict[str, Any]:
        return next(entry for entry in THRONELESS if entry["id"] == self.state.sovereign_id)

    @property
    def arena(self) -> str:
        return str(self.sovereign["arena_order"][min(self.state.arena_index, 2)])

    @property
    def active_targets(self) -> tuple[str, ...]:
        stage = self.state.stage
        if stage == STAGE_GATE:
            return (self.state.gate.id,) if not self.state.gate.defeated else ()
        if stage == STAGE_WARDENS:
            return tuple(target.id for target in self.state.wardens.values() if not target.defeated)
        if stage == STAGE_ANCHORS:
            return tuple(target.id for target in self.state.anchors.values() if not target.defeated)
        if stage == STAGE_ARMORED_FORM:
            return tuple(target.id for target in self.state.armor_parts.values() if not target.defeated)
        if stage == STAGE_TORN_WORLD:
            return ("throneless",)
        return ()

    @property
    def boss_attack_bonus(self) -> int:
        return self.state.threat // 3 + len(self.state.unresolved_problems)

    def public_view(self) -> dict[str, Any]:
        """Return UI-safe state without leaking the hidden sovereign identity."""

        reveal_identity = self.state.stage in {
            STAGE_ARMORED_FORM,
            STAGE_TORN_WORLD,
            STAGE_FINAL_OATH,
            STAGE_DEFEATED,
        }
        return {
            "stage": self.state.stage,
            "active_targets": list(self.active_targets),
            "gate": asdict(self.state.gate),
            "wardens": {key: asdict(value) for key, value in self.state.wardens.items()},
            "anchors": {key: asdict(value) for key, value in self.state.anchors.items()},
            "armor_parts": {key: asdict(value) for key, value in self.state.armor_parts.items()},
            "boss_hp": self.state.boss_hp,
            "boss_max_hp": self.state.boss_max_hp,
            "arena": self.arena if reveal_identity else None,
            "arena_index": self.state.arena_index,
            "threat": self.state.threat,
            "oath_power": self.state.oath_power,
            "oath_power_required": FINAL_OATH_REQUIRED_POWER,
            "revealed_clues": list(self.state.revealed_clues),
            "unresolved_problem_echoes": list(self.state.unresolved_problems),
            "sovereign": copy.deepcopy(self.sovereign) if reveal_identity else None,
            "final_oath_committed_players": sorted(self.state.final_oath_contributions),
            "final_oath_attempt": self.state.final_oath_attempt,
            "completed": self.state.completed,
        }

    def discover_clue(self, clue_id: str) -> dict[str, Any]:
        valid = set(self.sovereign["clues"])
        if clue_id not in valid:
            raise RuleViolation("This clue does not belong to the hidden sovereign")
        if clue_id not in self.state.revealed_clues:
            self.state.revealed_clues.append(clue_id)
        return {"type": "sovereign_clue_revealed", "clue_id": clue_id}

    def apply_damage(
        self,
        target_id: str,
        amount: int,
        *,
        bypass_armor: bool = False,
    ) -> list[dict[str, Any]]:
        if self.state.completed:
            raise RuleViolation("The final encounter is already complete")
        if target_id not in self.active_targets:
            raise RuleViolation(f"Target {target_id!r} is not vulnerable during {self.state.stage}")
        if amount < 0:
            raise RuleViolation("Damage cannot be negative")

        if target_id == "throneless":
            return self._damage_throneless(amount)

        objective = self._objective(target_id)
        dealt, absorbed = objective.damage(amount, bypass_armor=bypass_armor)
        events: list[dict[str, Any]] = [{
            "type": "boss_objective_damaged",
            "stage": self.state.stage,
            "target_id": target_id,
            "amount": dealt,
            "absorbed": absorbed,
            "hp": objective.hp,
        }]
        if objective.defeated:
            events.append({"type": "boss_objective_destroyed", "target_id": target_id})
            self._gain_oath_power(self._objective_oath_reward(target_id), events)
            self._raise_threat(1, events)
            if not self.active_targets:
                events.extend(self._advance_stage())
        return events

    def break_armor(self, target_id: str, amount: int) -> list[dict[str, Any]]:
        """Reduce armor on the currently vulnerable objective without dealing HP damage."""

        if self.state.completed:
            raise RuleViolation("The final encounter is already complete")
        if target_id not in self.active_targets:
            raise RuleViolation(f"Target {target_id!r} is not vulnerable during {self.state.stage}")
        if target_id == "throneless":
            # The torn-world form has HP gates instead of a mutable armor pool.
            return [{"type": "armor_broken", "target": target_id, "amount": 0}]
        objective = self._objective(target_id)
        removed = min(objective.armor, max(0, int(amount)))
        objective.armor -= removed
        return [{"type": "armor_broken", "target": target_id, "amount": removed}]

    def _damage_throneless(self, amount: int) -> list[dict[str, Any]]:
        # Arena floors are inclusive.  The final floor is one HP; only the joint oath
        # action may take the encounter to the defeated state.
        floors = (self.state.boss_max_hp * 2 // 3, self.state.boss_max_hp // 3, 1)
        floor = floors[self.state.arena_index]
        previous = self.state.boss_hp
        self.state.boss_hp = max(floor, self.state.boss_hp - max(0, int(amount)))
        dealt = previous - self.state.boss_hp
        events: list[dict[str, Any]] = [{
            "type": "throneless_damaged",
            "amount": dealt,
            "hp": self.state.boss_hp,
            "floor": floor,
            "arena_index": self.state.arena_index,
        }]
        if self.state.boss_hp == floor:
            self._gain_oath_power(1, events)
            if self.state.arena_index < 2:
                self.state.arena_index += 1
                self._raise_threat(2, events)
                events.append({
                    "type": "boss_arena_changed",
                    "arena_index": self.state.arena_index,
                    "arena": self.arena,
                    "problem_echoes": list(self.state.unresolved_problems),
                })
            else:
                self.state.stage = STAGE_FINAL_OATH
                events.append({
                    "type": "boss_stage_changed",
                    "stage": STAGE_FINAL_OATH,
                    "card_id": FINAL_OATH_CARD_ID,
                    "required_oath_power": FINAL_OATH_REQUIRED_POWER,
                })
        return events

    def end_round(self) -> list[dict[str, Any]]:
        if self.state.completed:
            return []
        self.state.round_number += 1
        pressure = 1
        if self.state.stage == STAGE_ANCHORS:
            pressure += sum(not anchor.defeated for anchor in self.state.anchors.values())
        if self.state.stage == STAGE_TORN_WORLD:
            pressure += min(2, len(self.state.unresolved_problems))
        events: list[dict[str, Any]] = []
        self._raise_threat(pressure, events)
        events.append({
            "type": "boss_round_started",
            "round": self.state.round_number,
            "threat": self.state.threat,
            "attack_bonus": self.boss_attack_bonus,
        })
        return events

    def reduce_threat(self, amount: int) -> dict[str, Any]:
        before = self.state.threat
        self.state.threat = max(0, before - max(0, int(amount)))
        return {"type": "boss_threat_reduced", "amount": before - self.state.threat, "threat": self.state.threat}

    def commit_final_oath(
        self,
        actor_id: str,
        *,
        available_action_points: int,
    ) -> list[dict[str, Any]]:
        """Lock one half of the joint final action.

        Each player pays the full five AP and receives an independent, server-generated
        pool.  Pools are kept separate so the ordinary eight-die cap cannot discard
        cooperation bonuses.  The caller must apply the emitted
        ``action_points_spent`` value to ``PlayerState``.
        """

        if self.state.stage != STAGE_FINAL_OATH or self.state.completed:
            raise RuleViolation("The final oath is not available")
        if actor_id not in self.state.player_ids:
            raise RuleViolation("Unknown final-oath contributor")
        if actor_id in self.state.final_oath_contributions:
            raise RuleViolation("This player already committed to the current final oath")
        if available_action_points < FINAL_OATH_AP_COST:
            raise RuleViolation("The final oath requires five action points from each player")
        if self.state.oath_power < FINAL_OATH_REQUIRED_POWER:
            raise RuleViolation("The party has not gathered enough oath power")

        # Objective completion beyond the minimum makes both halves of the oath
        # stronger.  The roll is generated here, never accepted from a client message.
        dice_count = 4 + min(4, (self.state.oath_power - FINAL_OATH_REQUIRED_POWER) // 2)
        roll = roll_d12(
            self.state.seed,
            self.state.final_oath_roll_index,
            dice_count,
            7,
        )
        self.state.final_oath_roll_index += 1

        self.state.final_oath_contributions[actor_id] = FinalOathContribution(
            actor_id=actor_id,
            action_points_spent=FINAL_OATH_AP_COST,
            dice_count=int(dice_count),
            values=list(roll["values"]),
            threshold=int(roll["threshold"]),
            successes=int(roll["successes"]),
        )
        events: list[dict[str, Any]] = [{
            "type": "dice_rolled",
            "actor": actor_id,
            "purpose": "final_oath",
            "sides": 12,
            **roll,
        }, {
            "type": "final_oath_contribution_locked",
            "player": actor_id,
            "action_points_spent": FINAL_OATH_AP_COST,
            "contributors": len(self.state.final_oath_contributions),
            "required_contributors": len(self.state.player_ids),
        }]
        if len(self.state.final_oath_contributions) < len(self.state.player_ids):
            return events

        total_successes = sum(value.successes for value in self.state.final_oath_contributions.values())
        total_dice = sum(value.dice_count for value in self.state.final_oath_contributions.values())
        contributors = sorted(self.state.final_oath_contributions)
        if total_successes >= FINAL_OATH_REQUIRED_SUCCESSES:
            self.state.boss_hp = 0
            self.state.stage = STAGE_DEFEATED
            self.state.completed = True
            events.append({
                "type": "final_oath_resolved",
                "success": True,
                "contributors": contributors,
                "dice_count": total_dice,
                "successes": total_successes,
                "boss_defeated": True,
            })
        else:
            self.state.final_oath_contributions.clear()
            self.state.final_oath_attempt += 1
            self._raise_threat(2, events)
            events.append({
                "type": "final_oath_resolved",
                "success": False,
                "contributors": contributors,
                "dice_count": total_dice,
                "successes": total_successes,
                "boss_defeated": False,
                "next_attempt": self.state.final_oath_attempt,
            })
        return events

    def validate_normal_card(self, card_id: str) -> None:
        if is_reserved_boss_card(card_id):
            raise RuleViolation("Der letzte Eid is resolved only as a joint boss action")

    def _objective(self, target_id: str) -> Objective:
        if target_id == self.state.gate.id:
            return self.state.gate
        for group in (self.state.wardens, self.state.anchors, self.state.armor_parts):
            if target_id in group:
                return group[target_id]
        raise RuleViolation(f"Unknown boss objective: {target_id}")

    @staticmethod
    def _objective_oath_reward(target_id: str) -> int:
        if target_id == "oath_gate":
            return 1
        if target_id.startswith("warden_"):
            return 1
        if target_id.startswith("anchor_"):
            return 2
        if target_id.startswith("armor_"):
            return 1
        return 0

    def _advance_stage(self) -> list[dict[str, Any]]:
        transitions = {
            STAGE_GATE: STAGE_WARDENS,
            STAGE_WARDENS: STAGE_ANCHORS,
            STAGE_ANCHORS: STAGE_ARMORED_FORM,
            STAGE_ARMORED_FORM: STAGE_TORN_WORLD,
        }
        current = self.state.stage
        if current not in transitions:
            return []
        self.state.stage = transitions[current]
        event: dict[str, Any] = {"type": "boss_stage_changed", "stage": self.state.stage}
        if self.state.stage == STAGE_ARMORED_FORM:
            event["sovereign"] = copy.deepcopy(self.sovereign)
        if self.state.stage == STAGE_TORN_WORLD:
            event["arena"] = self.arena
            event["problem_echoes"] = list(self.state.unresolved_problems)
        return [event]

    def _gain_oath_power(self, amount: int, events: list[dict[str, Any]]) -> None:
        before = self.state.oath_power
        self.state.oath_power = min(MAX_OATH_POWER, before + max(0, int(amount)))
        gained = self.state.oath_power - before
        if gained:
            events.append({"type": "oath_power_gained", "amount": gained, "oath_power": self.state.oath_power})

    def _raise_threat(self, amount: int, events: list[dict[str, Any]]) -> None:
        before = self.state.threat
        self.state.threat = min(MAX_THREAT, before + max(0, int(amount)))
        gained = self.state.threat - before
        if gained:
            events.append({
                "type": "boss_threat_changed",
                "amount": gained,
                "threat": self.state.threat,
                "attack_bonus": self.boss_attack_bonus,
            })
