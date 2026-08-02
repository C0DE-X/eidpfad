import unittest

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import get_current_profile, hash_token
from app.database import Base
from app.game_engine import RuleViolation
from app.lobby import lobbies
from app.main import (
    _finalize_disconnect,
    _handle_message,
    _initialize_connection,
    _is_loopback_host,
    create_campaign,
    join_campaign,
    create_profile,
    recover_profile,
    rotate_profile_recovery_code,
    rotate_profile_token,
    runtime_games,
)
from app.models import Campaign, CampaignMember, Profile, ProfileRecovery
from app.schemas import CampaignCreate, CampaignJoin, ProfileCreate, ProfileRecover, client_message_adapter


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self, **_kwargs) -> None:
        self.closed = True


class DatabaseMixin:
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()


class ProfileRecoveryTests(DatabaseMixin, unittest.TestCase):
    def test_recovery_rotates_both_secrets_and_invalidates_replay(self) -> None:
        created = create_profile(ProfileCreate(display_name="Recovery Hero"), self.db)
        original_token = created.device_token
        original_recovery = created.recovery_code

        recovered = recover_profile(
            ProfileRecover(display_name="Recovery Hero", recovery_code=original_recovery),
            self.db,
        )

        self.assertEqual(recovered.profile_id, created.profile_id)
        self.assertNotEqual(recovered.device_token, original_token)
        self.assertNotEqual(recovered.recovery_code, original_recovery)
        profile = self.db.get(Profile, created.profile_id)
        self.assertEqual(profile.token_hash, hash_token(recovered.device_token))
        credential = self.db.get(ProfileRecovery, created.profile_id)
        self.assertEqual(credential.recovery_hash, hash_token(recovered.recovery_code))

        with self.assertRaises(HTTPException) as replay:
            recover_profile(
                ProfileRecover(display_name="Recovery Hero", recovery_code=original_recovery),
                self.db,
            )
        self.assertEqual(replay.exception.status_code, 401)

    def test_authenticated_token_and_recovery_rotation(self) -> None:
        created = create_profile(ProfileCreate(display_name="Rotate Hero"), self.db)
        profile = self.db.get(Profile, created.profile_id)

        token_response = rotate_profile_token(profile, self.db)
        self.assertNotEqual(token_response.device_token, created.device_token)
        with self.assertRaises(HTTPException):
            get_current_profile(
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=created.device_token),
                self.db,
            )
        authenticated = get_current_profile(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_response.device_token),
            self.db,
        )
        self.assertEqual(authenticated.id, created.profile_id)

        recovery_response = rotate_profile_recovery_code(profile, self.db)
        self.assertNotEqual(recovery_response.recovery_code, created.recovery_code)

    def test_recovery_failure_does_not_reveal_profile_existence(self) -> None:
        create_profile(ProfileCreate(display_name="Known Hero"), self.db)
        details = []
        for display_name in ("Known Hero", "Unknown Hero"):
            with self.assertRaises(HTTPException) as failure:
                recover_profile(
                    ProfileRecover(display_name=display_name, recovery_code="x" * 43),
                    self.db,
                )
            details.append((failure.exception.status_code, failure.exception.detail))
        self.assertEqual(details[0], details[1])


class MatchLifecycleTests(DatabaseMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        lobbies.connections.clear()
        lobbies.ready.clear()
        lobbies.locks.clear()
        runtime_games.clear()

        self.player_ids = ["player-one", "player-two"]
        for number, player_id in enumerate(self.player_ids):
            self.db.add(
                Profile(
                    id=player_id,
                    display_name=f"Player {number + 1}",
                    token_hash=hash_token(f"token-{number}"),
                )
            )
        self.campaign = Campaign(
            id="campaign-one",
            invite_code="ABC123",
            owner_profile_id=self.player_ids[0],
            seed=42,
            campaign_length="expedition",
        )
        self.db.add(self.campaign)
        self.db.add_all(
            [
                CampaignMember(
                    campaign_id=self.campaign.id,
                    profile_id=self.player_ids[0],
                    weapon="dual_blades",
                    magic="ember",
                ),
                CampaignMember(
                    campaign_id=self.campaign.id,
                    profile_id=self.player_ids[1],
                    weapon="axe",
                    magic="rune",
                ),
            ]
        )
        self.db.commit()
        self.sockets = {player_id: FakeWebSocket() for player_id in self.player_ids}
        lobbies.connections[self.campaign.id].update(self.sockets)

    def tearDown(self) -> None:
        lobbies.connections.clear()
        lobbies.ready.clear()
        lobbies.locks.clear()
        runtime_games.clear()
        super().tearDown()

    async def _ready(self, player_id: str, value: bool = True) -> None:
        message = client_message_adapter.validate_python(
            {"type": "ready", "protocol_version": 2, "ready": value}
        )
        await _handle_message(self.db, self.campaign.id, player_id, message)

    async def _start(self) -> None:
        await self._ready(self.player_ids[0])
        await self._ready(self.player_ids[1])
        self.db.refresh(self.campaign)
        self.assertEqual(self.campaign.status, "playing")

    async def test_ready_is_idempotent_and_starts_once(self) -> None:
        await self._start()
        first_socket = self.sockets[self.player_ids[0]]
        starts_before = sum(packet.get("type") == "game_started" for packet in first_socket.sent)
        self.assertEqual(starts_before, 1)

        await self._ready(self.player_ids[1])

        starts_after = sum(packet.get("type") == "game_started" for packet in first_socket.sent)
        self.assertEqual(starts_after, starts_before)
        self.assertEqual(self.campaign.status, "playing")

    async def test_multiplayer_ready_requires_both_connected_members(self) -> None:
        lobbies.connections[self.campaign.id].pop(self.player_ids[1])

        with self.assertRaisesRegex(RuleViolation, "both players"):
            await self._ready(self.player_ids[0])

        self.assertFalse(lobbies.ready.get(self.campaign.id, set()))
        self.assertEqual(self.campaign.status, "waiting")

    async def test_singleplayer_starts_with_one_connected_ready_profile(self) -> None:
        solo = Campaign(
            id="campaign-solo", invite_code="SOLO12", owner_profile_id=self.player_ids[0],
            seed=7, campaign_length="expedition", game_mode="singleplayer",
        )
        self.db.add(solo)
        self.db.add(CampaignMember(
            campaign_id=solo.id, profile_id=self.player_ids[0], weapon="longsword", magic="rune",
        ))
        self.db.commit()
        socket = FakeWebSocket()
        lobbies.connections[solo.id][self.player_ids[0]] = socket
        message = client_message_adapter.validate_python(
            {"type": "ready", "protocol_version": 2, "ready": True}
        )
        await _handle_message(self.db, solo.id, self.player_ids[0], message)
        self.db.refresh(solo)
        self.assertEqual(solo.status, "playing")
        self.assertEqual(len(runtime_games[solo.id].game.state.players), 1)

    def test_singleplayer_campaign_rejects_join(self) -> None:
        owner = self.db.get(Profile, self.player_ids[0])
        created = create_campaign(
            CampaignCreate(weapon="longsword", magic="rune", campaign_length="expedition", game_mode="singleplayer"),
            owner,
            self.db,
        )
        joining = self.db.get(Profile, self.player_ids[1])
        with self.assertRaises(HTTPException) as failure:
            join_campaign(
                CampaignJoin(invite_code=created.invite_code, weapon="axe", magic="ember"),
                joining,
                self.db,
            )
        self.assertEqual(failure.exception.status_code, 409)

    async def test_disconnect_pauses_and_reconnect_gets_immediate_snapshot(self) -> None:
        await self._start()
        removed = lobbies.disconnect(
            self.campaign.id,
            self.player_ids[0],
            self.sockets[self.player_ids[0]],
        )
        self.assertTrue(removed)
        await _finalize_disconnect(self.db, self.campaign.id)
        self.db.refresh(self.campaign)
        self.assertEqual(self.campaign.status, "paused")
        self.assertFalse(lobbies.ready.get(self.campaign.id, set()))

        reconnect_socket = FakeWebSocket()
        lobbies.connections[self.campaign.id][self.player_ids[0]] = reconnect_socket
        await _initialize_connection(self.db, self.campaign.id, reconnect_socket)

        snapshot = reconnect_socket.sent[0]
        self.assertEqual(snapshot["type"], "state")
        self.assertTrue(snapshot["snapshot"])
        self.assertEqual(snapshot["campaign_status"], "paused")
        self.assertIn("players", snapshot["state"])

    async def test_paused_match_requires_two_fresh_ready_confirmations(self) -> None:
        await self._start()
        await self._ready(self.player_ids[0], False)
        self.assertEqual(self.campaign.status, "paused")
        self.assertFalse(lobbies.ready[self.campaign.id])

        await self._ready(self.player_ids[0])
        self.assertEqual(self.campaign.status, "paused")
        await self._ready(self.player_ids[1])
        self.assertEqual(self.campaign.status, "playing")
        resume_packets = [
            packet
            for packet in self.sockets[self.player_ids[0]].sent
            if any(event.get("type") == "campaign_resumed" for event in packet.get("events", []))
        ]
        self.assertEqual(len(resume_packets), 1)

    async def test_actions_are_rejected_while_paused(self) -> None:
        await self._start()
        await self._ready(self.player_ids[0], False)
        message = client_message_adapter.validate_python({"type": "pass_phase", "protocol_version": 2})
        with self.assertRaises(RuleViolation):
            await _handle_message(self.db, self.campaign.id, self.player_ids[0], message)

    async def test_completed_campaign_is_terminal(self) -> None:
        self.campaign.status = "completed"
        self.db.commit()
        with self.assertRaises(RuleViolation):
            await self._ready(self.player_ids[0])
        self.db.refresh(self.campaign)
        self.assertEqual(self.campaign.status, "completed")
        self.assertNotIn(self.player_ids[0], lobbies.ready.get(self.campaign.id, set()))

    async def test_lobby_snapshot_is_explicit_and_replacement_disconnect_is_safe(self) -> None:
        await _initialize_connection(self.db, self.campaign.id, self.sockets[self.player_ids[0]])
        lobby = self.sockets[self.player_ids[0]].sent[-1]
        self.assertEqual(lobby["campaign_status"], "waiting")
        self.assertEqual(len(lobby["players"]), 2)
        self.assertTrue(all(player["connected"] for player in lobby["players"]))

        replacement = FakeWebSocket()
        lobbies.connections[self.campaign.id][self.player_ids[0]] = replacement
        self.assertFalse(
            lobbies.disconnect(
                self.campaign.id,
                self.player_ids[0],
                self.sockets[self.player_ids[0]],
            )
        )
        self.assertIs(lobbies.connections[self.campaign.id][self.player_ids[0]], replacement)


class ProtocolAndTransportTests(unittest.TestCase):
    def test_ready_field_is_required_by_runtime_schema(self) -> None:
        with self.assertRaises(ValidationError):
            client_message_adapter.validate_python({"type": "ready", "protocol_version": 2})

    def test_only_loopback_hosts_are_allowed_cleartext(self) -> None:
        for host in ("localhost", "game.localhost", "127.0.0.1", "127.2.3.4", "::1"):
            self.assertTrue(_is_loopback_host(host))
        for host in ("game.example.com", "10.0.0.2", "192.168.1.20", "example.localhost.evil"):
            self.assertFalse(_is_loopback_host(host))


if __name__ == "__main__":
    unittest.main()
