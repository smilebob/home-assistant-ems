"""The Smart Residential EMS (Ecodan / Felicity / Tesla) integration."""

from __future__ import annotations

import logging
import os
from typing import Any

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_RETRAIN_ML = "retrain_ml_model"

try:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.const import Platform
    from homeassistant.core import HomeAssistant, ServiceCall

    PLATFORMS: list[Platform] = [
        Platform.SENSOR,
        Platform.SWITCH,
        Platform.SELECT,
        Platform.NUMBER,
    ]
except ImportError:
    PLATFORMS = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Residential EMS from a config entry."""
    from .coordinator import EMSDataUpdateCoordinator

    hass.data.setdefault(DOMAIN, {})

    coordinator = EMSDataUpdateCoordinator(hass, entry)
    await coordinator.async_initialize_ml()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register static path for the custom Lovelace card (/ems_frontend/ems-card.js)
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    if os.path.isdir(frontend_dir) and hasattr(hass, "http") and hass.http is not None:
        try:
            from homeassistant.components.http import StaticPathConfig

            await hass.http.async_register_static_paths(
                [StaticPathConfig("/ems_frontend", frontend_dir, False)]
            )
        except Exception:
            try:
                hass.http.register_static_path("/ems_frontend", frontend_dir, False)
            except Exception as err:
                _LOGGER.debug("Could not register static path /ems_frontend: %s", err)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    async def handle_retrain_ml(call: ServiceCall) -> None:
        """Handle manual service call to retrain the ML model from Recorder history."""
        for coord in hass.data.get(DOMAIN, {}).values():
            if isinstance(coord, EMSDataUpdateCoordinator):
                await coord.async_retrain_ml_model()
                await coord.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_RETRAIN_ML):
        hass.services.async_register(DOMAIN, SERVICE_RETRAIN_ML, handle_retrain_ml)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        coordinator = hass.data[DOMAIN][entry.entry_id]
        data = entry.data or {}
        options = entry.options or {}
        coordinator.update_configuration({**data, **options})
        await coordinator.async_request_refresh()
