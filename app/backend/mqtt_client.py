"""Generic MQTT Client with Home Assistant Auto-Discovery support."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable
import aiomqtt

_LOGGER = logging.getLogger(__name__)


class EMSMQTTClient:
    """Publishes EMS telemetry to a generic broker and exposes HA MQTT Auto-Discovery entities."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str = "",
        password: str = "",
        topic_prefix: str = "ems",
        discovery_prefix: str = "homeassistant",
        on_command_received: Callable[[str, str], None] | None = None,
    ) -> None:
        """Initialize MQTT client."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix.rstrip("/")
        self.discovery_prefix = discovery_prefix.rstrip("/")
        self.on_command_received = on_command_received
        self._client: aiomqtt.Client | None = None
        self._running = False

    async def start(self) -> None:
        """Connect to broker, send HA Discovery, and listen for command topics."""
        if not self.host:
            return

        self._running = True
        while self._running:
            try:
                _LOGGER.info("Connecting to MQTT broker %s:%d...", self.host, self.port)
                async with aiomqtt.Client(
                    hostname=self.host,
                    port=self.port,
                    username=self.username or None,
                    password=self.password or None,
                ) as client:
                    self._client = client
                    _LOGGER.info("Connected to MQTT broker")

                    # Publish Home Assistant Discovery
                    await self._publish_discovery()

                    # Subscribe to control topics
                    await client.subscribe(f"{self.topic_prefix}/set/#")

                    async for message in client.messages:
                        topic = str(message.topic)
                        payload = message.payload.decode("utf-8") if isinstance(message.payload, bytes) else str(message.payload)
                        _LOGGER.debug("MQTT Command received: %s -> %s", topic, payload)
                        if self.on_command_received:
                            sub_cmd = topic.replace(f"{self.topic_prefix}/set/", "")
                            self.on_command_received(sub_cmd, payload)
            except Exception as err:
                _LOGGER.warning("MQTT connection lost: %s. Reconnecting in 10s...", err)
                self._client = None
                await asyncio.sleep(10)

    async def publish_state(self, state: dict[str, Any]) -> None:
        """Publish full telemetry and discrete states to MQTT."""
        if not self._client:
            return

        try:
            # 1. Full JSON state
            await self._client.publish(
                f"{self.topic_prefix}/state",
                payload=json.dumps(state).encode(),
                retain=True,
            )

            # 2. Individual topics
            priority = state.get("active_priority", "idle")
            await self._client.publish(f"{self.topic_prefix}/priority", payload=priority.encode(), retain=True)

            reason = state.get("decision_reason", "")
            await self._client.publish(f"{self.topic_prefix}/decision_reason", payload=reason.encode(), retain=True)

            pv = str(state.get("pv_power_w", 0.0))
            await self._client.publish(f"{self.topic_prefix}/pv_power", payload=pv.encode(), retain=True)

            soc = str(state.get("battery_soc", 0.0))
            await self._client.publish(f"{self.topic_prefix}/battery_soc", payload=soc.encode(), retain=True)

            savings = str(state.get("cumulative_savings_eur", 0.0))
            await self._client.publish(f"{self.topic_prefix}/savings", payload=savings.encode(), retain=True)
        except Exception as err:
            _LOGGER.debug("Failed to publish MQTT state: %s", err)

    async def _publish_discovery(self) -> None:
        """Publish Home Assistant MQTT Auto-Discovery payloads."""
        if not self._client:
            return

        device = {
            "identifiers": ["smart_residential_ems_docker"],
            "name": "Smart Residential EMS (Docker)",
            "model": "Standalone Container & Add-on",
            "manufacturer": "Antigravity & Pierre",
            "sw_version": "2.0.0",
        }

        sensors = [
            {
                "id": "ems_active_priority",
                "name": "EMS Active Priority State",
                "stat_t": f"{self.topic_prefix}/priority",
                "icon": "mdi:state-machine",
            },
            {
                "id": "ems_decision_reason",
                "name": "EMS Decision Explanation",
                "stat_t": f"{self.topic_prefix}/decision_reason",
                "icon": "mdi:comment-quote",
            },
            {
                "id": "ems_pv_power",
                "name": "EMS PV Power",
                "stat_t": f"{self.topic_prefix}/pv_power",
                "unit_of_meas": "W",
                "dev_cla": "power",
                "icon": "mdi:solar-power",
            },
            {
                "id": "ems_battery_soc",
                "name": "EMS Battery SOC",
                "stat_t": f"{self.topic_prefix}/battery_soc",
                "unit_of_meas": "%",
                "dev_cla": "battery",
                "icon": "mdi:battery-high",
            },
            {
                "id": "ems_savings",
                "name": "EMS Cumulative Savings",
                "stat_t": f"{self.topic_prefix}/savings",
                "unit_of_meas": "€",
                "dev_cla": "monetary",
                "icon": "mdi:piggy-bank",
            },
        ]

        for s in sensors:
            topic = f"{self.discovery_prefix}/sensor/ems/{s['id']}/config"
            payload = {
                "name": s["name"],
                "unique_id": f"ems_docker_{s['id']}",
                "state_topic": s["stat_t"],
                "icon": s.get("icon"),
                "device": device,
            }
            if "unit_of_meas" in s:
                payload["unit_of_measurement"] = s["unit_of_meas"]
            if "dev_cla" in s:
                payload["device_class"] = s["dev_cla"]
            await self._client.publish(topic, payload=json.dumps(payload).encode(), retain=True)

        _LOGGER.info("Published %d Home Assistant MQTT Discovery entities", len(sensors))

    def stop(self) -> None:
        """Stop MQTT client."""
        self._running = False
