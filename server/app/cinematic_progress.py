"""Campaign-scoped cinematic acknowledgements.

Client-local ``seen`` flags cannot distinguish campaigns and disappear on reconnect.
This ledger is part of the authoritative campaign state.  Blocking cinematics finish
only after both clients acknowledged playback or an explicit skip.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .errors import RuleViolation


@dataclass
class ActiveCinematic:
    cinematic_id: str
    trigger: str
    blocking: bool = True
    acknowledged_players: list[str] = field(default_factory=list)
    skipped_players: list[str] = field(default_factory=list)


@dataclass
class CinematicProgressState:
    campaign_id: str
    player_ids: list[str]
    completed_cinematics: list[str] = field(default_factory=list)
    active: ActiveCinematic | None = None


class CinematicProgress:
    def __init__(self, state: CinematicProgressState) -> None:
        if len(set(state.player_ids)) not in {1, 2}:
            raise RuleViolation("Cinematic progress requires one or two players")
        self.state = state

    @classmethod
    def new(cls, campaign_id: str, player_ids: Iterable[str]) -> "CinematicProgress":
        return cls(CinematicProgressState(campaign_id=campaign_id, player_ids=list(player_ids)))

    @classmethod
    def restore(cls, value: dict[str, Any]) -> "CinematicProgress":
        payload = copy.deepcopy(value)
        if payload.get("active") is not None:
            payload["active"] = ActiveCinematic(**payload["active"])
        return cls(CinematicProgressState(**payload))

    def export(self) -> dict[str, Any]:
        return asdict(self.state)

    def request(self, cinematic_id: str, trigger: str, *, blocking: bool = True) -> list[dict[str, Any]]:
        if not cinematic_id:
            raise RuleViolation("A cinematic id is required")
        if cinematic_id in self.state.completed_cinematics:
            return []
        if self.state.active:
            if self.state.active.cinematic_id == cinematic_id:
                return []
            raise RuleViolation("Another cinematic is still awaiting acknowledgements")
        self.state.active = ActiveCinematic(
            cinematic_id=cinematic_id,
            trigger=trigger,
            blocking=bool(blocking),
        )
        return [{
            "type": "cinematic_started",
            "campaign_id": self.state.campaign_id,
            "cinematic_id": cinematic_id,
            "trigger": trigger,
            "blocking": bool(blocking),
        }]

    def acknowledge(self, actor_id: str, cinematic_id: str, *, skipped: bool = False) -> list[dict[str, Any]]:
        if actor_id not in self.state.player_ids:
            raise RuleViolation("Unknown cinematic participant")
        active = self.state.active
        if active is None or active.cinematic_id != cinematic_id:
            if cinematic_id in self.state.completed_cinematics:
                # Network retries are idempotent after completion.
                return []
            raise RuleViolation("This cinematic is not active")
        if actor_id in active.acknowledged_players:
            return []

        active.acknowledged_players.append(actor_id)
        if skipped:
            active.skipped_players.append(actor_id)
        events: list[dict[str, Any]] = [{
            "type": "cinematic_acknowledged",
            "cinematic_id": cinematic_id,
            "player": actor_id,
            "skipped": bool(skipped),
        }]
        if len(active.acknowledged_players) == len(self.state.player_ids):
            self.state.completed_cinematics.append(cinematic_id)
            events.append({
                "type": "cinematic_completed",
                "cinematic_id": cinematic_id,
                "skipped_players": sorted(active.skipped_players),
            })
            self.state.active = None
        return events

    def public_view(self) -> dict[str, Any]:
        return {
            "campaign_id": self.state.campaign_id,
            "completed_cinematics": list(self.state.completed_cinematics),
            "active": asdict(self.state.active) if self.state.active else None,
            "gameplay_blocked": bool(self.state.active and self.state.active.blocking),
        }
