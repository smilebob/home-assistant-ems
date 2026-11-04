"""DuckDB local time-series storage for Smart Residential EMS."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
from typing import Any
import duckdb

_LOGGER = logging.getLogger(__name__)


class EMSStorage:
    """Embedded DuckDB storage for high-performance ML telemetry and history."""

    def __init__(self, data_dir: str = "/data") -> None:
        """Initialize DuckDB database file in data_dir."""
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "ems.duckdb")
        self._init_schema()

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Return a thread-safe connection to the DuckDB database."""
        return duckdb.connect(self.db_path)

    def _init_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._get_connection() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    timestamp TIMESTAMP PRIMARY KEY,
                    pv_power_w DOUBLE,
                    grid_power_w DOUBLE,
                    house_load_w DOUBLE,
                    battery_soc DOUBLE,
                    battery_power_w DOUBLE,
                    dhw_temp DOUBLE,
                    z1_temp DOUBLE,
                    z2_temp DOUBLE,
                    outdoor_temp DOUBLE,
                    ev_soc DOUBLE,
                    ev_amps INTEGER,
                    active_priority VARCHAR,
                    instant_savings_eur_h DOUBLE
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS decision_log (
                    timestamp TIMESTAMP,
                    priority VARCHAR,
                    reason VARCHAR
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS solar_observations (
                    timestamp TIMESTAMP PRIMARY KEY,
                    solcast_watts DOUBLE,
                    actual_pv_watts DOUBLE,
                    outdoor_temp DOUBLE
                );
            """)

    def record_telemetry(self, data: dict[str, Any]) -> None:
        """Record an EMS cycle snapshot into DuckDB."""
        ts = data.get("timestamp") or datetime.now()
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        try:
            with self._get_connection() as con:
                con.execute("""
                    INSERT OR REPLACE INTO telemetry VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, [
                    ts,
                    data.get("pv_power_w", 0.0),
                    data.get("grid_power_w", 0.0),
                    data.get("house_load_w", 0.0),
                    data.get("battery_soc", 0.0),
                    data.get("battery_power_w", 0.0),
                    data.get("dhw_temp"),
                    data.get("z1_temp"),
                    data.get("z2_temp"),
                    data.get("outdoor_temp", 10.0),
                    data.get("ev_soc", 0.0),
                    data.get("ev_target_amps", 0),
                    data.get("active_priority", "idle"),
                    data.get("instant_savings_eur_h", 0.0),
                ])
        except Exception as err:
            _LOGGER.error("Failed to write telemetry to DuckDB: %s", err)

    def record_decision(self, priority: str, reason: str, ts: datetime | None = None) -> None:
        """Log an arbitration priority change with French explanation."""
        ts = ts or datetime.now()
        try:
            with self._get_connection() as con:
                con.execute("""
                    INSERT INTO decision_log VALUES (?, ?, ?)
                """, [ts, priority, reason])
        except Exception as err:
            _LOGGER.error("Failed to write decision log to DuckDB: %s", err)

    def get_recent_telemetry(self, hours: int = 24) -> list[dict[str, Any]]:
        """Retrieve recent telemetry records for frontend charts."""
        cutoff = datetime.now() - timedelta(hours=hours)
        try:
            with self._get_connection() as con:
                df = con.execute("""
                    SELECT 
                        strftime(timestamp, '%Y-%m-%dT%H:%M:%S') as timestamp,
                        pv_power_w,
                        grid_power_w,
                        house_load_w,
                        battery_soc,
                        battery_power_w,
                        dhw_temp,
                        z1_temp,
                        z2_temp,
                        outdoor_temp,
                        ev_soc,
                        ev_amps,
                        active_priority
                    FROM telemetry
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                """, [cutoff]).fetchdf()
                return df.to_dict(orient="records")
        except Exception as err:
            _LOGGER.error("Failed to read telemetry from DuckDB: %s", err)
            return []

    def get_recent_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve latest decision explanations."""
        try:
            with self._get_connection() as con:
                df = con.execute("""
                    SELECT 
                        strftime(timestamp, '%H:%M:%S') as time,
                        strftime(timestamp, '%Y-%m-%d') as date,
                        priority,
                        reason
                    FROM decision_log
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, [limit]).fetchdf()
                return df.to_dict(orient="records")
        except Exception as err:
            _LOGGER.error("Failed to read decision log from DuckDB: %s", err)
            return []

    def get_hourly_training_dataset(self, days: int = 30) -> list[dict[str, Any]]:
        """Compute clean hourly averages for Machine Learning model training."""
        cutoff = datetime.now() - timedelta(days=days)
        try:
            with self._get_connection() as con:
                df = con.execute("""
                    SELECT 
                        date_trunc('hour', timestamp) as dt,
                        avg(house_load_w) as load_w,
                        avg(outdoor_temp) as outdoor_temp,
                        avg(z1_temp) as z1_temp,
                        avg(z2_temp) as z2_temp
                    FROM telemetry
                    WHERE timestamp >= ?
                    GROUP BY 1
                    HAVING count(*) >= 2
                    ORDER BY dt ASC
                """, [cutoff]).fetchdf()
                return df.to_dict(orient="records")
        except Exception as err:
            _LOGGER.error("Failed to query ML training dataset: %s", err)
            return []
