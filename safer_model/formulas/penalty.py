"""
Penalty formulas — Equations 12–14.

Equation reference (arXiv:2408.02876v2):
    Eq. 12  penalty
    Eq. 13  context values (CONTEXT_* constants)
    Eq. 14  context constraint (∑ C_TXT_m = 1)
"""
from __future__ import annotations

# ── Context constants (Eq. 13) ────────────────────────────────────────────────
CONTEXT_SECURITY = 0.2
"""C_TXT for security software. Produces the steepest penalty curve."""

CONTEXT_AUTOMATION = 0.3
"""C_TXT for automation/system-management software."""

CONTEXT_OTHER = 0.5
"""C_TXT for general-purpose / other software."""

CONTEXT_VALUES: tuple[float, ...] = (CONTEXT_SECURITY, CONTEXT_AUTOMATION, CONTEXT_OTHER)
"""All valid context values. Their sum equals 1 (Eq. 14)."""

# Verify Eq. 14 at import time
assert abs(sum(CONTEXT_VALUES) - 1.0) < 1e-9, "Eq. 14: context values must sum to 1"


def penalty(context: float, vuln_proportion: float) -> float:
    """
    Eq. 12 (Section V-D).

        P = 1 - (C_TXT)^V_UP

    An exponential penalty based on the proportion of unresolved vulnerabilities,
    modulated by the software context:
    - Security software (C_TXT = 0.2): base is small → exponentiation decays fast
      → penalty rises quickly even for low V_UP → strictest assessment.
    - Other software (C_TXT = 0.5): base is larger → smaller penalty for the
      same V_UP.

    Key behaviour:
    - V_UP = 0 (no vulnerabilities): P = 1 - C_TXT^0 = 1 - 1 = 0 (no penalty).
    - V_UP = 1 (all vulns unresolved): P = 1 - C_TXT^1 = 1 - C_TXT.
    - 0 < V_UP < 1: penalty is between 0 and (1 - C_TXT).

    Parameters
    ----------
    context:
        C_TXT ∈ {0.2, 0.3, 0.5}. Use CONTEXT_SECURITY / CONTEXT_AUTOMATION /
        CONTEXT_OTHER constants. If unknown, default to CONTEXT_SECURITY
        (most stringent, per Section V-D).
    vuln_proportion:
        V_UP = V_U / V_T ∈ [0, 1]. Use SoftwareRecord.vuln_proportion.

    Returns
    -------
    float
        P ∈ [0, 1].
    """
    return 1.0 - (context ** vuln_proportion)
