"""Unit tests for safer_model/formulas/user.py (Equation 11)."""
import pytest

from safer_model.formulas.user import user_risk


class TestEq11UserRisk:
    def test_normal(self):
        # Paper: 1 - 7153/20455 ≈ 0.6503
        result = user_risk(7153.0, 20455)
        assert abs(result - 0.6503) < 0.001

    def test_zero_downloads(self):
        # No downloads → max risk = 1
        assert user_risk(0.0, 0) == 1.0

    def test_all_satisfied(self):
        # All downloaders rated → R_UR = 0
        assert user_risk(100.0, 100) == 0.0

    def test_none_satisfied(self):
        # No ratings → R_UR = 1
        assert user_risk(0.0, 1000) == 1.0

    def test_range(self):
        r = user_risk(500.0, 1000)
        assert 0.0 <= r <= 1.0
