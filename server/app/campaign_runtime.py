"""Authoritative, serialisable orchestration for one cooperative campaign.

GameEngine owns ordinary scenarios, BossContract owns the non-skippable final fight,
Postgame owns shared ending/legacy/NG+, and CinematicProgress owns reconnect-safe media
gates.  Keeping their public transitions here prevents the websocket layer from
mutating four partially overlapping state machines.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from .boss_contract import BossContract, FINAL_OATH_AP_COST, FINAL_OATH_CARD_ID
from .cinematic_progress import CinematicProgress
from .content import CardCatalog, EnemyCatalog, ItemCatalog
from .errors import RuleViolation
from .game_engine import GameEngine
from .game_state import MAX_ACTION_POINTS
from .postgame import Postgame, eligible_legacy_items


RUNTIME_VERSION = 1


@dataclass
class RuntimeContent:
    cards: CardCatalog
    items: ItemCatalog
    enemies: EnemyCatalog


class CampaignRuntime:
    """Single persistence and dispatch boundary for a two-player campaign."""

    def __init__(
        self,
        *,
        campaign_id: str,
        game: GameEngine,
        content: RuntimeContent,
        loadouts: Mapping[str, Mapping[str, str]],
        boss_contract: BossContract | None = None,
        postgame: Postgame | None = None,
        cinematics: CinematicProgress | None = None,
        cinematic_queue: list[dict[str, Any]] | None = None,
        pending_new_game_plus: dict[str, Any] | None = None,
    ) -> None:
        self.campaign_id = campaign_id
        self.game = game
        self.content = content
        self.loadouts = {key: dict(value) for key, value in loadouts.items()}
        self.boss_contract = boss_contract
        self.postgame = postgame
        self.cinematics = cinematics or CinematicProgress.new(campaign_id, game.state.turn_order)
        self.cinematic_queue = list(cinematic_queue or [])
        self.pending_new_game_plus = copy.deepcopy(pending_new_game_plus)
        if self.boss_contract is not None:
            self.game.attach_boss_contract(self.boss_contract)
        self._ensure_final_contract()

    @classmethod
    def new(
        cls,
        *,
        campaign_id: str,
        seed: int,
        loadouts: Mapping[str, Mapping[str, str]],
        cards: CardCatalog,
        items: ItemCatalog,
        enemies: EnemyCatalog,
        campaign_length: str,
        world_tier: int,
    ) -> "CampaignRuntime":
        content = RuntimeContent(cards, items, enemies)
        game = GameEngine.new(
            seed,
            {key: dict(value) for key, value in loadouts.items()},
            catalog=cards,
            items=items,
            enemies=enemies,
            campaign_length=campaign_length,
            world_tier=world_tier,
        )
        runtime = cls(
            campaign_id=campaign_id,
            game=game,
            content=content,
            loadouts=loadouts,
        )
        runtime.cinematics.request("prologue", "campaign_started", blocking=True)
        runtime._enqueue_cinematic("departure", "campaign_departure", blocking=True)
        return runtime

    @classmethod
    def restore(
        cls,
        campaign_id: str,
        value: dict[str, Any],
        *,
        cards: CardCatalog,
        items: ItemCatalog,
        enemies: EnemyCatalog,
        fallback_loadouts: Mapping[str, Mapping[str, str]],
    ) -> "CampaignRuntime":
        content = RuntimeContent(cards, items, enemies)
        if int(value.get("runtime_version", 0)) != RUNTIME_VERSION:
            # Backward-compatible import of the pre-orchestrator save format.
            game = GameEngine.restore(value, cards, items, enemies)
            cinematics = CinematicProgress.new(campaign_id, game.state.turn_order)
            cinematics.state.completed_cinematics.extend(["prologue", "departure"])
            return cls(
                campaign_id=campaign_id,
                game=game,
                content=content,
                loadouts=fallback_loadouts,
                cinematics=cinematics,
            )
        game = GameEngine.restore(value["game"], cards, items, enemies)
        boss = BossContract.restore(value["boss_contract"]) if value.get("boss_contract") else None
        postgame = Postgame.restore(value["postgame"]) if value.get("postgame") else None
        cinematics = CinematicProgress.restore(value["cinematics"])
        return cls(
            campaign_id=campaign_id,
            game=game,
            content=content,
            loadouts=value.get("loadouts", fallback_loadouts),
            boss_contract=boss,
            postgame=postgame,
            cinematics=cinematics,
            cinematic_queue=value.get("cinematic_queue", []),
            pending_new_game_plus=value.get("pending_new_game_plus"),
        )

    def export(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_VERSION,
            "campaign_id": self.campaign_id,
            "loadouts": copy.deepcopy(self.loadouts),
            "game": self.game.export(),
            "boss_contract": self.boss_contract.export() if self.boss_contract else None,
            "postgame": self.postgame.export() if self.postgame else None,
            "cinematics": self.cinematics.export(),
            "cinematic_queue": copy.deepcopy(self.cinematic_queue),
            "pending_new_game_plus": copy.deepcopy(self.pending_new_game_plus),
        }

    def client_view(self, viewer_id: str) -> dict[str, Any]:
        if viewer_id not in self.game.state.players:
            raise RuleViolation("Unknown campaign member")
        view = self.game.client_view()
        view["boss_contract"] = self.boss_contract.public_view() if self.boss_contract else None
        view["postgame"] = self.postgame.public_view(viewer_id) if self.postgame else None
        view["cinematics"] = self.cinematics.public_view()
        view["runtime_phase"] = (
            "postgame" if self.postgame else "final_boss" if self.boss_contract else "campaign"
        )
        view["final_oath_available"] = bool(
            self.boss_contract
            and self.boss_contract.state.stage == "final_oath"
            and not self.boss_contract.state.completed
        )
        return view

    def play_card(
        self,
        actor_id: str,
        card_id: str,
        *,
        target_id: str | None = None,
        target_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._require_gameplay()
        if card_id == FINAL_OATH_CARD_ID:
            return self.commit_final_oath(actor_id)
        events = self.game.play_card(actor_id, card_id, target_id, target_ids)
        return self._after_game_events(events)

    def pass_phase(self, actor_id: str) -> list[dict[str, Any]]:
        self._require_gameplay()
        return self._after_game_events(self.game.pass_phase(actor_id))

    def react(self, actor_id: str, card_id: str | None, target_ids: list[str] | None) -> list[dict[str, Any]]:
        self._require_gameplay()
        return self._after_game_events(self.game.react(actor_id, card_id, target_ids))

    def confirm_cooperation(self, actor_id: str, accepted: bool) -> list[dict[str, Any]]:
        self._require_gameplay()
        return self._after_game_events(self.game.confirm_cooperation(actor_id, accepted))

    def claim_loot(self, actor_id: str, item_id: str) -> list[dict[str, Any]]:
        self._require_gameplay()
        return self._after_game_events(self.game.claim_loot(actor_id, item_id))

    def choose_scenario(self, actor_id: str, scenario_id: str) -> list[dict[str, Any]]:
        self._require_gameplay()
        return self._after_game_events(self.game.choose_scenario(actor_id, scenario_id))

    def equip_item(self, actor_id: str, item_id: str) -> list[dict[str, Any]]:
        self._require_gameplay()
        return self.game.equip_item(actor_id, item_id)

    def perform_scenario_action(self, actor_id: str, action: str) -> list[dict[str, Any]]:
        self._require_gameplay()
        return self._after_game_events(self.game.perform_scenario_action(actor_id, action))

    def commit_final_oath(self, actor_id: str) -> list[dict[str, Any]]:
        self._require_gameplay()
        if self.boss_contract is None:
            raise RuleViolation("The final oath is not available")
        player = self.game.state.players.get(actor_id)
        if player is None:
            raise RuleViolation("Unknown player")
        events = self.boss_contract.commit_final_oath(
            actor_id, available_action_points=player.action_points
        )
        if any(event.get("type") == "final_oath_contribution_locked" for event in events):
            player.action_points -= FINAL_OATH_AP_COST
        resolved = next((event for event in events if event.get("type") == "final_oath_resolved"), None)
        if resolved and resolved.get("success"):
            self._begin_postgame()
            events.extend(self._start_cinematic_sequence([
                ("final_death", "final_boss_defeated"),
            ]))
        elif resolved:
            # A failed joint roll is a costly boss beat, not a campaign deadlock.
            # Both players receive a fresh five-AP attempt after threat has risen.
            for member in self.game.state.players.values():
                member.action_points = MAX_ACTION_POINTS
            events.append({
                "type": "final_oath_retry_ready",
                "attempt": self.boss_contract.state.final_oath_attempt,
                "action_points": MAX_ACTION_POINTS,
                "threat": self.boss_contract.state.threat,
            })
        self.game._record(events)
        return events

    def submit_ending(self, actor_id: str, choice: str) -> list[dict[str, Any]]:
        self._require_postgame()
        self._require_media_clear()
        events = self.postgame.submit_ending(actor_id, choice)  # type: ignore[union-attr]
        resolved = next((event for event in events if event.get("type") == "ending_resolved"), None)
        if resolved:
            events.extend(self._start_cinematic_sequence([
                (f"ending_{resolved['choice']}", "ending_resolved"),
            ]))
        return events

    def select_legacy(self, actor_id: str, item_id: str) -> list[dict[str, Any]]:
        self._require_postgame()
        self._require_media_clear()
        events = self.postgame.select_legacy(actor_id, item_id)  # type: ignore[union-attr]
        if any(event.get("type") == "legacy_transfer_ready" for event in events):
            events.extend(self._start_cinematic_sequence([
                ("legacy_transfer", "legacy_transfer_ready"),
            ]))
        return events

    def confirm_new_game_plus(self, actor_id: str) -> list[dict[str, Any]]:
        self._require_postgame()
        self._require_media_clear()
        events = self.postgame.confirm_new_game_plus(actor_id)  # type: ignore[union-attr]
        ready = next((event for event in events if event.get("type") == "new_game_plus_ready"), None)
        if ready:
            self.pending_new_game_plus = copy.deepcopy(ready)
        return events

    def cinematic_ack(self, actor_id: str, cinematic_id: str, skipped: bool = False) -> list[dict[str, Any]]:
        events = self.cinematics.acknowledge(actor_id, cinematic_id, skipped=skipped)
        if any(event.get("type") == "cinematic_completed" for event in events):
            events.extend(self._start_next_cinematic())
        return events

    def start_new_game_plus(self) -> list[dict[str, Any]]:
        """Apply the already-confirmed NG+ payload after the database transaction succeeds."""

        if not self.pending_new_game_plus or self.postgame is None:
            raise RuleViolation("New Game+ is not ready")
        payload = copy.deepcopy(self.pending_new_game_plus)
        self.game = GameEngine.new(
            int(payload["seed"]),
            self.loadouts,
            catalog=self.content.cards,
            items=self.content.items,
            enemies=self.content.enemies,
            campaign_length=str(payload["campaign_length"]),
            world_tier=int(payload["world_tier"]),
        )
        for profile_id, player in self.game.state.players.items():
            player.character_level = int(payload["character_levels"][profile_id])
            transfer = payload["legacy_items"][profile_id]
            item_id = str(transfer["item_id"])
            if item_id not in player.inventory:
                player.inventory.append(item_id)
        self.boss_contract = None
        self.postgame = None
        self.pending_new_game_plus = None
        self.cinematics = CinematicProgress.new(self.campaign_id, self.game.state.turn_order)
        self.cinematic_queue.clear()
        events = self.cinematics.request("departure", "new_game_plus_started", blocking=True)
        events.append({**payload, "type": "new_game_plus_started"})
        return events

    def _after_game_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._ensure_final_contract()
        if any(
            event.get("type") == "boss_stage_changed" and event.get("stage") == "final_oath"
            for event in events
        ):
            for player in self.game.state.players.values():
                player.action_points = MAX_ACTION_POINTS
            events.append({
                "type": "final_oath_ready",
                "action_points": MAX_ACTION_POINTS,
                "required_players": len(self.game.state.players),
            })
        if self.boss_contract is not None and any(
            event.get("type") in {"round_started", "boss_round_started"} for event in events
        ):
            events.extend(self.boss_contract.end_round())
            self.game._sync_boss_targets()
        sequence: list[tuple[str, str]] = []
        for event in events:
            if event.get("type") == "scenario_started":
                scenario = event.get("scenario", {})
                country_id = str(scenario.get("country_id", ""))
                if country_id:
                    sequence.append((f"country_{country_id}", "country_entered"))
                if scenario.get("is_boss"):
                    sequence.append((f"boss_{country_id}", "boss_started"))
                else:
                    sequence.append((f"briefing_{scenario.get('kind', '')}", "scenario_started"))
            elif event.get("type") == "boss_arena_changed":
                sequence.append((f"final_phase_{int(event.get('arena_index', 0)) + 1}", "boss_arena_changed"))
        if sequence:
            events.extend(self._start_cinematic_sequence(sequence))
        return events

    def _ensure_final_contract(self) -> None:
        if self.postgame is not None or self.boss_contract is not None:
            return
        scenario = self.game.state.scenario
        if not scenario.get("is_final"):
            return
        consequences = self.game.state.world.get("campaign_consequences", [])
        if isinstance(consequences, list):
            unresolved = [
                ":".join((
                    str(entry.get("country_id", "unknown")),
                    str(entry.get("kind", "scenario")),
                    str(entry.get("scenario_id", "unknown")),
                ))
                for entry in consequences
                if isinstance(entry, dict) and bool(entry.get("unresolved_problem"))
            ]
        elif isinstance(consequences, dict):
            # Pre-objective save games used a sparse key/value consequence map.
            unresolved = [str(key) for key, value in consequences.items() if value]
        else:
            unresolved = []
        self.boss_contract = BossContract.new(
            self.game.state.seed,
            self.game.state.turn_order,
            world_tier=self.game.state.world_tier,
            unresolved_problems=unresolved,
        )
        self.game.attach_boss_contract(self.boss_contract)

    def _begin_postgame(self) -> None:
        inventories = {
            profile_id: list(player.inventory)
            for profile_id, player in self.game.state.players.items()
        }
        options = eligible_legacy_items(inventories, self.content.items.items)
        # A completed campaign must never deadlock because a player declined earlier
        # loot. Add a deterministic high-rarity relic as a final fallback.
        fallback = next(
            item["id"] for item in sorted(self.content.items.items.values(), key=lambda item: item["id"])
            if item["rarity"] in {"exceptional", "legendary", "unique"}
        )
        for profile_id in self.game.state.turn_order:
            if not options[profile_id]:
                if fallback not in self.game.state.players[profile_id].inventory:
                    self.game.state.players[profile_id].inventory.append(fallback)
                options[profile_id] = [fallback]
        levels = {
            profile_id: player.character_level
            for profile_id, player in self.game.state.players.items()
        }
        self.postgame = Postgame.new(
            seed=self.game.state.seed,
            campaign_length=self.game.state.campaign_length,
            completed_world_tier=self.game.state.world_tier,
            player_ids=self.game.state.turn_order,
            legacy_options=options,
            character_levels=levels,
        )

    def _start_cinematic_sequence(self, sequence: list[tuple[str, str]]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for cinematic_id, trigger in sequence:
            if cinematic_id in self.cinematics.state.completed_cinematics:
                continue
            if self.cinematics.state.active is None and not self.cinematic_queue:
                events.extend(self.cinematics.request(cinematic_id, trigger, blocking=True))
            else:
                self._enqueue_cinematic(cinematic_id, trigger, blocking=True)
        return events

    def _enqueue_cinematic(self, cinematic_id: str, trigger: str, *, blocking: bool) -> None:
        if cinematic_id in self.cinematics.state.completed_cinematics:
            return
        if self.cinematics.state.active and self.cinematics.state.active.cinematic_id == cinematic_id:
            return
        if any(value["cinematic_id"] == cinematic_id for value in self.cinematic_queue):
            return
        self.cinematic_queue.append({
            "cinematic_id": cinematic_id,
            "trigger": trigger,
            "blocking": bool(blocking),
        })

    def _start_next_cinematic(self) -> list[dict[str, Any]]:
        while self.cinematic_queue and self.cinematics.state.active is None:
            value = self.cinematic_queue.pop(0)
            events = self.cinematics.request(
                str(value["cinematic_id"]),
                str(value["trigger"]),
                blocking=bool(value.get("blocking", True)),
            )
            if events:
                return events
        return []

    def _require_media_clear(self) -> None:
        if self.cinematics.public_view()["gameplay_blocked"]:
            raise RuleViolation("Both players must finish or skip the active cinematic")

    def _require_gameplay(self) -> None:
        self._require_media_clear()
        if self.postgame is not None:
            raise RuleViolation("The campaign is in postgame")

    def _require_postgame(self) -> None:
        if self.postgame is None:
            raise RuleViolation("Postgame has not started")
