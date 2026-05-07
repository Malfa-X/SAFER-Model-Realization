"""
Publisher-based risk formula — Equation 10.

Equation reference (arXiv:2408.02876v2):
    Eq. 10  publisher_risk
"""
from __future__ import annotations


def publisher_risk(
    years_publishing_sum: float,
    software_published_sum: int,
    update_frequency: float,
) -> float:
    """
    Eq. 10 (Section V-B).

        R_PB = (∑_x E_PY_{x,Si} / ∑_x E_PX_{x,Si}) * (1 / F_UP)
                  if E_PX ≠ 0 and F_UP ≠ 0
        R_PB = 1  otherwise  (new publisher or missing update data)

    The publisher risk combines:
    - Experience ratio: average years publishing per software published
      (∑ E_PY / ∑ E_PX). Higher experience → lower risk per unit.
    - Update frequency penalty: divided by F_UP so less frequent updates
      produce higher risk.

    Inverse effect: as both experience and update frequency increase, R_PB
    decreases. A new publisher (E_PX = 0) yields maximum risk = 1.

    Parameters
    ----------
    years_publishing_sum:
        Sum of E_PY over all publishers x: total years of publishing experience.
    software_published_sum:
        Sum of E_PX over all publishers x: total number of software published.
    update_frequency:
        F_UP ∈ (0, 1]. Frequency with which the software is updated relative
        to a normalised scale. Must be > 0 (validated by SoftwareRecord).

    Returns
    -------
    float
        Maximum risk 1.0 for new publishers (Section VI-C) or if
        update_frequency is zero (defensive guard).
    """
    if software_published_sum == 0 or update_frequency == 0.0:
        return 1.0
    return (years_publishing_sum / software_published_sum) * (1.0 / update_frequency)
