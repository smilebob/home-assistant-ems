"""Controller for Felicity Hybrid Inverter & 15 kWh Battery via ha_felicity."""

from __future__ import annotations

import logging
from typing import Any

from ...const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_MIN_SOC,
    CONF_BATTERY_TARGET_SOC_EV,
    CONF_FELICITY_WORK_MODE_ENTITY,
    CONF_FELICITY_FORCE_CHARGE_ENTITY,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_BATTERY_MIN_SOC,
    DEFAULT_BATTERY_TARGET_SOC_EV,
)

_LOGGER = logging.getLogger(__name__)


class FelicityController:
    """Manages Felicity inverter work mode and battery reserve calculations."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Felicity controller."""
        self.config = config
        self._last_forced_state: bool | None = None

    def update_config(self, config: dict[str, Any]) -> None:
        """Update configuration."""
        self.config = config

    @property
    def capacity_kwh(self) -> float:
        """Return total battery capacity in kWh."""
        return float(self.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))

    @property
    def min_soc(self) -> float:
        """Return minimum safety reserve SOC (%)."""
        return float(self.config.get(CONF_BATTERY_MIN_SOC, DEFAULT_BATTERY_MIN_SOC))

    @property
    def target_soc_for_ev(self) -> float:
        """Return target battery SOC (%) before diverting surplus to Tesla."""
        return float(self.config.get(CONF_BATTERY_TARGET_SOC_EV, DEFAULT_BATTERY_TARGET_SOC_EV))

    def calculate_dynamic_target_soc(
        self,
        predicted_overnight_load_kwh: float,
        solar_forecast_today_remaining_kwh: float,
        solar_forecast_tomorrow_kwh: float,
    ) -> float:
        """Compute smart battery SOC threshold before diverting solar to EV/thermal boost.

        If Solcast predicts plenty of remaining solar today or a very sunny day tomorrow,
        we can lower the SOC threshold required before starting Tesla solar charging,
        preventing battery saturation (clipping/4c€ export) in the afternoon.
        """
        base_target = self.target_soc_for_ev
        needed_reserve_soc = self.min_soc + (predicted_overnight_load_kwh / max(1.0, self.capacity_kwh)) * 100.0
        needed_reserve_soc = min(95.0, max(self.min_soc + 10.0, needed_reserve_soc))

        # If remaining solar today exceeds what's needed to fill the battery by > 4 kWh,
        # allow Tesla charging earlier so both battery and EV share the peak sun.
        if solar_forecast_today_remaining_kwh > 8.0 and solar_forecast_tomorrow_kwh > 12.0:
            dynamic_target = min(base_target, max(40.0, needed_reserve_soc - 20.0))
        elif solar_forecast_tomorrow_kwh < 5.0:
            # Cloudy tomorrow: prioritize filling the 15 kWh battery to 90%+
            dynamic_target = max(base_target, 90.0)
        else:
            dynamic_target = base_target

        return round(float(dynamic_target), 1)

    def build_commands(
        self,
        current_soc: float,
        should_force_grid_charge: bool,
    ) -> list[dict[str, Any]]:
        """Generate Home Assistant service call descriptors for ha_felicity."""
        commands: list[dict[str, Any]] = []
        force_switch = self.config.get(CONF_FELICITY_FORCE_CHARGE_ENTITY)
        work_mode_select = self.config.get(CONF_FELICITY_WORK_MODE_ENTITY)
        active_force = bool(should_force_grid_charge and current_soc < 95.0)

        if self._last_forced_state == active_force:
            return commands
        self._last_forced_state = active_force

        if force_switch:
            domain = force_switch.split(".")[0]
            if domain in ("select", "input_select"):
                commands.append(
                    {
                        "domain": domain,
                        "service": "select_option",
                        "entity_id": force_switch,
                        "data": {"option": "Charge" if active_force else "Disabled"},
                        "reason": "Dynamic/Off-Peak cheap grid charge" if active_force else "Self-consumption mode",
                    }
                )
            else:
                target_state = "turn_on" if active_force else "turn_off"
                commands.append(
                    {
                        "domain": domain,
                        "service": target_state,
                        "entity_id": force_switch,
                        "reason": "Dynamic/Off-Peak cheap grid charge" if active_force else "Self-consumption mode",
                    }
                )

        if work_mode_select:
            domain = work_mode_select.split(".")[0]
            option = (
                "Economic mode (scheduled charge-discharge)"
                if active_force
                else "General mode (self-use, load priority)"
            )
            commands.append(
                {
                    "domain": domain,
                    "service": "select_option",
                    "entity_id": work_mode_select,
                    "data": {"option": option},
                    "reason": "Switch Felicity operating mode",
                }
            )

        return commands
