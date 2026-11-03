"""Switch platform for Smart Residential EMS user controls and overrides."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
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
    """Set up EMS control switches."""
    coordinator: EMSDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    switches = [
        EMSSwitch(
            coordinator,
            attr_name="auto_mode_enabled",
            key="auto_mode",
            name="EMS Autonomous Optimization",
            icon="mdi:robot-happy",
        ),
        EMSSwitch(
            coordinator,
            attr_name="force_dhw_boost",
            key="force_dhw_boost",
            name="EMS Force Ecodan DHW Boost (55°C)",
            icon="mdi:water-boiler-alert",
        ),
        EMSSwitch(
            coordinator,
            attr_name="force_tesla_charge",
            key="force_tesla_charge",
            name="EMS Force Tesla Max Charge",
            icon="mdi:ev-station",
        ),
        EMSSwitch(
            coordinator,
            attr_name="allow_thermal_overheat",
            key="allow_thermal_overheat",
            name="EMS Allow Zone 2 Underfloor Thermal Storage",
            icon="mdi:heating-coil",
        ),
    ]
    async_add_entities(switches)


class EMSSwitch(CoordinatorEntity[EMSDataUpdateCoordinator], SwitchEntity):
    """Interactive Switch controlling EMS arbitration behavior."""

    def __init__(
        self,
        coordinator: EMSDataUpdateCoordinator,
        attr_name: str,
        key: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_field = attr_name
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
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
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return bool(getattr(self.coordinator.arbitrator, self._attr_field, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        setattr(self.coordinator.arbitrator, self._attr_field, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        setattr(self.coordinator.arbitrator, self._attr_field, False)
        await self.coordinator.async_request_refresh()
