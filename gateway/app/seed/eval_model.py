"""
Evaluates the trained Isolation Forest on a validation set of normal and attack traffic,
computing Precision, Recall, and FPR. Also performs a simple threshold sweep.
"""
from __future__ import annotations
import numpy as np
import joblib
import pathlib
from sklearn.metrics import precision_score, recall_score, confusion_matrix

from app.seed.train_baseline import generate_normal_traffic

def generate_attack_traffic(n_samples: int = 400, seed: int = 1337) -> np.ndarray:
    rng = np.random.default_rng(seed)
    
    # Attack traffic: high freq, new endpoints, new geo/device, weird hours, large payload
    request_frequency = np.clip(rng.normal(25, 10, n_samples), 10, 60)
    endpoint_novelty = rng.choice([0, 1], size=n_samples, p=[0.2, 0.8]) # 80% novel
    geo_change = rng.choice([0, 1], size=n_samples, p=[0.1, 0.9])
    device_change = rng.choice([0, 1], size=n_samples, p=[0.1, 0.9])
    time_of_day_dev = np.clip(rng.normal(0.8, 0.2, n_samples), 0, 1)
    payload_zscore = np.clip(np.abs(rng.normal(3.5, 1.5, n_samples)), 0, 10)
    token_age = np.clip(rng.normal(10, 5, n_samples), 0, 3600)
    
    X = np.column_stack([
        request_frequency, endpoint_novelty, geo_change, device_change,
        time_of_day_dev, payload_zscore, token_age,
    ])
    return X

def evaluate_model():
    model_path = pathlib.Path(__file__).parent / "model_v1.pkl"
    if not model_path.exists():
        print("Model not found. Train it first.")
        return
        
    model = joblib.load(model_path)
    
    X_normal = generate_normal_traffic(1000, seed=101)
    y_normal = np.ones(1000) # 1 = normal
    
    X_attack = generate_attack_traffic(200, seed=102)
    y_attack = -np.ones(200) # -1 = anomaly
    
    X = np.vstack([X_normal, X_attack])
    y_true = np.concatenate([y_normal, y_attack])
    
    # decision_function: higher = normal, lower = anomaly
    scores = model.decision_function(X)
    
    print(f"{'Threshold':>10} | {'Precision':>9} | {'Recall':>9} | {'FPR':>9}")
    print("-" * 45)
    
    # Sweep thresholds (in decision_function scale)
    for threshold in np.linspace(-0.15, 0.15, 10):
        y_pred = np.where(scores > threshold, 1, -1)
        
        # We want to detect anomalies (y == -1). 
        # So for evaluation, let's treat -1 as "positive class" (attack)
        y_true_anomaly = (y_true == -1)
        y_pred_anomaly = (y_pred == -1)
        
        precision = precision_score(y_true_anomaly, y_pred_anomaly, zero_division=0)
        recall = recall_score(y_true_anomaly, y_pred_anomaly, zero_division=0)
        tn, fp, fn, tp = confusion_matrix(y_true_anomaly, y_pred_anomaly, labels=[False, True]).ravel()
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        
        print(f"{threshold:10.3f} | {precision:9.3f} | {recall:9.3f} | {fpr:9.3f}")

if __name__ == "__main__":
    evaluate_model()
