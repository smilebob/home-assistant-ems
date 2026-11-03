"""Controller for Tesla Fleet current modulation & Local Tuya EVSE."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from ...const import (
    CONF_TESLA_CHARGE_SWITCH,
    CONF_TESLA_CURRENT_NUMBER,
    CONF_EVSE_POWER_SWITCH,
    CONF_EVSE_CURRENT_NUMBER,
    CONF_EV_MIN_CURRENT,
    CONF_EV_MAX_CURRENT,
    CONF_EV_VOLTAGE,
    CONF_EV_RAMP_SECONDS,
    DEFAULT_EV_MIN_CURRENT,
    DEFAULT_EV_MAX_CURRENT,
    DEFAULT_EV_VOLTAGE,
    DEFAULT_EV_RAMP_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class TeslaController:
    """Modulates Tesla charging current smoothly (1A steps) via Tesla Fleet."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Tesla controller."""
        self.config = config
        self.current_amps: int = 0
        self.is_charging: bool = False
        self.last_step_time: datetime | None = None
        self.charge_started_at: datetime | None = None

    def update_config(self, config: dict[str, Any]) -> None:
        """Update configuration."""
        self.config = config

    @property
    def min_amps(self) -> int:
        """Return minimum charging current (e.g. 5A)."""
        return int(self.config.get(CONF_EV_MIN_CURRENT, DEFAULT_EV_MIN_CURRENT))

    @property
    def max_amps(self) -> int:
        """Return maximum charging current (e.g. 16A or 32A)."""
        return int(self.config.get(CONF_EV_MAX_CURRENT, DEFAULT_EV_MAX_CURRENT))

    @property
    def voltage(self) -> float:
        """Return nominal grid voltage (e.g. 230V)."""
        return float(self.config.get(CONF_EV_VOLTAGE, DEFAULT_EV_VOLTAGE))

    @property
    def ramp_seconds(self) -> int:
        """Return minimum delay in seconds between current adjustments."""
        return int(self.config.get(CONF_EV_RAMP_SECONDS, DEFAULT_EV_RAMP_SECONDS))

    @property
    def min_start_power_watts(self) -> float:
        """Return minimum power in Watts required to start charging."""
        return self.min_amps * self.voltage

    def compute_charging_step(
        self,
        now: datetime,
        ev_plugged: bool,
        ev_soc: float,
        ev_target_soc: float,
        available_power_for_ev_watts: float,
        force_max_charge: bool = False,
    ) -> tuple[bool, int, list[dict[str, Any]]]:
        """Calculate smooth 1A step adjustment for Tesla Fleet without tripping Tuya EVSE.

         Note: `available_power_for_ev_watts` includes power already consumed by the Tesla
        plus current net solar surplus.
        """
        commands: list[dict[str, Any]] = []
        charge_switch = self.config.get(CONF_TESLA_CHARGE_SWITCH)
        current_number = self.config.get(CONF_TESLA_CURRENT_NUMBER)
        evse_switch = self.config.get(CONF_EVSE_POWER_SWITCH)
        evse_current_number = self.config.get(CONF_EVSE_CURRENT_NUMBER)

        if not ev_plugged or ev_soc >= ev_target_soc:
            if self.is_charging:
                self._append_stop_commands(commands, charge_switch, evse_switch)
                self.is_charging = False
                self.current_amps = 0
            return False, 0, commands

        if force_max_charge:
            desired_amps = self.max_amps
        else:
            raw_amps = int(available_power_for_ev_watts // self.voltage)
            if raw_amps < self.min_amps:
                desired_amps = 0
            else:
                desired_amps = min(self.max_amps, raw_amps)

        # Check ramp cooldown to avoid rapid oscillation and protect hardware
        can_step = (
            self.last_step_time is None
            or (now - self.last_step_time).total_seconds() >= self.ramp_seconds
        )

        # Case 1: Need to stop charging
        if desired_amps == 0:
            if self.is_charging:
                # Anti-short-cycle: keep charging at min_amps for at least 3 minutes before stopping
                min_run_ok = (
                    self.charge_started_at is None
                    or (now - self.charge_started_at).total_seconds() >= 180
                )
                if self.current_amps > self.min_amps and can_step:
                    # Step down gently towards min_amps first
                    self.current_amps = max(self.min_amps, self.current_amps - 1)
                    self.last_step_time = now
                    self._append_amp_command(
                        commands, current_number, evse_current_number, self.current_amps
                    )
                elif self.current_amps <= self.min_amps and min_run_ok and can_step:
                    self._append_stop_commands(commands, charge_switch, evse_switch)
                    self.is_charging = False
                    self.current_amps = 0
                    self.last_step_time = now
            return self.is_charging, self.current_amps, commands

        # Case 2: Need to start charging
        if not self.is_charging:
            if can_step:
                self.is_charging = True
                self.current_amps = self.min_amps if not force_max_charge else self.max_amps
                self.charge_started_at = now
                self.last_step_time = now

                # Ensure EVSE supply is enabled (supports select e.g. Tuya toggle_charging or switch)
                self._append_start_commands(commands, charge_switch, evse_switch)
                self._append_amp_command(
                    commands, current_number, evse_current_number, self.current_amps
                )
            return self.is_charging, self.current_amps, commands

        # Case 3: Already charging -> modulate smoothly by +1A or -1A per ramp interval
        if can_step and desired_amps != self.current_amps:
            if force_max_charge:
                self.current_amps = self.max_amps
            elif desired_amps > self.current_amps:
                # Can ramp up by up to +2A if big surplus, or +1A for fine tracking
                step_up = min(2, desired_amps - self.current_amps)
                self.current_amps = min(self.max_amps, self.current_amps + step_up)
            else:
                # Always step down by 1A at a time to prevent any voltage/contactor glitch
                self.current_amps = max(self.min_amps, self.current_amps - 1)

            self.last_step_time = now
            self._append_amp_command(
                commands, current_number, evse_current_number, self.current_amps
            )

        return self.is_charging, self.current_amps, commands

    @staticmethod
    def _append_amp_command(
        commands: list[dict[str, Any]],
        current_number: str | None,
        evse_current_number: str | None,
        amps: int,
    ) -> None:
        if current_number:
            domain = current_number.split(".")[0]
            commands.append(
                {
                    "domain": domain,
                    "service": "set_value",
                    "entity_id": current_number,
                    "data": {"value": amps},
                    "reason": f"Adjust vehicle charging current to {amps}A via {domain}",
                }
            )
        if evse_current_number:
            domain = evse_current_number.split(".")[0]
            commands.append(
                {
                    "domain": domain,
                    "service": "set_value",
                    "entity_id": evse_current_number,
                    "data": {"value": float(amps)},
                    "reason": f"Adjust Tuya EVSE setpoint current to {amps}A",
                }
            )

    @staticmethod
    def _append_start_commands(
        commands: list[dict[str, Any]],
        charge_switch: str | None,
        evse_switch: str | None,
    ) -> None:
        if evse_switch:
            domain = evse_switch.split(".")[0]
            if domain == "select":
                commands.append(
                    {
                        "domain": "select",
                        "service": "select_option",
                        "entity_id": evse_switch,
                        "data": {"option": "Start charging"},
                        "reason": "Start charging on Tuya EVSE select",
                    }
                )
            elif domain in ("switch", "input_boolean"):
                commands.append(
                    {
                        "domain": domain,
                        "service": "turn_on",
                        "entity_id": evse_switch,
                        "reason": "Ensure Tuya EVSE supply is enabled",
                    }
                )
        if charge_switch:
            domain = charge_switch.split(".")[0]
            commands.append(
                {
                    "domain": domain,
                    "service": "turn_on",
                    "entity_id": charge_switch,
                    "reason": "Start vehicle charging",
                }
            )

    @staticmethod
    def _append_stop_commands(
        commands: list[dict[str, Any]],
        charge_switch: str | None,
        evse_switch: str | None = None,
    ) -> None:
        if charge_switch:
            domain = charge_switch.split(".")[0]
            commands.append(
                {
                    "domain": domain,
                    "service": "turn_off",
                    "entity_id": charge_switch,
                    "reason": "Stop vehicle charging cleanly",
                }
            )
        if evse_switch:
            domain = evse_switch.split(".")[0]
            if domain == "select":
                commands.append(
                    {
                        "domain": "select",
                        "service": "select_option",
                        "entity_id": evse_switch,
                        "data": {"option": "Stop charging"},
                        "reason": "Stop charging on Tuya EVSE select",
                    }
                )
            elif domain in ("switch", "input_boolean"):
                commands.append(
                    {
                        "domain": domain,
                        "service": "turn_off",
                        "entity_id": evse_switch,
                        "reason": "Turn off EVSE power supply",
                    }
                )
