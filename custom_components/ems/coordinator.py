"""DataUpdateCoordinator for Smart Residential EMS."""

from __future__ import annotations

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
    CONF_Z2_TEMP_ENTITY,
    CONF_Z2_TARGET_ENTITY,
    CONF_EV_PLUGGED_ENTITY,
    CONF_EV_SOC_ENTITY,
    CONF_EV_TARGET_SOC_ENTITY,
    CONF_EVSE_POWER_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_SOLAR_FORECAST_TODAY_REMAINING,
    CONF_SOLAR_FORECAST_TOMORROW,
    CONF_SOLAR_FORECAST_DAY_AFTER,
    CONF_ML_TRAINING_DAYS,
    CONF_ML_AUTO_TRAIN,
    DEFAULT_ML_TRAINING_DAYS,
)
from .core.arbitrator import EnergyArbitrator
from .ml.dataset_builder import RecorderDatasetBuilder
from .ml.model import ConsumptionMLModel

_LOGGER = logging.getLogger(__name__)


class EMSDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates live sensor polling, ML inference, and actuator command dispatch."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the EMS coordinator."""
        self.hass = hass
        self.entry = entry
        self.config: dict[str, Any] = {**entry.data, **entry.options}

        storage_dir = hass.config.path(".storage")
        model_path = os.path.join(storage_dir, "ems_ml_model.pkl")

        self.ml_model = ConsumptionMLModel(storage_path=model_path)
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

    async def async_initialize_ml(self) -> None:
        """Load persisted ML model or perform initial training from 2-year Recorder history."""
        loaded = await self.hass.async_add_executor_job(self.ml_model.load_from_disk)
        if not loaded:
            await self.async_retrain_ml_model()

    async def async_retrain_ml_model(self) -> dict[str, Any]:
        """Extract 2-year history from Recorder and train RandomForestRegressor."""
        days = int(self.config.get(CONF_ML_TRAINING_DAYS, DEFAULT_ML_TRAINING_DAYS))
        X, y = await self.dataset_builder.async_fetch_training_dataset(
            load_entity=self.config.get(CONF_HOUSE_LOAD_ENTITY),
            ecodan_power_entity=self.config.get(CONF_ECODAN_POWER_ENTITY),
            outdoor_temp_entity=self.config.get(CONF_OUTDOOR_TEMP_ENTITY),
            z1_temp_entity=self.config.get(CONF_Z1_TEMP_ENTITY),
            z2_temp_entity=self.config.get(CONF_Z2_TEMP_ENTITY),
            days=days,
        )
        metrics = await self.hass.async_add_executor_job(self.ml_model.train, X, y)
        self._last_ml_train_date = datetime.now().day
        return metrics

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
            # If entity is a climate or water_heater entity, read temperature attribute
            temp_attr = state_obj.attributes.get("temperature") or state_obj.attributes.get("current_temperature")
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest sensor states, run ML prediction + arbitration, and dispatch commands."""
        now = datetime.now()

        pv_power = self._read_float(self.config.get(CONF_PV_POWER_ENTITY), 0.0)
        grid_power = self._read_float(self.config.get(CONF_GRID_POWER_ENTITY), 0.0)
        house_load = self._read_float(self.config.get(CONF_HOUSE_LOAD_ENTITY), 400.0)
        battery_soc = self._read_float(self.config.get(CONF_BATTERY_SOC_ENTITY), 50.0)
        battery_power = self._read_float(self.config.get(CONF_BATTERY_POWER_ENTITY), 0.0)

        dhw_temp = self._read_optional_float(self.config.get(CONF_DHW_TEMP_ENTITY))
        z1_temp = self._read_optional_float(self.config.get(CONF_Z1_TEMP_ENTITY))
        z2_temp = self._read_optional_float(self.config.get(CONF_Z2_TEMP_ENTITY))
        z2_target = self._read_optional_float(self.config.get(CONF_Z2_TARGET_ENTITY))

        ev_plugged = self._read_bool(self.config.get(CONF_EV_PLUGGED_ENTITY), False)
        ev_soc = self._read_float(self.config.get(CONF_EV_SOC_ENTITY), 50.0)
        ev_target_soc = self._read_float(self.config.get(CONF_EV_TARGET_SOC_ENTITY), 80.0)

        outdoor_temp = self._read_float(self.config.get(CONF_OUTDOOR_TEMP_ENTITY), 12.0)
        solar_today_rem = self._read_float(self.config.get(CONF_SOLAR_FORECAST_TODAY_REMAINING), 5.0)
        solar_tomorrow = self._read_float(self.config.get(CONF_SOLAR_FORECAST_TOMORROW), 12.0)
        solar_day_after = self._read_float(self.config.get(CONF_SOLAR_FORECAST_DAY_AFTER), 12.0)

        # Record hourly observation for incremental ML learning
        if self._last_hourly_record_hour != now.hour:
            self.ml_model.record_observation(
                dt=now,
                power_watts=house_load,
                outdoor_temp=outdoor_temp,
                indoor_z1_temp=z1_temp or 20.0,
                indoor_z2_temp=z2_temp or 20.5,
            )
            self._last_hourly_record_hour = now.hour

        # Nightly automatic ML retraining at 03:00 AM
        if (
            self.config.get(CONF_ML_AUTO_TRAIN, True)
            and now.hour == 3
            and self._last_ml_train_date != now.day
        ):
            await self.async_retrain_ml_model()

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
            solar_today_remaining_kwh=solar_today_rem,
            solar_tomorrow_kwh=solar_tomorrow,
            solar_day_after_kwh=solar_day_after,
            predicted_24h_kwh=pred_24h_kwh,
            predicted_overnight_kwh=pred_overnight_kwh,
            live_states=live_states,
            ev_measured_power_w=self._read_power_watts(self.config.get(CONF_EVSE_POWER_ENTITY)),
        )

        # Accumulate financial savings over time
        step_hours = UPDATE_INTERVAL_SECONDS / 3600.0
        self.cumulative_savings_eur = round(
            self.cumulative_savings_eur + result["instant_savings_eur_per_h"] * step_hours,
            3,
        )
        result["cumulative_savings_eur"] = self.cumulative_savings_eur
        result["ml_samples"] = self.ml_model.training_samples
        result["ml_mae_watts"] = self.ml_model.mae_score
        result["hourly_forecast"] = hourly_forecast[:12]

        # Execute generated service calls if auto_mode is enabled
        for cmd in result.get("commands", []):
            await self._async_execute_command(cmd)

        return result

    async def _async_execute_command(self, cmd: dict[str, Any]) -> None:
        """Safely execute a Home Assistant service call."""
        domain = cmd.get("domain")
        service = cmd.get("service")
        entity_id = cmd.get("entity_id")
        data = dict(cmd.get("data", {}))

        if not domain or not service or not entity_id:
            return

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
            _LOGGER.warning("Failed to execute EMS command %s.%s on %s: %s", domain, service, entity_id, err)
