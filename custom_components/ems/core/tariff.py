"""Tariff Manager handling Fixed Base, Time-of-Use (HP/HC), and Dynamic Spot pricing."""

from __future__ import annotations

from typing import Any

from ..const import (
    TARIFF_MODE_FIXED,
    TARIFF_MODE_TOU,
    TARIFF_MODE_DYNAMIC,
    CONF_TARIFF_MODE,
    CONF_GRID_IMPORT_PRICE_FIXED,
    CONF_GRID_EXPORT_PRICE_FIXED,
    CONF_GRID_IMPORT_PRICE_ENTITY,
    CONF_GRID_EXPORT_PRICE_ENTITY,
    CONF_DYNAMIC_CHEAP_THRESHOLD,
    DEFAULT_IMPORT_PRICE,
    DEFAULT_EXPORT_PRICE,
    DEFAULT_DYNAMIC_CHEAP_THRESHOLD,
)


class TariffManager:
    """Evaluates electricity prices, self-consumption value, and grid charge opportunities."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the tariff manager with user configuration."""
        self.config = config

    def update_config(self, config: dict[str, Any]) -> None:
        """Update tariff configuration."""
        self.config = config

    @property
    def mode(self) -> str:
        """Return current tariff mode (fixed, time_of_use, dynamic)."""
        return self.config.get(CONF_TARIFF_MODE, TARIFF_MODE_FIXED)

    def get_current_prices(self, live_states: dict[str, Any]) -> tuple[float, float]:
        """Return (import_price_eur_kwh, export_price_eur_kwh)."""
        fixed_import = float(self.config.get(CONF_GRID_IMPORT_PRICE_FIXED, DEFAULT_IMPORT_PRICE))
        fixed_export = float(self.config.get(CONF_GRID_EXPORT_PRICE_FIXED, DEFAULT_EXPORT_PRICE))

        import_price = fixed_import
        export_price = fixed_export

        if self.mode in (TARIFF_MODE_TOU, TARIFF_MODE_DYNAMIC):
            imp_entity = self.config.get(CONF_GRID_IMPORT_PRICE_ENTITY)
            if imp_entity and imp_entity in live_states and live_states[imp_entity] is not None:
                try:
                    import_price = float(live_states[imp_entity])
                except (ValueError, TypeError):
                    pass

            exp_entity = self.config.get(CONF_GRID_EXPORT_PRICE_ENTITY)
            if exp_entity and exp_entity in live_states and live_states[exp_entity] is not None:
                try:
                    export_price = float(live_states[exp_entity])
                except (ValueError, TypeError):
                    pass

        return round(import_price, 4), round(export_price, 4)

    def is_cheap_grid_opportunity(self, live_states: dict[str, Any]) -> bool:
        """Determine if current grid import price is low enough to trigger grid charging."""
        if self.mode == TARIFF_MODE_FIXED:
            return False

        import_price, _ = self.get_current_prices(live_states)
        threshold = float(
            self.config.get(CONF_DYNAMIC_CHEAP_THRESHOLD, DEFAULT_DYNAMIC_CHEAP_THRESHOLD)
        )
        return import_price <= threshold

    def calculate_self_consumption_spread(self, live_states: dict[str, Any]) -> float:
        """Return financial savings per kWh self-consumed instead of exported (€/kWh)."""
        import_price, export_price = self.get_current_prices(live_states)
        return round(max(0.0, import_price - export_price), 4)
