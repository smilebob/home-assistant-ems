"""Scikit-learn (with built-in Regression Tree Ensemble fallback) Load & PAC Predictor."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import math
import os
import pickle
import random
from typing import Any

from .dataset_builder import build_feature_vector

_LOGGER = logging.getLogger(__name__)

try:
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor

    HAS_SKLEARN = True
except ImportError:
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

        # Sample candidate features (Random Forest feature bagging)
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
            if row[node["feat"]] <= node["thresh"]:
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
        self._online_X: list[list[float]] = []
        self._online_y: list[float] = []

    def load_from_disk(self) -> bool:
        """Load persisted model if available."""
        if not self.storage_path or not os.path.exists(self.storage_path):
            return False
        try:
            with open(self.storage_path, "rb") as f:
                saved = pickle.load(f)
            self.model = saved.get("model")
            self.last_trained = saved.get("last_trained")
            self.training_samples = saved.get("training_samples", 0)
            self.mae_score = saved.get("mae_score")
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
                        "model": self.model,
                        "last_trained": self.last_trained,
                        "training_samples": self.training_samples,
                        "mae_score": self.mae_score,
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
        X_list = list(X) if X is not None else []
        y_list = list(y) if y is not None else []

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
            preds = rf.predict(X_arr)
            mae = float(np.mean(np.abs(preds - y_arr)))
            self.model = rf
        else:
            rf_native = _NativeRandomForestRegressor(n_estimators=25, max_depth=8, seed=42)
            rf_native.fit(X_list, y_list)
            preds = rf_native.predict(X_list)
            mae = sum(abs(p - t) for p, t in zip(preds, y_list)) / len(y_list)
            self.model = rf_native

        self.is_trained = True
        self.last_trained = datetime.now()
        self.training_samples = len(X_list)
        self.mae_score = round(mae, 1)
        self.save_to_disk()

        _LOGGER.info(
            "EMS ML Model trained on %d hourly samples (MAE: %.1f W, backend: %s)",
            self.training_samples,
            self.mae_score,
            "scikit-learn" if HAS_SKLEARN else "native-rf",
        )
        return {
            "samples": self.training_samples,
            "mae_watts": self.mae_score,
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
        pred = float(self.model.predict(vec)[0])
        return max(150.0, round(pred, 1))

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
