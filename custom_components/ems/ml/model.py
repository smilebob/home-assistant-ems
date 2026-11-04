"""Scikit-learn (with built-in Regression Tree Ensemble fallback) Load & Solar Calibrator ML."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import math
import os
import pickle
import random
from typing import Any

from .dataset_builder import build_feature_vector, build_solar_feature_vector

_LOGGER = logging.getLogger(__name__)

EXPECTED_LOAD_FEATURES = 13
EXPECTED_SOLAR_FEATURES = 8

HAS_SKLEARN = False
if os.environ.get("EMS_DISABLE_NUMPY") != "1":
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestRegressor

        HAS_SKLEARN = True
    except (ImportError, RuntimeError, Exception) as err:
        _LOGGER.info("Scikit-learn/NumPy binary acceleration unavailable (%s), using pure Python ensemble fallback", err)
        HAS_SKLEARN = False


class _NativeDecisionTree:
    """Lightweight regression tree when scikit-learn is not installed in the host OS."""

    def __init__(self, max_depth: int = 6, min_samples_leaf: int = 3) -> None:
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.tree: dict[str, Any] = {}

    def fit(self, X: list[list[float]], y: list[float], rng: random.Random) -> None:
        self.tree = self._build(X, y, depth=0, rng=rng)

    def _build(
        self, X: list[list[float]], y: list[float], depth: int, rng: random.Random
    ) -> dict[str, Any]:
        n = len(y)
        mean_val = sum(y) / n if n > 0 else 400.0
        if depth >= self.max_depth or n < 2 * self.min_samples_leaf:
            return {"leaf": True, "val": mean_val}

        n_features = len(X[0])
        best_gain = 0.0
        best_feat = -1
        best_thresh = 0.0
        best_split: tuple[list[list[float]], list[float], list[list[float]], list[float]] | None = None

        total_var = sum((v - mean_val) ** 2 for v in y)
        if total_var < 1e-3:
            return {"leaf": True, "val": mean_val}

        cand_features = rng.sample(range(n_features), k=max(3, n_features // 2))
        for feat_idx in cand_features:
            col = [row[feat_idx] for row in X]
            min_v, max_v = min(col), max(col)
            if max_v - min_v < 1e-6:
                continue
            for _ in range(5):
                thresh = rng.uniform(min_v, max_v)
                left_X, left_y, right_X, right_y = [], [], [], []
                for r, target in zip(X, y):
                    if r[feat_idx] <= thresh:
                        left_X.append(r)
                        left_y.append(target)
                    else:
                        right_X.append(r)
                        right_y.append(target)
                if len(left_y) < self.min_samples_leaf or len(right_y) < self.min_samples_leaf:
                    continue
                l_mean = sum(left_y) / len(left_y)
                r_mean = sum(right_y) / len(right_y)
                l_var = sum((v - l_mean) ** 2 for v in left_y)
                r_var = sum((v - r_mean) ** 2 for v in right_y)
                gain = total_var - (l_var + r_var)
                if gain > best_gain:
                    best_gain = gain
                    best_feat = feat_idx
                    best_thresh = thresh
                    best_split = (left_X, left_y, right_X, right_y)

        if best_split is None:
            return {"leaf": True, "val": mean_val}

        l_X, l_y, r_X, r_y = best_split
        return {
            "leaf": False,
            "feat": best_feat,
            "thresh": best_thresh,
            "left": self._build(l_X, l_y, depth + 1, rng),
            "right": self._build(r_X, r_y, depth + 1, rng),
        }

    def predict_one(self, row: list[float]) -> float:
        node = self.tree
        while not node.get("leaf", True):
            feat_idx = node["feat"]
            if feat_idx >= len(row):
                break
            if row[feat_idx] <= node["thresh"]:
                node = node["left"]
            else:
                node = node["right"]
        return float(node.get("val", 400.0))


class _NativeRandomForestRegressor:
    """Pure-Python Random Forest Regressor fallback matching scikit-learn's API."""

    def __init__(self, n_estimators: int = 20, max_depth: int = 7, seed: int = 42) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.seed = seed
        self.trees: list[_NativeDecisionTree] = []

    def fit(self, X: list[list[float]], y: list[float]) -> None:
        rng = random.Random(self.seed)
        self.trees = []
        n = len(X)
        for _ in range(self.n_estimators):
            indices = [rng.randrange(n) for _ in range(n)]
            boot_X = [X[i] for i in indices]
            boot_y = [y[i] for i in indices]
            tree = _NativeDecisionTree(max_depth=self.max_depth)
            tree.fit(boot_X, boot_y, rng)
            self.trees.append(tree)

    def predict(self, X: list[list[float]]) -> list[float]:
        out: list[float] = []
        for row in X:
            preds = [t.predict_one(row) for t in self.trees]
            out.append(sum(preds) / len(preds) if preds else 400.0)
        return out


class ConsumptionMLModel:
    """Machine Learning model predicting hourly household + PAC electricity load."""

    def __init__(self, storage_path: str | None = None) -> None:
        """Initialize the ML model."""
        self.storage_path = storage_path
        self.model: Any = None
        self.is_trained: bool = False
        self.last_trained: datetime | None = None
        self.training_samples: int = 0
        self.mae_score: float | None = None
        self.accuracy_pct: float = 0.0
        self.r2_score: float = 0.0
        self.mean_load_watts: float = 500.0
        self.feature_version: int = EXPECTED_LOAD_FEATURES
        self._online_X: list[list[float]] = []
        self._online_y: list[float] = []

    def load_from_disk(self) -> bool:
        """Load persisted model if available and compatible with current feature count."""
        if not self.storage_path or not os.path.exists(self.storage_path):
            return False
        try:
            with open(self.storage_path, "rb") as f:
                saved = pickle.load(f)
            if saved.get("feature_version") != EXPECTED_LOAD_FEATURES:
                _LOGGER.info("Upgrading ML model schema to %d features", EXPECTED_LOAD_FEATURES)
                return False
            self.model = saved.get("model")
            self.last_trained = saved.get("last_trained")
            self.training_samples = saved.get("training_samples", 0)
            self.mae_score = saved.get("mae_score")
            self.accuracy_pct = saved.get("accuracy_pct", 85.0)
            self.r2_score = saved.get("r2_score", 0.75)
            self.mean_load_watts = saved.get("mean_load_watts", 500.0)
            self.is_trained = self.model is not None
            return self.is_trained
        except Exception as err:
            _LOGGER.warning("Could not load saved ML model: %s", err)
            return False

    def save_to_disk(self) -> None:
        """Persist trained model to disk."""
        if not self.storage_path or not self.is_trained:
            return
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "wb") as f:
                pickle.dump(
                    {
                        "feature_version": EXPECTED_LOAD_FEATURES,
                        "model": self.model,
                        "last_trained": self.last_trained,
                        "training_samples": self.training_samples,
                        "mae_score": self.mae_score,
                        "accuracy_pct": self.accuracy_pct,
                        "r2_score": self.r2_score,
                        "mean_load_watts": self.mean_load_watts,
                    },
                    f,
                )
        except Exception as err:
            _LOGGER.warning("Could not save ML model to disk: %s", err)

    def record_observation(
        self,
        dt: datetime,
        power_watts: float,
        outdoor_temp: float,
        indoor_z1_temp: float = 20.0,
        indoor_z2_temp: float = 20.5,
    ) -> None:
        """Store live observation in memory buffer for incremental retraining."""
        if 0.0 <= power_watts <= 25000.0:
            vec = build_feature_vector(dt, outdoor_temp, indoor_z1_temp, indoor_z2_temp)
            self._online_X.append(vec)
            self._online_y.append(float(power_watts))
            if len(self._online_X) > 2000:
                self._online_X = self._online_X[-2000:]
                self._online_y = self._online_y[-2000:]

    def train(self, X: list[list[float]] | Any, y: list[float] | Any) -> dict[str, Any]:
        """Train RandomForestRegressor on historical and online data."""
        X_list = [row for row in (list(X) if X is not None else []) if len(row) == EXPECTED_LOAD_FEATURES]
        y_list = list(y)[: len(X_list)] if y is not None else []

        if self._online_X:
            X_list.extend(self._online_X)
            y_list.extend(self._online_y)

        if len(X_list) < 12:
            X_list, y_list = self._generate_synthetic_prior()

        if HAS_SKLEARN:
            X_arr = np.array(X_list, dtype=np.float64)
            y_arr = np.array(y_list, dtype=np.float64)
            rf = RandomForestRegressor(
                n_estimators=60,
                max_depth=12,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=1,
            )
            rf.fit(X_arr, y_arr)
            preds = list(rf.predict(X_arr))
            self.model = rf
        else:
            rf_native = _NativeRandomForestRegressor(n_estimators=25, max_depth=8, seed=42)
            rf_native.fit(X_list, y_list)
            preds = rf_native.predict(X_list)
            self.model = rf_native

        n = len(y_list)
        mean_y = sum(y_list) / n if n > 0 else 500.0
        mae = sum(abs(p - t) for p, t in zip(preds, y_list)) / n if n > 0 else 0.0
        ss_res = sum((t - p) ** 2 for p, t in zip(preds, y_list))
        ss_tot = sum((t - mean_y) ** 2 for t in y_list)
        r2 = max(0.0, min(1.0, 1.0 - (ss_res / ss_tot))) if ss_tot > 1e-3 else 0.85
        acc_pct = max(0.0, min(100.0, 100.0 * (1.0 - mae / max(mean_y, 200.0))))

        self.is_trained = True
        self.last_trained = datetime.now()
        self.training_samples = n
        self.mean_load_watts = round(mean_y, 1)
        self.mae_score = round(mae, 1)
        self.accuracy_pct = round(acc_pct, 1)
        self.r2_score = round(r2, 3)
        self.save_to_disk()

        _LOGGER.info(
            "EMS Load ML Model trained on %d samples (MAE: %.1f W, Accuracy: %.1f%%, R2: %.3f)",
            self.training_samples,
            self.mae_score,
            self.accuracy_pct,
            self.r2_score,
        )
        return {
            "samples": self.training_samples,
            "mae_watts": self.mae_score,
            "accuracy_pct": self.accuracy_pct,
            "r2_score": self.r2_score,
            "last_trained": self.last_trained.isoformat(),
        }

    def predict_power_watts(
        self,
        dt: datetime,
        outdoor_temp: float,
        indoor_z1_temp: float = 20.0,
        indoor_z2_temp: float = 20.5,
    ) -> float:
        """Predict power consumption (W) for a specific datetime and temperature."""
        if not self.is_trained or self.model is None:
            return self._heuristic_fallback(dt, outdoor_temp)

        vec = [build_feature_vector(dt, outdoor_temp, indoor_z1_temp, indoor_z2_temp)]
        try:
            pred = float(self.model.predict(vec)[0])
            return max(150.0, round(pred, 1))
        except Exception:
            return self._heuristic_fallback(dt, outdoor_temp)

    def predict_next_hours_kwh(
        self,
        start_dt: datetime,
        hours: int,
        outdoor_temp: float,
        indoor_z1_temp: float = 20.0,
        indoor_z2_temp: float = 20.5,
    ) -> tuple[float, list[dict[str, Any]]]:
        """Predict total energy (kWh) and hourly profile over the next `hours`."""
        profile: list[dict[str, Any]] = []
        total_wh = 0.0

        for h in range(hours):
            target_dt = start_dt + timedelta(hours=h)
            diurnal_offset = -2.0 * math.cos(2.0 * math.pi * (target_dt.hour - 4) / 24.0)
            est_outdoor = outdoor_temp + diurnal_offset
            watts = self.predict_power_watts(target_dt, est_outdoor, indoor_z1_temp, indoor_z2_temp)
            total_wh += watts
            profile.append(
                {
                    "datetime": target_dt.isoformat(),
                    "hour": target_dt.hour,
                    "day_of_week": target_dt.weekday(),
                    "predicted_watts": watts,
                    "estimated_outdoor_temp": round(est_outdoor, 1),
                }
            )

        return round(total_wh / 1000.0, 2), profile

    @staticmethod
    def _heuristic_fallback(dt: datetime, outdoor_temp: float) -> float:
        """Fallback thermal + domestic profile before first training completes."""
        base_domestic = 400.0
        if 7 <= dt.hour <= 9 or 18 <= dt.hour <= 22:
            base_domestic += 600.0
        if dt.weekday() >= 5 and 10 <= dt.hour <= 17:
            base_domestic += 250.0
        heating_watts = max(0.0, (17.0 - outdoor_temp) * 140.0)
        return round(base_domestic + heating_watts, 1)

    def _generate_synthetic_prior(self) -> tuple[list[list[float]], list[float]]:
        """Generate a 30-day synthetic prior reflecting Ecodan + household patterns."""
        X_syn: list[list[float]] = []
        y_syn: list[float] = []
        base_dt = datetime(2026, 1, 1, 0, 0)
        for h in range(24 * 30):
            dt = base_dt + timedelta(hours=h)
            outdoor = 8.0 + 6.0 * math.sin(2.0 * math.pi * h / (24.0 * 15.0))
            X_syn.append(build_feature_vector(dt, outdoor, 20.0, 20.5))
            y_syn.append(self._heuristic_fallback(dt, outdoor))
        return X_syn, y_syn


class SolarCalibrationModel:
    """Intermediate ML & Bayesian auto-correction layer between theoretical Solcast and actual PV."""

    def __init__(self, storage_path: str | None = None) -> None:
        """Initialize the solar calibration model."""
        self.storage_path = storage_path
        self.rf_model: Any = None
        self.is_trained: bool = False
        self.last_trained: datetime | None = None
        self.training_samples: int = 0
        self.hourly_ratios: dict[int, float] = {h: 1.0 for h in range(24)}
        self.global_ratio: float = 1.0
        self.mae_watts: float = 0.0
        self.accuracy_pct: float = 100.0
        self._online_X: list[list[float]] = []
        self._online_y: list[float] = []
        self._online_pairs: list[tuple[int, float, float]] = []

    def load_from_disk(self) -> bool:
        """Load persisted solar calibration model if available."""
        if not self.storage_path or not os.path.exists(self.storage_path):
            return False
        try:
            with open(self.storage_path, "rb") as f:
                saved = pickle.load(f)
            self.rf_model = saved.get("rf_model")
            self.last_trained = saved.get("last_trained")
            self.training_samples = saved.get("training_samples", 0)
            self.hourly_ratios = saved.get("hourly_ratios", {h: 1.0 for h in range(24)})
            self.global_ratio = saved.get("global_ratio", 1.0)
            self.mae_watts = saved.get("mae_watts", 0.0)
            self.accuracy_pct = saved.get("accuracy_pct", 100.0)
            self.is_trained = True
            return True
        except Exception as err:
            _LOGGER.warning("Could not load solar calibration model: %s", err)
            return False

    def save_to_disk(self) -> None:
        """Save solar calibration model to disk."""
        if not self.storage_path:
            return
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "wb") as f:
                pickle.dump(
                    {
                        "rf_model": self.rf_model,
                        "last_trained": self.last_trained,
                        "training_samples": self.training_samples,
                        "hourly_ratios": self.hourly_ratios,
                        "global_ratio": self.global_ratio,
                        "mae_watts": self.mae_watts,
                        "accuracy_pct": self.accuracy_pct,
                    },
                    f,
                )
        except Exception as err:
            _LOGGER.warning("Could not save solar calibration model: %s", err)

    def record_observation(
        self,
        dt: datetime,
        solcast_watts: float,
        actual_pv_watts: float,
        outdoor_temp: float = 15.0,
    ) -> None:
        """Record a daytime observation of Solcast vs actual PV production."""
        if (solcast_watts >= 30.0 or actual_pv_watts >= 30.0) and actual_pv_watts <= 15000.0:
            vec = build_solar_feature_vector(dt, solcast_watts, outdoor_temp)
            self._online_X.append(vec)
            self._online_y.append(float(actual_pv_watts))
            self._online_pairs.append((dt.hour, float(solcast_watts), float(actual_pv_watts)))
            if len(self._online_X) > 2000:
                self._online_X = self._online_X[-2000:]
                self._online_y = self._online_y[-2000:]
                self._online_pairs = self._online_pairs[-2000:]

    def train(
        self,
        X_solar: list[list[float]],
        y_solar: list[float],
        hourly_pairs: list[tuple[int, float, float]],
    ) -> dict[str, Any]:
        """Train Bayesian hourly shading profile + Random Forest transfer model."""
        X_all = list(X_solar) + self._online_X
        y_all = list(y_solar) + self._online_y
        pairs_all = list(hourly_pairs) + self._online_pairs

        # 1. Compute Bayesian-smoothed hourly ratios (captures morning/evening roof shading)
        # Prior: equivalent to 1500W of unbiased (ratio=1.0) production per hour bucket
        prior_weight_w = 1500.0
        sum_sol_by_h: dict[int, float] = {h: 0.0 for h in range(24)}
        sum_act_by_h: dict[int, float] = {h: 0.0 for h in range(24)}

        total_sol = 0.0
        total_act = 0.0

        for h, sol_w, act_w in pairs_all:
            if 0 <= h <= 23:
                sum_sol_by_h[h] += sol_w
                sum_act_by_h[h] += act_w
                total_sol += sol_w
                total_act += act_w

        for h in range(24):
            ratio_h = (sum_act_by_h[h] + prior_weight_w) / (sum_sol_by_h[h] + prior_weight_w)
            self.hourly_ratios[h] = round(max(0.25, min(1.40, ratio_h)), 3)

        global_prior_w = 10000.0
        raw_global = (total_act + global_prior_w) / (total_sol + global_prior_w)
        self.global_ratio = round(max(0.40, min(1.35, raw_global)), 3)

        # 2. Train non-linear Random Forest model if sufficient historical samples exist
        if len(X_all) >= 24:
            if HAS_SKLEARN:
                X_arr = np.array(X_all, dtype=np.float64)
                y_arr = np.array(y_all, dtype=np.float64)
                rf = RandomForestRegressor(
                    n_estimators=40,
                    max_depth=8,
                    min_samples_leaf=3,
                    random_state=42,
                    n_jobs=1,
                )
                rf.fit(X_arr, y_arr)
                self.rf_model = rf
            else:
                rf_native = _NativeRandomForestRegressor(n_estimators=20, max_depth=6, seed=42)
                rf_native.fit(X_all, y_all)
                self.rf_model = rf_native

            # Evaluate accuracy on dataset
            preds = [
                self.calibrate_power_watts(
                    datetime(2026, int(row[4]), 15, int(row[1]), 0),
                    row[0],
                    row[7],
                )
                for row in X_all
            ]
            n = len(y_all)
            mean_act = sum(y_all) / n if n > 0 else 1000.0
            mae = sum(abs(p - t) for p, t in zip(preds, y_all)) / n
            self.mae_watts = round(mae, 1)
            self.accuracy_pct = round(
                max(0.0, min(100.0, 100.0 * (1.0 - mae / max(mean_act, 300.0)))), 1
            )
        else:
            self.rf_model = None
            self.mae_watts = 0.0
            self.accuracy_pct = 100.0

        self.training_samples = len(X_all)
        self.is_trained = True
        self.last_trained = datetime.now()
        self.save_to_disk()

        _LOGGER.info(
            "EMS Solar Calibration Model trained on %d daytime hours (Global ratio: %.3f, MAE: %.1f W)",
            self.training_samples,
            self.global_ratio,
            self.mae_watts,
        )
        return {
            "solar_samples": self.training_samples,
            "global_ratio": self.global_ratio,
            "hourly_ratios": self.hourly_ratios,
            "solar_mae_watts": self.mae_watts,
            "solar_accuracy_pct": self.accuracy_pct,
        }

    def calibrate_power_watts(
        self,
        dt: datetime,
        solcast_watts: float,
        outdoor_temp: float = 15.0,
    ) -> float:
        """Return auto-calibrated solar power forecast (W) from raw Solcast power."""
        if solcast_watts <= 10.0:
            return 0.0

        h_ratio = self.hourly_ratios.get(dt.hour, self.global_ratio)
        bayesian_pred = solcast_watts * h_ratio

        if self.rf_model is not None and self.training_samples >= 24:
            try:
                vec = [build_solar_feature_vector(dt, solcast_watts, outdoor_temp)]
                rf_pred = float(self.rf_model.predict(vec)[0])
                # 50/50 blend between Bayesian hourly shading ratio and RF non-linear regressor
                blended = 0.5 * bayesian_pred + 0.5 * rf_pred
                # Bound within reasonable physical limits [0.2 * solcast, 1.45 * solcast]
                bounded = max(0.2 * solcast_watts, min(1.45 * solcast_watts, blended))
                return round(max(0.0, bounded), 1)
            except Exception:
                pass

        return round(max(0.0, bayesian_pred), 1)

    def calibrate_daily_forecasts(
        self,
        now: datetime,
        raw_today_rem_kwh: float,
        raw_tomorrow_kwh: float,
        raw_day_after_kwh: float,
    ) -> tuple[float, float, float]:
        """Apply learned installation calibration to daily remaining (J+0) and J+1/J+2 kWh."""
        # Remaining hours of daylight today (between max(7, now.hour) and 19)
        rem_hours = [h for h in range(max(7, now.hour), 20)]
        if rem_hours:
            rem_ratio = sum(self.hourly_ratios.get(h, self.global_ratio) for h in rem_hours) / len(
                rem_hours
            )
        else:
            rem_ratio = self.global_ratio

        cal_today = round(max(0.0, raw_today_rem_kwh * rem_ratio), 2)
        cal_tomorrow = round(max(0.0, raw_tomorrow_kwh * self.global_ratio), 2)
        cal_day_after = round(max(0.0, raw_day_after_kwh * self.global_ratio), 2)
        return cal_today, cal_tomorrow, cal_day_after
