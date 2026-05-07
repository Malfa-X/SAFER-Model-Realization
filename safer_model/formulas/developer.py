"""
Developer-based risk formulas — Equations 1–9.

All functions are pure (no side effects). They accept numeric primitives only.
Callers are responsible for aggregating cross-dataset sums before calling.

Equation reference (arXiv:2408.02876v2):
    Eq. 1  code_dependencies_risk
    Eq. 2  code_specifications_risk
    Eq. 3  weight_code_length
    Eq. 4  programming_language_risk
    Eq. 5  developer_risk
    Eq. 6  weight_code_dependency
    Eq. 7  weight_code_specifications
    Eq. 8  developer_expertise
    Eq. 9  weight_programming_language
"""
from __future__ import annotations

import math


def code_dependencies_risk(
    dependencies: int,
    sensitivity: float = 1.0,
) -> float:
    """
    Eq. 1 (Section V-A-1), with optional Section VI-A sensitivity factor.

        R_CD = sensitivity * D

    Parameters
    ----------
    dependencies:
        Number of 3rd-party software packages the code depends on (D).
        When the software has no dependencies (Section VI-B), D = 0 → R_CD = 0.
    sensitivity:
        Organisation-defined multiplier (Section VI-A). Default 1.0 (no scaling).
    """
    return float(dependencies) * sensitivity


def weight_code_length(
    total_vulns_across_dev_software: int,
    total_software_by_dev: int,
) -> float:
    """
    Eq. 3 (Section V-A-2) — historical vulnerability rate of the developer.

        w_LC = [∑_j ∑_i V_D_{j,Si}] / [∑_j |S_D_j|]

    This is the average number of known vulnerabilities per software
    developed by the same developer(s).

    Parameters
    ----------
    total_vulns_across_dev_software:
        Sum of known_vulnerabilities for all software developed by developer j
        (summed across all developers j who worked on the target software).
        Corresponds to the numerator ∑_j ∑_i V_D_{j,Si,tk}.
    total_software_by_dev:
        Total count of software developed by developer j, summed across all
        developers j. Corresponds to ∑_j |S_D_j,tk|.

    Returns
    -------
    float
        0.0 when developer has no prior software (benefit of the doubt — a
        developer with no history receives zero weight on code-spec risk,
        as stated in the paper).
    """
    if total_software_by_dev == 0:
        return 0.0
    return total_vulns_across_dev_software / total_software_by_dev


def code_specifications_risk(w_lc: float, code_length: int) -> float:
    """
    Eq. 2 (Section V-A-2).

        R_CS = w_LC * l

    Parameters
    ----------
    w_lc:
        Weight from Eq. 3 (historical vulnerability rate).
    code_length:
        Total lines of code (l).
    """
    return w_lc * code_length


def programming_language_risk(
    years_same_lang_sum: float,
    years_total_sum: float,
) -> float:
    """
    Eq. 4 (Section V-A-3).

        R_PL = 1 - (∑_j E_DS_{j,Si} / ∑_j E_DA_{j,Si})   if ∑ E_DA > 0
        R_PL = 1                                            otherwise

    As experience in the specific language grows relative to total experience,
    risk decreases (inverse effect via subtraction from 1).

    Parameters
    ----------
    years_same_lang_sum:
        Sum of E_DS over all developers j: years of experience in the target
        programming language.
    years_total_sum:
        Sum of E_DA over all developers j: total years of software development
        experience.

    Returns
    -------
    float
        ∈ [0, 1]. Returns 1.0 (maximum risk) when developers have zero total
        experience.
    """
    if years_total_sum == 0.0:
        return 1.0
    return 1.0 - (years_same_lang_sum / years_total_sum)


def developer_expertise(
    software_same_lang_sum: int,
    software_total_sum: int,
) -> float:
    """
    Eq. 8 (Section V-A, weight w_CS motiviation).

        E_DB = ∑_j |S_L_j| / ∑_j |S_D_j|    ∈ [0, 1]

    Ratio of previously developed software in the same language to all
    previously developed software.

    Parameters
    ----------
    software_same_lang_sum:
        Sum of |S_L_j| over all developers j: count of prior software in the
        same language.
    software_total_sum:
        Sum of |S_D_j| over all developers j: count of all prior software.

    Returns
    -------
    float
        ∈ [0, 1]. Returns 0.0 when developer has no prior software.
    """
    if software_total_sum == 0:
        return 0.0
    return software_same_lang_sum / software_total_sum


def weight_code_dependency(code_coverage: float) -> float:
    """
    Eq. 6 (Section V-A-4).

        w_CD = 1 - C_C

    Higher code coverage → smaller weight on dependency risk
    (thoroughly tested code is less exposed).

    Parameters
    ----------
    code_coverage:
        C_C ∈ [0, 1]. 0 = no tests, 1 = full coverage.
    """
    return 1.0 - code_coverage


def weight_code_specifications(e_db: float) -> float:
    """
    Eq. 7 (Section V-A-4).

        w_CS = exp(-E_DB)

    Exponential decay: more experienced developers have a smaller weight on
    code-specification risk. Chosen over tanh because it maps all real numbers
    to positive reals and is straightforward to scale to [0, 1].

    Parameters
    ----------
    e_db:
        Developer expertise E_DB ∈ [0, 1] from Eq. 8.
    """
    return math.exp(-e_db)


def weight_programming_language(w_cd: float, w_cs: float) -> float:
    """
    Eq. 9 (Section V-A-4).

        w_PL = |1 - (w_CD + w_CS)|

    Residual weight ensuring the three developer sub-weights sum to 1.

    Parameters
    ----------
    w_cd:
        Code dependency weight (Eq. 6).
    w_cs:
        Code specifications weight (Eq. 7).
    """
    return abs(1.0 - (w_cd + w_cs))


def developer_risk(
    w_cd: float,
    r_cd: float,
    w_cs: float,
    r_cs: float,
    w_pl: float,
    r_pl: float,
) -> float:
    """
    Eq. 5 (Section V-A-4) — weighted aggregation of developer sub-risks.

        R_DEV = w_CD * R_CD + w_CS * R_CS + w_PL * R_PL

    IMPORTANT: R_DEV is NOT bounded to [0, 1].
    Because R_CS = w_LC * code_length, and w_LC can be large (e.g., 751 in the
    paper's worked example), R_DEV can reach hundreds of thousands
    (Table IV shows values like 48476, 225369, 295440).
    The modified sigmoid in Eq. 15 (final_risk_score) normalises this range.
    Do NOT attempt to normalise R_DEV before passing it to final_risk_score.

    Parameters
    ----------
    w_cd, r_cd:
        Code dependency weight (Eq. 6) and risk (Eq. 1).
    w_cs, r_cs:
        Code specifications weight (Eq. 7) and risk (Eq. 2).
    w_pl, r_pl:
        Programming language weight (Eq. 9) and risk (Eq. 4).
    """
    return w_cd * r_cd + w_cs * r_cs + w_pl * r_pl
