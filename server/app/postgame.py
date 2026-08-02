"""Shared ending, legacy and New Game+ progression for completed campaigns.

The postgame is deliberately independent from the SQLAlchemy models.  It can be stored
inside the campaign's authoritative JSON state and only produces a database update
payload after both players have confirmed it.  This makes reconnects idempotent and
prevents one client from choosing an ending or starting the next world for the other.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .errors import RuleViolation


ENDING_SEAL = "seal"
ENDING_DESTROY = "destroy"
ENDING_BIND = "bind"
ENDING_DOMINATE = "dominate"
ENDING_CHOICES = (ENDING_SEAL, ENDING_DESTROY, ENDING_BIND, ENDING_DOMINATE)

PHASE_ENDING_VOTE = "ending_vote"
PHASE_LEGACY_SELECTION = "legacy_selection"
PHASE_NEW_GAME_PLUS = "new_game_plus"
PHASE_COMPLETE = "complete"

POSTGAME_PHASES = (
    PHASE_ENDING_VOTE,
    PHASE_LEGACY_SELECTION,
    PHASE_NEW_GAME_PLUS,
    PHASE_COMPLETE,
)

LEGACY_RARITIES = {"exceptional", "legendary", "unique"}
MAX_CHARACTER_LEVEL = 30


@dataclass
class LegacyTransfer:
    profile_id: str
    item_id: str
    origin_world_tier: int
    legacy_rank: int


@dataclass
class PostgameState:
    seed: int
    campaign_length: str
    completed_world_tier: int
    player_ids: list[str]
    legacy_options: dict[str, list[str]]
    character_levels: dict[str, int]
    phase: str = PHASE_ENDING_VOTE
    vote_round: int = 1
    ending_votes: dict[str, str] = field(default_factory=dict)
    ending_result: str | None = None
    legacy_selections: dict[str, LegacyTransfer] = field(default_factory=dict)
    new_game_confirmations: list[str] = field(default_factory=list)
    next_world_tier: int | None = None
    next_seed: int | None = None
    completed: bool = False


def eligible_legacy_items(
    inventories: Mapping[str, Iterable[str]],
    item_definitions: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[str]]:
    """Build stable per-player choices from owned high-rarity items.

    Items may explicitly opt out through ``legacy_eligible: false``.  Duplicates are
    removed while inventory order is retained so the UI remains deterministic.
    """

    result: dict[str, list[str]] = {}
    for profile_id, inventory in inventories.items():
        choices: list[str] = []
        for item_id in inventory:
            if item_id in choices:
                continue
            definition = item_definitions.get(item_id)
            if not definition:
                continue
            if definition.get("rarity") not in LEGACY_RARITIES:
                continue
            if definition.get("legacy_eligible", True) is False:
                continue
            choices.append(item_id)
        result[profile_id] = choices
    return result


def character_levels_after_campaign(
    current_levels: Mapping[str, int], campaign_length: str, world_tier: int
) -> dict[str, int]:
    """Award bounded character progression even after the card pool is exhausted."""

    length_bonus = {"expedition": 1, "fieldzug": 2, "saga": 3}.get(campaign_length)
    if length_bonus is None:
        raise RuleViolation(f"Unknown campaign length: {campaign_length}")
    tier_bonus = max(0, int(world_tier)) // 3
    return {
        profile_id: min(MAX_CHARACTER_LEVEL, max(1, int(level)) + length_bonus + tier_bonus)
        for profile_id, level in current_levels.items()
    }


class Postgame:
    """Reconnect-safe two-player postgame state machine."""

    def __init__(self, state: PostgameState) -> None:
        if len(set(state.player_ids)) not in {1, 2}:
            raise RuleViolation("Postgame requires one or two different players")
        if state.phase not in POSTGAME_PHASES:
            raise RuleViolation(f"Unknown postgame phase: {state.phase}")
        if set(state.legacy_options) != set(state.player_ids):
            raise RuleViolation("Legacy choices must be supplied for both players")
        if set(state.character_levels) != set(state.player_ids):
            raise RuleViolation("Character levels must be supplied for both players")
        self.state = state

    @classmethod
    def new(
        cls,
        *,
        seed: int,
        campaign_length: str,
        completed_world_tier: int,
        player_ids: Iterable[str],
        legacy_options: Mapping[str, Iterable[str]],
        character_levels: Mapping[str, int],
    ) -> "Postgame":
        players = list(player_ids)
        options = {
            player_id: list(dict.fromkeys(legacy_options.get(player_id, ())))
            for player_id in players
        }
        if any(not choices for choices in options.values()):
            raise RuleViolation("Each player needs at least one eligible legacy item")
        levels = {player_id: max(1, int(character_levels.get(player_id, 1))) for player_id in players}
        return cls(PostgameState(
            seed=int(seed),
            campaign_length=campaign_length,
            completed_world_tier=max(1, int(completed_world_tier)),
            player_ids=players,
            legacy_options=options,
            character_levels=levels,
        ))

    @classmethod
    def restore(cls, value: dict[str, Any]) -> "Postgame":
        payload = copy.deepcopy(value)
        payload["legacy_selections"] = {
            profile_id: LegacyTransfer(**transfer)
            for profile_id, transfer in payload.get("legacy_selections", {}).items()
        }
        return cls(PostgameState(**payload))

    def export(self) -> dict[str, Any]:
        return asdict(self.state)

    def public_view(self, viewer_id: str) -> dict[str, Any]:
        self._require_player(viewer_id)
        # Votes remain hidden until both are locked.  A reconnecting client only needs
        # to know who has locked a choice, never what the other player selected.
        return {
            "phase": self.state.phase,
            "vote_round": self.state.vote_round,
            "ending_choices": list(ENDING_CHOICES),
            "ending_vote_locked_players": sorted(self.state.ending_votes),
            "ending_result": self.state.ending_result,
            "legacy_options": list(self.state.legacy_options[viewer_id]),
            "legacy_locked_players": sorted(self.state.legacy_selections),
            "legacy_selection": (
                asdict(self.state.legacy_selections[viewer_id])
                if viewer_id in self.state.legacy_selections else None
            ),
            "new_game_confirmed_players": sorted(self.state.new_game_confirmations),
            "next_world_tier": self.state.next_world_tier,
            "completed": self.state.completed,
        }

    def submit_ending(self, actor_id: str, choice: str) -> list[dict[str, Any]]:
        """Lock a secret ending vote and reveal only after both players submitted.

        A disagreement starts a new simultaneous vote round.  There is no host override
        and no first-click advantage: a shared ending requires actual consensus.
        """

        self._require_phase(PHASE_ENDING_VOTE)
        self._require_player(actor_id)
        if choice not in ENDING_CHOICES:
            raise RuleViolation(f"Unknown ending choice: {choice}")
        if actor_id in self.state.ending_votes:
            raise RuleViolation("This player already locked an ending choice")

        self.state.ending_votes[actor_id] = choice
        events: list[dict[str, Any]] = [{
            "type": "ending_choice_locked",
            "player": actor_id,
            "vote_round": self.state.vote_round,
            # Deliberately no choice here: this event is safe to broadcast.
        }]
        if len(self.state.ending_votes) < len(self.state.player_ids):
            return events

        revealed = dict(self.state.ending_votes)
        choices = set(revealed.values())
        if len(choices) == 1:
            result = choices.pop()
            self.state.ending_result = result
            self.state.phase = PHASE_LEGACY_SELECTION
            events.append({
                "type": "ending_resolved",
                "choice": result,
                "choices": revealed,
                "vote_round": self.state.vote_round,
            })
        else:
            events.append({
                "type": "ending_consensus_required",
                "choices": revealed,
                "vote_round": self.state.vote_round,
            })
            self.state.ending_votes.clear()
            self.state.vote_round += 1
        return events

    def select_legacy(self, actor_id: str, item_id: str) -> list[dict[str, Any]]:
        self._require_phase(PHASE_LEGACY_SELECTION)
        self._require_player(actor_id)
        if actor_id in self.state.legacy_selections:
            raise RuleViolation("This player already selected a legacy item")
        if item_id not in self.state.legacy_options[actor_id]:
            raise RuleViolation("The selected item is not an eligible owned legacy")

        transfer = LegacyTransfer(
            profile_id=actor_id,
            item_id=item_id,
            origin_world_tier=self.state.completed_world_tier,
            legacy_rank=min(5, 1 + self.state.completed_world_tier // 2),
        )
        self.state.legacy_selections[actor_id] = transfer
        events: list[dict[str, Any]] = [{
            "type": "legacy_item_locked",
            "player": actor_id,
            "item_id": item_id,
        }]
        if len(self.state.legacy_selections) == len(self.state.player_ids):
            self.state.next_world_tier = self.state.completed_world_tier + 1
            self.state.next_seed = self._derive_next_seed()
            self.state.phase = PHASE_NEW_GAME_PLUS
            events.append({
                "type": "legacy_transfer_ready",
                "transfers": {
                    player_id: asdict(value)
                    for player_id, value in self.state.legacy_selections.items()
                },
                "next_world_tier": self.state.next_world_tier,
            })
        return events

    def confirm_new_game_plus(self, actor_id: str) -> list[dict[str, Any]]:
        self._require_phase(PHASE_NEW_GAME_PLUS)
        self._require_player(actor_id)
        if actor_id in self.state.new_game_confirmations:
            raise RuleViolation("This player already confirmed New Game+")
        self.state.new_game_confirmations.append(actor_id)
        events: list[dict[str, Any]] = [{
            "type": "new_game_plus_confirmed",
            "player": actor_id,
            "confirmed_players": sorted(self.state.new_game_confirmations),
        }]
        if len(self.state.new_game_confirmations) == len(self.state.player_ids):
            self.state.phase = PHASE_COMPLETE
            self.state.completed = True
            events.append({"type": "new_game_plus_ready", **self.next_campaign_payload()})
        return events

    def next_campaign_payload(self) -> dict[str, Any]:
        if self.state.next_world_tier is None or self.state.next_seed is None:
            raise RuleViolation("Legacy selection is not complete")
        next_levels = character_levels_after_campaign(
            self.state.character_levels,
            self.state.campaign_length,
            self.state.completed_world_tier,
        )
        return {
            "seed": self.state.next_seed,
            "campaign_length": self.state.campaign_length,
            "world_tier": self.state.next_world_tier,
            "ending": self.state.ending_result,
            "legacy_items": {
                player_id: asdict(transfer)
                for player_id, transfer in self.state.legacy_selections.items()
            },
            "character_levels": next_levels,
        }

    def meta_progress_for(self, actor_id: str, current: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Return the idempotent profile meta update for one player.

        The caller should write this object to ``Profile.meta_progress`` in the same
        transaction that creates the next campaign.
        """

        self._require_player(actor_id)
        if self.state.phase != PHASE_COMPLETE or not self.state.completed:
            raise RuleViolation("Meta progression is awarded only after both players confirm")
        payload = copy.deepcopy(dict(current or {}))
        completion_key = f"{self.state.seed}:{self.state.completed_world_tier}:{self.state.ending_result}"
        completed_campaigns = list(payload.get("completed_campaigns", []))
        if completion_key in completed_campaigns:
            return payload
        completed_campaigns.append(completion_key)
        endings = list(dict.fromkeys([*payload.get("endings", []), self.state.ending_result]))
        legacy_vault = list(payload.get("legacy_vault", []))
        selected = self.state.legacy_selections[actor_id]
        record = asdict(selected)
        if record not in legacy_vault:
            legacy_vault.append(record)
        payload.update({
            "campaign_wins": int(payload.get("campaign_wins", 0)) + 1,
            "highest_world_tier": max(
                int(payload.get("highest_world_tier", 1)), int(self.state.next_world_tier or 1)
            ),
            "endings": endings,
            "legacy_vault": legacy_vault,
            "character_level": self.next_campaign_payload()["character_levels"][actor_id],
            "completed_campaigns": completed_campaigns,
        })
        return payload

    def _derive_next_seed(self) -> int:
        material = ":".join((
            "eidpfad-new-game-plus",
            str(self.state.seed),
            str(self.state.completed_world_tier + 1),
            str(self.state.ending_result),
            *(self.state.legacy_selections[player].item_id for player in sorted(self.state.player_ids)),
        ))
        # GameEngine accepts signed-database-friendly 31-bit seeds.
        return int.from_bytes(hashlib.sha256(material.encode()).digest()[:4], "big") & 0x7FFFFFFF

    def _require_player(self, actor_id: str) -> None:
        if actor_id not in self.state.player_ids:
            raise RuleViolation("Unknown postgame player")

    def _require_phase(self, phase: str) -> None:
        if self.state.phase != phase or self.state.completed:
            raise RuleViolation(f"Postgame action requires phase {phase}")
