"""
Risk band classification (Section V-G).

The four bands and their default thresholds:
    LOW      [0.00, 0.25)
    MODERATE [0.25, 0.50)
    HIGH     [0.50, 0.75)
    CRITICAL [0.75, 1.00]

Thresholds are customisable per Section VI-D.
"""
from __future__ import annotations

from safer_model.schemas.output import RiskBand

# Ordered list of (band, lower_bound, upper_bound).
# Upper bound is exclusive except for CRITICAL which catches r_fp == 1.0.
DEFAULT_BAND_THRESHOLDS: list[tuple[RiskBand, float, float]] = [
    (RiskBand.LOW,      0.00, 0.25),
    (RiskBand.MODERATE, 0.25, 0.50),
    (RiskBand.HIGH,     0.50, 0.75),
    (RiskBand.CRITICAL, 0.75, 1.01),   # 1.01 to include r_fp == 1.0
]


def classify_risk_band(
    r_fp: float,
    thresholds: list[tuple[RiskBand, float, float]] | None = None,
) -> RiskBand:
    """
    Map a penalised final risk score R_FP to a risk band.

    Parameters
    ----------
    r_fp:
        Final risk score with penalty R_FP (Eq. 19). ∈ [0, 1].
    thresholds:
        Optional custom band thresholds as a list of (band, lo, hi) tuples,
        ordered from lowest to highest. Each band matches lo ≤ r_fp < hi.
        Defaults to DEFAULT_BAND_THRESHOLDS (Section V-G).

    Returns
    -------
    RiskBand
        The appropriate risk band for the given score.
    """
    active = thresholds if thresholds is not None else DEFAULT_BAND_THRESHOLDS
    for band, lo, hi in active:
        if lo <= r_fp < hi:
            return band
    # Fallback: return highest band (handles floating-point edge cases near 1.0)
    return RiskBand.CRITICAL
