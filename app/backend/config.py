"""Configuration management for the Smart Residential EMS standalone container & Add-on."""

from __future__ import annotations

import json
import os
from typing import Any
from pydantic import BaseModel, Field


class EMSConfig(BaseModel):
    """Runtime configuration for EMS application."""

    # Home Assistant connectivity
    ha_url: str = Field(default="http://supervisor/core", description="Home Assistant URL or Supervisor internal URL")
    ha_token: str = Field(default="", description="Long-lived access token or SUPERVISOR_TOKEN")
    ha_verify_ssl: bool = Field(default=True, description="Verify SSL certificates for HA REST/WS")

    # Generic MQTT connectivity
    mqtt_enabled: bool = Field(default=False, description="Enable generic MQTT reporting and HA Auto-Discovery")
    mqtt_host: str = Field(default="localhost", description="MQTT Broker hostname or IP")
    mqtt_port: int = Field(default=1883, description="MQTT Broker port")
    mqtt_username: str = Field(default="", description="MQTT Username")
    mqtt_password: str = Field(default="", description="MQTT Password")
    mqtt_discovery_prefix: str = Field(default="homeassistant", description="HA MQTT Discovery prefix")
    mqtt_topic_prefix: str = Field(default="ems", description="Base topic prefix for EMS telemetry")

    # Storage and paths
    data_dir: str = Field(default="/data", description="Persistent data directory for DuckDB and ML models")
    port: int = Field(default=8080, description="Web server HTTP port")
    ingress_path: str = Field(default="", description="Ingress base path when loaded via HA sidebar")
    auth_password: str = Field(default="", description="Optional password for direct LAN access (outside HA Ingress)")

    # Equipment Entity Mappings (Home Assistant)
    pv_power_entity: str = "sensor.felicity_inverter_total_pv_power"
    grid_power_entity: str = "sensor.felicity_inverter_total_ac_input_power"
    house_load_entity: str = "sensor.felicity_inverter_loadpower_lineside"
    battery_soc_entity: str = "sensor.felicity_inverter_battery_capacity"
    battery_power_entity: str = "sensor.felicity_inverter_battery_power"
    felicity_work_mode_entity: str = "select.felicity_inverter_operating_mode"
    felicity_force_charge_entity: str = "select.felicity_inverter_economic_mode_rule_1_enable"

    dhw_temp_entity: str = "sensor.ecodan_heatpump_temp_actuelle_ecs"
    dhw_target_entity: str = "climate.ecodan_heatpump_thermostat_ecs"
    dhw_force_entity: str = "switch.ecodan_heatpump_forcer_ecs"
    z1_temp_entity: str = "sensor.ecodan_heatpump_z1_temp_pi_ce"
    z1_target_entity: str = "climate.ecodan_heatpump_zone_1_temp_ambiante"
    z1_rooms_entities: list[str] = [
        "sensor.ambiance_eleonore_temperature",
        "sensor.ambiance_gaston_temperature_2",
        "sensor.chambre_parents_temperature_4",
        "sensor.tz3000_xr3htd96_ts0201_temperature_7",
    ]
    z2_temp_entity: str = "sensor.ecodan_heatpump_z2_temp_pi_ce"
    z2_target_entity: str = "climate.ecodan_heatpump_zone_2_temp_ambiante"

    ev_plugged_entity: str = "binary_sensor.sally_charge_cable"
    ev_soc_entity: str = "sensor.sally_battery"
    ev_target_soc_entity: str = "number.sally_charge_limit"
    tesla_charge_switch: str = "switch.sally_charge"
    tesla_current_number: str = "number.sally_charging_amps"
    evse_power_switch: str = "select.garage_borne_voiture_toggle_charging"
    evse_current_number: str = "number.garage_borne_voiture_set_charge_current"
    evse_power_entity: str = "sensor.garage_borne_voiture_charging_power"

    outdoor_temp_entity: str = "sensor.ecodan_heatpump_temp_ext"
    solar_forecast_power_now: str = "sensor.solcast_pv_forecast_forecast_power"
    solar_forecast_today_remaining: str = "sensor.solcast_pv_forecast_forecast_today"
    solar_forecast_tomorrow: str = "sensor.solcast_pv_forecast_forecast_tomorrow"
    solar_forecast_day_after: str = "sensor.solcast_pv_forecast_forecast_day_3"

    # Optimization Parameters
    battery_capacity_kwh: float = 15.0
    battery_min_soc: float = 15.0
    battery_target_soc_ev: float = 80.0
    battery_thermal_soc_threshold: float = 95.0
    dhw_normal_temp: float = 50.0
    dhw_boost_temp: float = 55.0
    dhw_solar_window_start: int = 11
    dhw_solar_window_end: int = 16
    z2_max_overheat_offset: float = 1.0

    # Tariff Parameters
    tariff_mode: str = "fixed"
    grid_import_price_fixed: float = 0.1689
    grid_export_price_fixed: float = 0.0400
    grid_import_price_entity: str = "sensor.electricity_market_price"
    dynamic_cheap_threshold: float = 0.0600

    auto_mode: bool = True
    allow_thermal_overheat: bool = True
    force_dhw_boost: bool = False
    force_tesla_charge: bool = False


def load_config() -> EMSConfig:
    """Load configuration from /data/options.json (HA Add-on) or config.json or environment."""
    data: dict[str, Any] = {}

    # 1. HA Add-on configuration file
    if os.path.exists("/data/options.json"):
        try:
            with open("/data/options.json", "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception as err:
            print(f"[Config] Error reading /data/options.json: {err}")

    # 2. Local config.json for standalone Docker
    elif os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception as err:
            print(f"[Config] Error reading config.json: {err}")

    # 3. Supervisor Token Injection
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    if supervisor_token and not data.get("ha_token"):
        data["ha_token"] = supervisor_token
        data["ha_url"] = "http://supervisor/core"

    # 4. Ingress path injection from HA Supervisor header or env
    if "INGRESS_PATH" in os.environ and not data.get("ingress_path"):
        data["ingress_path"] = os.environ["INGRESS_PATH"]

    # 5. Fallback persistent dir if /data is not mounted
    if not os.path.exists("/data"):
        os.makedirs("./data", exist_ok=True)
        data.setdefault("data_dir", "./data")

    return EMSConfig(**data)
