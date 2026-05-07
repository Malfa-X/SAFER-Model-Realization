"""Unit tests for safer_model/formulas/final_score.py (Equations 15–19)."""
import math

import pytest

from safer_model.formulas.final_score import (
    final_risk_score,
    final_risk_with_penalty,
    weight_developer,
    weight_publisher,
    weight_user,
)


class TestEq17WeightDeveloper:
    def test_normal(self):
        # Paper: 1/2003 ≈ 4.99e-4
        result = weight_developer(2003)
        assert abs(result - (1 / 2003)) < 1e-8

    def test_zero_forks(self):
        # No forks → maximum weight = 1
        assert weight_developer(0) == 1.0

    def test_many_forks_low_weight(self):
        assert weight_developer(10000) == 1 / 10000


class TestEq18WeightPublisher:
    def test_normal(self):
        # Paper: (135+1)/(7421+135+2) = 136/7558 ≈ 0.01799
        result = weight_publisher(135, 7421)
        assert abs(result - (136 / 7558)) < 1e-6

    def test_no_vulnerabilities(self):
        # V_U=0, V_R=0 → (0+1)/(0+0+2) = 0.5
        assert weight_publisher(0, 0) == 0.5

    def test_all_unresolved(self):
        # V_U=100, V_R=0 → 101/102
        result = weight_publisher(100, 0)
        assert abs(result - 101 / 102) < 1e-9

    def test_range(self):
        r = weight_publisher(50, 100)
        assert 0.0 < r < 1.0


class TestEq16WeightUser:
    def test_constraint(self):
        # w_DEV + w_PB + w_UR must = 1
        w_dev = weight_developer(2003)
        w_pb = weight_publisher(135, 7421)
        w_ur = weight_user(w_dev, w_pb)
        assert abs(w_dev + w_pb + w_ur - 1.0) < 1e-9

    def test_paper_example(self):
        w_dev = 1 / 2003
        w_pb = 136 / 7558
        w_ur = weight_user(w_dev, w_pb)
        assert abs(w_ur - 0.9815) < 0.001


class TestEq15FinalRiskScore:
    def test_paper_example(self):
        # Paper: R_F ≈ 0.3755 (full precision gives ~0.391)
        w_dev = 1 / 2003
        r_dev = 176831.46
        w_pb = 136 / 7558
        r_pb = 0.1930
        w_ur = weight_user(w_dev, w_pb)
        r_ur = 0.6503
        result = final_risk_score(w_dev, r_dev, w_pb, r_pb, w_ur, r_ur)
        # Allow tolerance of ±0.02 (paper rounds intermediate values)
        assert abs(result - 0.3755) < 0.03

    def test_range(self):
        r = final_risk_score(0.001, 100000, 0.02, 0.5, 0.979, 0.5)
        assert 0.0 < r < 1.0

    def test_large_r_dev_increases_score(self):
        # Larger R_DEV (more developer risk) → higher final score
        r_low = final_risk_score(0.001, 50000, 0.02, 0.3, 0.979, 0.5)
        r_hi = final_risk_score(0.001, 200000, 0.02, 0.3, 0.979, 0.5)
        assert r_hi > r_low

    def test_sigmoid_shape(self):
        # At combined = 100 (= 4/0.04), sigmoid should be ≈ 0.5
        # combined = 100: 1 / (1 + exp(4 - 0.04*100)) = 1/(1+exp(0)) = 0.5
        result = final_risk_score(1.0, 100, 0.0, 0.0, 0.0, 0.0)
        assert abs(result - 0.5) < 1e-9


class TestEq19FinalRiskWithPenalty:
    def test_case_c_no_penalty_below_threshold(self):
        # R_F = 0.3 (≤ 0.5) → no penalty applied
        assert final_risk_with_penalty(0.3, 0.1) == 0.3

    def test_case_a_penalty_applied(self):
        # R_F = 0.6 > 0.5, R_F + P = 0.7 < 1 → R_FP = 0.7
        assert abs(final_risk_with_penalty(0.6, 0.1) - 0.7) < 1e-9

    def test_case_b_capped_at_one(self):
        # R_F = 0.95 ≥ (1 - 0.1) = 0.9 → R_FP = 1
        assert final_risk_with_penalty(0.95, 0.1) == 1.0

    def test_case_b_sum_exceeds_one(self):
        # R_F = 0.6 + P = 0.5 → sum = 1.1 → Case (a) condition fails → Case (b)
        # R_F >= 1 - 0.5 = 0.5 → True → R_FP = 1
        assert final_risk_with_penalty(0.6, 0.5) == 1.0

    def test_paper_example_no_penalty(self):
        # R_F ≈ 0.3755 < 0.5 → R_FP = R_F (case c)
        r_f = 0.3755
        p = 0.0283
        assert final_risk_with_penalty(r_f, p) == r_f
