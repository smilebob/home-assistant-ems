"""Config flow and Options flow for Smart Residential EMS."""

from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    SETUP_MODE_WIZARD,
    SETUP_MODE_TABS,
    TARIFF_MODE_FIXED,
    TARIFF_MODE_TOU,
    TARIFF_MODE_DYNAMIC,
    CONF_TARIFF_MODE,
    CONF_GRID_IMPORT_PRICE_FIXED,
    CONF_GRID_EXPORT_PRICE_FIXED,
    CONF_GRID_IMPORT_PRICE_ENTITY,
    CONF_GRID_EXPORT_PRICE_ENTITY,
    CONF_DYNAMIC_CHEAP_THRESHOLD,
    CONF_PV_POWER_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_HOUSE_LOAD_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_FELICITY_WORK_MODE_ENTITY,
    CONF_FELICITY_FORCE_CHARGE_ENTITY,
    CONF_BATTERY_MIN_SOC,
    CONF_BATTERY_TARGET_SOC_EV,
    CONF_ECODAN_POWER_ENTITY,
    CONF_DHW_TEMP_ENTITY,
    CONF_DHW_TARGET_ENTITY,
    CONF_DHW_FORCE_ENTITY,
    CONF_DHW_NORMAL_TEMP,
    CONF_DHW_BOOST_TEMP,
    CONF_DHW_SOLAR_WINDOW_START,
    CONF_DHW_SOLAR_WINDOW_END,
    CONF_Z1_TEMP_ENTITY,
    CONF_Z1_TARGET_ENTITY,
    CONF_Z1_ROOMS_ENTITIES,
    CONF_Z2_TEMP_ENTITY,
    CONF_Z2_TARGET_ENTITY,
    CONF_Z2_MAX_OVERHEAT_OFFSET,
    CONF_EV_PLUGGED_ENTITY,
    CONF_EV_SOC_ENTITY,
    CONF_EV_TARGET_SOC_ENTITY,
    CONF_TESLA_CHARGE_SWITCH,
    CONF_TESLA_CURRENT_NUMBER,
    CONF_EVSE_POWER_SWITCH,
    CONF_EVSE_CURRENT_NUMBER,
    CONF_EVSE_POWER_ENTITY,
    CONF_EV_MIN_CURRENT,
    CONF_EV_MAX_CURRENT,
    CONF_EV_VOLTAGE,
    CONF_EV_RAMP_SECONDS,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_SOLAR_FORECAST_TODAY_REMAINING,
    CONF_SOLAR_FORECAST_TOMORROW,
    CONF_SOLAR_FORECAST_DAY_AFTER,
    CONF_ML_TRAINING_DAYS,
    CONF_ML_AUTO_TRAIN,
    DEFAULT_IMPORT_PRICE,
    DEFAULT_EXPORT_PRICE,
    DEFAULT_DYNAMIC_CHEAP_THRESHOLD,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_BATTERY_MIN_SOC,
    DEFAULT_BATTERY_TARGET_SOC_EV,
    DEFAULT_DHW_NORMAL_TEMP,
    DEFAULT_DHW_BOOST_TEMP,
    DEFAULT_DHW_WINDOW_START,
    DEFAULT_DHW_WINDOW_END,
    DEFAULT_Z2_MAX_OFFSET,
    DEFAULT_EV_MIN_CURRENT,
    DEFAULT_EV_MAX_CURRENT,
    DEFAULT_EV_VOLTAGE,
    DEFAULT_EV_RAMP_SECONDS,
    DEFAULT_ML_TRAINING_DAYS,
)


def _opt_marker(key: str, defaults: dict[str, Any]) -> vol.Optional:
    """Safely create a vol.Optional with suggested_value only if non-None."""
    val = defaults.get(key)
    if val is not None and val != "":
        return vol.Optional(key, description={"suggested_value": val})
    return vol.Optional(key)


def get_tariff_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Return schema for Tariff configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_TARIFF_MODE,
                default=defaults.get(CONF_TARIFF_MODE, TARIFF_MODE_FIXED),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[TARIFF_MODE_FIXED, TARIFF_MODE_TOU, TARIFF_MODE_DYNAMIC],
                    translation_key="tariff_mode",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_GRID_IMPORT_PRICE_FIXED,
                default=float(defaults.get(CONF_GRID_IMPORT_PRICE_FIXED, DEFAULT_IMPORT_PRICE)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=2.0, step=0.001, unit_of_measurement="cEUR/kWh"
                )
            ),
            vol.Required(
                CONF_GRID_EXPORT_PRICE_FIXED,
                default=float(defaults.get(CONF_GRID_EXPORT_PRICE_FIXED, DEFAULT_EXPORT_PRICE)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=2.0, step=0.001, unit_of_measurement="cEUR/kWh"
                )
            ),
            _opt_marker(CONF_GRID_IMPORT_PRICE_ENTITY, defaults): selector.EntitySelector(),
            _opt_marker(CONF_GRID_EXPORT_PRICE_ENTITY, defaults): selector.EntitySelector(),
            vol.Optional(
                CONF_DYNAMIC_CHEAP_THRESHOLD,
                default=float(defaults.get(CONF_DYNAMIC_CHEAP_THRESHOLD, DEFAULT_DYNAMIC_CHEAP_THRESHOLD)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-1.0, max=1.0, step=0.005, unit_of_measurement="cEUR/kWh"
                )
            ),
        }
    )


def get_felicity_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Return schema for Felicity Inverter & Battery (ha_felicity)."""
    return vol.Schema(
        {
            _opt_marker(CONF_PV_POWER_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _opt_marker(CONF_GRID_POWER_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _opt_marker(CONF_HOUSE_LOAD_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _opt_marker(CONF_BATTERY_SOC_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _opt_marker(CONF_BATTERY_POWER_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _opt_marker(CONF_FELICITY_WORK_MODE_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["select", "input_select"])
            ),
            _opt_marker(CONF_FELICITY_FORCE_CHARGE_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
            ),
            vol.Required(
                CONF_BATTERY_CAPACITY_KWH,
                default=float(defaults.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1.0, max=100.0, step=0.5, unit_of_measurement="kWh")
            ),
            vol.Required(
                CONF_BATTERY_MIN_SOC,
                default=int(defaults.get(CONF_BATTERY_MIN_SOC, DEFAULT_BATTERY_MIN_SOC)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=5, max=50, step=1, unit_of_measurement="%")
            ),
            vol.Required(
                CONF_BATTERY_TARGET_SOC_EV,
                default=int(defaults.get(CONF_BATTERY_TARGET_SOC_EV, DEFAULT_BATTERY_TARGET_SOC_EV)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=20, max=100, step=5, unit_of_measurement="%")
            ),
        }
    )


def get_ecodan_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Return schema for Mitsubishi Ecodan Heat Pump (esphome-ecodan-hp)."""
    return vol.Schema(
        {
            _opt_marker(CONF_ECODAN_POWER_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _opt_marker(CONF_DHW_TEMP_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _opt_marker(CONF_DHW_TARGET_ENTITY, defaults): selector.EntitySelector(),
            _opt_marker(CONF_DHW_FORCE_ENTITY, defaults): selector.EntitySelector(),
            vol.Required(
                CONF_DHW_NORMAL_TEMP,
                default=float(defaults.get(CONF_DHW_NORMAL_TEMP, DEFAULT_DHW_NORMAL_TEMP)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=40.0, max=60.0, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(
                CONF_DHW_BOOST_TEMP,
                default=float(defaults.get(CONF_DHW_BOOST_TEMP, DEFAULT_DHW_BOOST_TEMP)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=45.0, max=65.0, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(
                CONF_DHW_SOLAR_WINDOW_START,
                default=int(defaults.get(CONF_DHW_SOLAR_WINDOW_START, DEFAULT_DHW_WINDOW_START)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=23, step=1, unit_of_measurement="h")
            ),
            vol.Required(
                CONF_DHW_SOLAR_WINDOW_END,
                default=int(defaults.get(CONF_DHW_SOLAR_WINDOW_END, DEFAULT_DHW_WINDOW_END)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=23, step=1, unit_of_measurement="h")
            ),
            _opt_marker(CONF_Z1_TEMP_ENTITY, defaults): selector.EntitySelector(),
            _opt_marker(CONF_Z1_TARGET_ENTITY, defaults): selector.EntitySelector(),
            vol.Optional(
                CONF_Z1_ROOMS_ENTITIES,
                default=defaults.get(CONF_Z1_ROOMS_ENTITIES, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            _opt_marker(CONF_Z2_TEMP_ENTITY, defaults): selector.EntitySelector(),
            _opt_marker(CONF_Z2_TARGET_ENTITY, defaults): selector.EntitySelector(),
            vol.Required(
                CONF_Z2_MAX_OVERHEAT_OFFSET,
                default=float(defaults.get(CONF_Z2_MAX_OVERHEAT_OFFSET, DEFAULT_Z2_MAX_OFFSET)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.0, max=3.0, step=0.5, unit_of_measurement="°C")
            ),
        }
    )


def get_ev_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Return schema for Tesla Fleet & Local Tuya EVSE."""
    return vol.Schema(
        {
            _opt_marker(CONF_EV_PLUGGED_ENTITY, defaults): selector.EntitySelector(),
            _opt_marker(CONF_EV_SOC_ENTITY, defaults): selector.EntitySelector(),
            _opt_marker(CONF_EV_TARGET_SOC_ENTITY, defaults): selector.EntitySelector(),
            _opt_marker(CONF_TESLA_CHARGE_SWITCH, defaults): selector.EntitySelector(),
            _opt_marker(CONF_TESLA_CURRENT_NUMBER, defaults): selector.EntitySelector(),
            _opt_marker(CONF_EVSE_POWER_SWITCH, defaults): selector.EntitySelector(),
            _opt_marker(CONF_EVSE_CURRENT_NUMBER, defaults): selector.EntitySelector(),
            _opt_marker(CONF_EVSE_POWER_ENTITY, defaults): selector.EntitySelector(),
            vol.Required(
                CONF_EV_MIN_CURRENT,
                default=int(defaults.get(CONF_EV_MIN_CURRENT, DEFAULT_EV_MIN_CURRENT)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=5, max=16, step=1, unit_of_measurement="A")
            ),
            vol.Required(
                CONF_EV_MAX_CURRENT,
                default=int(defaults.get(CONF_EV_MAX_CURRENT, DEFAULT_EV_MAX_CURRENT)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=6, max=32, step=1, unit_of_measurement="A")
            ),
            vol.Required(
                CONF_EV_VOLTAGE,
                default=int(defaults.get(CONF_EV_VOLTAGE, DEFAULT_EV_VOLTAGE)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=210, max=250, step=1, unit_of_measurement="V")
            ),
            vol.Required(
                CONF_EV_RAMP_SECONDS,
                default=int(defaults.get(CONF_EV_RAMP_SECONDS, DEFAULT_EV_RAMP_SECONDS)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=15, max=300, step=15, unit_of_measurement="s")
            ),
        }
    )


def get_forecast_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Return schema for Solcast / Open-Meteo & Machine Learning."""
    return vol.Schema(
        {
            _opt_marker(CONF_OUTDOOR_TEMP_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "weather"])
            ),
            _opt_marker(CONF_SOLAR_FORECAST_TODAY_REMAINING, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _opt_marker(CONF_SOLAR_FORECAST_TOMORROW, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _opt_marker(CONF_SOLAR_FORECAST_DAY_AFTER, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_ML_TRAINING_DAYS,
                default=int(defaults.get(CONF_ML_TRAINING_DAYS, DEFAULT_ML_TRAINING_DAYS)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=30, max=1095, step=30, unit_of_measurement="jours")
            ),
            vol.Required(
                CONF_ML_AUTO_TRAIN,
                default=bool(defaults.get(CONF_ML_AUTO_TRAIN, True)),
            ): selector.BooleanSelector(),
        }
    )


class EMSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Residential EMS."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._setup_mode: str = SETUP_MODE_WIZARD

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Initial step: choose between Guided Wizard or Thematic Tabs."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            self._setup_mode = user_input.get("setup_mode", SETUP_MODE_WIZARD)
            if self._setup_mode == SETUP_MODE_WIZARD:
                return await self.async_step_tariff()
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("setup_mode", default=SETUP_MODE_WIZARD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[SETUP_MODE_WIZARD, SETUP_MODE_TABS],
                            translation_key="setup_mode",
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show thematic tabs menu when in Tabs mode."""
        return self.async_show_menu(
            step_id="menu",
            menu_options=["tariff", "felicity", "ecodan", "ev", "forecast", "finish"],
        )

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Tariff Configuration."""
        if user_input is not None:
            self._data.update(user_input)
            if self._setup_mode == SETUP_MODE_WIZARD:
                return await self.async_step_felicity()
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="tariff",
            data_schema=get_tariff_schema(self._data),
        )

    async def async_step_felicity(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Felicity Inverter & Battery Configuration."""
        if user_input is not None:
            self._data.update(user_input)
            if self._setup_mode == SETUP_MODE_WIZARD:
                return await self.async_step_ecodan()
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="felicity",
            data_schema=get_felicity_schema(self._data),
        )

    async def async_step_ecodan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Mitsubishi Ecodan Heat Pump Configuration."""
        if user_input is not None:
            self._data.update(user_input)
            if self._setup_mode == SETUP_MODE_WIZARD:
                return await self.async_step_ev()
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="ecodan",
            data_schema=get_ecodan_schema(self._data),
        )

    async def async_step_ev(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4: Tesla Fleet & EVSE Configuration."""
        if user_input is not None:
            self._data.update(user_input)
            if self._setup_mode == SETUP_MODE_WIZARD:
                return await self.async_step_forecast()
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="ev",
            data_schema=get_ev_schema(self._data),
        )

    async def async_step_forecast(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 5: Solcast / Open-Meteo & ML Configuration."""
        if user_input is not None:
            self._data.update(user_input)
            if self._setup_mode == SETUP_MODE_WIZARD:
                return await self.async_step_finish()
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="forecast",
            data_schema=get_forecast_schema(self._data),
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Finalize setup and create config entry."""
        return self.async_create_entry(
            title="Smart Residential EMS",
            data=self._data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return EMSOptionsFlowHandler(config_entry)


class EMSOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle EMS options via either Wizard or Thematic Tabs."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize EMS options flow."""
        self._entry = config_entry
        data = (config_entry.data if config_entry else None) or {}
        options = (config_entry.options if config_entry else None) or {}
        self._options: dict[str, Any] = {**data, **options}
        self._mode: str = SETUP_MODE_TABS

    @property
    def options(self) -> dict[str, Any]:
        """Return options dictionary."""
        if not self._options:
            entry = self._entry or getattr(self, "config_entry", None)
            if entry:
                data = entry.data or {}
                options = entry.options or {}
                self._options = {**data, **options}
        return self._options

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options: choose between thematic tabs or full wizard."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["tariff", "felicity", "ecodan", "ev", "forecast", "wizard_start", "save"],
        )

    async def async_step_wizard_start(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start guided wizard in options."""
        self._mode = SETUP_MODE_WIZARD
        return await self.async_step_tariff()

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit Tariff options."""
        if user_input is not None:
            self.options.update(user_input)
            if self._mode == SETUP_MODE_WIZARD:
                return await self.async_step_felicity()
            return await self.async_step_init()

        return self.async_show_form(
            step_id="tariff",
            data_schema=get_tariff_schema(self.options),
        )

    async def async_step_felicity(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit Felicity Inverter & Battery options."""
        if user_input is not None:
            self.options.update(user_input)
            if self._mode == SETUP_MODE_WIZARD:
                return await self.async_step_ecodan()
            return await self.async_step_init()

        return self.async_show_form(
            step_id="felicity",
            data_schema=get_felicity_schema(self.options),
        )

    async def async_step_ecodan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit Mitsubishi Ecodan options."""
        if user_input is not None:
            self.options.update(user_input)
            if self._mode == SETUP_MODE_WIZARD:
                return await self.async_step_ev()
            return await self.async_step_init()

        return self.async_show_form(
            step_id="ecodan",
            data_schema=get_ecodan_schema(self.options),
        )

    async def async_step_ev(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit EV & Tesla Fleet options."""
        if user_input is not None:
            self.options.update(user_input)
            if self._mode == SETUP_MODE_WIZARD:
                return await self.async_step_forecast()
            return await self.async_step_init()

        return self.async_show_form(
            step_id="ev",
            data_schema=get_ev_schema(self.options),
        )

    async def async_step_forecast(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit Forecast & ML options."""
        if user_input is not None:
            self.options.update(user_input)
            if self._mode == SETUP_MODE_WIZARD:
                return await self.async_step_save()
            return await self.async_step_init()

        return self.async_show_form(
            step_id="forecast",
            data_schema=get_forecast_schema(self.options),
        )

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Save updated options."""
        return self.async_create_entry(title="", data=self.options)
