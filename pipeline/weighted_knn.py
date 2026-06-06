"""
WeightedKNNRegressor — standalone module so the class can be pickled and
unpickled from any entry-point script (not just train_stuff_plus_model.py).

Pickle stores class references by module path.  When WeightedKNNRegressor
lives here it is always stored as ``weighted_knn.WeightedKNNRegressor``,
which Python can resolve regardless of which pipeline script loads the bundle.
"""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.neighbors import NearestNeighbors


class WeightedKNNRegressor(BaseEstimator, RegressorMixin):
    """
    KNN regressor weighting each neighbour by (1/distance) x sqrt(pitch_count).

    ``sample_weight`` passed to ``fit()`` is treated as raw pitch counts.
    Internally it is sqrt-damped so high-count pitchers have elevated but not
    overwhelming influence -- a 500-pitch row is 5x more influential than a
    20-pitch row, not 25x.

    Uses sklearn BallTree for efficient nearest-neighbour lookup.
    """

    def __init__(self, n_neighbors: int = 50) -> None:
        self.n_neighbors = n_neighbors

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> "WeightedKNNRegressor":
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        self.X_train_ = X
        self.y_train_ = y

        if sample_weight is not None:
            sw = np.asarray(sample_weight, dtype=np.float64)
            self.sample_weight_ = np.sqrt(np.maximum(sw, 1.0))
        else:
            self.sample_weight_ = np.ones(len(y), dtype=np.float64)

        k = min(self.n_neighbors, len(y))
        self._nn = NearestNeighbors(
            n_neighbors=k,
            algorithm="ball_tree",
            metric="euclidean",
            n_jobs=-1,
        )
        self._nn.fit(X)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        k = min(self.n_neighbors, len(self.y_train_))
        distances, indices = self._nn.kneighbors(X, n_neighbors=k)

        inv_dist    = 1.0 / (distances + 1e-10)
        sw          = self.sample_weight_[indices]
        weights     = inv_dist * sw
        y_neighbors = self.y_train_[indices]

        w_sum = weights.sum(axis=1)
        w_sum = np.maximum(w_sum, 1e-10)
        return (weights * y_neighbors).sum(axis=1) / w_sum
