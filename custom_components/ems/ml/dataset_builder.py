"""Dataset builder extracting 2-year historical data from Home Assistant Recorder."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import math
from typing import Any

_LOGGER = logging.getLogger(__name__)


def build_feature_vector(
    dt: datetime,
    outdoor_temp: float,
    indoor_z1_temp: float = 20.0,
    indoor_z2_temp: float = 20.5,
) -> list[float]:
    """Build a 10-feature vector for ML inference or training.

    Features:
    0: sin(hour)
    1: cos(hour)
    2: sin(day_of_week)
    3: cos(day_of_week)
    4: sin(day_of_year)
    5: cos(day_of_year)
    6: is_weekend (0 or 1)
    7: outdoor_temp (°C)
    8: heating_degree_delta_z1 (max(0, 19.0 - outdoor_temp))
    9: indoor_avg_temp (°C)
    """
    hour = dt.hour + dt.minute / 60.0
    dow = dt.weekday()
    doy = dt.timetuple().tm_yday

    sin_hour = math.sin(2.0 * math.pi * hour / 24.0)
    cos_hour = math.cos(2.0 * math.pi * hour / 24.0)
    sin_dow = math.sin(2.0 * math.pi * dow / 7.0)
    cos_dow = math.cos(2.0 * math.pi * dow / 7.0)
    sin_doy = math.sin(2.0 * math.pi * doy / 365.25)
    cos_doy = math.cos(2.0 * math.pi * doy / 365.25)
    is_weekend = 1.0 if dow >= 5 else 0.0
    hdd = max(0.0, 19.0 - outdoor_temp)
    indoor_avg = (indoor_z1_temp + indoor_z2_temp) / 2.0

    return [
        float(sin_hour),
        float(cos_hour),
        float(sin_dow),
        float(cos_dow),
        float(sin_doy),
        float(cos_doy),
        float(is_weekend),
        float(outdoor_temp),
        float(hdd),
        float(indoor_avg),
    ]


class RecorderDatasetBuilder:
    """Extracts and aligns historical sensor data from Home Assistant Recorder."""

    def __init__(self, hass: Any) -> None:
        """Initialize the dataset builder."""
        self.hass = hass

    async def async_fetch_training_dataset(
        self,
        load_entity: str | None,
        ecodan_power_entity: str | None,
        outdoor_temp_entity: str | None,
        z1_temp_entity: str | None,
        z2_temp_entity: str | None,
        days: int = 730,
    ) -> tuple[list[list[float]], list[float]]:
        """Fetch historical states from HA Recorder and align into hourly X, y lists."""
        if not load_entity and not ecodan_power_entity:
            _LOGGER.warning("No load or Ecodan power entity configured for ML training")
            return [], []

        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import get_significant_states
        except ImportError:
            _LOGGER.warning("HA Recorder not available; falling back to synthetic/incremental learning")
            return [], []

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)

        entities = [
            e
            for e in [
                load_entity,
                ecodan_power_entity,
                outdoor_temp_entity,
                z1_temp_entity,
                z2_temp_entity,
            ]
            if e
        ]

        if not entities:
            return [], []

        def _fetch_sync() -> dict[str, list[Any]]:
            return get_significant_states(
                self.hass,
                start_time=start_time,
                end_time=end_time,
                entity_ids=entities,
                include_start_time_state=True,
                minimal_response=True,
            )

        try:
            history_data = await get_instance(self.hass).async_add_executor_job(_fetch_sync)
        except Exception as err:
            _LOGGER.error("Error fetching Recorder history for ML training: %s", err)
            return [], []

        return self._align_hourly_records(
            history_data=history_data,
            load_entity=load_entity,
            ecodan_power_entity=ecodan_power_entity,
            outdoor_temp_entity=outdoor_temp_entity,
            z1_temp_entity=z1_temp_entity,
            z2_temp_entity=z2_temp_entity,
        )

    def _align_hourly_records(
        self,
        history_data: dict[str, list[Any]],
        load_entity: str | None,
        ecodan_power_entity: str | None,
        outdoor_temp_entity: str | None,
        z1_temp_entity: str | None,
        z2_temp_entity: str | None,
    ) -> tuple[list[list[float]], list[float]]:
        """Group state changes by hour bucket and construct X, y matrices."""
        buckets: dict[datetime, dict[str, list[float]]] = {}

        def _ingest_entity(entity_id: str | None, key: str) -> None:
            if not entity_id or entity_id not in history_data:
                return
            for state_obj in history_data[entity_id]:
                try:
                    val = float(state_obj.state)
                    ts: datetime = state_obj.last_updated
                    hour_bucket = ts.replace(minute=0, second=0, microsecond=0)
                    if hour_bucket not in buckets:
                        buckets[hour_bucket] = {}
                    buckets[hour_bucket].setdefault(key, []).append(val)
                except (ValueError, TypeError, AttributeError):
                    continue

        _ingest_entity(load_entity, "load")
        _ingest_entity(ecodan_power_entity, "ecodan")
        _ingest_entity(outdoor_temp_entity, "outdoor")
        _ingest_entity(z1_temp_entity, "z1")
        _ingest_entity(z2_temp_entity, "z2")

        X_list: list[list[float]] = []
        y_list: list[float] = []

        last_outdoor = 12.0
        last_z1 = 20.0
        last_z2 = 20.5

        for hour_dt in sorted(buckets.keys()):
            b = buckets[hour_dt]
            if "outdoor" in b and b["outdoor"]:
                last_outdoor = sum(b["outdoor"]) / len(b["outdoor"])
            if "z1" in b and b["z1"]:
                last_z1 = sum(b["z1"]) / len(b["z1"])
            if "z2" in b and b["z2"]:
                last_z2 = sum(b["z2"]) / len(b["z2"])

            total_power: float | None = None
            if "load" in b and b["load"]:
                total_power = sum(b["load"]) / len(b["load"])
            elif "ecodan" in b and b["ecodan"]:
                # Base domestic load (~350W) + Ecodan PAC power
                total_power = 350.0 + (sum(b["ecodan"]) / len(b["ecodan"]))

            if total_power is not None and 0.0 <= total_power <= 25000.0:
                features = build_feature_vector(
                    dt=hour_dt,
                    outdoor_temp=last_outdoor,
                    indoor_z1_temp=last_z1,
                    indoor_z2_temp=last_z2,
                )
                X_list.append(features)
                y_list.append(float(total_power))

        return X_list, y_list
