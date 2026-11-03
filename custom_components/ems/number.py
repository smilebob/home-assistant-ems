"""Number platform for runtime tuning of EMS thresholds."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    NAME,
    VERSION,
    CONF_BATTERY_MIN_SOC,
    CONF_BATTERY_TARGET_SOC_EV,
    CONF_Z2_MAX_OVERHEAT_OFFSET,
    DEFAULT_BATTERY_MIN_SOC,
    DEFAULT_BATTERY_TARGET_SOC_EV,
    DEFAULT_Z2_MAX_OFFSET,
)
from .coordinator import EMSDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EMS number entities."""
    coordinator: EMSDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    numbers = [
        EMSConfigNumber(
            coordinator,
            conf_key=CONF_BATTERY_MIN_SOC,
            name="EMS Battery Reserve Minimum SOC",
            min_val=5.0,
            max_val=50.0,
            step=1.0,
            unit=PERCENTAGE,
            default_val=DEFAULT_BATTERY_MIN_SOC,
            icon="mdi:battery-lock",
        ),
        EMSConfigNumber(
            coordinator,
            conf_key=CONF_BATTERY_TARGET_SOC_EV,
            name="EMS Battery Target SOC Before Tesla",
            min_val=20.0,
            max_val=100.0,
            step=5.0,
            unit=PERCENTAGE,
            default_val=DEFAULT_BATTERY_TARGET_SOC_EV,
            icon="mdi:battery-arrow-up",
        ),
        EMSConfigNumber(
            coordinator,
            conf_key=CONF_Z2_MAX_OVERHEAT_OFFSET,
            name="EMS Zone 2 Floor Thermal Storage Offset",
            min_val=0.0,
            max_val=3.0,
            step=0.5,
            unit=UnitOfTemperature.CELSIUS,
            default_val=DEFAULT_Z2_MAX_OFFSET,
            icon="mdi:thermometer-plus",
        ),
    ]
    async_add_entities(numbers)


class EMSConfigNumber(CoordinatorEntity[EMSDataUpdateCoordinator], NumberEntity):
    """Number entity allowing live threshold tuning from the dashboard."""

    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: EMSDataUpdateCoordinator,
        conf_key: str,
        name: str,
        min_val: float,
        max_val: float,
        step: float,
        unit: str,
        default_val: float,
        icon: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._conf_key = conf_key
        self._default_val = default_val
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{conf_key}"
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
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
    def native_value(self) -> float:
        """Return the current threshold value."""
        return float(self.coordinator.config.get(self._conf_key, self._default_val))

    async def async_set_native_value(self, value: float) -> None:
        """Update threshold value."""
        new_conf = {**self.coordinator.config, self._conf_key: value}
        self.coordinator.update_configuration(new_conf)
        self.hass.config_entries.async_update_entry(
            self.coordinator.entry, options=new_conf
        )
        await self.coordinator.async_request_refresh()
