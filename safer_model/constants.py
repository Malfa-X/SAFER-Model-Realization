"""
Shared constants used across the SAFER framework.
"""

# ── Sigmoid adjustment factors (Eq. 15) ──────────────────────────────────────
SIGMOID_SHIFT = 4.0
"""The additive shift in the sigmoid exponent (4 in Eq. 15)."""

SIGMOID_SCALE = 0.04
"""The multiplicative scale in the sigmoid exponent (0.04 in Eq. 15)."""

# ── Penalty threshold (Section VI-G) ─────────────────────────────────────────
PENALTY_THRESHOLD = 0.5
"""
Default R_F threshold above which penalty is applied (Eq. 19 case a/b).
Set as the mean of minimum (0) and maximum (1) possible risk values.
Customisable per Section VI-G.
"""

# ── Context values (Eq. 13) ──────────────────────────────────────────────────
CONTEXT_SECURITY = 0.2
CONTEXT_AUTOMATION = 0.3
CONTEXT_OTHER = 0.5
VALID_CONTEXT_VALUES: frozenset[float] = frozenset({0.2, 0.3, 0.5})
