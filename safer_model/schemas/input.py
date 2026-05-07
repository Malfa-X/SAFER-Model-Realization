"""
Input data models for the SAFER framework.

SoftwareRecord   — one row in the dataset (Table III in the paper)
DeveloperHistory — cross-dataset developer aggregates (used in Eq. 3, 4, 7, 8)
PublisherHistory — cross-dataset publisher aggregates (used in Eq. 10)
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class DeveloperHistory(BaseModel):
    """
    Aggregated cross-dataset statistics for one developer.

    These values are computed by DeveloperRegistry when a full dataset is
    available, or supplied directly for standalone (single-record) scoring.

    Fields map to paper notation:
        total_vulnerabilities    → V_D  (numerator of w_LC, Eq. 3)
        total_software_count     → |S_D| (denominator of w_LC, Eq. 3; and Eq. 8)
        software_same_lang_count → |S_L| (numerator of E_DB, Eq. 8)
        years_same_lang          → E_DS (Eq. 4)
        years_total              → E_DA (Eq. 4)
    """
    developer_id: str
    total_vulnerabilities: int = Field(default=0, ge=0)
    total_software_count: int = Field(default=0, ge=0)
    software_same_lang_count: int = Field(default=0, ge=0)
    years_same_lang: float = Field(default=0.0, ge=0.0)
    years_total: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def same_lang_le_total(self) -> "DeveloperHistory":
        if self.software_same_lang_count > self.total_software_count:
            raise ValueError(
                "software_same_lang_count cannot exceed total_software_count"
            )
        if self.years_same_lang > self.years_total:
            raise ValueError("years_same_lang cannot exceed years_total")
        return self


class PublisherHistory(BaseModel):
    """
    Aggregated cross-dataset statistics for one publisher.

    Fields map to paper notation:
        software_published_count → E_PX (Eq. 10)
        years_publishing         → E_PY (Eq. 10)
    """
    publisher_id: str
    software_published_count: int = Field(default=0, ge=0)
    years_publishing: float = Field(default=0.0, ge=0.0)


class SoftwareRecord(BaseModel):
    """
    One software entry — mirrors the Table III dataset structure.

    Required fields match the paper's observable attributes.
    developer_histories and publisher_histories are populated either:
      (a) automatically by DeveloperRegistry / PublisherRegistry when scoring
          from a full dataset, or
      (b) provided directly for standalone single-record scoring.

    If neither source is available, defaults of 0 apply
    (benefit of the doubt per paper Section V).
    """
    software_id: str

    # ── Code / repository attributes ─────────────────────────────────────────
    code_length: int = Field(ge=0, description="Total lines of code (l)")
    dependencies: int = Field(ge=0, description="Number of 3rd-party packages (D)")
    code_coverage: float = Field(
        ge=0.0, le=1.0, description="Test coverage ratio C_C ∈ [0, 1]"
    )
    language: str = Field(description="Primary programming language")

    # ── Vulnerability data ───────────────────────────────────────────────────
    known_vulnerabilities: int = Field(
        ge=0, description="Total known vulnerabilities (V_T)"
    )
    unresolved_vulnerabilities: int = Field(
        ge=0, description="Unresolved known vulnerabilities (V_U)"
    )

    # ── Publisher / release attributes ───────────────────────────────────────
    update_frequency: float = Field(
        gt=0.0, le=1.0,
        description="Update frequency F_UP ∈ (0, 1]. 1.0 = updated every release cycle."
    )
    forks: int = Field(ge=0, description="Number of repository forks (f)")
    downloads: int = Field(ge=0, description="Total download count (N_DS)")
    rating: float = Field(ge=0.0, description="User star/rating count (G_US)")

    # ── Context (Section V, Eq. 13) ──────────────────────────────────────────
    context: float = Field(
        default=0.2,
        description=(
            "Software context C_TXT: "
            "0.2=security software, 0.3=automation software, 0.5=other. "
            "Defaults to 0.2 (most stringent) when unknown."
        ),
    )

    # ── Cross-dataset actor histories ────────────────────────────────────────
    developer_histories: list[DeveloperHistory] = Field(
        default_factory=list,
        description=(
            "Aggregated developer statistics. "
            "Populated by DeveloperRegistry or provided directly."
        ),
    )
    publisher_histories: list[PublisherHistory] = Field(
        default_factory=list,
        description=(
            "Aggregated publisher statistics. "
            "Populated by PublisherRegistry or provided directly."
        ),
    )

    # ── Validators ───────────────────────────────────────────────────────────
    @field_validator("context")
    @classmethod
    def valid_context(cls, v: float) -> float:
        allowed = {0.2, 0.3, 0.5}
        # float comparison: round to 1 decimal to handle minor float drift
        if round(v, 1) not in allowed:
            raise ValueError(
                f"context must be 0.2 (security), 0.3 (automation), or 0.5 (other); got {v}"
            )
        return round(v, 1)

    @model_validator(mode="after")
    def unresolved_le_known(self) -> "SoftwareRecord":
        if self.unresolved_vulnerabilities > self.known_vulnerabilities:
            raise ValueError(
                "unresolved_vulnerabilities cannot exceed known_vulnerabilities"
            )
        return self

    # ── Derived properties ───────────────────────────────────────────────────
    @property
    def resolved_vulnerabilities(self) -> int:
        """V_R = V_T - V_U"""
        return self.known_vulnerabilities - self.unresolved_vulnerabilities

    @property
    def vuln_proportion(self) -> float:
        """V_UP = V_U / V_T. Returns 0.0 when no vulnerabilities exist."""
        if self.known_vulnerabilities == 0:
            return 0.0
        return self.unresolved_vulnerabilities / self.known_vulnerabilities
