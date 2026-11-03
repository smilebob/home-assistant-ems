"""Unit tests for Smart Residential EMS core logic, ML model, and controllers."""

from __future__ import annotations

from datetime import datetime, timedelta
import os
import tempfile
import unittest

from custom_components.ems.const import (
    CONF_TARIFF_MODE,
    CONF_GRID_IMPORT_PRICE_FIXED,
    CONF_GRID_EXPORT_PRICE_FIXED,
    CONF_GRID_IMPORT_PRICE_ENTITY,
    CONF_DYNAMIC_CHEAP_THRESHOLD,
    CONF_DHW_TARGET_ENTITY,
    CONF_DHW_FORCE_ENTITY,
    CONF_Z2_TARGET_ENTITY,
    CONF_TESLA_CHARGE_SWITCH,
    CONF_TESLA_CURRENT_NUMBER,
    CONF_EVSE_POWER_SWITCH,
    CONF_FELICITY_FORCE_CHARGE_ENTITY,
    CONF_FELICITY_WORK_MODE_ENTITY,
    TARIFF_MODE_FIXED,
    TARIFF_MODE_DYNAMIC,
    PRIORITY_1_COMFORT_DHW,
    PRIORITY_2_BATTERY,
    PRIORITY_3_TESLA,
    PRIORITY_4_THERMAL_BOOST,
)
from custom_components.ems.core.arbitrator import EnergyArbitrator
from custom_components.ems.core.controllers.tesla import TeslaController
from custom_components.ems.core.tariff import TariffManager
from custom_components.ems.ml.dataset_builder import build_feature_vector
from custom_components.ems.ml.model import ConsumptionMLModel


class TestSmartResidentialEMS(unittest.TestCase):
    """Test suite validating ML load prediction, Tesla current ramping, Tariff, and Arbitrator."""

    def test_ml_feature_vector_and_training(self) -> None:
        """Verify ML feature generation, training on simulated historical data, and 24h prediction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "ems_ml.pkl")
            ml = ConsumptionMLModel(storage_path=model_path)

            X_rows: list[list[float]] = []
            y_rows: list[float] = []
            base_dt = datetime(2025, 1, 1, 0, 0)
            for h in range(24 * 30):
                dt = base_dt + timedelta(hours=h)
                outdoor = 2.0 if (h // 24) % 2 == 0 else 16.0
                vec = build_feature_vector(dt, outdoor_temp=outdoor, indoor_z1_temp=19.5, indoor_z2_temp=20.5)
                load_w = 450.0 + max(0.0, (18.0 - outdoor) * 150.0) + (500.0 if 18 <= dt.hour <= 21 else 0.0)
                X_rows.append(vec)
                y_rows.append(load_w)

            metrics = ml.train(X_rows, y_rows)
            self.assertTrue(ml.is_trained)
            self.assertEqual(metrics["samples"], 24 * 30)
            self.assertLess(metrics["mae_watts"], 250.0)

            # Predict in cold weather (0°C) vs warm weather (18°C)
            cold_pred = ml.predict_power_watts(datetime(2026, 1, 15, 19, 0), outdoor_temp=0.0)
            warm_pred = ml.predict_power_watts(datetime(2026, 6, 15, 19, 0), outdoor_temp=18.0)
            self.assertGreater(cold_pred, warm_pred + 800.0)

            # Test persistence
            ml2 = ConsumptionMLModel(storage_path=model_path)
            self.assertTrue(ml2.load_from_disk())
            kwh_24h, profile = ml2.predict_next_hours_kwh(datetime(2026, 2, 1, 8, 0), hours=24, outdoor_temp=4.0)
            self.assertGreater(kwh_24h, 10.0)
            self.assertEqual(len(profile), 24)

    def test_tesla_controller_smooth_ramp_and_anti_short_cycle(self) -> None:
        """Verify Tesla Fleet current modulation never drops abruptly and respects ramp delays."""
        config = {
            CONF_TESLA_CHARGE_SWITCH: "switch.tesla_charge",
            CONF_TESLA_CURRENT_NUMBER: "number.tesla_charging_amps",
            CONF_EVSE_POWER_SWITCH: "switch.tuya_evse",
            "ev_min_current": 5,
            "ev_max_current": 16,
            "ev_voltage": 230,
            "ev_ramp_seconds": 60,
        }
        ctrl = TeslaController(config)
        t0 = datetime(2026, 5, 10, 12, 0, 0)

        # 1. Start charging with 2500W surplus (~10A available, starts at 5A minimum)
        charging, amps, cmds = ctrl.compute_charging_step(
            now=t0,
            ev_plugged=True,
            ev_soc=50.0,
            ev_target_soc=80.0,
            available_power_for_ev_watts=2500.0,
        )
        self.assertTrue(charging)
        self.assertEqual(amps, 5)
        self.assertTrue(any(c["entity_id"] == "switch.tuya_evse" and c["service"] == "turn_on" for c in cmds))
        self.assertTrue(any(c["entity_id"] == "number.tesla_charging_amps" and c["data"]["value"] == 5 for c in cmds))

        # 2. Only 20s later, surplus increases to 3500W -> should NOT step yet due to 60s ramp protection
        t1 = t0 + timedelta(seconds=20)
        charging, amps, cmds = ctrl.compute_charging_step(
            now=t1,
            ev_plugged=True,
            ev_soc=50.0,
            ev_target_soc=80.0,
            available_power_for_ev_watts=3500.0,
        )
        self.assertEqual(amps, 5)
        self.assertEqual(len(cmds), 0)

        # 3. 65s after t0, ramp up by max +2A -> goes from 5A to 7A
        t2 = t0 + timedelta(seconds=65)
        charging, amps, cmds = ctrl.compute_charging_step(
            now=t2,
            ev_plugged=True,
            ev_soc=50.0,
            ev_target_soc=80.0,
            available_power_for_ev_watts=3500.0,
        )
        self.assertEqual(amps, 7)

        # 4. Sudden cloud drops surplus to 0W 65s later -> steps down by only -1A (7A -> 6A), does NOT crash Tuya EVSE
        t3 = t2 + timedelta(seconds=65)
        charging, amps, cmds = ctrl.compute_charging_step(
            now=t3,
            ev_plugged=True,
            ev_soc=50.0,
            ev_target_soc=80.0,
            available_power_for_ev_watts=0.0,
        )
        self.assertTrue(charging)
        self.assertEqual(amps, 6)

    def test_tariff_evolution_fixed_to_dynamic(self) -> None:
        """Verify seamless switch from Fixed (16.89c€ / 4c€) to Dynamic pricing."""
        config = {
            CONF_TARIFF_MODE: TARIFF_MODE_FIXED,
            CONF_GRID_IMPORT_PRICE_FIXED: 0.1689,
            CONF_GRID_EXPORT_PRICE_FIXED: 0.0400,
            CONF_GRID_IMPORT_PRICE_ENTITY: "sensor.spot_price",
            CONF_DYNAMIC_CHEAP_THRESHOLD: 0.0600,
        }
        tm = TariffManager(config)
        imp, exp = tm.get_current_prices({"sensor.spot_price": 0.02})
        self.assertEqual(imp, 0.1689)
        self.assertEqual(exp, 0.04)
        self.assertEqual(tm.calculate_self_consumption_spread({}), 0.1289)
        self.assertFalse(tm.is_cheap_grid_opportunity({"sensor.spot_price": 0.02}))

        # Switch to Dynamic mode
        config[CONF_TARIFF_MODE] = TARIFF_MODE_DYNAMIC
        tm.update_config(config)
        imp_dyn, _ = tm.get_current_prices({"sensor.spot_price": 0.02})
        self.assertEqual(imp_dyn, 0.02)
        self.assertTrue(tm.is_cheap_grid_opportunity({"sensor.spot_price": 0.02}))

    def test_full_arbitrator_priority_cascade(self) -> None:
        """Verify the 4-priority cascade in EnergyArbitrator across Felicity, Ecodan, and Tesla."""
        config = {
            CONF_TARIFF_MODE: TARIFF_MODE_FIXED,
            CONF_GRID_IMPORT_PRICE_FIXED: 0.1689,
            CONF_GRID_EXPORT_PRICE_FIXED: 0.0400,
            CONF_DHW_TARGET_ENTITY: "number.ecodan_dhw_target",
            CONF_DHW_FORCE_ENTITY: "switch.ecodan_dhw_force",
            CONF_Z2_TARGET_ENTITY: "climate.ecodan_zone2_salon",
            CONF_TESLA_CHARGE_SWITCH: "switch.tesla_charge",
            CONF_TESLA_CURRENT_NUMBER: "number.tesla_amps",
            CONF_FELICITY_FORCE_CHARGE_ENTITY: "switch.felicity_force_charge",
            CONF_FELICITY_WORK_MODE_ENTITY: "select.felicity_work_mode",
            "battery_target_soc_ev": 80,
        }
        arb = EnergyArbitrator(config)
        noon = datetime(2026, 4, 15, 12, 30)

        # Scenario 1: Cold DHW tank (41°C) at 12:30 with 3000W solar -> Priority 1 (Comfort & DHW)
        res1 = arb.evaluate_cycle(
            now=noon,
            pv_power_w=3500.0,
            grid_power_w=-3000.0,
            house_load_w=500.0,
            battery_soc=45.0,
            battery_power_w=2500.0,
            dhw_temp=41.0,
            z1_temp=19.8,
            z2_temp=20.2,
            z2_target=20.5,
            ev_plugged=True,
            ev_soc=60.0,
            ev_target_soc=80.0,
            outdoor_temp=11.0,
            solar_today_remaining_kwh=15.0,
            solar_tomorrow_kwh=18.0,
            solar_day_after_kwh=16.0,
            predicted_24h_kwh=14.0,
            predicted_overnight_kwh=5.0,
            live_states={},
        )
        self.assertEqual(res1["active_priority"], PRIORITY_1_COMFORT_DHW)
        self.assertTrue(res1["dhw_heating_recommended"])

        # Scenario 2: DHW is hot (49°C), Battery SOC is low (35%) -> Priority 2 (Home Battery)
        res2 = arb.evaluate_cycle(
            now=noon,
            pv_power_w=4000.0,
            grid_power_w=-3500.0,
            house_load_w=500.0,
            battery_soc=35.0,
            battery_power_w=3500.0,
            dhw_temp=49.0,
            z1_temp=19.8,
            z2_temp=20.2,
            z2_target=20.5,
            ev_plugged=True,
            ev_soc=60.0,
            ev_target_soc=80.0,
            outdoor_temp=11.0,
            solar_today_remaining_kwh=6.0,
            solar_tomorrow_kwh=8.0,
            solar_day_after_kwh=10.0,
            predicted_24h_kwh=14.0,
            predicted_overnight_kwh=6.0,
            live_states={},
        )
        self.assertEqual(res2["active_priority"], PRIORITY_2_BATTERY)

        # Scenario 3: Battery reached target SOC (85%), Tesla plugged at 60% -> Priority 3 (Tesla Solar Charging)
        res3 = arb.evaluate_cycle(
            now=noon + timedelta(minutes=5),
            pv_power_w=4200.0,
            grid_power_w=-3700.0,
            house_load_w=500.0,
            battery_soc=85.0,
            battery_power_w=500.0,
            dhw_temp=49.0,
            z1_temp=19.8,
            z2_temp=20.2,
            z2_target=20.5,
            ev_plugged=True,
            ev_soc=60.0,
            ev_target_soc=80.0,
            outdoor_temp=11.0,
            solar_today_remaining_kwh=10.0,
            solar_tomorrow_kwh=15.0,
            solar_day_after_kwh=15.0,
            predicted_24h_kwh=14.0,
            predicted_overnight_kwh=5.0,
            live_states={},
        )
        self.assertEqual(res3["active_priority"], PRIORITY_3_TESLA)
        self.assertTrue(res3["ev_charging"])
        self.assertGreaterEqual(res3["ev_target_amps"], 5)

        # Scenario 4: Battery full (95%), Tesla unplugged -> Priority 4 (Thermal Storage in Zone 2 Floor + DHW 55°C Boost)
        res4 = arb.evaluate_cycle(
            now=noon + timedelta(minutes=10),
            pv_power_w=4500.0,
            grid_power_w=-4000.0,
            house_load_w=500.0,
            battery_soc=95.0,
            battery_power_w=0.0,
            dhw_temp=49.0,
            z1_temp=19.8,
            z2_temp=20.2,
            z2_target=20.5,
            ev_plugged=False,
            ev_soc=80.0,
            ev_target_soc=80.0,
            outdoor_temp=10.0,
            solar_today_remaining_kwh=8.0,
            solar_tomorrow_kwh=15.0,
            solar_day_after_kwh=15.0,
            predicted_24h_kwh=14.0,
            predicted_overnight_kwh=5.0,
            live_states={},
        )
        self.assertEqual(res4["active_priority"], PRIORITY_4_THERMAL_BOOST)
        self.assertEqual(res4["dhw_target"], 55.0)
        self.assertEqual(res4["z2_target"], 21.5)


if __name__ == "__main__":
    unittest.main()
