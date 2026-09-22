"""
Unit tests for the decision engine (gateway/app/decision.py).

Tests validate:
  - tier_for_score mapping with default thresholds
  - tier_for_score with custom thresholds
  - Boundary values (exactly on threshold)
  - Score clamping at 100
"""
import pytest
from app.decision import tier_for_score


class TestTierForScore:
    """Tests for the score -> tier mapping function."""

    def test_low_score_is_allow(self):
        thresholds = {"allow": 30, "step_up": 60, "restrict": 85}
        assert tier_for_score(0.0, thresholds) == "allow"
        assert tier_for_score(15.0, thresholds) == "allow"
        assert tier_for_score(29.99, thresholds) == "allow"

    def test_exact_allow_boundary(self):
        """Score exactly at the allow threshold should be 'allow'."""
        thresholds = {"allow": 30, "step_up": 60, "restrict": 85}
        assert tier_for_score(30.0, thresholds) == "allow"

    def test_step_up_range(self):
        thresholds = {"allow": 30, "step_up": 60, "restrict": 85}
        assert tier_for_score(31.0, thresholds) == "step_up"
        assert tier_for_score(45.0, thresholds) == "step_up"
        assert tier_for_score(60.0, thresholds) == "step_up"

    def test_restrict_range(self):
        thresholds = {"allow": 30, "step_up": 60, "restrict": 85}
        assert tier_for_score(61.0, thresholds) == "restrict"
        assert tier_for_score(75.0, thresholds) == "restrict"
        assert tier_for_score(85.0, thresholds) == "restrict"

    def test_revoke_range(self):
        thresholds = {"allow": 30, "step_up": 60, "restrict": 85}
        assert tier_for_score(85.01, thresholds) == "revoke"
        assert tier_for_score(90.0, thresholds) == "revoke"
        assert tier_for_score(100.0, thresholds) == "revoke"

    def test_custom_thresholds(self):
        """Verify tier_for_score respects dynamically changed thresholds."""
        strict = {"allow": 15, "step_up": 40, "restrict": 70}
        assert tier_for_score(14.0, strict) == "allow"
        assert tier_for_score(16.0, strict) == "step_up"
        assert tier_for_score(41.0, strict) == "restrict"
        assert tier_for_score(71.0, strict) == "revoke"

    def test_lenient_thresholds(self):
        """Very lenient thresholds should shift all boundaries up."""
        lenient = {"allow": 50, "step_up": 80, "restrict": 95}
        assert tier_for_score(49.0, lenient) == "allow"
        assert tier_for_score(51.0, lenient) == "step_up"
        assert tier_for_score(81.0, lenient) == "restrict"
        assert tier_for_score(96.0, lenient) == "revoke"

    def test_zero_score(self):
        thresholds = {"allow": 30, "step_up": 60, "restrict": 85}
        assert tier_for_score(0.0, thresholds) == "allow"

    def test_max_score(self):
        thresholds = {"allow": 30, "step_up": 60, "restrict": 85}
        assert tier_for_score(100.0, thresholds) == "revoke"

    def test_missing_threshold_uses_defaults(self):
        """If a threshold key is missing, the .get() defaults should apply."""
        partial = {"allow": 30}  # missing step_up and restrict
        assert tier_for_score(15.0, partial) == "allow"
        assert tier_for_score(35.0, partial) == "step_up"  # default 60
        assert tier_for_score(65.0, partial) == "restrict"  # default 85
        assert tier_for_score(90.0, partial) == "revoke"
