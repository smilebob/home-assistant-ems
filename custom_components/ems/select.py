"""Select platform for switching Tariff Mode dynamically (Fixed -> HP/HC -> Dynamic)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    NAME,
    VERSION,
    CONF_TARIFF_MODE,
    TARIFF_MODE_FIXED,
    TARIFF_MODE_TOU,
    TARIFF_MODE_DYNAMIC,
)
from .coordinator import EMSDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EMS select entities."""
    coordinator: EMSDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EMSTariffModeSelect(coordinator)])


class EMSTariffModeSelect(CoordinatorEntity[EMSDataUpdateCoordinator], SelectEntity):
    """Select entity to switch Tariff Mode on the fly."""

    _attr_options = [TARIFF_MODE_FIXED, TARIFF_MODE_TOU, TARIFF_MODE_DYNAMIC]
    _attr_icon = "mdi:cash-clock"

    def __init__(self, coordinator: EMSDataUpdateCoordinator) -> None:
        """Initialize the tariff mode selector."""
        super().__init__(coordinator)
        self._attr_name = "EMS Active Tariff Mode"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_tariff_mode_select"

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
    def current_option(self) -> str:
        """Return current selected tariff mode."""
        return self.coordinator.config.get(CONF_TARIFF_MODE, TARIFF_MODE_FIXED)

    async def async_select_option(self, option: str) -> None:
        """Update tariff mode in config and refresh coordinator."""
        new_conf = {**self.coordinator.config, CONF_TARIFF_MODE: option}
        self.coordinator.update_configuration(new_conf)
        self.hass.config_entries.async_update_entry(
            self.coordinator.entry, options=new_conf
        )
        await self.coordinator.async_request_refresh()
