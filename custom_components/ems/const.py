"""Constants for the Smart Residential EMS integration."""

from typing import Final

DOMAIN: Final = "ems"
NAME: Final = "Smart Residential EMS"
VERSION: Final = "1.0.0"

# Update interval
UPDATE_INTERVAL_SECONDS: Final = 30

# Configuration Steps / Tabs
STEP_USER: Final = "user"
STEP_TARIFF: Final = "tariff"
STEP_FELICITY: Final = "felicity"
STEP_ECODAN: Final = "ecodan"
STEP_EV: Final = "ev"
STEP_FORECAST: Final = "forecast"

# Setup modes
SETUP_MODE_WIZARD: Final = "wizard"
SETUP_MODE_TABS: Final = "tabs"

# Tariff Modes
TARIFF_MODE_FIXED: Final = "fixed"
TARIFF_MODE_TOU: Final = "time_of_use"
TARIFF_MODE_DYNAMIC: Final = "dynamic"

# Tariff Config Keys
CONF_TARIFF_MODE: Final = "tariff_mode"
CONF_GRID_IMPORT_PRICE_FIXED: Final = "grid_import_price_fixed"
CONF_GRID_EXPORT_PRICE_FIXED: Final = "grid_export_price_fixed"
CONF_GRID_IMPORT_PRICE_ENTITY: Final = "grid_import_price_entity"
CONF_GRID_EXPORT_PRICE_ENTITY: Final = "grid_export_price_entity"
CONF_DYNAMIC_CHEAP_THRESHOLD: Final = "dynamic_cheap_threshold"

# Felicity Solar & Battery Config Keys (ha_felicity)
CONF_PV_POWER_ENTITY: Final = "pv_power_entity"
CONF_GRID_POWER_ENTITY: Final = "grid_power_entity"
CONF_HOUSE_LOAD_ENTITY: Final = "house_load_entity"
CONF_BATTERY_SOC_ENTITY: Final = "battery_soc_entity"
CONF_BATTERY_POWER_ENTITY: Final = "battery_power_entity"
CONF_BATTERY_CAPACITY_KWH: Final = "battery_capacity_kwh"
CONF_FELICITY_WORK_MODE_ENTITY: Final = "felicity_work_mode_entity"
CONF_FELICITY_FORCE_CHARGE_ENTITY: Final = "felicity_force_charge_entity"
CONF_BATTERY_MIN_SOC: Final = "battery_min_soc"
CONF_BATTERY_TARGET_SOC_EV: Final = "battery_target_soc_ev"

# Mitsubishi Ecodan Config Keys (esphome-ecodan-hp)
CONF_ECODAN_POWER_ENTITY: Final = "ecodan_power_entity"
CONF_DHW_TEMP_ENTITY: Final = "dhw_temp_entity"
CONF_DHW_TARGET_ENTITY: Final = "dhw_target_entity"
CONF_DHW_FORCE_ENTITY: Final = "dhw_force_entity"
CONF_DHW_NORMAL_TEMP: Final = "dhw_normal_temp"
CONF_DHW_BOOST_TEMP: Final = "dhw_boost_temp"
CONF_DHW_SOLAR_WINDOW_START: Final = "dhw_solar_window_start"
CONF_DHW_SOLAR_WINDOW_END: Final = "dhw_solar_window_end"

CONF_Z1_TEMP_ENTITY: Final = "z1_temp_entity"  # Eleonore (North)
CONF_Z1_TARGET_ENTITY: Final = "z1_target_entity"
CONF_Z1_ROOMS_ENTITIES: Final = "z1_rooms_entities"  # Gaston, Parents, SdB

CONF_Z2_TEMP_ENTITY: Final = "z2_temp_entity"  # Salon (Floor heating)
CONF_Z2_TARGET_ENTITY: Final = "z2_target_entity"
CONF_Z2_MAX_OVERHEAT_OFFSET: Final = "z2_max_overheat_offset"

# EV & Tesla Fleet Config Keys
CONF_EV_PLUGGED_ENTITY: Final = "ev_plugged_entity"
CONF_EV_SOC_ENTITY: Final = "ev_soc_entity"
CONF_EV_TARGET_SOC_ENTITY: Final = "ev_target_soc_entity"
CONF_TESLA_CHARGE_SWITCH: Final = "tesla_charge_switch"
CONF_TESLA_CURRENT_NUMBER: Final = "tesla_current_number"
CONF_EVSE_POWER_SWITCH: Final = "evse_power_switch"  # Local Tuya switch or select (toggle_charging)
CONF_EVSE_CURRENT_NUMBER: Final = "evse_current_number"  # Local Tuya EVSE current setpoint number
CONF_EVSE_POWER_ENTITY: Final = "evse_power_entity"  # Local Tuya EVSE measured power (W or kW)
CONF_EV_MIN_CURRENT: Final = "ev_min_current"
CONF_EV_MAX_CURRENT: Final = "ev_max_current"
CONF_EV_VOLTAGE: Final = "ev_voltage"
CONF_EV_RAMP_SECONDS: Final = "ev_ramp_seconds"

# Weather, Solcast & ML Config Keys
CONF_OUTDOOR_TEMP_ENTITY: Final = "outdoor_temp_entity"
CONF_SOLAR_FORECAST_TODAY_REMAINING: Final = "solar_forecast_today_remaining"
CONF_SOLAR_FORECAST_TOMORROW: Final = "solar_forecast_tomorrow"
CONF_SOLAR_FORECAST_DAY_AFTER: Final = "solar_forecast_day_after"
CONF_ML_TRAINING_DAYS: Final = "ml_training_days"
CONF_ML_AUTO_TRAIN: Final = "ml_auto_train"

# Default Values (calibrated to user setup)
DEFAULT_IMPORT_PRICE: Final = 0.1689
DEFAULT_EXPORT_PRICE: Final = 0.0400
DEFAULT_DYNAMIC_CHEAP_THRESHOLD: Final = 0.0800
DEFAULT_BATTERY_CAPACITY_KWH: Final = 15.0
DEFAULT_BATTERY_MIN_SOC: Final = 15
DEFAULT_BATTERY_TARGET_SOC_EV: Final = 80
DEFAULT_DHW_NORMAL_TEMP: Final = 48.0
DEFAULT_DHW_BOOST_TEMP: Final = 55.0
DEFAULT_DHW_WINDOW_START: Final = 11
DEFAULT_DHW_WINDOW_END: Final = 15
DEFAULT_Z2_MAX_OFFSET: Final = 1.0
DEFAULT_EV_MIN_CURRENT: Final = 5
DEFAULT_EV_MAX_CURRENT: Final = 16
DEFAULT_EV_VOLTAGE: Final = 230
DEFAULT_EV_RAMP_SECONDS: Final = 60
DEFAULT_ML_TRAINING_DAYS: Final = 730  # 2 years

# Priority States
PRIORITY_IDLE: Final = "idle"
PRIORITY_1_COMFORT_DHW: Final = "priority_1_comfort_dhw"
PRIORITY_2_BATTERY: Final = "priority_2_battery"
PRIORITY_3_TESLA: Final = "priority_3_tesla"
PRIORITY_4_THERMAL_BOOST: Final = "priority_4_thermal_boost"
PRIORITY_DYNAMIC_GRID_CHARGE: Final = "priority_dynamic_grid_charge"
