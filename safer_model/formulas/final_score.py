"""
Actor weights and final risk score formulas — Equations 15–19.

Equation reference (arXiv:2408.02876v2):
    Eq. 15  final_risk_score
    Eq. 16  weight_user   (derived from constraint ∑w = 1)
    Eq. 17  weight_developer
    Eq. 18  weight_publisher
    Eq. 19  final_risk_with_penalty
"""
from __future__ import annotations

import math


def weight_developer(forks: int) -> float:
    """
    Eq. 17 (Section V-E).

        w_DEV = 1 / f    if f > 0
        w_DEV = 1        if f = 0

    Forks enable distributed code review and vulnerability audits. More forks
    → more community scrutiny → lower weight on unverified developer risk.

    Parameters
    ----------
    forks:
        Number of repository forks (f). Non-negative integer.
    """
    if forks <= 0:
        return 1.0
    return 1.0 / forks


def weight_publisher(unresolved_vulns: int, resolved_vulns: int) -> float:
    """
    Eq. 18 (Section V-E).

        w_PB = (V_U + 1) / (V_R + V_U + 2)

    Laplace-smoothed ratio of unresolved to total known vulnerabilities.
    Higher proportion of unresolved vulnerabilities → higher publisher risk weight.
    Smoothing prevents zero weights when no vulnerabilities exist.

    Parameters
    ----------
    unresolved_vulns:
        V_U — number of known unresolved vulnerabilities.
    resolved_vulns:
        V_R = V_T - V_U — number of resolved vulnerabilities.
    """
    return (unresolved_vulns + 1) / (resolved_vulns + unresolved_vulns + 2)


def weight_user(w_dev: float, w_pb: float) -> float:
    """
    Eq. 16 (Section V-E) — derived from the constraint ∑w = 1.

        w_UR = 1 - (w_DEV + w_PB)

    Parameters
    ----------
    w_dev:
        Developer actor weight (Eq. 17).
    w_pb:
        Publisher actor weight (Eq. 18).
    """
    return 1.0 - (w_dev + w_pb)


def final_risk_score(
    w_dev: float,
    r_dev: float,
    w_pb: float,
    r_pb: float,
    w_ur: float,
    r_ur: float,
) -> float:
    """
    Eq. 15 (Section V-E) — modified sigmoid mapping.

        R_F = 1 / (1 + exp(4 - 0.04 * (w_DEV*R_DEV + w_PB*R_PB + w_UR*R_UR)))

    The sigmoid is modified with adjustment factors 4 and 0.04 (determined by
    graph analysis in the paper). These factors ensure R_F gradually increases
    and enables comparison across different software packages by mapping the
    potentially enormous combined weighted score (dominated by R_DEV) to (0, 1).

    Do NOT pre-normalise R_DEV — its large scale is intentional and the sigmoid
    handles it. Pre-normalising would destroy the relative sensitivity of the
    framework.

    Parameters
    ----------
    w_dev, r_dev:
        Developer actor weight (Eq. 17) and developer-based risk (Eq. 5).
        R_DEV can be very large (e.g., 176831 in the paper's worked example).
    w_pb, r_pb:
        Publisher actor weight (Eq. 18) and publisher-based risk (Eq. 10).
    w_ur, r_ur:
        User actor weight (Eq. 16) and user-indicated risk (Eq. 11).

    Returns
    -------
    float
        R_F ∈ (0, 1) — strictly between 0 and 1 due to sigmoid.
    """
    combined = w_dev * r_dev + w_pb * r_pb + w_ur * r_ur
    return 1.0 / (1.0 + math.exp(4.0 - 0.04 * combined))


def final_risk_with_penalty(r_f: float, penalty_val: float) -> float:
    """
    Eq. 19 (Section V-F) — conditional penalty application.

    The penalty is only applied when the base risk already exceeds 0.5,
    i.e., only to software that has already established a degree of mistrust.

        Case (a): R_F > 0.5  AND  R_F + P < 1  →  R_FP = R_F + P
        Case (b): R_F ≥ (1 - P)                 →  R_FP = 1  (cap at maximum)
        Case (c): Otherwise                      →  R_FP = R_F (no penalty applied)

    Note: For Case (c) this means R_F ≤ 0.5 → no penalty regardless of P.
    The threshold 0.5 is the default (mean of min and max); it is customisable
    per Section VI-G.

    Parameters
    ----------
    r_f:
        Final risk score before penalty R_F (Eq. 15). ∈ (0, 1).
    penalty_val:
        Penalty P (Eq. 12). ∈ [0, 1].

    Returns
    -------
    float
        R_FP ∈ [0, 1].
    """
    if r_f > 0.5 and (r_f + penalty_val) < 1.0:
        return r_f + penalty_val
    elif r_f >= (1.0 - penalty_val):
        return 1.0
    else:
        return r_f
