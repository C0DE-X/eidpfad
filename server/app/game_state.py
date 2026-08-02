from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PHASES = ("attack", "defense", "magic", "utility")
MAX_ACTION_POINTS = 5


@dataclass
class PlayerState:
    profile_id: str
    weapon: str
    magic: str
    hp: int = 30
    max_hp: int = 30
    action_points: int = MAX_ACTION_POINTS
    guard: int = 0
    bonus_block_dice: int = 0
    hand: list[str] = field(default_factory=list)
    deck: list[str] = field(default_factory=list)
    discard: list[str] = field(default_factory=list)
    exhausted: list[str] = field(default_factory=list)
    statuses: dict[str, int] = field(default_factory=dict)
    talents: dict[str, int] = field(default_factory=dict)
    inventory: list[str] = field(default_factory=list)
    equipment: dict[str, str] = field(default_factory=dict)
    played_weapon_this_round: bool = False
    character_level: int = 1
    experience: int = 0
    mastery_points: int = 0


@dataclass
class EnemyState:
    enemy_id: str = "unknown"
    name: str = "Unbekannter Gegner"
    role: str = "skirmisher"
    hp: int = 1
    max_hp: int = 1
    armor: int = 0
    block_dice: int = 0
    block_threshold: int = 8
    ward_dice: int = 0
    ward_threshold: int = 9
    attack_dice: int = 1
    hit_threshold: int = 7
    damage_per_hit: int = 2
    elite: bool = False
    boss: bool = False
    final_boss: bool = False
    boss_phase: int = 1
    traits: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)
    intent: str = "strike"
    art: str = ""
    model: str = ""
    body_family: str = "humanoid"
    animation_set: str = "combat_humanoid"
    scale: float = 1.0
    voice_profile: str = "enemy_skirmisher"
    statuses: dict[str, int] = field(default_factory=dict)


@dataclass
class GameState:
    seed: int
    players: dict[str, PlayerState]
    turn_order: list[str]
    content_version: int = 2
    campaign_length: str = "fieldzug"
    world_tier: int = 1
    world: dict[str, Any] = field(default_factory=dict)
    scenario_index: int = 0
    phase_index: int = 0
    active_slot: int = 0
    starter_index: int = 0
    passed_players: list[str] = field(default_factory=list)
    round_number: int = 1
    enemy: EnemyState = field(default_factory=EnemyState)
    enemy_queue: list[str] = field(default_factory=list)
    defeated_enemies: list[str] = field(default_factory=list)
    pending_loot: list[str] = field(default_factory=list)
    loot_claims: dict[str, str] = field(default_factory=dict)
    campaign_complete: bool = False
    awaiting_scenario_choice: bool = False
    scenario_selected_id: str = ""
    scenario_votes: dict[str, str] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    rollback_count: int = 0
    roll_index: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def phase(self) -> str:
        return PHASES[self.phase_index]

    @property
    def phase_order(self) -> list[str]:
        return self.turn_order[self.starter_index :] + self.turn_order[: self.starter_index]

    @property
    def active_player(self) -> str:
        return self.phase_order[self.active_slot]

    @property
    def scenario(self) -> dict[str, Any]:
        primary = self.world["route"][self.scenario_index]
        selected_id = self.scenario_selected_id or str(primary["id"])
        for candidate in [primary, *primary.get("alternatives", [])]:
            if candidate.get("id") == selected_id:
                return candidate
        return primary

    @property
    def available_scenarios(self) -> list[dict[str, Any]]:
        primary = self.world["route"][self.scenario_index]
        return [primary, *primary.get("alternatives", [])]

    def snapshot(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("checkpoint", None)
        # Checkpoints represent recoverable gameplay state.  The rolling audit log
        # is persisted separately and must not recursively double every save.
        value.pop("history", None)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> GameState:
        return cls(
            seed=value["seed"],
            players={key: PlayerState(**player) for key, player in value["players"].items()},
            turn_order=value["turn_order"], content_version=value.get("content_version", 1), campaign_length=value.get("campaign_length", "fieldzug"),
            world_tier=value.get("world_tier", 1), world=value.get("world", {}),
            scenario_index=value.get("scenario_index", 0), phase_index=value.get("phase_index", 0),
            active_slot=value.get("active_slot", 0), starter_index=value.get("starter_index", 0),
            passed_players=value.get("passed_players", []), round_number=value.get("round_number", 1),
            enemy=EnemyState(**value.get("enemy", {})), enemy_queue=value.get("enemy_queue", []),
            defeated_enemies=value.get("defeated_enemies", []), pending_loot=value.get("pending_loot", []),
            loot_claims=value.get("loot_claims", {}), campaign_complete=value.get("campaign_complete", False),
            awaiting_scenario_choice=value.get("awaiting_scenario_choice", False),
            scenario_selected_id=value.get("scenario_selected_id", ""),
            scenario_votes=value.get("scenario_votes", {}),
            checkpoint=value.get("checkpoint", {}), rollback_count=value.get("rollback_count", 0),
            roll_index=value.get("roll_index", 0), history=value.get("history", []),
        )
