"""Unit tests for safer_model/formulas/penalty.py (Equations 12–14)."""
import pytest

from safer_model.formulas.penalty import (
    CONTEXT_AUTOMATION,
    CONTEXT_OTHER,
    CONTEXT_SECURITY,
    CONTEXT_VALUES,
    penalty,
)


class TestContextConstants:
    def test_values(self):
        assert CONTEXT_SECURITY == 0.2
        assert CONTEXT_AUTOMATION == 0.3
        assert CONTEXT_OTHER == 0.5

    def test_sum_equals_one(self):
        # Eq. 14
        assert abs(sum(CONTEXT_VALUES) - 1.0) < 1e-9


class TestEq12Penalty:
    def test_no_vulnerabilities(self):
        # V_UP = 0 → P = 1 - C_TXT^0 = 0
        assert penalty(CONTEXT_SECURITY, 0.0) == 0.0
        assert penalty(CONTEXT_OTHER, 0.0) == 0.0

    def test_all_unresolved_security(self):
        # V_UP = 1 → P = 1 - 0.2 = 0.8
        assert abs(penalty(CONTEXT_SECURITY, 1.0) - 0.8) < 1e-9

    def test_all_unresolved_other(self):
        # V_UP = 1 → P = 1 - 0.5 = 0.5
        assert abs(penalty(CONTEXT_OTHER, 1.0) - 0.5) < 1e-9

    def test_paper_worked_example(self):
        # V_UP = 135/7556 ≈ 0.017867 → P = 1 - 0.2^0.017867 ≈ 0.0283
        v_up = 135 / 7556
        result = penalty(CONTEXT_SECURITY, v_up)
        assert abs(result - 0.0283) < 0.001

    def test_security_stricter_than_other(self):
        # For the same V_UP, security software gets higher penalty
        v_up = 0.5
        p_sec = penalty(CONTEXT_SECURITY, v_up)
        p_oth = penalty(CONTEXT_OTHER, v_up)
        assert p_sec > p_oth

    def test_range(self):
        for ctx in CONTEXT_VALUES:
            for v_up in [0.0, 0.25, 0.5, 0.75, 1.0]:
                p = penalty(ctx, v_up)
                assert 0.0 <= p <= 1.0
