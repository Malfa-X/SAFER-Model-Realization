"""Unit tests for safer_model/formulas/publisher.py (Equation 10)."""
import pytest

from safer_model.formulas.publisher import publisher_risk


class TestEq10PublisherRisk:
    def test_normal(self):
        # Paper: (2/123) * (1/0.08424) ≈ 0.1930
        result = publisher_risk(2.0, 123, 0.08424)
        assert abs(result - 0.1930) < 0.001

    def test_new_publisher_zero_count(self):
        # Section VI-C: E_PX = 0 → R_PB = 1
        assert publisher_risk(5.0, 0, 0.5) == 1.0

    def test_new_publisher_zero_freq(self):
        # F_UP = 0 → R_PB = 1 (defensive guard)
        assert publisher_risk(5.0, 10, 0.0) == 1.0

    def test_high_frequency_low_risk(self):
        r_high = publisher_risk(5.0, 10, 1.0)   # F_UP = 1
        r_low  = publisher_risk(5.0, 10, 0.1)   # F_UP = 0.1
        assert r_low > r_high   # lower frequency → higher risk

    def test_more_experience_lower_risk(self):
        r_less = publisher_risk(1.0, 10, 0.5)
        r_more = publisher_risk(1.0, 100, 0.5)
        # More software published → lower E_PY/E_PX ratio → lower risk
        assert r_more < r_less
