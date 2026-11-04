"""Asynchronous Home Assistant WebSocket & REST API Client."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine
import aiohttp

_LOGGER = logging.getLogger(__name__)


class HAClient:
    """Maintains a persistent WebSocket connection to Home Assistant with state caching."""

    def __init__(self, base_url: str, token: str, verify_ssl: bool = True) -> None:
        """Initialize client."""
        self.base_url = base_url.rstrip("/")
        # Convert http(s) to ws(s)
        if self.base_url.startswith("https://"):
            self.ws_url = f"wss://{self.base_url[8:]}/api/websocket"
        elif self.base_url.startswith("http://"):
            self.ws_url = f"ws://{self.base_url[7:]}/api/websocket"
        else:
            self.ws_url = f"{self.base_url}/api/websocket"

        self.token = token
        self.verify_ssl = verify_ssl
        self.states: dict[str, dict[str, Any]] = {}
        self._running = False
        self._msg_id = 1
        self._on_state_change_callbacks: list[Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]] = []
        self._session: aiohttp.ClientSession | None = None

    def register_state_callback(
        self, callback: Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]
    ) -> None:
        """Register an async callback triggered when any entity updates."""
        self._on_state_change_callbacks.append(callback)

    async def get_session(self) -> aiohttp.ClientSession:
        """Return or create aiohttp ClientSession."""
        if self._session is None or self._session.closed:
            ssl_ctx = None if self.verify_ssl else False
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def fetch_initial_states(self) -> bool:
        """Fetch all initial states via REST API."""
        session = await self.get_session()
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/api/states"
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data:
                        eid = item.get("entity_id")
                        if eid:
                            self.states[eid] = item
                    _LOGGER.info("Fetched %d initial states from Home Assistant", len(self.states))
                    return True
                _LOGGER.error("Failed to fetch HA states: HTTP %d", resp.status)
        except Exception as err:
            _LOGGER.error("Error connecting to HA REST API: %s", err)
        return False

    async def call_service(self, domain: str, service: str, service_data: dict[str, Any]) -> bool:
        """Call a Home Assistant service via REST API."""
        session = await self.get_session()
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/api/services/{domain}/{service}"
        try:
            async with session.post(
                url, json=service_data, headers=headers, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status in (200, 201):
                    return True
                _LOGGER.warning("Service call %s.%s failed: HTTP %d", domain, service, resp.status)
        except Exception as err:
            _LOGGER.error("Error executing service call %s.%s: %s", domain, service, err)
        return False

    async def start_websocket_listener(self) -> None:
        """Maintain an auto-reconnecting WebSocket connection to HA for instant state updates."""
        self._running = True
        while self._running:
            try:
                session = await self.get_session()
                _LOGGER.info("Connecting to HA WebSocket: %s", self.ws_url)
                async with session.ws_connect(self.ws_url, heartbeat=30.0) as ws:
                    # 1. Handle Auth
                    auth_req = await ws.receive_json()
                    if auth_req.get("type") == "auth_required":
                        await ws.send_json({"type": "auth", "access_token": self.token})
                        auth_resp = await ws.receive_json()
                        if auth_resp.get("type") != "auth_ok":
                            _LOGGER.error("HA WebSocket Authentication failed: %s", auth_resp)
                            await asyncio.sleep(10)
                            continue

                    _LOGGER.info("Connected and authenticated to HA WebSocket")

                    # 2. Subscribe to state_changed events
                    sub_id = self._msg_id
                    self._msg_id += 1
                    await ws.send_json({
                        "id": sub_id,
                        "type": "subscribe_events",
                        "event_type": "state_changed",
                    })

                    # 3. Message loop
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            payload = json.loads(msg.data)
                            event = payload.get("event")
                            if event and event.get("event_type") == "state_changed":
                                data = event.get("data", {})
                                eid = data.get("entity_id")
                                new_state = data.get("new_state")
                                if eid and new_state:
                                    self.states[eid] = new_state
                                    for cb in self._on_state_change_callbacks:
                                        asyncio.create_task(cb(eid, new_state))
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            _LOGGER.warning("HA WebSocket closed: %s", msg)
                            break
            except Exception as err:
                _LOGGER.warning("HA WebSocket connection lost: %s. Reconnecting in 5s...", err)
                await asyncio.sleep(5)

    def stop(self) -> None:
        """Stop client."""
        self._running = False
