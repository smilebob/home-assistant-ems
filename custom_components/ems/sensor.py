"""Sensor platform for Smart Residential EMS."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent, UnitOfEnergy, UnitOfPower, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, VERSION
from .coordinator import EMSDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EMS sensors from a config entry."""
    coordinator: EMSDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        EMSSensor(
            coordinator,
            key="active_priority",
            name="EMS Active Priority State",
            icon="mdi:state-machine",
        ),
        EMSSensor(
            coordinator,
            key="decision_reason",
            name="EMS Decision Explanation",
            icon="mdi:comment-check-outline",
        ),
        EMSSensor(
            coordinator,
            key="valve_summary",
            name="EMS Thermostatic Valve Advice",
            icon="mdi:valve",
        ),
        EMSSensor(
            coordinator,
            key="smoothed_surplus_w",
            name="EMS Smoothed Solar Surplus",
            unit=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:solar-power-variant",
        ),
        EMSSensor(
            coordinator,
            key="predicted_24h_kwh",
            name="EMS ML Predicted Load 24h",
            unit=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:brain",
        ),
        EMSSensor(
            coordinator,
            key="predicted_overnight_kwh",
            name="EMS ML Predicted Overnight Load (12h)",
            unit=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:weather-night",
        ),
        EMSSensor(
            coordinator,
            key="ml_mae_watts",
            name="EMS ML Load Forecast Error (MAE)",
            unit=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:chart-bell-curve-cumulative",
        ),
        EMSSensor(
            coordinator,
            key="ml_accuracy_pct",
            name="EMS ML Load Forecast Accuracy",
            unit=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:bullseye-arrow",
        ),
        EMSSensor(
            coordinator,
            key="calibrated_solar_today_remaining_kwh",
            name="EMS Calibrated Solar Forecast Today Remaining",
            unit=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:solar-power",
        ),
        EMSSensor(
            coordinator,
            key="calibrated_solar_tomorrow_kwh",
            name="EMS Calibrated Solar Forecast Tomorrow",
            unit=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:weather-sunny-alert",
        ),
        EMSSensor(
            coordinator,
            key="calibrated_solar_power_w",
            name="EMS Calibrated Solar Power Forecast",
            unit=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:white-balance-sunny",
        ),
        EMSSensor(
            coordinator,
            key="solar_calibration_ratio",
            name="EMS Solcast Auto-Correction Ratio",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:scale-balance",
        ),
        EMSSensor(
            coordinator,
            key="dynamic_battery_target_soc",
            name="EMS Dynamic Battery Target SOC",
            unit=PERCENTAGE,
            device_class=SensorDeviceClass.BATTERY,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:battery-charging-80",
        ),
        EMSSensor(
            coordinator,
            key="ev_target_amps",
            name="EMS Tesla Target Charging Current",
            unit=UnitOfElectricCurrent.AMPERE,
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:car-electric",
        ),
        EMSSensor(
            coordinator,
            key="cumulative_savings_eur",
            name="EMS Self-Consumption Savings",
            unit="€",
            device_class=SensorDeviceClass.MONETARY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:piggy-bank",
        ),
        EMSSensor(
            coordinator,
            key="ml_samples",
            name="EMS ML Training Samples (Recorder)",
            unit="samples",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:database-check",
        ),
    ]
    async_add_entities(sensors)


class EMSSensor(CoordinatorEntity[EMSDataUpdateCoordinator], SensorEntity):
    """Representation of an EMS Sensor."""

    def __init__(
        self,
        coordinator: EMSDataUpdateCoordinator,
        key: str,
        name: str,
        unit: str | None = None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=NAME,
            manufacturer="Smart Residential EMS",
            model="Ecodan / Felicity / Tesla Fleet Arbitrator",
            sw_version=VERSION,
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        val = self.coordinator.data.get(self._key)
        if isinstance(val, str) and len(val) > 250:
            return val[:247] + "..."
        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose complete EMS dashboard telemetry on the active_priority and specialized sensors."""
        if not self.coordinator.data:
            return {}
        d = self.coordinator.data

        if self._key == "decision_reason":
            return {
                "active_priority": d.get("active_priority"),
                "ev_sequencing_status": d.get("ev_sequencing_status"),
                "decision_log": d.get("decision_log"),
            }

        if self._key == "valve_summary":
            return {
                "recommendations": d.get("valve_recommendations"),
            }

        if self._key == "solar_calibration_ratio":
            return {
                "solar_calibration_samples": d.get("solar_calibration_samples"),
                "raw_solcast_power_w": d.get("raw_solcast_power_w"),
                "calibrated_solar_power_w": d.get("calibrated_solar_power_w"),
                "raw_solar_today_remaining_kwh": d.get("raw_solar_today_remaining_kwh"),
                "calibrated_solar_today_remaining_kwh": d.get("calibrated_solar_today_remaining_kwh"),
                "hourly_ratios": d.get("solar_hourly_ratios"),
            }

        if self._key == "active_priority":
            return {
                "decision_reason": d.get("decision_reason"),
                "decision_log": d.get("decision_log"),
                "pv_power_w": d.get("pv_power_w"),
                "grid_power_w": d.get("grid_power_w"),
                "house_load_w": d.get("house_load_w"),
                "smoothed_surplus_w": d.get("smoothed_surplus_w"),
                "battery_soc": d.get("battery_soc"),
                "dynamic_battery_target_soc": d.get("dynamic_battery_target_soc"),
                "battery_thermal_soc_threshold": d.get("battery_thermal_soc_threshold"),
                "dhw_temp": d.get("dhw_temp"),
                "dhw_target": d.get("dhw_target"),
                "z1_temp": d.get("z1_temp"),
                "z2_temp": d.get("z2_temp"),
                "z2_target": d.get("z2_target"),
                "valve_summary": d.get("valve_summary"),
                "valve_recommendations": d.get("valve_recommendations"),
                "ev_plugged": d.get("ev_plugged"),
                "ev_soc": d.get("ev_soc"),
                "ev_charging": d.get("ev_charging"),
                "ev_target_amps": d.get("ev_target_amps"),
                "ev_sequencing_status": d.get("ev_sequencing_status"),
                "raw_solar_today_remaining_kwh": d.get("raw_solar_today_remaining_kwh"),
                "raw_solar_tomorrow_kwh": d.get("raw_solar_tomorrow_kwh"),
                "raw_solcast_power_w": d.get("raw_solcast_power_w"),
                "calibrated_solar_power_w": d.get("calibrated_solar_power_w"),
                "solar_today_remaining_kwh": d.get("solar_today_remaining_kwh"),
                "solar_tomorrow_kwh": d.get("solar_tomorrow_kwh"),
                "solar_day_after_kwh": d.get("solar_day_after_kwh"),
                "solar_calibration_ratio": d.get("solar_calibration_ratio"),
                "solar_calibration_samples": d.get("solar_calibration_samples"),
                "predicted_24h_kwh": d.get("predicted_24h_kwh"),
                "import_price_eur": d.get("import_price_eur"),
                "export_price_eur": d.get("export_price_eur"),
                "ml_mae_watts": d.get("ml_mae_watts"),
                "ml_accuracy_pct": d.get("ml_accuracy_pct"),
                "ml_r2_score": d.get("ml_r2_score"),
                "hourly_forecast": d.get("hourly_forecast"),
            }
        return {}
