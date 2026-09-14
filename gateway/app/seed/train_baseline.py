"""
Generates synthetic "normal" behavioural traffic and trains the Isolation
Forest on it. Model is trained on the behavioural feature vector
representing standard traffic patterns.

Feature order MUST match app.features.feature_vector_to_array:
  [request_frequency_per_min, endpoint_novelty, geo_change, device_change,
   time_of_day_deviation, payload_size_zscore, token_age_seconds]
"""
from __future__ import annotations
import numpy as np
from sklearn.ensemble import IsolationForest

N_SAMPLES = 4000
RANDOM_STATE = 42


def generate_normal_traffic(n_samples: int = N_SAMPLES, seed: int = RANDOM_STATE) -> np.ndarray:
    rng = np.random.default_rng(seed)

    # Normal, everyday behaviour: low frequency, mostly-seen endpoints,
    # rarely a new geo/device, small time-of-day drift, near-baseline
    # payload sizes, and tokens that are a healthy age (not brand new,
    # not stale).
    request_frequency = np.clip(rng.normal(3, 2, n_samples), 0, 12)
    endpoint_novelty = rng.choice([0, 1], size=n_samples, p=[0.93, 0.07])
    geo_change = rng.choice([0, 1], size=n_samples, p=[0.97, 0.03])
    device_change = rng.choice([0, 1], size=n_samples, p=[0.95, 0.05])
    time_of_day_dev = np.clip(rng.normal(0.15, 0.15, n_samples), 0, 1)
    payload_zscore = np.clip(np.abs(rng.normal(0, 1, n_samples)), 0, 4)
    token_age = np.clip(rng.normal(1800, 900, n_samples), 30, 3600 * 6)

    X = np.column_stack([
        request_frequency, endpoint_novelty, geo_change, device_change,
        time_of_day_dev, payload_zscore, token_age,
    ])
    return X


def train_isolation_forest() -> IsolationForest:
    X = generate_normal_traffic()
    model = IsolationForest(
        n_estimators=150,
        contamination=0.05,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X)
    return model


if __name__ == "__main__":
    import joblib
    import pathlib

    model = train_isolation_forest()
    out = pathlib.Path(__file__).parent / "isolation_forest.joblib"
    joblib.dump(model, out)
    print(f"Trained Isolation Forest on {N_SAMPLES} synthetic normal samples -> {out}")
