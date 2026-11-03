"""Controller for Mitsubishi Ecodan Heat Pump (esphome-ecodan-hp)."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from ...const import (
    CONF_DHW_TARGET_ENTITY,
    CONF_DHW_FORCE_ENTITY,
    CONF_DHW_NORMAL_TEMP,
    CONF_DHW_BOOST_TEMP,
    CONF_DHW_SOLAR_WINDOW_START,
    CONF_DHW_SOLAR_WINDOW_END,
    CONF_Z2_TARGET_ENTITY,
    CONF_Z2_MAX_OVERHEAT_OFFSET,
    DEFAULT_DHW_NORMAL_TEMP,
    DEFAULT_DHW_BOOST_TEMP,
    DEFAULT_DHW_WINDOW_START,
    DEFAULT_DHW_WINDOW_END,
    DEFAULT_Z2_MAX_OFFSET,
)

_LOGGER = logging.getLogger(__name__)


class EcodanController:
    """Manages Mitsubishi Ecodan DHW solar scheduling and Zone 2 floor thermal storage."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Ecodan controller."""
        self.config = config
        self._base_z2_setpoint: float | None = None
        self._thermal_boost_active: bool = False

    def update_config(self, config: dict[str, Any]) -> None:
        """Update configuration."""
        self.config = config

    def is_in_dhw_solar_window(self, now: datetime) -> bool:
        """Check if current time is inside the preferred solar DHW window (e.g. 11h-15h)."""
        start_h = int(self.config.get(CONF_DHW_SOLAR_WINDOW_START, DEFAULT_DHW_WINDOW_START))
        end_h = int(self.config.get(CONF_DHW_SOLAR_WINDOW_END, DEFAULT_DHW_WINDOW_END))
        return start_h <= now.hour < end_h

    def evaluate_dhw_need(
        self,
        now: datetime,
        dhw_temp: float | None,
        net_surplus_watts: float,
        force_boost_requested: bool = False,
        thermal_storage_priority: bool = False,
    ) -> tuple[bool, float, list[dict[str, Any]]]:
        """Evaluate whether DHW heating or boost should be triggered.

        Returns:
            (dhw_active, target_dhw_temp, commands)
        """
        normal_temp = float(self.config.get(CONF_DHW_NORMAL_TEMP, DEFAULT_DHW_NORMAL_TEMP))
        boost_temp = float(self.config.get(CONF_DHW_BOOST_TEMP, DEFAULT_DHW_BOOST_TEMP))
        dhw_target_entity = self.config.get(CONF_DHW_TARGET_ENTITY)
        dhw_force_entity = self.config.get(CONF_DHW_FORCE_ENTITY)

        commands: list[dict[str, Any]] = []

        if dhw_temp is None:
            return False, normal_temp, commands

        in_window = self.is_in_dhw_solar_window(now)
        need_daily_dhw = in_window and (dhw_temp < normal_temp - 3.0) and (net_surplus_watts > 600.0 or now.hour >= 13)
        emergency_dhw = dhw_temp < 38.0
        do_boost = force_boost_requested or (thermal_storage_priority and dhw_temp < boost_temp - 1.5)

        target_temp = boost_temp if do_boost else normal_temp
        should_heat = emergency_dhw or need_daily_dhw or do_boost

        if dhw_target_entity:
            domain = dhw_target_entity.split(".")[0]
            if domain in ("number", "input_number"):
                commands.append(
                    {
                        "domain": domain,
                        "service": "set_value",
                        "entity_id": dhw_target_entity,
                        "data": {"value": target_temp},
                        "reason": "Set DHW target temperature",
                    }
                )
            elif domain == "water_heater":
                commands.append(
                    {
                        "domain": "water_heater",
                        "service": "set_temperature",
                        "entity_id": dhw_target_entity,
                        "data": {"temperature": target_temp},
                        "reason": "Set DHW water_heater temperature",
                    }
                )
            elif domain == "climate":
                commands.append(
                    {
                        "domain": "climate",
                        "service": "set_temperature",
                        "entity_id": dhw_target_entity,
                        "data": {"temperature": target_temp},
                        "reason": "Set DHW climate target temperature",
                    }
                )

        if should_heat and dhw_force_entity:
            domain = dhw_force_entity.split(".")[0]
            service = "press" if domain == "button" else "turn_on"
            commands.append(
                {
                    "domain": domain,
                    "service": service,
                    "entity_id": dhw_force_entity,
                    "reason": "Trigger Ecodan DHW cycle during solar optimum / boost",
                }
            )

        return should_heat, target_temp, commands

    def evaluate_zone2_thermal_storage(
        self,
        enable_thermal_storage: bool,
        current_z2_temp: float | None,
        current_z2_target: float | None,
        outdoor_temp: float,
    ) -> tuple[float | None, list[dict[str, Any]]]:
        """Manage Zone 2 (living room underfloor heating) thermal inertia pre-heating.

        Only applies in heating season (outdoor_temp < 16°C) when Priority 4 surplus is available.
        """
        z2_target_entity = self.config.get(CONF_Z2_TARGET_ENTITY)
        max_offset = float(self.config.get(CONF_Z2_MAX_OVERHEAT_OFFSET, DEFAULT_Z2_MAX_OFFSET))
        commands: list[dict[str, Any]] = []

        if not z2_target_entity or current_z2_target is None:
            return current_z2_target, commands

        if not self._thermal_boost_active:
            self._base_z2_setpoint = current_z2_target

        base_setpoint = self._base_z2_setpoint or current_z2_target

        # Only store thermal energy in floor slab if outdoor temperature requires heating
        if enable_thermal_storage and outdoor_temp < 16.0 and max_offset > 0.0:
            new_target = round(base_setpoint + max_offset, 1)
            if current_z2_temp is not None and current_z2_temp >= new_target + 0.5:
                # Floor/room already warm enough
                return current_z2_target, commands
            self._thermal_boost_active = True
        else:
            if self._thermal_boost_active:
                new_target = round(base_setpoint, 1)
                self._thermal_boost_active = False
            else:
                return current_z2_target, commands

        if abs(new_target - current_z2_target) >= 0.2:
            domain = z2_target_entity.split(".")[0]
            if domain == "climate":
                commands.append(
                    {
                        "domain": "climate",
                        "service": "set_temperature",
                        "entity_id": z2_target_entity,
                        "data": {"temperature": new_target},
                        "reason": "Zone 2 underfloor thermal storage modulation",
                    }
                )
            elif domain in ("number", "input_number"):
                commands.append(
                    {
                        "domain": domain,
                        "service": "set_value",
                        "entity_id": z2_target_entity,
                        "data": {"value": new_target},
                        "reason": "Zone 2 underfloor thermal storage modulation",
                    }
                )

        return new_target, commands

    def evaluate_valve_recommendations(
        self,
        z1_ref_temp: float | None,
        z1_target_temp: float | None,
        room_readings: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Compute thermostatic radiator valve balancing advice for Zone 1 rooms.

        Compares each room against the Zone 1 comfort target (or reference room temperature
        when Zone 1 is driven by water departure temperature / loi d'eau).
        """
        if z1_target_temp is not None and 15.0 <= z1_target_temp <= 24.5:
            ref_temp = round(z1_target_temp, 1)
        elif z1_ref_temp is not None and 15.0 <= z1_ref_temp <= 24.5:
            ref_temp = round(z1_ref_temp, 1)
        else:
            ref_temp = 20.0

        recommendations: list[dict[str, Any]] = []
        adjust_count = 0

        for item in room_readings:
            name = item.get("name", item.get("entity_id", "Pièce"))
            temp = item.get("temp")
            if temp is None:
                continue
            delta = round(float(temp) - ref_temp, 1)
            if delta > 1.2:
                action = "Fermer (-1/2 tour / -1 cran)"
                direction = "close"
                adjust_count += 1
            elif delta > 0.5:
                action = "Fermer légèrement (-1/4 tour)"
                direction = "close_slight"
                adjust_count += 1
            elif delta < -1.2:
                action = "Ouvrir (+1/2 tour / +1 cran)"
                direction = "open"
                adjust_count += 1
            elif delta < -0.5:
                action = "Ouvrir légèrement (+1/4 tour)"
                direction = "open_slight"
                adjust_count += 1
            else:
                action = "Équilibrée (ne pas toucher)"
                direction = "ok"

            recommendations.append(
                {
                    "room": name,
                    "entity_id": item.get("entity_id"),
                    "temp": round(float(temp), 1),
                    "reference_temp": ref_temp,
                    "delta": delta,
                    "action": action,
                    "direction": direction,
                }
            )

        if not recommendations:
            return "Aucun capteur de pièce configuré", []
        if adjust_count == 0:
            return f"Toutes les vannes sont équilibrées (réf. {ref_temp}°C)", recommendations
        return f"{adjust_count} vanne(s) à ajuster (réf. {ref_temp}°C)", recommendations
