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
            icon="mdi:Dynamic-feed",
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
        return self.coordinator.data.get(self._key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose complete EMS dashboard telemetry on the active_priority sensor."""
        if self._key == "active_priority" and self.coordinator.data:
            return {
                "pv_power_w": self.coordinator.data.get("pv_power_w"),
                "grid_power_w": self.coordinator.data.get("grid_power_w"),
                "house_load_w": self.coordinator.data.get("house_load_w"),
                "smoothed_surplus_w": self.coordinator.data.get("smoothed_surplus_w"),
                "battery_soc": self.coordinator.data.get("battery_soc"),
                "dynamic_battery_target_soc": self.coordinator.data.get("dynamic_battery_target_soc"),
                "dhw_temp": self.coordinator.data.get("dhw_temp"),
                "dhw_target": self.coordinator.data.get("dhw_target"),
                "z1_temp": self.coordinator.data.get("z1_temp"),
                "z2_temp": self.coordinator.data.get("z2_temp"),
                "z2_target": self.coordinator.data.get("z2_target"),
                "ev_plugged": self.coordinator.data.get("ev_plugged"),
                "ev_soc": self.coordinator.data.get("ev_soc"),
                "ev_charging": self.coordinator.data.get("ev_charging"),
                "ev_target_amps": self.coordinator.data.get("ev_target_amps"),
                "solar_today_remaining_kwh": self.coordinator.data.get("solar_today_remaining_kwh"),
                "solar_tomorrow_kwh": self.coordinator.data.get("solar_tomorrow_kwh"),
                "solar_day_after_kwh": self.coordinator.data.get("solar_day_after_kwh"),
                "predicted_24h_kwh": self.coordinator.data.get("predicted_24h_kwh"),
                "import_price_eur": self.coordinator.data.get("import_price_eur"),
                "export_price_eur": self.coordinator.data.get("export_price_eur"),
                "ml_mae_watts": self.coordinator.data.get("ml_mae_watts"),
                "hourly_forecast": self.coordinator.data.get("hourly_forecast"),
            }
        return {}
