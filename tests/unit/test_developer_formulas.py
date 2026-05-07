"""Unit tests for safer_model/formulas/developer.py (Equations 1–9)."""
import math

import pytest

from safer_model.formulas.developer import (
    code_dependencies_risk,
    code_specifications_risk,
    developer_expertise,
    developer_risk,
    programming_language_risk,
    weight_code_dependency,
    weight_code_length,
    weight_code_specifications,
    weight_programming_language,
)


class TestEq1CodeDependenciesRisk:
    def test_normal(self):
        assert code_dependencies_risk(28) == 28.0

    def test_zero_dependencies(self):
        # Section VI-B: no dependencies → R_CD = 0
        assert code_dependencies_risk(0) == 0.0

    def test_sensitivity_factor(self):
        # Section VI-A
        assert code_dependencies_risk(10, sensitivity=2.0) == 20.0

    def test_default_sensitivity(self):
        assert code_dependencies_risk(5, sensitivity=1.0) == 5.0


class TestEq3WeightCodeLength:
    def test_normal(self):
        # Paper worked example: 96912 / 129 ≈ 751.2558
        result = weight_code_length(96912, 129)
        assert abs(result - 751.2558) < 0.001

    def test_zero_software_count(self):
        # Developer with no prior software → benefit of the doubt → 0
        assert weight_code_length(1000, 0) == 0.0

    def test_zero_vulns(self):
        # Developer with prior software but no vulnerabilities → 0
        assert weight_code_length(0, 50) == 0.0


class TestEq2CodeSpecificationsRisk:
    def test_normal(self):
        # Paper: 751.2558 * 304 = 228381.8
        r = code_specifications_risk(751.2558, 304)
        assert abs(r - 228381.8) < 1.0

    def test_zero_w_lc(self):
        assert code_specifications_risk(0.0, 1000) == 0.0

    def test_zero_length(self):
        assert code_specifications_risk(100.0, 0) == 0.0


class TestEq4ProgrammingLanguageRisk:
    def test_full_experience(self):
        # E_DS == E_DA → R_PL = 1 - 1 = 0 (paper worked example)
        assert programming_language_risk(2.0, 2.0) == 0.0

    def test_no_experience(self):
        # E_DA = 0 → R_PL = 1
        assert programming_language_risk(0.0, 0.0) == 1.0

    def test_partial_experience(self):
        # 50% language-specific experience → R_PL = 0.5
        assert programming_language_risk(1.0, 2.0) == 0.5

    def test_range(self):
        r = programming_language_risk(3.0, 10.0)
        assert 0.0 <= r <= 1.0


class TestEq8DeveloperExpertise:
    def test_normal(self):
        # Paper: 33/129 ≈ 0.255814
        result = developer_expertise(33, 129)
        assert abs(result - 0.255814) < 0.0001

    def test_zero_total(self):
        assert developer_expertise(10, 0) == 0.0

    def test_full_expertise(self):
        assert developer_expertise(10, 10) == 1.0

    def test_range(self):
        r = developer_expertise(5, 20)
        assert 0.0 <= r <= 1.0


class TestEq6WeightCodeDependency:
    def test_full_coverage(self):
        # Paper worked example: 1 - 0.99 = 0.01
        assert abs(weight_code_dependency(0.99) - 0.01) < 1e-9

    def test_no_coverage(self):
        assert weight_code_dependency(0.0) == 1.0

    def test_half_coverage(self):
        assert weight_code_dependency(0.5) == 0.5


class TestEq7WeightCodeSpecifications:
    def test_normal(self):
        # Paper: exp(-0.255814) ≈ 0.77428
        result = weight_code_specifications(0.255814)
        assert abs(result - 0.77428) < 0.0001

    def test_zero_expertise(self):
        # exp(0) = 1
        assert weight_code_specifications(0.0) == 1.0

    def test_full_expertise(self):
        # exp(-1) ≈ 0.3679
        assert abs(weight_code_specifications(1.0) - math.exp(-1)) < 1e-9

    def test_always_positive(self):
        assert weight_code_specifications(0.5) > 0


class TestEq9WeightProgrammingLanguage:
    def test_normal(self):
        # Paper: |1 - (0.01 + 0.77428)| = |1 - 0.78428| = 0.21572
        result = weight_programming_language(0.01, 0.77428)
        assert abs(result - 0.2157) < 0.001

    def test_weights_sum_to_one(self):
        w_cd = weight_code_dependency(0.99)          # 0.01
        e_db = developer_expertise(33, 129)          # 0.255814
        w_cs = weight_code_specifications(e_db)      # 0.77428
        w_pl = weight_programming_language(w_cd, w_cs)
        total = w_cd + w_cs + w_pl
        assert abs(total - 1.0) < 1e-6

    def test_always_non_negative(self):
        assert weight_programming_language(0.3, 0.5) >= 0.0


class TestEq5DeveloperRisk:
    def test_normal(self):
        # Paper: 0.01*28 + 0.77428*228381.8 + 0.2157*0 ≈ 176831
        w_cd = 0.01
        r_cd = 28.0
        w_cs = 0.77428
        r_cs = 228381.8
        w_pl = 0.2157
        r_pl = 0.0
        result = developer_risk(w_cd, r_cd, w_cs, r_cs, w_pl, r_pl)
        assert abs(result - 176831.46) < 100   # tolerance for rounding

    def test_proportionality(self):
        # Doubling r_cs should roughly double the result (when dominated by CS term)
        r1 = developer_risk(0.0, 0, 1.0, 1000, 0.0, 0)
        r2 = developer_risk(0.0, 0, 1.0, 2000, 0.0, 0)
        assert abs(r2 - 2 * r1) < 1e-9
