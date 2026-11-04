"""Core EMS Orchestration Engine for standalone container & Add-on."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any, Callable
import sys
import os

# Ensure repo root is in python path to import core and ml models
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from custom_components.ems.core.arbitrator import EnergyArbitrator
from custom_components.ems.ml.model import ConsumptionMLModel, SolarCalibrationModel
from custom_components.ems.ml.dataset_builder import build_feature_vector
from .config import EMSConfig
from .ha_client import HAClient
from .mqtt_client import EMSMQTTClient
from .storage import EMSStorage

_LOGGER = logging.getLogger(__name__)


class EMSEngine:
    """Manages arbitration cycles, ML inference, DuckDB persistence, and client synchronization."""

    def __init__(
        self,
        config: EMSConfig,
        ha_client: HAClient,
        storage: EMSStorage,
        mqtt_client: EMSMQTTClient | None = None,
    ) -> None:
        """Initialize engine."""
        self.config = config
        self.ha_client = ha_client
        self.storage = storage
        self.mqtt_client = mqtt_client

        # Arbitrator configuration dictionary
        arb_cfg = {
            "tariff_mode": config.tariff_mode,
            "grid_import_price_fixed": config.grid_import_price_fixed,
            "grid_export_price_fixed": config.grid_export_price_fixed,
            "grid_import_price_entity": config.grid_import_price_entity,
            "dynamic_cheap_threshold": config.dynamic_cheap_threshold,
            "battery_capacity_kwh": config.battery_capacity_kwh,
            "battery_min_soc": config.battery_min_soc,
            "battery_target_soc_ev": config.battery_target_soc_ev,
            "battery_thermal_soc_threshold": config.battery_thermal_soc_threshold,
            "felicity_work_mode_entity": config.felicity_work_mode_entity,
            "felicity_force_charge_entity": config.felicity_force_charge_entity,
            "dhw_temp_entity": config.dhw_temp_entity,
            "dhw_target_entity": config.dhw_target_entity,
            "dhw_force_entity": config.dhw_force_entity,
            "dhw_normal_temp": config.dhw_normal_temp,
            "dhw_boost_temp": config.dhw_boost_temp,
            "dhw_solar_window_start": config.dhw_solar_window_start,
            "dhw_solar_window_end": config.dhw_solar_window_end,
            "z1_temp_entity": config.z1_temp_entity,
            "z1_target_entity": config.z1_target_entity,
            "z2_temp_entity": config.z2_temp_entity,
            "z2_target_entity": config.z2_target_entity,
            "z2_max_overheat_offset": config.z2_max_overheat_offset,
            "ev_plugged_entity": config.ev_plugged_entity,
            "ev_soc_entity": config.ev_soc_entity,
            "ev_target_soc_entity": config.ev_target_soc_entity,
            "tesla_charge_switch": config.tesla_charge_switch,
            "tesla_current_number": config.tesla_current_number,
            "evse_power_switch": config.evse_power_switch,
            "evse_current_number": config.evse_current_number,
            "evse_power_entity": config.evse_power_entity,
        }
        self.arbitrator = EnergyArbitrator(arb_cfg)
        self.ml_model = ConsumptionMLModel(storage_path=os.path.join(config.data_dir, "ems_ml.pkl"))
        self.solar_calibrator = SolarCalibrationModel(
            storage_path=os.path.join(config.data_dir, "solar_cal.pkl")
        )

        self._bootstrap_models()
        self._cycle_counter = 0

        self.latest_result: dict[str, Any] = {}
        self.cumulative_savings_eur: float = 0.0
        self._ws_broadcast_subscribers: list[Callable[[dict[str, Any]], None]] = []
        self._running = False

    def _bootstrap_models(self) -> None:
        """Load persisted models or initialize and train baseline prior models."""
        loaded_ml = self.ml_model.load_from_disk()
        loaded_solar = self.solar_calibrator.load_from_disk()
        if not loaded_ml or not self.ml_model.is_trained:
            _LOGGER.info("Bootstrapping baseline Consumption ML model...")
            self.ml_model.train([], [])
            self.ml_model.save_to_disk()
        if not loaded_solar or not self.solar_calibrator.is_trained:
            _LOGGER.info("Bootstrapping baseline Solar Calibration model...")
            self.solar_calibrator.train([], [], [])
            self.solar_calibrator.save_to_disk()

    def retrain_models(self) -> dict[str, Any]:
        """Automatically reinforce and retrain both ML models with accumulated telemetry."""
        _LOGGER.info("Executing periodic automatic reinforcement of ML models...")
        historical_rows = self.storage.get_hourly_training_dataset(days=30)
        X_hist: list[list[float]] = []
        y_hist: list[float] = []
        for r in historical_rows:
            dt_str = r.get("dt")
            load = r.get("load_w")
            out_t = r.get("outdoor_temp", 12.0)
            z1_t = r.get("z1_temp", 20.0)
            z2_t = r.get("z2_temp", 20.5)
            if dt_str and load is not None and float(load) > 50.0:
                try:
                    dt = datetime.fromisoformat(dt_str)
                    vec = build_feature_vector(dt, out_t, z1_t, z2_t)
                    X_hist.append(vec)
                    y_hist.append(float(load))
                except Exception:
                    pass

        ml_res = self.ml_model.train(X_hist, y_hist)
        self.ml_model.save_to_disk()

        solar_res = self.solar_calibrator.train([], [], [])
        self.solar_calibrator.save_to_disk()

        _LOGGER.info(
            "ML models successfully reinforced: ML accuracy=%.1f%% (R²=%.3f, MAE=%.1fW) | Solar ratio=%.3f (samples=%d)",
            ml_res.get("accuracy_pct", 0.0),
            ml_res.get("r2_score", 0.0),
            ml_res.get("mae_watts", 0.0),
            solar_res.get("global_ratio", 1.0),
            solar_res.get("solar_samples", 0),
        )
        return {"ml": ml_res, "solar": solar_res}

    def subscribe_ws(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Subscribe a WebSocket client to real-time state broadcasts."""
        self._ws_broadcast_subscribers.append(callback)

    def unsubscribe_ws(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Unsubscribe a WebSocket client."""
        if callback in self._ws_broadcast_subscribers:
            self._ws_broadcast_subscribers.remove(callback)

    def _read_float(self, entity_id: str | None, default: float = 0.0) -> float:
        """Safely read float from cached HA entity state."""
        if not entity_id:
            return default
        st = self.ha_client.states.get(entity_id)
        if not st or st.get("state") in (None, "unknown", "unavailable"):
            return default
        try:
            return float(st["state"])
        except (ValueError, TypeError):
            return default

    def _read_bool(self, entity_id: str | None, default: bool = False) -> bool:
        """Safely read boolean from cached HA entity state."""
        if not entity_id:
            return default
        st = self.ha_client.states.get(entity_id)
        if not st:
            return default
        return st.get("state") in ("on", "true", "True", "1")

    async def execute_arbitration_cycle(self) -> dict[str, Any]:
        """Perform one optimization step, write to DuckDB, and notify subscribers."""
        now = datetime.now()

        # 1. Read live states
        pv_power = self._read_float(self.config.pv_power_entity, 0.0)
        grid_power = self._read_float(self.config.grid_power_entity, 0.0)
        house_load = self._read_float(self.config.house_load_entity, 400.0)
        battery_soc = self._read_float(self.config.battery_soc_entity, 50.0)
        battery_power = self._read_float(self.config.battery_power_entity, 0.0)

        dhw_temp = self._read_float(self.config.dhw_temp_entity, 50.0)
        z1_temp = self._read_float(self.config.z1_temp_entity, 19.5)
        z1_target = self._read_float(self.config.z1_target_entity, 19.0)
        z2_temp = self._read_float(self.config.z2_temp_entity, 20.0)
        z2_target = self._read_float(self.config.z2_target_entity, 20.0)
        outdoor_temp = self._read_float(self.config.outdoor_temp_entity, 10.0)

        ev_plugged = self._read_bool(self.config.ev_plugged_entity, False)
        ev_soc = self._read_float(self.config.ev_soc_entity, 50.0)
        ev_target_soc = self._read_float(self.config.ev_target_soc_entity, 80.0)
        reported_vehicle_amps = self._read_float(self.config.tesla_current_number, 0.0)

        raw_solcast_power = self._read_float(self.config.solar_forecast_power_now, pv_power)
        raw_solar_today_rem = self._read_float(self.config.solar_forecast_today_remaining, 5.0)
        raw_solar_tomorrow = self._read_float(self.config.solar_forecast_tomorrow, 15.0)
        raw_solar_day_after = self._read_float(self.config.solar_forecast_day_after, 15.0)

        # Calibrate Solcast
        cal_solar_today_rem, cal_solar_tomorrow, cal_solar_day_after = (
            self.solar_calibrator.calibrate_daily_forecasts(
                now=now,
                raw_today_rem_kwh=raw_solar_today_rem,
                raw_tomorrow_kwh=raw_solar_tomorrow,
                raw_day_after_kwh=raw_solar_day_after,
            )
        )

        pred_24h_kwh, hourly_forecast = self.ml_model.predict_next_hours_kwh(
            start_dt=now,
            hours=24,
            outdoor_temp=outdoor_temp,
            indoor_z1_temp=z1_temp,
            indoor_z2_temp=z2_temp,
        )
        pred_overnight_kwh, _ = self.ml_model.predict_next_hours_kwh(
            start_dt=now,
            hours=12,
            outdoor_temp=outdoor_temp,
            indoor_z1_temp=z1_temp,
            indoor_z2_temp=z2_temp,
        )

        # Room readings for valve recommendations
        room_readings = []
        for eid in self.config.z1_rooms_entities:
            temp = self._read_float(eid, None)
            if temp is not None:
                friendly = self.ha_client.states.get(eid, {}).get("attributes", {}).get("friendly_name", eid)
                room_readings.append({"entity_id": eid, "name": friendly, "temp": temp})

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
            live_states={},
            reported_vehicle_amps=reported_vehicle_amps,
            z1_target=z1_target,
            z1_rooms_readings=room_readings,
        )

        # Current instant prediction for storage telemetry and real-time validation
        instant_pred_load = self.ml_model.predict_power_watts(now, outdoor_temp, z1_temp, z2_temp)
        calibrated_solcast_power = round(raw_solcast_power * self.solar_calibrator.global_ratio, 1)

        # Accumulate financial savings
        step_hours = 30.0 / 3600.0
        self.cumulative_savings_eur = round(
            self.cumulative_savings_eur + result.get("instant_savings_eur_per_h", 0.0) * step_hours, 3
        )
        result["cumulative_savings_eur"] = self.cumulative_savings_eur
        result["hourly_forecast"] = hourly_forecast[:12]
        result["solar_calibration_ratio"] = self.solar_calibrator.global_ratio
        result["solcast_power_w"] = calibrated_solcast_power
        result["raw_solcast_power_w"] = raw_solcast_power
        result["predicted_load_w"] = round(instant_pred_load, 1)

        # Continuous online learning and calibration
        self.solar_calibrator.record_observation(now, raw_solcast_power, pv_power, outdoor_temp)
        self.storage.record_solar_observation(now, raw_solcast_power, pv_power, outdoor_temp)
        self.ml_model.record_observation(now, house_load, outdoor_temp, z1_temp)

        # 2. Persist to SQLite
        self.storage.record_telemetry(result)
        if result.get("active_priority") != self.latest_result.get("active_priority"):
            self.storage.record_decision(result["active_priority"], result.get("decision_reason", ""))

        self.latest_result = result

        # 3. Dispatch commands to HA in sequence order
        commands = sorted(result.get("commands", []), key=lambda c: c.get("sequence_order", 0))
        for cmd in commands:
            domain = cmd.get("domain")
            service = cmd.get("service")
            data = dict(cmd.get("data", {}))
            data["entity_id"] = cmd.get("entity_id")
            if domain and service:
                asyncio.create_task(self.ha_client.call_service(domain, service, data))

        # 4. Publish to MQTT if configured
        if self.mqtt_client:
            asyncio.create_task(self.mqtt_client.publish_state(result))

        # 5. Broadcast to WebSocket clients
        for subscriber in list(self._ws_broadcast_subscribers):
            try:
                subscriber(result)
            except Exception as err:
                _LOGGER.debug("Error broadcasting to WS client: %s", err)

        return result

    async def run_loop(self) -> None:
        """Main periodic optimization loop (every 30 seconds) with continuous reinforcement learning."""
        self._running = True
        _LOGGER.info("EMS Engine loop started (interval: 30s)")
        while self._running:
            try:
                await self.execute_arbitration_cycle()
                self._cycle_counter += 1
                # Automatic model reinforcement every 120 cycles (1 hour)
                if self._cycle_counter % 120 == 0:
                    try:
                        self.retrain_models()
                    except Exception as train_err:
                        _LOGGER.warning("Automatic ML model retraining encountered an issue: %s", train_err)
            except Exception as err:
                _LOGGER.error("Error in EMS arbitration loop: %s", err, exc_info=True)
            await asyncio.sleep(30)

    def stop(self) -> None:
        """Stop engine loop."""
        self._running = False
