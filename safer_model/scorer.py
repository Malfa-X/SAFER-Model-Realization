"""
SAFERScorer — main orchestrator for the SAFER risk assessment pipeline.

Usage (dataset mode — preferred):
    records = load_csv("data/sample_dataset.csv")
    scorer = SAFERScorer(records)
    results = scorer.score_all()

Usage (standalone mode — single record with inline histories):
    scorer = SAFERScorer()
    result = scorer.score(record_with_inline_histories)
"""
from __future__ import annotations

from safer_model.bands import classify_risk_band
from safer_model.config import SAFERConfig
from safer_model.formulas.developer import (
    code_dependencies_risk,
    code_specifications_risk,
    developer_expertise,
    developer_risk,
    programming_language_risk,
    weight_code_dependency,
    weight_code_length,
    weight_code_specifications,
    weight_programming_language,
)
from safer_model.formulas.final_score import (
    final_risk_score,
    final_risk_with_penalty,
    weight_developer,
    weight_publisher,
    weight_user,
)
from safer_model.formulas.penalty import penalty
from safer_model.formulas.publisher import publisher_risk
from safer_model.formulas.user import user_risk
from safer_model.registry import DeveloperRegistry, PublisherRegistry
from safer_model.schemas.input import DeveloperHistory, PublisherHistory, SoftwareRecord
from safer_model.schemas.output import SAFERResult


class SAFERScorer:
    """
    Orchestrates the full SAFER computation pipeline.

    Two operating modes:

    Dataset mode (instantiate with records):
        The scorer builds DeveloperRegistry and PublisherRegistry from the full
        record list. Cross-dataset aggregates (w_LC, E_DB, R_PL, R_PB) are
        derived automatically. This is the mode used when scoring a CSV dataset.

    Standalone mode (instantiate without records):
        No registries are built. Each SoftwareRecord must carry its own
        developer_histories and publisher_histories with pre-populated values.
        Missing histories default to zero (benefit of the doubt, Section V).
    """

    def __init__(
        self,
        records: list[SoftwareRecord] | None = None,
        config: SAFERConfig | None = None,
    ) -> None:
        """
        Parameters
        ----------
        records:
            Optional full dataset. When provided, registries are built and
            cross-dataset aggregates are computed automatically.
        config:
            Optional SAFERConfig with tunable parameters (Section VI).
            Defaults to all paper-specified values.
        """
        self.config = config or SAFERConfig()
        self._records = records or []

        if records:
            self._dev_registry: DeveloperRegistry | None = DeveloperRegistry(records)
            self._pub_registry: PublisherRegistry | None = PublisherRegistry(records)
        else:
            self._dev_registry = None
            self._pub_registry = None

    # ── Public API ────────────────────────────────────────────────────────────

    def score(self, record: SoftwareRecord) -> SAFERResult:
        """
        Compute the full SAFER risk score for a single SoftwareRecord.

        Follows the 9-step pipeline described in the paper:
          1. Resolve cross-dataset actor histories
          2. Aggregate cross-dataset sums (∑_j, ∑_x)
          3. Developer sub-risks: R_CD, R_CS, R_PL and weights (Eqs. 1–9)
          4. Developer-based risk R_DEV (Eq. 5)
          5. Publisher-based risk R_PB (Eq. 10)
          6. User-indicated risk R_UR (Eq. 11)
          7. Penalty P (Eq. 12)
          8. Actor weights w_DEV, w_PB, w_UR (Eqs. 16–18)
          9. Final scores R_F (Eq. 15) and R_FP (Eq. 19), and risk band
        """
        # ── Step 1: Resolve actor histories ──────────────────────────────────
        dev_histories = self._resolve_dev_histories(record)
        pub_histories = self._resolve_pub_histories(record)

        # ── Step 2: Aggregate cross-dataset sums ─────────────────────────────
        total_vulns = sum(h.total_vulnerabilities for h in dev_histories)
        total_sw = sum(h.total_software_count for h in dev_histories)
        sw_same_lang = sum(h.software_same_lang_count for h in dev_histories)
        yrs_same_lang = sum(h.years_same_lang for h in dev_histories)
        yrs_total = sum(h.years_total for h in dev_histories)

        sw_published = sum(h.software_published_count for h in pub_histories)
        yrs_pub = sum(h.years_publishing for h in pub_histories)

        # ── Step 3: Developer sub-risks and weights (Eqs. 1–9) ───────────────
        r_cd = code_dependencies_risk(
            record.dependencies, self.config.dep_sensitivity
        )
        w_lc = weight_code_length(total_vulns, total_sw)
        r_cs = code_specifications_risk(w_lc, record.code_length)
        r_pl = programming_language_risk(yrs_same_lang, yrs_total)
        e_db = developer_expertise(sw_same_lang, total_sw)
        w_cd = weight_code_dependency(record.code_coverage)
        w_cs = weight_code_specifications(e_db)
        w_pl = weight_programming_language(w_cd, w_cs)

        # ── Step 4: Developer-based risk R_DEV (Eq. 5) ───────────────────────
        r_dev = developer_risk(w_cd, r_cd, w_cs, r_cs, w_pl, r_pl)

        # ── Step 5: Publisher-based risk R_PB (Eq. 10) ───────────────────────
        r_pb = publisher_risk(yrs_pub, sw_published, record.update_frequency)

        # ── Step 6: User-indicated risk R_UR (Eq. 11) ────────────────────────
        r_ur = user_risk(record.rating, record.downloads)

        # ── Step 7: Penalty P (Eq. 12) ───────────────────────────────────────
        p = penalty(record.context, record.vuln_proportion)

        # ── Step 8: Actor weights (Eqs. 16–18) ───────────────────────────────
        w_dev = weight_developer(record.forks)
        w_pb = weight_publisher(
            record.unresolved_vulnerabilities,
            record.resolved_vulnerabilities,
        )
        w_ur = weight_user(w_dev, w_pb)

        # ── Step 9: Final scores (Eqs. 15, 19) and band ──────────────────────
        r_f = final_risk_score(w_dev, r_dev, w_pb, r_pb, w_ur, r_ur)
        r_fp = final_risk_with_penalty(r_f, p)
        band = classify_risk_band(r_fp, self.config.risk_band_thresholds)

        return SAFERResult(
            software_id=record.software_id,
            r_cd=r_cd,
            r_cs=r_cs,
            r_pl=r_pl,
            r_dev=r_dev,
            r_pb=r_pb,
            r_ur=r_ur,
            w_lc=w_lc,
            e_db=e_db,
            w_cd=w_cd,
            w_cs=w_cs,
            w_pl=w_pl,
            w_dev=w_dev,
            w_pb=w_pb,
            w_ur=w_ur,
            penalty=p,
            r_f=r_f,
            r_fp=r_fp,
            band=band,
        )

    def score_all(self) -> list[SAFERResult]:
        """Score every record in the dataset (dataset mode only)."""
        if not self._records:
            raise ValueError(
                "score_all() requires records to be provided at construction time. "
                "Use SAFERScorer(records=[...]) to enable dataset mode."
            )
        return [self.score(r) for r in self._records]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve_dev_histories(
        self, record: SoftwareRecord
    ) -> list[DeveloperHistory]:
        """
        Return developer histories for this record.

        Priority:
          1. Registry-derived (dataset mode) — cross-dataset aggregates
          2. Inline (record.developer_histories) — for standalone mode
          3. Empty list → all aggregates default to 0
        """
        if self._dev_registry is not None:
            return self._dev_registry.get_histories_for_software(record)
        return record.developer_histories

    def _resolve_pub_histories(
        self, record: SoftwareRecord
    ) -> list[PublisherHistory]:
        if self._pub_registry is not None:
            return self._pub_registry.get_histories_for_software(record)
        return record.publisher_histories
