from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class LobbyManager:
    def __init__(self) -> None:
        self.connections: dict[str, dict[str, WebSocket]] = defaultdict(dict)
        self.ready: dict[str, set[str]] = defaultdict(set)
        self.locks: dict[str, asyncio.Lock] = {}

    def lock(self, campaign_id: str) -> asyncio.Lock:
        return self.locks.setdefault(campaign_id, asyncio.Lock())

    async def connect(self, campaign_id: str, profile_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        old_socket = self.connections[campaign_id].get(profile_id)
        # Install the replacement before awaiting close. If the old handler's
        # ``finally`` runs during that await, it sees itself as stale and must
        # not pause the campaign or remove this new socket.
        self.connections[campaign_id][profile_id] = websocket
        if old_socket is not None:
            await old_socket.close(code=4001, reason="Connected from another client")

    def disconnect(self, campaign_id: str, profile_id: str, websocket: WebSocket | None = None) -> bool:
        """Remove the current socket and report whether it was actually removed.

        A newly connected socket replaces an older socket for the same profile.
        The old handler's eventual ``finally`` must not pause the match or remove
        the replacement connection.
        """
        current = self.connections.get(campaign_id, {}).get(profile_id)
        if websocket is not None and current is not websocket:
            return False
        if current is None:
            return False
        self.connections[campaign_id].pop(profile_id, None)
        self.ready.get(campaign_id, set()).discard(profile_id)
        if not self.connections.get(campaign_id):
            self.connections.pop(campaign_id, None)
            self.ready.pop(campaign_id, None)
            self.locks.pop(campaign_id, None)
        return True

    def set_ready(self, campaign_id: str, profile_id: str, value: bool) -> bool:
        before = profile_id in self.ready[campaign_id]
        if value:
            self.ready[campaign_id].add(profile_id)
        else:
            self.ready[campaign_id].discard(profile_id)
        return before != value

    def clear_ready(self, campaign_id: str) -> None:
        ready = self.ready.get(campaign_id)
        if ready is not None:
            ready.clear()

    def all_connected(self, campaign_id: str, member_ids: list[str]) -> bool:
        return len(member_ids) == 2 and set(member_ids) <= set(self.connections.get(campaign_id, {}))

    def all_ready(self, campaign_id: str, member_ids: list[str]) -> bool:
        return (
            self.all_connected(campaign_id, member_ids)
            and set(member_ids) <= self.ready.get(campaign_id, set())
        )

    async def broadcast(self, campaign_id: str, payload: dict) -> None:
        for websocket in list(self.connections.get(campaign_id, {}).values()):
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                # The owning socket handler performs the authoritative
                # disconnect transition. Removing it here would make that
                # handler look stale and could skip the required pause.
                try:
                    await websocket.close(code=1011, reason="Connection lost")
                except RuntimeError:
                    pass

    async def send_to(self, campaign_id: str, profile_id: str, payload: dict) -> None:
        websocket = self.connections.get(campaign_id, {}).get(profile_id)
        if websocket is None:
            return
        try:
            await websocket.send_json(payload)
        except RuntimeError:
            try:
                await websocket.close(code=1011, reason="Connection lost")
            except RuntimeError:
                pass


lobbies = LobbyManager()
