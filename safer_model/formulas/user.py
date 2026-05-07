"""
User-indicated risk formula — Equation 11.

Equation reference (arXiv:2408.02876v2):
    Eq. 11  user_risk
"""
from __future__ import annotations


def user_risk(rating: float, downloads: int) -> float:
    """
    Eq. 11 (Section V-C).

        R_UR = 1 - (G_US / N_DS)

    Consumer trust is represented by the proportion of users who expressed
    satisfaction (starred the software) relative to those who downloaded it.
    As the satisfaction proportion increases, risk decreases (inverse effect
    via subtraction from 1).

    Parameters
    ----------
    rating:
        G_US — star count (or analogous satisfaction signal).
    downloads:
        N_DS — total download count.

    Returns
    -------
    float
        ∈ [0, 1]. Returns 1.0 (maximum risk) when the software has no downloads
        (no user feedback available → maximum uncertainty).
    """
    if downloads == 0:
        return 1.0
    return 1.0 - (rating / downloads)
