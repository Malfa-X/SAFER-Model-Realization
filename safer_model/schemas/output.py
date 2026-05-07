"""
Output data models for the SAFER framework.

SAFERResult — full computation result for one software record
RiskBand    — enumeration of the four risk bands (Section V-G)
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class RiskBand(str, Enum):
    """
    Risk band classification (Section V-G).

    Bands are determined by the final penalised risk score R_FP:
        LOW      [0.00, 0.25)
        MODERATE [0.25, 0.50)
        HIGH     [0.50, 0.75)
        CRITICAL [0.75, 1.00]
    """
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"
    CRITICAL = "Critical"


class SAFERResult(BaseModel):
    """
    Complete SAFER computation output for a single software record.

    All intermediate values are preserved to support transparency,
    debugging, and the paper's heat-map sensitivity analyses.
    """
    software_id: str

    # ── Developer sub-risk components (Section V-A) ──────────────────────────
    r_cd: float
    """Code dependencies risk R_CD (Eq. 1). Equals raw dependency count D."""

    r_cs: float
    """Code specifications risk R_CS (Eq. 2). = w_LC * code_length."""

    r_pl: float
    """Programming language risk R_PL (Eq. 4). ∈ [0, 1]."""

    r_dev: float
    """
    Developer-based risk R_DEV (Eq. 5).
    NOT bounded to [0, 1] — the sigmoid in Eq. 15 handles normalisation.
    Typical values: tens of thousands (see Table IV in the paper).
    """

    # ── Publisher risk (Section V-B) ─────────────────────────────────────────
    r_pb: float
    """Publisher-based risk R_PB (Eq. 10). ∈ [0, 1] in typical cases, max = 1."""

    # ── User risk (Section V-C) ──────────────────────────────────────────────
    r_ur: float
    """User-indicated risk R_UR (Eq. 11). ∈ [0, 1]."""

    # ── Developer internal weights ───────────────────────────────────────────
    w_lc: float
    """Historical vulnerability rate w_LC (Eq. 3). Average vulns/software for developer."""

    e_db: float
    """Developer expertise E_DB (Eq. 8). ∈ [0, 1]."""

    w_cd: float
    """Weight for code dependency risk w_CD (Eq. 6). = 1 - code_coverage."""

    w_cs: float
    """Weight for code specifications risk w_CS (Eq. 7). = exp(-E_DB)."""

    w_pl: float
    """Weight for programming language risk w_PL (Eq. 9). = |1 - (w_CD + w_CS)|."""

    # ── Actor weights (Eqs. 16–18) ───────────────────────────────────────────
    w_dev: float
    """Developer actor weight w_DEV (Eq. 17). = 1/forks (or 1 if forks=0)."""

    w_pb: float
    """Publisher actor weight w_PB (Eq. 18). Laplace-smoothed unresolved vuln ratio."""

    w_ur: float
    """User actor weight w_UR (Eq. 16). = 1 - (w_DEV + w_PB)."""

    # ── Final scores ─────────────────────────────────────────────────────────
    penalty: float
    """Penalty factor P (Eq. 12). ∈ [0, 1]."""

    r_f: float
    """Final risk score before penalty R_F (Eq. 15). ∈ (0, 1)."""

    r_fp: float
    """Final risk score with penalty R_FP (Eq. 19). ∈ [0, 1]."""

    band: RiskBand
    """Risk band classification derived from R_FP."""
