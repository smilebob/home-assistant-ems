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
    CONF_EVSE_CURRENT_NUMBER,
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
from custom_components.ems.core.controllers.ecodan import EcodanController
from custom_components.ems.core.controllers.tesla import TeslaController
from custom_components.ems.core.tariff import TariffManager
from custom_components.ems.ml.dataset_builder import build_feature_vector, build_solar_feature_vector
from custom_components.ems.ml.model import ConsumptionMLModel, SolarCalibrationModel


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

    def test_tuya_local_evse_select_and_current_control(self) -> None:
        """Verify that Tuya Local select entity (Start charging/Stop charging) and EVSE current setpoint work."""
        config = {
            CONF_TESLA_CHARGE_SWITCH: "switch.sally_charge",
            CONF_TESLA_CURRENT_NUMBER: "number.sally_courant_de_recharge",
            CONF_EVSE_POWER_SWITCH: "select.garage_borne_voiture_toggle_charging",
            CONF_EVSE_CURRENT_NUMBER: "number.garage_borne_voiture_set_charge_current",
            "ev_min_current": 6,
            "ev_max_current": 16,
            "ev_voltage": 230,
            "ev_ramp_seconds": 60,
        }
        ctrl = TeslaController(config)
        t0 = datetime(2026, 5, 10, 12, 0, 0)

        # 1. Start charging -> should set vehicle current first (sequence_order 1), then EVSE after vehicle ack
        charging, amps, cmds = ctrl.compute_charging_step(
            now=t0,
            ev_plugged=True,
            ev_soc=45.0,
            ev_target_soc=80.0,
            available_power_for_ev_watts=2300.0,
            reported_vehicle_amps=6.0,
        )
        self.assertTrue(charging)
        self.assertEqual(amps, 6)
        # Verify strict sequence_order: vehicle number (1) < EVSE number (3) < EVSE start (4)
        veh_cmd = next(c for c in cmds if c["entity_id"] == "number.sally_courant_de_recharge")
        evse_num_cmd = next(c for c in cmds if c["entity_id"] == "number.garage_borne_voiture_set_charge_current")
        evse_start_cmd = next(c for c in cmds if c["entity_id"] == "select.garage_borne_voiture_toggle_charging")
        self.assertLess(veh_cmd["sequence_order"], evse_num_cmd["sequence_order"])
        self.assertEqual(evse_num_cmd["wait_for_entity"], "number.sally_courant_de_recharge")
        self.assertEqual(evse_num_cmd["wait_for_value"], 6)
        self.assertEqual(evse_start_cmd["data"]["option"], "Start charging")
        self.assertEqual(evse_num_cmd["data"]["value"], 6.0)
        self.assertTrue(any(c["entity_id"] == "switch.sally_charge" and c["service"] == "turn_on" for c in cmds))

        # 2. Stop charging -> should send "Stop charging" to Tuya EVSE select and turn_off to vehicle
        ctrl.charge_started_at = t0 - timedelta(minutes=5)  # past anti-short-cycle
        t_stop = t0 + timedelta(minutes=5)
        charging, amps, stop_cmds = ctrl.compute_charging_step(
            now=t_stop,
            ev_plugged=True,
            ev_soc=80.0,  # reached target SOC
            ev_target_soc=80.0,
            available_power_for_ev_watts=0.0,
        )
        self.assertFalse(charging)
        self.assertEqual(amps, 0)
        self.assertTrue(any(
            c["entity_id"] == "select.garage_borne_voiture_toggle_charging"
            and c["domain"] == "select"
            and c["service"] == "select_option"
            and c["data"]["option"] == "Stop charging"
            for c in stop_cmds
        ))
        self.assertTrue(any(
            c["entity_id"] == "switch.sally_charge"
            and c["service"] == "turn_off"
            for c in stop_cmds
        ))

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
        self.assertIn("Priorité 4", res4["decision_reason"])

    def test_solar_calibration_model_and_valves(self) -> None:
        """Verify intermediate SolarCalibrationModel learns shading/derating vs Solcast and Ecodan evaluates valves."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cal_path = os.path.join(tmpdir, "solar_cal.pkl")
            cal = SolarCalibrationModel(storage_path=cal_path)

            X_rows: list[list[float]] = []
            y_rows: list[float] = []
            hour_pairs: list[tuple[int, float, float]] = []
            base_dt = datetime(2025, 6, 1, 0, 0)
            for d in range(30):
                for h in range(7, 20):
                    dt = base_dt + timedelta(days=d, hours=h)
                    solcast_w = 4000.0 if 11 <= h <= 15 else 1500.0
                    # Simulate morning tree shading at 8h-9h (50% actual) and 90% midday efficiency
                    true_ratio = 0.50 if h in (8, 9) else 0.90
                    actual_w = solcast_w * true_ratio
                    X_rows.append(build_solar_feature_vector(dt, solcast_watts=solcast_w, outdoor_temp=22.0))
                    y_rows.append(actual_w)
                    hour_pairs.append((h, solcast_w, actual_w))

            metrics = cal.train(X_rows, y_rows, hour_pairs)
            self.assertTrue(cal.is_trained)
            self.assertGreater(metrics["solar_samples"], 100)

            # Morning shaded hour should be calibrated down significantly compared to raw Solcast
            cal_morning_w = cal.calibrate_power_watts(
                datetime(2026, 6, 10, 8, 30), solcast_watts=1500.0, outdoor_temp=20.0
            )
            self.assertLess(cal_morning_w, 1100.0)
            self.assertLess(cal.hourly_ratios[8], 0.75)

            # Daily kWh forecasts should also be calibrated
            rem_kwh, tom_kwh, day3_kwh = cal.calibrate_daily_forecasts(
                now=datetime(2026, 6, 10, 8, 0),
                raw_today_rem_kwh=20.0,
                raw_tomorrow_kwh=25.0,
                raw_day_after_kwh=25.0,
            )
            self.assertLess(tom_kwh, 25.0)
            self.assertGreater(tom_kwh, 15.0)

        # Verify thermostatic valve balancing recommendations
        ecodan = EcodanController({})
        summary, valves = ecodan.evaluate_valve_recommendations(
            z1_ref_temp=19.5,
            z1_target_temp=19.5,
            room_readings=[
                {"entity_id": "sensor.chambre_gaston", "name": "Chambre Gaston", "temp": 21.0},
                {"entity_id": "sensor.chambre_parents", "name": "Chambre Parents", "temp": 18.2},
                {"entity_id": "sensor.sdb", "name": "Salle de Bain", "temp": 19.6},
            ],
        )
        self.assertIn("2 vanne(s)", summary)
        self.assertEqual(len(valves), 3)
        self.assertEqual(valves[0]["direction"], "close")
        self.assertIn("Fermer", valves[0]["action"])
        self.assertEqual(valves[1]["direction"], "open")
        self.assertIn("Ouvrir", valves[1]["action"])
        self.assertEqual(valves[2]["direction"], "ok")

        # Verify strict DHW solar window lock (no morning trigger at 08:20 even at 36°C)
        ecodan_dhw = EcodanController(
            {
                CONF_DHW_TARGET_ENTITY: "climate.ecodan_heatpump_thermostat_ecs",
                CONF_DHW_FORCE_ENTITY: "switch.ecodan_heatpump_forcer_ecs",
                "dhw_normal_temp": 50.0,
                "dhw_boost_temp": 55.0,
                "dhw_solar_window_start": 11,
                "dhw_solar_window_end": 16,
            }
        )
        morning_8h20 = datetime(2026, 11, 5, 8, 20)
        heat_morning, target_morning, cmds_morning = ecodan_dhw.evaluate_dhw_need(
            now=morning_8h20,
            dhw_temp=36.0,
            net_surplus_watts=1000.0,
        )
        self.assertFalse(heat_morning)
        self.assertEqual(target_morning, 40.0)
        self.assertFalse(any(c["entity_id"] == "switch.ecodan_heatpump_forcer_ecs" for c in cmds_morning))

        solar_11h30 = datetime(2026, 11, 5, 11, 30)
        heat_noon, target_noon, cmds_noon = ecodan_dhw.evaluate_dhw_need(
            now=solar_11h30,
            dhw_temp=36.0,
            net_surplus_watts=1000.0,
        )
        self.assertTrue(heat_noon)
        self.assertEqual(target_noon, 50.0)
        self.assertTrue(any(c["entity_id"] == "switch.ecodan_heatpump_forcer_ecs" for c in cmds_noon))

    def test_sqlite_storage_telemetry_and_decisions(self) -> None:
        """Verify SQLite storage records telemetry, decisions, and produces correct JSON-serializable output."""
        from app.backend.storage import EMSStorage
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EMSStorage(tmpdir)
            storage.record_telemetry({
                "pv_power_w": 4200.0,
                "grid_power_w": -2500.0,
                "house_load_w": 1700.0,
                "battery_soc": 85.0,
                "battery_power_w": 2500.0,
                "active_priority": "battery_first",
                "instant_savings_eur_h": 1.05,
                "solcast_power_w": 4050.0,
                "predicted_load_w": 1650.0,
            })
            storage.record_decision("battery_first", "Surplus solaire dirigé vers la batterie Felicity")

            telemetry = storage.get_recent_telemetry(hours=1)
            self.assertEqual(len(telemetry), 1)
            self.assertEqual(telemetry[0]["pv_power_w"], 4200.0)
            self.assertEqual(telemetry[0]["solcast_power_w"], 4050.0)
            self.assertEqual(telemetry[0]["predicted_load_w"], 1650.0)
            self.assertEqual(telemetry[0]["active_priority"], "battery_first")

            daily = storage.get_daily_solar_comparison(days=7)
            self.assertEqual(len(daily), 1)
            self.assertIn("actual_kwh", daily[0])
            self.assertIn("predicted_kwh", daily[0])

            decisions = storage.get_recent_decisions(limit=10)
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["priority"], "battery_first")
            self.assertEqual(decisions[0]["reason"], "Surplus solaire dirigé vers la batterie Felicity")


if __name__ == "__main__":
    unittest.main()
