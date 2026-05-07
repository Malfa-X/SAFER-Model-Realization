"""
SAFER framework configuration — Section VI tunable parameters.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from safer_model.bands import DEFAULT_BAND_THRESHOLDS
from safer_model.constants import CONTEXT_SECURITY, PENALTY_THRESHOLD
from safer_model.schemas.output import RiskBand


class SAFERConfig(BaseModel):
    """
    Tunable parameters for the SAFER framework (Section VI).

    All parameters have sensible defaults matching the paper. Override them
    to adapt the framework to organisational requirements.

    Note: Customising weights or band thresholds between organisations
    introduces inter-organisation subjectivity, but keeps computations
    *within* an organisation consistent (Section VI note).
    """

    # Section VI-A: sensitivity multiplier for dependency risk
    dep_sensitivity: float = Field(
        default=1.0,
        gt=0.0,
        description=(
            "Sensitivity multiplier for R_CD (Eq. 1). "
            "Values > 1.0 amplify dependency risk. Default 1.0."
        ),
    )

    # Section V-D / VI default for unknown context
    unknown_context: float = Field(
        default=CONTEXT_SECURITY,
        description=(
            "Context value C_TXT to use when the software context is unknown. "
            "Defaults to CONTEXT_SECURITY (0.2) for the most stringent assessment."
        ),
    )

    # Section VI-G: penalty application threshold
    penalty_threshold: float = Field(
        default=PENALTY_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=(
            "R_F threshold above which penalty is applied (Eq. 19). "
            "Default 0.5 = mean of [0, 1]. Lower values make the framework stricter."
        ),
    )

    # Section VI-D: customisable risk band thresholds
    risk_band_thresholds: list[tuple[RiskBand, float, float]] = Field(
        default_factory=lambda: list(DEFAULT_BAND_THRESHOLDS),
        description=(
            "List of (band, lower_bound, upper_bound) tuples defining risk bands. "
            "Default follows Section V-G: Low<0.25, Moderate<0.5, High<0.75, Critical≤1."
        ),
    )

    model_config = {"arbitrary_types_allowed": True}
