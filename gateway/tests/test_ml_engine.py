"""
Unit tests for the ML engine (gateway/app/ml_engine.py).

Tests validate:
  - Model trains without errors
  - Normal feature vectors produce low anomaly scores
  - Anomalous feature vectors produce high anomaly scores
  - Score is always in [0, 100] range
  - Score is a float (not NaN or inf)
"""
import pytest
import math
from app.models import FeatureVector
from app.ml_engine import MLEngine


@pytest.fixture(scope="module")
def engine():
    """Single ML engine instance for all tests (training is deterministic)."""
    return MLEngine()


def _normal_fv() -> FeatureVector:
    """A feature vector representing completely normal behaviour."""
    return FeatureVector(
        request_frequency_per_min=2.0,
        endpoint_novelty=0.0,
        geo_change=0.0,
        device_change=0.0,
        time_of_day_deviation=0.1,
        payload_size_zscore=0.2,
        token_age_seconds=600.0,
    )


def _anomalous_fv() -> FeatureVector:
    """A feature vector representing highly anomalous behaviour."""
    return FeatureVector(
        request_frequency_per_min=50.0,
        endpoint_novelty=1.0,
        geo_change=1.0,
        device_change=1.0,
        time_of_day_deviation=0.9,
        payload_size_zscore=5.0,
        token_age_seconds=10.0,
    )


class TestMLEngine:

    def test_engine_initializes(self, engine):
        """Engine should train the model during __init__ without errors."""
        assert engine.model is not None
        assert hasattr(engine.model, "decision_function")

    def test_normal_traffic_scores_low(self, engine):
        """Normal traffic should produce a low anomaly score."""
        fv = _normal_fv()
        score = engine.score(fv)
        assert score < 40, f"Normal traffic should score < 40, got {score}"

    def test_anomalous_traffic_scores_high(self, engine):
        """Clearly anomalous traffic should produce a high anomaly score."""
        fv = _anomalous_fv()
        score = engine.score(fv)
        assert score > 40, f"Anomalous traffic should score > 40, got {score}"

    def test_score_range_normal(self, engine):
        """Score must be in [0, 100]."""
        fv = _normal_fv()
        score = engine.score(fv)
        assert 0.0 <= score <= 100.0, f"Score out of range: {score}"

    def test_score_range_anomalous(self, engine):
        """Score must be in [0, 100] even for extreme inputs."""
        fv = _anomalous_fv()
        score = engine.score(fv)
        assert 0.0 <= score <= 100.0, f"Score out of range: {score}"

    def test_score_is_finite(self, engine):
        """Score must not be NaN or infinity."""
        fv = _normal_fv()
        score = engine.score(fv)
        assert not math.isnan(score), "Score is NaN"
        assert not math.isinf(score), "Score is infinite"

    def test_score_is_float(self, engine):
        """Score should be a float."""
        fv = _normal_fv()
        score = engine.score(fv)
        assert isinstance(score, float), f"Score should be float, got {type(score)}"

    def test_anomalous_scores_higher_than_normal(self, engine):
        """Anomalous feature vectors should score consistently higher than normal ones."""
        normal_score = engine.score(_normal_fv())
        anomalous_score = engine.score(_anomalous_fv())
        assert anomalous_score > normal_score, \
            f"Anomalous ({anomalous_score}) should score higher than normal ({normal_score})"

    def test_zero_vector(self, engine):
        """A zero feature vector should not crash the engine."""
        fv = FeatureVector(
            request_frequency_per_min=0.0,
            endpoint_novelty=0.0,
            geo_change=0.0,
            device_change=0.0,
            time_of_day_deviation=0.0,
            payload_size_zscore=0.0,
            token_age_seconds=0.0,
        )
        score = engine.score(fv)
        assert 0.0 <= score <= 100.0, f"Zero vector score out of range: {score}"

    def test_extreme_vector(self, engine):
        """An extreme feature vector should not crash the engine."""
        fv = FeatureVector(
            request_frequency_per_min=1000.0,
            endpoint_novelty=1.0,
            geo_change=1.0,
            device_change=1.0,
            time_of_day_deviation=1.0,
            payload_size_zscore=100.0,
            token_age_seconds=99999.0,
        )
        score = engine.score(fv)
        assert 0.0 <= score <= 100.0, f"Extreme vector score out of range: {score}"
