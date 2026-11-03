"""Central Energy Arbitrator implementing the 4-priority cascade, explainability, and cloud smoothing."""

from __future__ import annotations

from collections import deque
from datetime import datetime
import logging
from typing import Any

from ..const import (
    CONF_BATTERY_THERMAL_SOC_THRESHOLD,
    DEFAULT_BATTERY_THERMAL_SOC_THRESHOLD,
    PRIORITY_IDLE,
    PRIORITY_1_COMFORT_DHW,
    PRIORITY_2_BATTERY,
    PRIORITY_3_TESLA,
    PRIORITY_4_THERMAL_BOOST,
    PRIORITY_DYNAMIC_GRID_CHARGE,
)
from .controllers.ecodan import EcodanController
from .controllers.felicity import FelicityController
from .controllers.tesla import TeslaController
from .tariff import TariffManager

_LOGGER = logging.getLogger(__name__)


class EnergyArbitrator:
    """Orchestrates energy flows across Felicity, Mitsubishi Ecodan, and Tesla Fleet."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the energy arbitrator and sub-controllers."""
        self.config = config
        self.tariff = TariffManager(config)
        self.felicity = FelicityController(config)
        self.ecodan = EcodanController(config)
        self.tesla = TeslaController(config)

        # Rolling window of net surplus power (W) for cloud smoothing (last 5 readings = ~2.5 min)
        self._surplus_window: deque[float] = deque(maxlen=5)
        self._decision_log: deque[dict[str, str]] = deque(maxlen=10)
        self._last_logged_priority: str | None = None

        # Runtime user overrides (switches)
        self.auto_mode_enabled: bool = True
        self.force_dhw_boost: bool = False
        self.force_tesla_charge: bool = False
        self.allow_thermal_overheat: bool = True

    def update_config(self, config: dict[str, Any]) -> None:
        """Propagate updated config to all controllers."""
        self.config = config
        self.tariff.update_config(config)
        self.felicity.update_config(config)
        self.ecodan.update_config(config)
        self.tesla.update_config(config)

    def evaluate_cycle(
        self,
        now: datetime,
        pv_power_w: float,
        grid_power_w: float,
        house_load_w: float,
        battery_soc: float,
        battery_power_w: float,
        dhw_temp: float | None,
        z1_temp: float | None,
        z2_temp: float | None,
        z2_target: float | None,
        ev_plugged: bool,
        ev_soc: float,
        ev_target_soc: float,
        outdoor_temp: float,
        solar_today_remaining_kwh: float,
        solar_tomorrow_kwh: float,
        solar_day_after_kwh: float,
        predicted_24h_kwh: float,
        predicted_overnight_kwh: float,
        live_states: dict[str, Any],
        ev_measured_power_w: float = 0.0,
        reported_vehicle_amps: float | None = None,
        z1_target: float | None = None,
        z1_rooms_readings: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run one full arbitration cycle and return state metrics + hardware commands."""
        # 1. Calculate raw and smoothed solar surplus
        if ev_measured_power_w > 50.0:
            ev_current_power_w = ev_measured_power_w
        else:
            ev_current_power_w = (
                self.tesla.current_amps * self.tesla.voltage if self.tesla.is_charging else 0.0
            )
        base_house_without_ev_w = max(0.0, house_load_w - ev_current_power_w)
        raw_surplus_w = pv_power_w - base_house_without_ev_w
        self._surplus_window.append(raw_surplus_w)
        smoothed_surplus_w = sum(self._surplus_window) / len(self._surplus_window)

        # 2. Evaluate Tariff & Dynamic/Off-Peak opportunity
        import_price, export_price = self.tariff.get_current_prices(live_states)
        cheap_grid_active = self.tariff.is_cheap_grid_opportunity(live_states)
        spread_eur = self.tariff.calculate_self_consumption_spread(live_states)

        # 3. Compute dynamic battery target SOC based on calibrated Solcast & ML load prediction
        dynamic_batt_target_soc = self.felicity.calculate_dynamic_target_soc(
            predicted_overnight_load_kwh=predicted_overnight_kwh,
            solar_forecast_today_remaining_kwh=solar_today_remaining_kwh,
            solar_forecast_tomorrow_kwh=solar_tomorrow_kwh,
        )
        thermal_soc_threshold = float(
            self.config.get(
                CONF_BATTERY_THERMAL_SOC_THRESHOLD, DEFAULT_BATTERY_THERMAL_SOC_THRESHOLD
            )
        )

        all_commands: list[dict[str, Any]] = []
        active_priority = PRIORITY_IDLE

        # Determine Priority Hierarchy:
        # Priority 1: Comfort Heating & Scheduled Solar DHW
        # Priority 2: Home Battery (15 kWh) up to dynamic_batt_target_soc (and up to thermal_soc_threshold before P4)
        # Priority 3: Tesla Solar Charging (modulated via Tesla Fleet -> Borne Tuya)
        # Priority 4: Thermal inertia storage (only when battery_soc >= thermal_soc_threshold)
        dhw_normal_cfg = float(self.config.get("dhw_normal_temp", 48.0))
        if cheap_grid_active:
            active_priority = PRIORITY_DYNAMIC_GRID_CHARGE
        elif smoothed_surplus_w > 300.0:
            if (
                dhw_temp is not None
                and dhw_temp < dhw_normal_cfg - 3.0
                and self.ecodan.is_in_dhw_solar_window(now)
            ):
                active_priority = PRIORITY_1_COMFORT_DHW
            elif battery_soc < dynamic_batt_target_soc:
                active_priority = PRIORITY_2_BATTERY
            elif (
                ev_plugged
                and ev_soc < ev_target_soc
                and smoothed_surplus_w >= self.tesla.min_start_power_watts
            ):
                active_priority = PRIORITY_3_TESLA
            elif battery_soc < thermal_soc_threshold:
                # Continue charging battery until it reaches the thermal storage SOC threshold (e.g. 95%)
                active_priority = PRIORITY_2_BATTERY
            else:
                active_priority = PRIORITY_4_THERMAL_BOOST

        # Execute controller evaluations if Auto Mode is active
        dhw_heating = False
        dhw_target = dhw_normal_cfg
        new_z2_target = z2_target
        ev_charging = self.tesla.is_charging
        ev_amps = self.tesla.current_amps

        if self.auto_mode_enabled:
            # A. Felicity Inverter & Battery Commands
            felicity_cmds = self.felicity.build_commands(
                current_soc=battery_soc,
                should_force_grid_charge=cheap_grid_active,
            )
            all_commands.extend(felicity_cmds)

            # B. Mitsubishi Ecodan DHW & Zone 2 Commands
            is_p4 = active_priority == PRIORITY_4_THERMAL_BOOST and self.allow_thermal_overheat
            dhw_heating, dhw_target, dhw_cmds = self.ecodan.evaluate_dhw_need(
                now=now,
                dhw_temp=dhw_temp,
                net_surplus_watts=smoothed_surplus_w,
                force_boost_requested=self.force_dhw_boost or cheap_grid_active,
                thermal_storage_priority=is_p4,
            )
            all_commands.extend(dhw_cmds)

            new_z2_target, z2_cmds = self.ecodan.evaluate_zone2_thermal_storage(
                enable_thermal_storage=is_p4,
                current_z2_temp=z2_temp,
                current_z2_target=z2_target,
                outdoor_temp=outdoor_temp,
            )
            all_commands.extend(z2_cmds)

            # C. Tesla Fleet + Tuya EVSE Strict Sequenced Current Modulation
            if self.force_tesla_charge or cheap_grid_active:
                avail_ev_watts = self.tesla.max_amps * self.tesla.voltage
            elif battery_soc >= dynamic_batt_target_soc:
                avail_ev_watts = max(0.0, smoothed_surplus_w)
            elif battery_soc >= dynamic_batt_target_soc - 10.0 and smoothed_surplus_w > 2500.0:
                avail_ev_watts = smoothed_surplus_w * 0.6
            else:
                avail_ev_watts = 0.0

            ev_charging, ev_amps, ev_cmds = self.tesla.compute_charging_step(
                now=now,
                ev_plugged=ev_plugged,
                ev_soc=ev_soc,
                ev_target_soc=ev_target_soc,
                available_power_for_ev_watts=avail_ev_watts,
                force_max_charge=self.force_tesla_charge or cheap_grid_active,
                reported_vehicle_amps=reported_vehicle_amps,
            )
            all_commands.extend(ev_cmds)

        # 4. Evaluate Thermostatic Valve Balancing Advice for Zone 1 Rooms
        valve_summary, valve_details = self.ecodan.evaluate_valve_recommendations(
            z1_ref_temp=z1_temp,
            z1_target_temp=z1_target,
            room_readings=z1_rooms_readings or [],
        )

        # 5. Build clear French Decision Explainability string
        decision_reason = self._build_decision_explanation(
            active_priority=active_priority,
            smoothed_surplus_w=smoothed_surplus_w,
            grid_power_w=grid_power_w,
            house_load_w=house_load_w,
            battery_soc=battery_soc,
            battery_power_w=battery_power_w,
            dynamic_batt_target_soc=dynamic_batt_target_soc,
            thermal_soc_threshold=thermal_soc_threshold,
            dhw_temp=dhw_temp,
            dhw_target=dhw_target,
            ev_plugged=ev_plugged,
            ev_soc=ev_soc,
            ev_target_soc=ev_target_soc,
            ev_charging=ev_charging,
            ev_amps=ev_amps,
            new_z2_target=new_z2_target,
            import_price=import_price,
        )

        if active_priority != self._last_logged_priority:
            self._decision_log.appendleft(
                {
                    "time": now.strftime("%H:%M:%S"),
                    "priority": active_priority,
                    "reason": decision_reason,
                }
            )
            self._last_logged_priority = active_priority

        # Estimate instant hourly savings rate (€/h) from self-consumed PV
        self_consumed_watts = min(pv_power_w, max(0.0, house_load_w + max(0.0, battery_power_w)))
        instant_savings_eur_per_hour = round((self_consumed_watts / 1000.0) * spread_eur, 3)

        return {
            "timestamp": now.isoformat(),
            "active_priority": active_priority,
            "decision_reason": decision_reason,
            "decision_log": list(self._decision_log),
            "auto_mode": self.auto_mode_enabled,
            "pv_power_w": round(pv_power_w, 1),
            "grid_power_w": round(grid_power_w, 1),
            "house_load_w": round(house_load_w, 1),
            "raw_surplus_w": round(raw_surplus_w, 1),
            "smoothed_surplus_w": round(smoothed_surplus_w, 1),
            "battery_soc": round(battery_soc, 1),
            "battery_power_w": round(battery_power_w, 1),
            "dynamic_battery_target_soc": dynamic_batt_target_soc,
            "battery_thermal_soc_threshold": thermal_soc_threshold,
            "dhw_temp": dhw_temp,
            "dhw_target": dhw_target,
            "dhw_heating_recommended": dhw_heating,
            "z1_temp": z1_temp,
            "z2_temp": z2_temp,
            "z2_target": new_z2_target,
            "valve_summary": valve_summary,
            "valve_recommendations": valve_details,
            "ev_plugged": ev_plugged,
            "ev_soc": ev_soc,
            "ev_target_soc": ev_target_soc,
            "ev_charging": ev_charging,
            "ev_target_amps": ev_amps,
            "ev_sequencing_status": self.tesla.sequencing_status,
            "outdoor_temp": outdoor_temp,
            "solar_today_remaining_kwh": solar_today_remaining_kwh,
            "solar_tomorrow_kwh": solar_tomorrow_kwh,
            "solar_day_after_kwh": solar_day_after_kwh,
            "predicted_24h_kwh": predicted_24h_kwh,
            "predicted_overnight_kwh": predicted_overnight_kwh,
            "import_price_eur": import_price,
            "export_price_eur": export_price,
            "self_consumption_spread_eur": spread_eur,
            "instant_savings_eur_per_h": instant_savings_eur_per_hour,
            "cheap_grid_opportunity": cheap_grid_active,
            "commands": all_commands,
        }

    def _build_decision_explanation(
        self,
        active_priority: str,
        smoothed_surplus_w: float,
        grid_power_w: float,
        house_load_w: float,
        battery_soc: float,
        battery_power_w: float,
        dynamic_batt_target_soc: float,
        thermal_soc_threshold: float,
        dhw_temp: float | None,
        dhw_target: float,
        ev_plugged: bool,
        ev_soc: float,
        ev_target_soc: float,
        ev_charging: bool,
        ev_amps: int,
        new_z2_target: float | None,
        import_price: float,
    ) -> str:
        """Return a human-readable French explanation of the current arbitrage decision."""
        if not self.auto_mode_enabled:
            return "Pilote automatique désactivé par l'utilisateur (mode manuel)."

        surplus_int = int(round(smoothed_surplus_w))
        batt_int = int(round(battery_soc))
        grid_int = int(round(grid_power_w))
        load_int = int(round(house_load_w))

        if active_priority == PRIORITY_DYNAMIC_GRID_CHARGE:
            return (
                f"Tarif réseau très bas ({import_price:.3f} €/kWh) : "
                f"charge forcée batterie ({batt_int}%), VE et ballon ECS."
            )
        if active_priority == PRIORITY_1_COMFORT_DHW:
            return (
                f"Priorité 1 (ECS Solaire) : Surplus de {surplus_int} W utilisé pour chauffer "
                f"l'ECS ({dhw_temp}°C -> cible {dhw_target}°C) dans le créneau solaire optimal."
            )
        if active_priority == PRIORITY_2_BATTERY:
            if battery_soc < dynamic_batt_target_soc:
                return (
                    f"Priorité 2 (Batterie Felicity) : Surplus de {surplus_int} W réservé à la "
                    f"batterie ({batt_int}% < cible autonomie nuit {int(dynamic_batt_target_soc)}%)."
                )
            return (
                f"Priorité 2 (Complément Batterie) : VE non demandeur ; le surplus ({surplus_int} W) "
                f"charge la batterie ({batt_int}%) jusqu'au seuil d'inertie thermique ({int(thermal_soc_threshold)}%)."
            )
        if active_priority == PRIORITY_3_TESLA:
            return (
                f"Priorité 3 (Charge VE) : Batterie à {batt_int}% (>= cible {int(dynamic_batt_target_soc)}%). "
                f"Surplus de {surplus_int} W modulé vers VE à {ev_amps} A ({self.tesla.sequencing_status})."
            )
        if active_priority == PRIORITY_4_THERMAL_BOOST:
            return (
                f"Priorité 4 (Inertie Thermique) : Batterie pleine ({batt_int}% >= {int(thermal_soc_threshold)}%). "
                f"Surplus ({surplus_int} W) stocké dans le plancher Zone 2 (cible {new_z2_target}°C) et l'ECS ({dhw_target}°C)."
            )

        # IDLE explanation based on actual grid vs battery flow
        if smoothed_surplus_w <= 0:
            if grid_power_w > 150.0:
                if abs(battery_power_w) < 150.0 or battery_soc <= self.felicity.min_soc + 5.0:
                    return (
                        f"Veille (Pas de production solaire) : batterie en réserve ({batt_int}%), "
                        f"le réseau alimente la maison ({grid_int} W)."
                    )
                return (
                    f"Autoconsommation partielle : déficit solaire ({surplus_int} W), "
                    f"la batterie ({batt_int}%) et le réseau ({grid_int} W) alimentent la maison ({load_int} W)."
                )
            return (
                f"Autoconsommation sur batterie : déficit solaire ({surplus_int} W), "
                f"la batterie ({batt_int}%) couvre les besoins de la maison ({load_int} W)."
            )
        return (
            f"Veille active : faible surplus lissé ({surplus_int} W < 300 W), "
            f"absorbé par la batterie ({batt_int}%)."
        )
