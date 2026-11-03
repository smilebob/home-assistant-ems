"""Controller for Tesla Fleet current modulation & Local Tuya EVSE with strict sequencing."""

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

VEHICLE_ACK_TIMEOUT_SECONDS = 15


class TeslaController:
    """Modulates EV charging current smoothly (1A steps) with strict Vehicle-before-EVSE sequencing."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Tesla controller."""
        self.config = config
        self.current_amps: int = 0
        self.is_charging: bool = False
        self.last_step_time: datetime | None = None
        self.charge_started_at: datetime | None = None
        self.awaiting_vehicle_ack: bool = False
        self.pending_vehicle_since: datetime | None = None
        self.last_confirmed_evse_amps: int = 0
        self.sequencing_status: str = "Veille"

    def update_config(self, config: dict[str, Any]) -> None:
        """Update configuration."""
        self.config = config

    @property
    def min_amps(self) -> int:
        """Return minimum charging current (e.g. 5A or 6A)."""
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
        reported_vehicle_amps: float | None = None,
    ) -> tuple[bool, int, list[dict[str, Any]]]:
        """Calculate smooth 1A step adjustment with strict Vehicle -> Ack -> EVSE sequencing.

        1. Always configure the vehicle charging current (`tesla_current_number`) FIRST.
        2. Wait until the vehicle setpoint is confirmed (or 15s safety timeout) before piloting the EVSE.
        """
        commands: list[dict[str, Any]] = []
        charge_switch = self.config.get(CONF_TESLA_CHARGE_SWITCH)
        current_number = self.config.get(CONF_TESLA_CURRENT_NUMBER)
        evse_switch = self.config.get(CONF_EVSE_POWER_SWITCH)
        evse_current_number = self.config.get(CONF_EVSE_CURRENT_NUMBER)

        if not ev_plugged or ev_soc >= ev_target_soc:
            if self.is_charging or self.awaiting_vehicle_ack:
                self._append_stop_commands(commands, charge_switch, evse_switch)
                self.is_charging = False
                self.awaiting_vehicle_ack = False
                self.pending_vehicle_since = None
                self.current_amps = 0
                self.last_confirmed_evse_amps = 0
                self.sequencing_status = (
                    "Arrêté (Non branché)" if not ev_plugged else f"Arrêté (SOC {ev_soc}% >= {ev_target_soc}%)"
                )
            return False, 0, commands

        # If we were waiting for vehicle confirmation from a previous cycle, check if confirmed now
        if self.awaiting_vehicle_ack and self.current_amps > 0:
            elapsed = (
                (now - self.pending_vehicle_since).total_seconds()
                if self.pending_vehicle_since
                else VEHICLE_ACK_TIMEOUT_SECONDS
            )
            confirmed = (
                reported_vehicle_amps is None
                or abs(reported_vehicle_amps - self.current_amps) < 0.5
                or elapsed >= VEHICLE_ACK_TIMEOUT_SECONDS
            )
            if confirmed:
                self.awaiting_vehicle_ack = False
                self.pending_vehicle_since = None
                self._append_evse_commands(
                    commands,
                    evse_current_number=evse_current_number,
                    evse_switch=evse_switch if not self.is_charging else None,
                    amps=self.current_amps,
                    wait_for_entity=current_number,
                )
                if not self.is_charging:
                    self._append_vehicle_start_switch(commands, charge_switch, current_number, self.current_amps)
                    self.is_charging = True
                    self.charge_started_at = now
                self.last_confirmed_evse_amps = self.current_amps
                self.sequencing_status = f"Consigne {self.current_amps}A confirmée côté véhicule -> Borne pilotée"
                return self.is_charging, self.current_amps, commands
            else:
                # Re-assert vehicle current while waiting
                self._append_vehicle_amp_command(commands, current_number, self.current_amps)
                self.sequencing_status = (
                    f"Attente confirmation véhicule : {self.current_amps}A demandé "
                    f"(lu: {reported_vehicle_amps}A, {int(elapsed)}s/{VEHICLE_ACK_TIMEOUT_SECONDS}s)"
                )
                return self.is_charging, self.current_amps, commands

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
                min_run_ok = (
                    self.charge_started_at is None
                    or (now - self.charge_started_at).total_seconds() >= 180
                )
                if self.current_amps > self.min_amps and can_step:
                    self.current_amps = max(self.min_amps, self.current_amps - 1)
                    self.last_step_time = now
                    self._dispatch_sequenced_amp_change(
                        now=now,
                        commands=commands,
                        current_number=current_number,
                        charge_switch=None,
                        evse_current_number=evse_current_number,
                        evse_switch=None,
                        amps=self.current_amps,
                        reported_vehicle_amps=reported_vehicle_amps,
                        is_starting=False,
                    )
                elif self.current_amps <= self.min_amps and min_run_ok and can_step:
                    self._append_stop_commands(commands, charge_switch, evse_switch)
                    self.is_charging = False
                    self.current_amps = 0
                    self.last_confirmed_evse_amps = 0
                    self.last_step_time = now
                    self.sequencing_status = "Arrêt propre (Voiture coupée puis Borne arrêtée)"
            return self.is_charging, self.current_amps, commands

        # Case 2: Need to start charging
        if not self.is_charging:
            if can_step:
                self.current_amps = self.min_amps if not force_max_charge else self.max_amps
                self.last_step_time = now
                self._dispatch_sequenced_amp_change(
                    now=now,
                    commands=commands,
                    current_number=current_number,
                    charge_switch=charge_switch,
                    evse_current_number=evse_current_number,
                    evse_switch=evse_switch,
                    amps=self.current_amps,
                    reported_vehicle_amps=reported_vehicle_amps,
                    is_starting=True,
                )
            return self.is_charging, self.current_amps, commands

        # Case 3: Already charging -> modulate smoothly by +1A/+2A or -1A per ramp interval
        if can_step and desired_amps != self.current_amps:
            if force_max_charge:
                self.current_amps = self.max_amps
            elif desired_amps > self.current_amps:
                step_up = min(2, desired_amps - self.current_amps)
                self.current_amps = min(self.max_amps, self.current_amps + step_up)
            else:
                self.current_amps = max(self.min_amps, self.current_amps - 1)

            self.last_step_time = now
            self._dispatch_sequenced_amp_change(
                now=now,
                commands=commands,
                current_number=current_number,
                charge_switch=None,
                evse_current_number=evse_current_number,
                evse_switch=None,
                amps=self.current_amps,
                reported_vehicle_amps=reported_vehicle_amps,
                is_starting=False,
            )

        return self.is_charging, self.current_amps, commands

    def _dispatch_sequenced_amp_change(
        self,
        now: datetime,
        commands: list[dict[str, Any]],
        current_number: str | None,
        charge_switch: str | None,
        evse_current_number: str | None,
        evse_switch: str | None,
        amps: int,
        reported_vehicle_amps: float | None,
        is_starting: bool,
    ) -> None:
        """Enforce strict sequence: 1. Vehicle Current -> 2. Confirm -> 3. Borne Current & Start."""
        # Step 1: Always emit vehicle current setpoint FIRST
        self._append_vehicle_amp_command(commands, current_number, amps)

        # If caller supplied a live reported_vehicle_amps that does not yet match `amps`,
        # hold EVSE commands in awaiting_vehicle_ack state until confirmed on next check
        if (
            current_number
            and reported_vehicle_amps is not None
            and abs(reported_vehicle_amps - amps) >= 0.5
        ):
            self.awaiting_vehicle_ack = True
            self.pending_vehicle_since = now
            self.sequencing_status = (
                f"Étape 1/2 : Consigne {amps}A envoyée à la voiture "
                f"(attente confirmation avant pilotage borne)"
            )
            return

        # Step 2: Vehicle confirmed (or will be confirmed in coordinator's 15s wait loop)
        if is_starting:
            self.is_charging = True
            self.charge_started_at = now
            self._append_vehicle_start_switch(commands, charge_switch, current_number, amps)

        self._append_evse_commands(
            commands,
            evse_current_number=evse_current_number,
            evse_switch=evse_switch if is_starting else None,
            amps=amps,
            wait_for_entity=current_number,
        )
        self.last_confirmed_evse_amps = amps
        self.sequencing_status = f"Séquence complète : Voiture ({amps}A) -> Borne ({amps}A)"

    @staticmethod
    def _append_vehicle_amp_command(
        commands: list[dict[str, Any]],
        current_number: str | None,
        amps: int,
    ) -> None:
        """Step 1: Set charging current on the vehicle first."""
        if not current_number:
            return
        domain = current_number.split(".")[0]
        commands.append(
            {
                "domain": domain,
                "service": "set_value",
                "entity_id": current_number,
                "data": {"value": amps},
                "sequence_order": 1,
                "reason": f"Étape 1 : Configurer le courant côté véhicule à {amps}A",
            }
        )

    @staticmethod
    def _append_vehicle_start_switch(
        commands: list[dict[str, Any]],
        charge_switch: str | None,
        wait_for_entity: str | None,
        amps: int,
    ) -> None:
        """Step 2: Enable vehicle charging switch."""
        if not charge_switch:
            return
        domain = charge_switch.split(".")[0]
        cmd: dict[str, Any] = {
            "domain": domain,
            "service": "turn_on",
            "entity_id": charge_switch,
            "sequence_order": 2,
            "reason": "Étape 2 : Autoriser la charge côté véhicule",
        }
        if wait_for_entity:
            cmd["wait_for_entity"] = wait_for_entity
            cmd["wait_for_value"] = amps
            cmd["wait_timeout_s"] = VEHICLE_ACK_TIMEOUT_SECONDS
        commands.append(cmd)

    @staticmethod
    def _append_evse_commands(
        commands: list[dict[str, Any]],
        evse_current_number: str | None,
        evse_switch: str | None,
        amps: int,
        wait_for_entity: str | None,
    ) -> None:
        """Step 3: After vehicle current is confirmed, configure EVSE current and start EVSE."""
        if evse_current_number:
            domain = evse_current_number.split(".")[0]
            cmd_curr: dict[str, Any] = {
                "domain": domain,
                "service": "set_value",
                "entity_id": evse_current_number,
                "data": {"value": float(amps)},
                "sequence_order": 3,
                "reason": f"Étape 3 : Ajuster le courant de la borne IRVE à {amps}A (après confirmation voiture)",
            }
            if wait_for_entity:
                cmd_curr["wait_for_entity"] = wait_for_entity
                cmd_curr["wait_for_value"] = amps
                cmd_curr["wait_timeout_s"] = VEHICLE_ACK_TIMEOUT_SECONDS
            commands.append(cmd_curr)

        if evse_switch:
            domain = evse_switch.split(".")[0]
            if domain == "select":
                cmd_sw: dict[str, Any] = {
                    "domain": "select",
                    "service": "select_option",
                    "entity_id": evse_switch,
                    "data": {"option": "Start charging"},
                    "sequence_order": 4,
                    "reason": "Étape 4 : Activer la borne Tuya (Start charging) après confirmation voiture",
                }
            else:
                cmd_sw = {
                    "domain": domain,
                    "service": "turn_on",
                    "entity_id": evse_switch,
                    "sequence_order": 4,
                    "reason": "Étape 4 : Activer l'alimentation de la borne IRVE après confirmation voiture",
                }
            if wait_for_entity:
                cmd_sw["wait_for_entity"] = wait_for_entity
                cmd_sw["wait_for_value"] = amps
                cmd_sw["wait_timeout_s"] = VEHICLE_ACK_TIMEOUT_SECONDS
            commands.append(cmd_sw)

    @staticmethod
    def _append_stop_commands(
        commands: list[dict[str, Any]],
        charge_switch: str | None,
        evse_switch: str | None = None,
    ) -> None:
        """Stop vehicle first, then stop EVSE."""
        if charge_switch:
            domain = charge_switch.split(".")[0]
            commands.append(
                {
                    "domain": domain,
                    "service": "turn_off",
                    "entity_id": charge_switch,
                    "sequence_order": 1,
                    "reason": "Étape 1 : Arrêter la charge côté véhicule",
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
                        "sequence_order": 2,
                        "reason": "Étape 2 : Arrêter la borne Tuya (Stop charging)",
                    }
                )
            elif domain in ("switch", "input_boolean"):
                commands.append(
                    {
                        "domain": domain,
                        "service": "turn_off",
                        "entity_id": evse_switch,
                        "sequence_order": 2,
                        "reason": "Étape 2 : Couper l'alimentation de la borne IRVE",
                    }
                )
