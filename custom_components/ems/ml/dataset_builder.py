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
    """Build a 13-feature vector for consumption ML inference or training.

    Features:
    0: sin(hour)
    1: cos(hour)
    2: hour (0..23)
    3: sin(day_of_week)
    4: cos(day_of_week)
    5: day_of_week (0=Monday .. 6=Sunday)
    6: is_weekend (0 or 1)
    7: sin(day_of_year)
    8: cos(day_of_year)
    9: month (1..12)
    10: outdoor_temp (°C)
    11: heating_degree_delta_z1 (max(0, 19.0 - outdoor_temp))
    12: indoor_avg_temp (°C)
    """
    hour = dt.hour + dt.minute / 60.0
    dow = float(dt.weekday())
    doy = float(dt.timetuple().tm_yday)
    month = float(dt.month)

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
        float(hour),
        float(sin_dow),
        float(cos_dow),
        float(dow),
        float(is_weekend),
        float(sin_doy),
        float(cos_doy),
        float(month),
        float(outdoor_temp),
        float(hdd),
        float(indoor_avg),
    ]


def build_solar_feature_vector(
    dt: datetime,
    solcast_watts: float,
    outdoor_temp: float = 15.0,
) -> list[float]:
    """Build an 8-feature vector for Solar Solcast vs Actual PV calibration.

    Features:
    0: solcast_watts (W)
    1: hour (0..23)
    2: sin(hour)
    3: cos(hour)
    4: month (1..12)
    5: sin(day_of_year)
    6: cos(day_of_year)
    7: outdoor_temp (°C)
    """
    hour = dt.hour + dt.minute / 60.0
    doy = float(dt.timetuple().tm_yday)
    month = float(dt.month)

    sin_hour = math.sin(2.0 * math.pi * hour / 24.0)
    cos_hour = math.cos(2.0 * math.pi * hour / 24.0)
    sin_doy = math.sin(2.0 * math.pi * doy / 365.25)
    cos_doy = math.cos(2.0 * math.pi * doy / 365.25)

    return [
        float(max(0.0, solcast_watts)),
        float(hour),
        float(sin_hour),
        float(cos_hour),
        float(month),
        float(sin_doy),
        float(cos_doy),
        float(outdoor_temp),
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
                minimal_response=False,
                no_attributes=True,
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

    async def async_fetch_solar_calibration_dataset(
        self,
        pv_power_entity: str | None,
        solcast_power_entity: str | None,
        outdoor_temp_entity: str | None,
        days: int = 365,
    ) -> tuple[list[list[float]], list[float], list[tuple[int, float, float]]]:
        """Fetch historical actual PV vs Solcast forecast from Recorder."""
        if not pv_power_entity or not solcast_power_entity:
            return [], [], []

        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import get_significant_states
        except ImportError:
            return [], [], []

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)

        entities = [e for e in [pv_power_entity, solcast_power_entity, outdoor_temp_entity] if e]

        def _fetch_sync() -> dict[str, list[Any]]:
            return get_significant_states(
                self.hass,
                start_time=start_time,
                end_time=end_time,
                entity_ids=entities,
                include_start_time_state=True,
                minimal_response=False,
                no_attributes=True,
            )

        try:
            history_data = await get_instance(self.hass).async_add_executor_job(_fetch_sync)
        except Exception as err:
            _LOGGER.error("Error fetching Recorder history for Solar Calibration: %s", err)
            return [], [], []

        return self._align_solar_records(
            history_data=history_data,
            pv_power_entity=pv_power_entity,
            solcast_power_entity=solcast_power_entity,
            outdoor_temp_entity=outdoor_temp_entity,
        )

    @staticmethod
    def _extract_val_and_ts(state_obj: Any) -> tuple[float, datetime] | None:
        """Extract numeric state and UTC datetime from either a HA State object or minimal dict."""
        try:
            if isinstance(state_obj, dict):
                raw_s = state_obj.get("state", state_obj.get("s"))
                raw_ts = state_obj.get("last_updated", state_obj.get("lu"))
                val = float(raw_s)
                if isinstance(raw_ts, (int, float)):
                    ts = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
                elif isinstance(raw_ts, str):
                    ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                else:
                    return None
                return val, ts
            val = float(state_obj.state)
            ts = state_obj.last_updated
            return val, ts
        except (ValueError, TypeError, AttributeError):
            return None

    def _align_solar_records(
        self,
        history_data: dict[str, list[Any]],
        pv_power_entity: str | None,
        solcast_power_entity: str | None,
        outdoor_temp_entity: str | None,
    ) -> tuple[list[list[float]], list[float], list[tuple[int, float, float]]]:
        """Align hourly PV actuals and Solcast predictions."""
        buckets: dict[datetime, dict[str, list[float]]] = {}

        def _ingest_entity(entity_id: str | None, key: str) -> None:
            if not entity_id or entity_id not in history_data:
                return
            for state_obj in history_data[entity_id]:
                extracted = self._extract_val_and_ts(state_obj)
                if extracted is None:
                    continue
                val, ts = extracted
                hour_bucket = ts.replace(minute=0, second=0, microsecond=0)
                if hour_bucket not in buckets:
                    buckets[hour_bucket] = {}
                buckets[hour_bucket].setdefault(key, []).append(val)

        _ingest_entity(pv_power_entity, "pv")
        _ingest_entity(solcast_power_entity, "solcast")
        _ingest_entity(outdoor_temp_entity, "outdoor")

        X_solar: list[list[float]] = []
        y_solar: list[float] = []
        hourly_pairs: list[tuple[int, float, float]] = []

        last_outdoor = 15.0

        for hour_dt in sorted(buckets.keys()):
            b = buckets[hour_dt]
            if "outdoor" in b and b["outdoor"]:
                last_outdoor = sum(b["outdoor"]) / len(b["outdoor"])

            if "pv" in b and b["pv"] and "solcast" in b and b["solcast"]:
                pv_w = sum(b["pv"]) / len(b["pv"])
                sol_w = sum(b["solcast"]) / len(b["solcast"])
                # Auto-detect if Solcast entity was recorded in kW instead of W
                if 0.0 < sol_w < 15.0 and pv_w > 150.0:
                    sol_w *= 1000.0
                if 0.0 < pv_w < 15.0 and sol_w > 150.0:
                    pv_w *= 1000.0

                if (sol_w >= 30.0 or pv_w >= 30.0) and pv_w <= 15000.0 and sol_w <= 15000.0:
                    vec = build_solar_feature_vector(hour_dt, sol_w, last_outdoor)
                    X_solar.append(vec)
                    y_solar.append(float(pv_w))
                    hourly_pairs.append((hour_dt.hour, float(sol_w), float(pv_w)))

        return X_solar, y_solar, hourly_pairs

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
                extracted = self._extract_val_and_ts(state_obj)
                if extracted is None:
                    continue
                val, ts = extracted
                hour_bucket = ts.replace(minute=0, second=0, microsecond=0)
                if hour_bucket not in buckets:
                    buckets[hour_bucket] = {}
                buckets[hour_bucket].setdefault(key, []).append(val)

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
