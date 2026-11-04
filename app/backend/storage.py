"""SQLite local time-series storage for Smart Residential EMS."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
import sqlite3
from typing import Any

_LOGGER = logging.getLogger(__name__)


class EMSStorage:
    """Embedded SQLite storage for lightweight, ultra-portable ML telemetry and history.
    
    Zero external binary dependencies, guaranteeing 100% compatibility across all CPU architectures
    (x86_64 generic, x86_64-v2, v3, aarch64, armv7) without SIGILL or AVX requirements.
    """

    def __init__(self, data_dir: str = "/data") -> None:
        """Initialize SQLite database file in data_dir."""
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "ems.db")
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Return a configured connection to the SQLite database."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._get_connection() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    timestamp TEXT PRIMARY KEY,
                    pv_power_w REAL,
                    grid_power_w REAL,
                    house_load_w REAL,
                    battery_soc REAL,
                    battery_power_w REAL,
                    dhw_temp REAL,
                    z1_temp REAL,
                    z2_temp REAL,
                    outdoor_temp REAL,
                    ev_soc REAL,
                    ev_amps INTEGER,
                    active_priority TEXT,
                    instant_savings_eur_h REAL,
                    solcast_power_w REAL DEFAULT 0.0,
                    predicted_load_w REAL DEFAULT 0.0
                );
            """)

            # Gracefully ensure new columns exist for existing databases
            for col in ["solcast_power_w", "predicted_load_w"]:
                try:
                    con.execute(f"ALTER TABLE telemetry ADD COLUMN {col} REAL DEFAULT 0.0;")
                except Exception:
                    pass

            con.execute("""
                CREATE TABLE IF NOT EXISTS decision_log (
                    timestamp TEXT,
                    priority TEXT,
                    reason TEXT
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS solar_observations (
                    timestamp TEXT PRIMARY KEY,
                    solcast_watts REAL,
                    actual_pv_watts REAL,
                    outdoor_temp REAL
                );
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(timestamp);")
            con.execute("CREATE INDEX IF NOT EXISTS idx_decision_ts ON decision_log(timestamp);")

    def record_telemetry(self, data: dict[str, Any]) -> None:
        """Record an EMS cycle snapshot into SQLite."""
        ts = data.get("timestamp") or datetime.now()
        if isinstance(ts, datetime):
            ts_str = ts.isoformat()
        else:
            ts_str = str(ts)

        try:
            with self._get_connection() as con:
                con.execute("""
                    INSERT OR REPLACE INTO telemetry (
                        timestamp, pv_power_w, grid_power_w, house_load_w,
                        battery_soc, battery_power_w, dhw_temp, z1_temp, z2_temp,
                        outdoor_temp, ev_soc, ev_amps, active_priority, instant_savings_eur_h,
                        solcast_power_w, predicted_load_w
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, [
                    ts_str,
                    float(data.get("pv_power_w") or 0.0),
                    float(data.get("grid_power_w") or 0.0),
                    float(data.get("house_load_w") or 0.0),
                    float(data.get("battery_soc") or 0.0),
                    float(data.get("battery_power_w") or 0.0),
                    data.get("dhw_temp"),
                    data.get("z1_temp"),
                    data.get("z2_temp"),
                    float(data.get("outdoor_temp") or 10.0),
                    float(data.get("ev_soc") or 0.0),
                    int(data.get("ev_target_amps") or 0),
                    str(data.get("active_priority") or "idle"),
                    float(data.get("instant_savings_eur_h") or 0.0),
                    float(data.get("solcast_power_w") or 0.0),
                    float(data.get("predicted_load_w") or 0.0),
                ])
                con.commit()
        except Exception as err:
            _LOGGER.error("Failed to write telemetry to SQLite: %s", err)

    def record_solar_observation(
        self,
        timestamp: datetime,
        solcast_watts: float,
        actual_pv_watts: float,
        outdoor_temp: float = 15.0,
    ) -> None:
        """Persist real-time comparison point between Solcast and actual inverter output."""
        try:
            with self._get_connection() as con:
                con.execute("""
                    INSERT OR REPLACE INTO solar_observations (
                        timestamp, solcast_watts, actual_pv_watts, outdoor_temp
                    ) VALUES (?, ?, ?, ?)
                """, [timestamp.isoformat(), float(solcast_watts), float(actual_pv_watts), float(outdoor_temp)])
                con.commit()
        except Exception as err:
            _LOGGER.error("Failed to write solar observation: %s", err)

    def record_decision(self, priority: str, reason: str, ts: datetime | None = None) -> None:
        """Log an arbitration priority change with French explanation."""
        ts = ts or datetime.now()
        ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        try:
            with self._get_connection() as con:
                con.execute("""
                    INSERT INTO decision_log VALUES (?, ?, ?)
                """, [ts_str, priority, reason])
                con.commit()
        except Exception as err:
            _LOGGER.error("Failed to write decision log to SQLite: %s", err)

    def get_recent_telemetry(self, hours: int = 24) -> list[dict[str, Any]]:
        """Retrieve recent telemetry records for frontend charts."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        try:
            with self._get_connection() as con:
                cur = con.execute("""
                    SELECT 
                        timestamp,
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
                        active_priority,
                        solcast_power_w,
                        predicted_load_w
                    FROM telemetry
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                """, [cutoff])
                return [dict(row) for row in cur.fetchall()]
        except Exception as err:
            _LOGGER.error("Failed to read telemetry from SQLite: %s", err)
            return []

    def get_daily_solar_comparison(self, days: int = 7) -> list[dict[str, Any]]:
        """Compute aggregated daily solar energy (kWh): Solcast predicted vs Actual inverter production."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
        results: list[dict[str, Any]] = []
        try:
            with self._get_connection() as con:
                # Integrate average power per hour to obtain daily kWh
                cur = con.execute("""
                    SELECT 
                        date(timestamp) as day,
                        round(sum(pv_power_w) / count(*) * 24.0 / 1000.0, 2) as actual_kwh,
                        round(sum(solcast_power_w) / count(*) * 24.0 / 1000.0, 2) as predicted_kwh
                    FROM telemetry
                    WHERE timestamp >= ?
                    GROUP BY date(timestamp)
                    ORDER BY day ASC
                """, [cutoff])
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    act = float(r.get("actual_kwh") or 0.0)
                    pred = float(r.get("predicted_kwh") or 0.0)
                    ratio = round((act / pred * 100.0), 1) if pred > 0.5 else 100.0
                    results.append({
                        "date": r["day"],
                        "actual_kwh": act,
                        "predicted_kwh": pred,
                        "accuracy_pct": ratio,
                        "delta_kwh": round(act - pred, 2)
                    })
        except Exception as err:
            _LOGGER.error("Failed to compute daily solar comparison: %s", err)

        return results

    def get_recent_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve latest decision explanations."""
        try:
            with self._get_connection() as con:
                cur = con.execute("""
                    SELECT 
                        time(timestamp) as time,
                        date(timestamp) as date,
                        priority,
                        reason
                    FROM decision_log
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, [limit])
                return [dict(row) for row in cur.fetchall()]
        except Exception as err:
            _LOGGER.error("Failed to read decision log from SQLite: %s", err)
            return []

    def get_hourly_training_dataset(self, days: int = 30) -> list[dict[str, Any]]:
        """Compute clean hourly averages for Machine Learning model training."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        try:
            with self._get_connection() as con:
                cur = con.execute("""
                    SELECT 
                        strftime('%Y-%m-%d %H:00:00', timestamp) as dt,
                        avg(house_load_w) as load_w,
                        avg(outdoor_temp) as outdoor_temp,
                        avg(z1_temp) as z1_temp,
                        avg(z2_temp) as z2_temp
                    FROM telemetry
                    WHERE timestamp >= ?
                    GROUP BY strftime('%Y-%m-%d %H:00:00', timestamp)
                    HAVING count(*) >= 2
                    ORDER BY dt ASC
                """, [cutoff])
                return [dict(row) for row in cur.fetchall()]
        except Exception as err:
            _LOGGER.error("Failed to query ML training dataset: %s", err)
            return []
