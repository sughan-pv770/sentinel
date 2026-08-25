"""
ML layer (§4.4.2): lightweight unsupervised anomaly detector. Trained once
at process startup on synthetic normal traffic (no labelled attack data
needed for the hackathon MVP -- matches the master doc's design note).

sklearn's IsolationForest.decision_function returns higher = more normal,
lower/negative = more anomalous. We invert and rescale into a 0-100
"how anomalous is this" score so it composes cleanly with the rule score.
"""
from __future__ import annotations
import numpy as np
from app.seed.train_baseline import train_isolation_forest
from app.features import feature_vector_to_array
from app.models import FeatureVector


class MLEngine:
    def __init__(self):
        self.model = train_isolation_forest()
        # decision_function on the training distribution roughly spans
        # about [-0.15, 0.25]; we calibrate the rescale against that.
        self._lo, self._hi = -0.20, 0.25

    def score(self, fv: FeatureVector) -> float:
        x = np.array([feature_vector_to_array(fv)])
        raw = float(self.model.decision_function(x)[0])  # higher = normal
        # invert: lower raw -> higher anomaly
        anomaly = (self._hi - raw) / (self._hi - self._lo)
        anomaly = max(0.0, min(1.0, anomaly))
        return round(anomaly * 100, 2)


_engine: MLEngine | None = None


def get_ml_engine() -> MLEngine:
    global _engine
    if _engine is None:
        _engine = MLEngine()
    return _engine
