"""DataUpdateCoordinator for Smart Residential EMS."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    UPDATE_INTERVAL_SECONDS,
    CONF_PV_POWER_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_HOUSE_LOAD_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
    CONF_ECODAN_POWER_ENTITY,
    CONF_DHW_TEMP_ENTITY,
    CONF_Z1_TEMP_ENTITY,
    CONF_Z1_TARGET_ENTITY,
    CONF_Z1_ROOMS_ENTITIES,
    CONF_Z2_TEMP_ENTITY,
    CONF_Z2_TARGET_ENTITY,
    CONF_EV_PLUGGED_ENTITY,
    CONF_EV_SOC_ENTITY,
    CONF_EV_TARGET_SOC_ENTITY,
    CONF_TESLA_CURRENT_NUMBER,
    CONF_EVSE_POWER_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_SOLAR_FORECAST_POWER_NOW,
    CONF_SOLAR_FORECAST_TODAY_REMAINING,
    CONF_SOLAR_FORECAST_TOMORROW,
    CONF_SOLAR_FORECAST_DAY_AFTER,
    CONF_ML_TRAINING_DAYS,
    CONF_ML_AUTO_TRAIN,
    DEFAULT_ML_TRAINING_DAYS,
)
from .core.arbitrator import EnergyArbitrator
from .ml.dataset_builder import RecorderDatasetBuilder
from .ml.model import ConsumptionMLModel, SolarCalibrationModel

_LOGGER = logging.getLogger(__name__)


class EMSDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates live sensor polling, ML inference, solar calibration, and sequenced actuator dispatch."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the EMS coordinator."""
        self.hass = hass
        self.entry = entry
        data = entry.data or {}
        options = entry.options or {}
        self.config: dict[str, Any] = {**data, **options}

        storage_dir = hass.config.path(".storage")
        model_path = os.path.join(storage_dir, "ems_ml_model.pkl")
        solar_model_path = os.path.join(storage_dir, "ems_solar_calibration.pkl")

        self.ml_model = ConsumptionMLModel(storage_path=model_path)
        self.solar_calibrator = SolarCalibrationModel(storage_path=solar_model_path)
        self.dataset_builder = RecorderDatasetBuilder(hass)
        self.arbitrator = EnergyArbitrator(self.config)

        self._last_ml_train_date: int | None = None
        self._last_hourly_record_hour: int | None = None
        self.cumulative_savings_eur: float = 0.0

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )

    def update_configuration(self, new_config: dict[str, Any]) -> None:
        """Apply updated configuration from Options Flow."""
        self.config = new_config
        self.arbitrator.update_config(new_config)

    def _resolve_solcast_power_entity(self) -> str | None:
        """Return configured or auto-discovered Solcast instant power entity."""
        configured = self.config.get(CONF_SOLAR_FORECAST_POWER_NOW)
        if configured:
            return configured
        candidates = (
            "sensor.solcast_pv_forecast_puissance_maintenant",
            "sensor.solcast_pv_forecast_previsions_heure_actuel",
            "sensor.solcast_pv_forecast_power_now",
        )
        for cand in candidates:
            if self.hass.states.get(cand) is not None:
                return cand
        return None

    async def async_initialize_ml(self) -> None:
        """Load persisted ML models or perform initial training from 2-year Recorder history."""
        loaded_load = await self.hass.async_add_executor_job(self.ml_model.load_from_disk)
        loaded_solar = await self.hass.async_add_executor_job(self.solar_calibrator.load_from_disk)
        if not loaded_load or not loaded_solar:
            await self.async_retrain_ml_model()

    async def async_retrain_ml_model(self) -> dict[str, Any]:
        """Extract Recorder history and train both Consumption ML and Solar Calibration ML."""
        days = int(self.config.get(CONF_ML_TRAINING_DAYS, DEFAULT_ML_TRAINING_DAYS))
        X, y = await self.dataset_builder.async_fetch_training_dataset(
            load_entity=self.config.get(CONF_HOUSE_LOAD_ENTITY),
            ecodan_power_entity=self.config.get(CONF_ECODAN_POWER_ENTITY),
            outdoor_temp_entity=self.config.get(CONF_OUTDOOR_TEMP_ENTITY),
            z1_temp_entity=self.config.get(CONF_Z1_TEMP_ENTITY),
            z2_temp_entity=self.config.get(CONF_Z2_TEMP_ENTITY),
            days=days,
        )
        load_metrics = await self.hass.async_add_executor_job(self.ml_model.train, X, y)

        solcast_power_ent = self._resolve_solcast_power_entity()
        X_sol, y_sol, sol_pairs = await self.dataset_builder.async_fetch_solar_calibration_dataset(
            pv_power_entity=self.config.get(CONF_PV_POWER_ENTITY),
            solcast_power_entity=solcast_power_ent,
            outdoor_temp_entity=self.config.get(CONF_OUTDOOR_TEMP_ENTITY),
            days=min(days, 365),
        )
        solar_metrics = await self.hass.async_add_executor_job(
            self.solar_calibrator.train, X_sol, y_sol, sol_pairs
        )

        self._last_ml_train_date = datetime.now().day
        return {**load_metrics, **solar_metrics}

    def _read_float(self, entity_id: str | None, default: float = 0.0) -> float:
        """Safely read a float state or attribute from Home Assistant."""
        if not entity_id:
            return default
        state_obj = self.hass.states.get(entity_id)
        if state_obj is None or state_obj.state in ("unknown", "unavailable", None):
            return default
        try:
            return float(state_obj.state)
        except (ValueError, TypeError):
            temp_attr = state_obj.attributes.get("temperature") or state_obj.attributes.get(
                "current_temperature"
            )
            if temp_attr is not None:
                try:
                    return float(temp_attr)
                except (ValueError, TypeError):
                    pass
            return default

    def _read_optional_float(self, entity_id: str | None) -> float | None:
        """Safely read an optional float state."""
        if not entity_id:
            return None
        state_obj = self.hass.states.get(entity_id)
        if state_obj is None or state_obj.state in ("unknown", "unavailable", None):
            return None
        try:
            return float(state_obj.state)
        except (ValueError, TypeError):
            temp_attr = state_obj.attributes.get("temperature")
            if temp_attr is not None:
                try:
                    return float(temp_attr)
                except (ValueError, TypeError):
                    pass
            return None

    def _read_bool(self, entity_id: str | None, default: bool = False) -> bool:
        """Safely read a boolean or connectivity state."""
        if not entity_id:
            return default
        state_obj = self.hass.states.get(entity_id)
        if state_obj is None or state_obj.state in ("unknown", "unavailable", None):
            return default
        val = str(state_obj.state).lower().strip()
        plugged_states = (
            "on",
            "true",
            "connected",
            "plugged",
            "plugged_in",
            "charging",
            "waiting",
            "waiting_for_authorization",
            "charged",
            "1",
        )
        return val in plugged_states

    def _read_power_watts(self, entity_id: str | None, default: float = 0.0) -> float:
        """Safely read power in Watts, converting from kW if needed."""
        if not entity_id:
            return default
        state_obj = self.hass.states.get(entity_id)
        if state_obj is None or state_obj.state in ("unknown", "unavailable", None):
            return default
        try:
            val = float(state_obj.state)
        except (ValueError, TypeError):
            return default
        unit = str(state_obj.attributes.get("unit_of_measurement", "")).strip().lower()
        if unit == "kw":
            return val * 1000.0
        return val

    def _collect_z1_room_readings(self) -> list[dict[str, Any]]:
        """Read all Zone 1 room temperature sensors for thermostatic valve balancing."""
        room_entities: list[str] = list(self.config.get(CONF_Z1_ROOMS_ENTITIES) or [])
        z1_main = self.config.get(CONF_Z1_TEMP_ENTITY)
        if z1_main and z1_main not in room_entities:
            room_entities.insert(0, z1_main)

        readings: list[dict[str, Any]] = []
        for ent_id in room_entities:
            state_obj = self.hass.states.get(ent_id)
            if state_obj is None:
                continue
            temp_val = self._read_optional_float(ent_id)
            if temp_val is not None:
                friendly = state_obj.attributes.get("friendly_name", ent_id)
                readings.append(
                    {
                        "entity_id": ent_id,
                        "name": friendly,
                        "temp": temp_val,
                    }
                )
        return readings

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest sensor states, run ML prediction + solar calibration + arbitration, and dispatch."""
        now = datetime.now()

        pv_power = self._read_power_watts(self.config.get(CONF_PV_POWER_ENTITY), 0.0)
        grid_power = self._read_power_watts(self.config.get(CONF_GRID_POWER_ENTITY), 0.0)
        house_load = self._read_power_watts(self.config.get(CONF_HOUSE_LOAD_ENTITY), 400.0)
        battery_soc = self._read_float(self.config.get(CONF_BATTERY_SOC_ENTITY), 50.0)
        battery_power = self._read_power_watts(self.config.get(CONF_BATTERY_POWER_ENTITY), 0.0)

        dhw_temp = self._read_optional_float(self.config.get(CONF_DHW_TEMP_ENTITY))
        z1_temp = self._read_optional_float(self.config.get(CONF_Z1_TEMP_ENTITY))
        z1_target = self._read_optional_float(self.config.get(CONF_Z1_TARGET_ENTITY))
        z2_temp = self._read_optional_float(self.config.get(CONF_Z2_TEMP_ENTITY))
        z2_target = self._read_optional_float(self.config.get(CONF_Z2_TARGET_ENTITY))
        z1_rooms_readings = self._collect_z1_room_readings()

        ev_plugged = self._read_bool(self.config.get(CONF_EV_PLUGGED_ENTITY), False)
        ev_soc = self._read_float(self.config.get(CONF_EV_SOC_ENTITY), 50.0)
        ev_target_soc = self._read_float(self.config.get(CONF_EV_TARGET_SOC_ENTITY), 80.0)
        reported_vehicle_amps = self._read_optional_float(self.config.get(CONF_TESLA_CURRENT_NUMBER))

        outdoor_temp = self._read_float(self.config.get(CONF_OUTDOOR_TEMP_ENTITY), 12.0)

        # Raw Solcast Forecasts
        solcast_power_ent = self._resolve_solcast_power_entity()
        raw_solcast_power_w = self._read_power_watts(solcast_power_ent, pv_power)
        raw_solar_today_rem = self._read_float(
            self.config.get(CONF_SOLAR_FORECAST_TODAY_REMAINING), 5.0
        )
        raw_solar_tomorrow = self._read_float(self.config.get(CONF_SOLAR_FORECAST_TOMORROW), 12.0)
        raw_solar_day_after = self._read_float(self.config.get(CONF_SOLAR_FORECAST_DAY_AFTER), 12.0)

        # Record hourly observation for incremental ML & Solar Calibration learning
        if self._last_hourly_record_hour != now.hour:
            self.ml_model.record_observation(
                dt=now,
                power_watts=house_load,
                outdoor_temp=outdoor_temp,
                indoor_z1_temp=z1_temp or 20.0,
                indoor_z2_temp=z2_temp or 20.5,
            )
            if solcast_power_ent:
                self.solar_calibrator.record_observation(
                    dt=now,
                    solcast_watts=raw_solcast_power_w,
                    actual_pv_watts=pv_power,
                    outdoor_temp=outdoor_temp,
                )
            self._last_hourly_record_hour = now.hour

        # Nightly automatic ML retraining at 03:00 AM
        if (
            self.config.get(CONF_ML_AUTO_TRAIN, True)
            and now.hour == 3
            and self._last_ml_train_date != now.day
        ):
            await self.async_retrain_ml_model()

        # Intermediate Solar Calibration Layer (Historical Deye vs Solcast auto-correction)
        calibrated_solar_power_w = self.solar_calibrator.calibrate_power_watts(
            dt=now,
            solcast_watts=raw_solcast_power_w,
            outdoor_temp=outdoor_temp,
        )
        cal_solar_today_rem, cal_solar_tomorrow, cal_solar_day_after = (
            self.solar_calibrator.calibrate_daily_forecasts(
                now=now,
                raw_today_rem_kwh=raw_solar_today_rem,
                raw_tomorrow_kwh=raw_solar_tomorrow,
                raw_day_after_kwh=raw_solar_day_after,
            )
        )

        # Predict 24h and overnight (next 12h) consumption via ML model
        pred_24h_kwh, hourly_forecast = self.ml_model.predict_next_hours_kwh(
            start_dt=now,
            hours=24,
            outdoor_temp=outdoor_temp,
            indoor_z1_temp=z1_temp or 20.0,
            indoor_z2_temp=z2_temp or 20.5,
        )
        pred_overnight_kwh, _ = self.ml_model.predict_next_hours_kwh(
            start_dt=now,
            hours=12,
            outdoor_temp=outdoor_temp,
            indoor_z1_temp=z1_temp or 20.0,
            indoor_z2_temp=z2_temp or 20.5,
        )

        # Collect dynamic price states if configured
        live_states: dict[str, Any] = {}
        for key in ("grid_import_price_entity", "grid_export_price_entity"):
            ent = self.config.get(key)
            if ent:
                live_states[ent] = self._read_optional_float(ent)

        result = self.arbitrator.evaluate_cycle(
            now=now,
            pv_power_w=pv_power,
            grid_power_w=grid_power,
            house_load_w=house_load,
            battery_soc=battery_soc,
            battery_power_w=battery_power,
            dhw_temp=dhw_temp,
            z1_temp=z1_temp,
            z2_temp=z2_temp,
            z2_target=z2_target,
            ev_plugged=ev_plugged,
            ev_soc=ev_soc,
            ev_target_soc=ev_target_soc,
            outdoor_temp=outdoor_temp,
            solar_today_remaining_kwh=cal_solar_today_rem,
            solar_tomorrow_kwh=cal_solar_tomorrow,
            solar_day_after_kwh=cal_solar_day_after,
            predicted_24h_kwh=pred_24h_kwh,
            predicted_overnight_kwh=pred_overnight_kwh,
            live_states=live_states,
            ev_measured_power_w=self._read_power_watts(self.config.get(CONF_EVSE_POWER_ENTITY)),
            reported_vehicle_amps=reported_vehicle_amps,
            z1_target=z1_target,
            z1_rooms_readings=z1_rooms_readings,
        )

        # Accumulate financial savings over time
        step_hours = UPDATE_INTERVAL_SECONDS / 3600.0
        self.cumulative_savings_eur = round(
            self.cumulative_savings_eur + result["instant_savings_eur_per_h"] * step_hours,
            3,
        )
        result["cumulative_savings_eur"] = self.cumulative_savings_eur

        # ML Consumption accuracy metrics
        result["ml_samples"] = self.ml_model.training_samples
        result["ml_mae_watts"] = self.ml_model.mae_score
        result["ml_accuracy_pct"] = self.ml_model.accuracy_pct
        result["ml_r2_score"] = self.ml_model.r2_score
        result["hourly_forecast"] = hourly_forecast[:12]

        # Intermediate Solar Calibrator metrics
        result["raw_solar_today_remaining_kwh"] = round(raw_solar_today_rem, 2)
        result["raw_solar_tomorrow_kwh"] = round(raw_solar_tomorrow, 2)
        result["raw_solar_day_after_kwh"] = round(raw_solar_day_after, 2)
        result["raw_solcast_power_w"] = round(raw_solcast_power_w, 1)
        result["calibrated_solar_power_w"] = calibrated_solar_power_w
        result["calibrated_solar_today_remaining_kwh"] = cal_solar_today_rem
        result["calibrated_solar_tomorrow_kwh"] = cal_solar_tomorrow
        result["solar_calibration_ratio"] = self.solar_calibrator.global_ratio
        result["solar_calibration_samples"] = self.solar_calibrator.training_samples
        result["solar_hourly_ratios"] = self.solar_calibrator.hourly_ratios

        # Execute generated service calls in strict sequence order
        commands = sorted(result.get("commands", []), key=lambda c: c.get("sequence_order", 0))
        for cmd in commands:
            await self._async_execute_command(cmd)

        return result

    async def _async_wait_for_entity_value(
        self, entity_id: str, expected_val: float, timeout_s: int = 15
    ) -> bool:
        """Wait until `entity_id` reports `expected_val` in Home Assistant states (up to timeout_s)."""
        for _ in range(timeout_s):
            curr = self._read_optional_float(entity_id)
            if curr is not None and abs(curr - expected_val) < 0.5:
                return True
            await asyncio.sleep(1.0)
        _LOGGER.debug(
            "Timeout (%ds) waiting for %s to confirm value %s; proceeding with guard fallback",
            timeout_s,
            entity_id,
            expected_val,
        )
        return False

    async def _async_execute_command(self, cmd: dict[str, Any]) -> None:
        """Safely execute a Home Assistant service call, respecting vehicle-before-borne wait rules."""
        domain = cmd.get("domain")
        service = cmd.get("service")
        entity_id = cmd.get("entity_id")
        data = dict(cmd.get("data", {}))

        if not domain or not service or not entity_id:
            return

        # If this command (e.g. Borne IRVE) requires confirmation from the vehicle first, wait for it
        wait_entity = cmd.get("wait_for_entity")
        wait_val = cmd.get("wait_for_value")
        wait_timeout = int(cmd.get("wait_timeout_s", 15))
        if wait_entity and wait_val is not None:
            await self._async_wait_for_entity_value(wait_entity, float(wait_val), wait_timeout)

        if not self.hass.services.has_service(domain, service):
            _LOGGER.debug("Service %s.%s not available for %s", domain, service, entity_id)
            return

        service_data = {"entity_id": entity_id, **data}
        try:
            await self.hass.services.async_call(
                domain,
                service,
                service_data,
                blocking=False,
            )
        except Exception as err:
            _LOGGER.warning(
                "Failed to execute EMS command %s.%s on %s: %s", domain, service, entity_id, err
            )
