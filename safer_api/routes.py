"""
FastAPI route definitions for the SAFER API.

Endpoints:
    GET  /health          — liveness check
    POST /score           — score a single SoftwareRecord (standalone mode)
    POST /score/batch     — score a list of SoftwareRecords (dataset mode)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from safer_model.schemas.input import SoftwareRecord
from safer_model.schemas.output import SAFERResult
from safer_model.scorer import SAFERScorer

router = APIRouter()


# ── Health check ──────────────────────────────────────────────────────────────

@router.get("/health", tags=["Status"])
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


# ── Single-record scoring ─────────────────────────────────────────────────────

@router.post(
    "/score",
    response_model=SAFERResult,
    tags=["Scoring"],
    summary="Score a single software record (standalone mode)",
    description=(
        "Accepts a SoftwareRecord with inline developer_histories and "
        "publisher_histories. Computes SAFER risk score without a dataset context. "
        "For accurate w_LC and E_DB values, provide pre-populated DeveloperHistory "
        "and PublisherHistory objects."
    ),
)
def score_single(record: SoftwareRecord) -> SAFERResult:
    """Score one software record using inline actor histories."""
    try:
        scorer = SAFERScorer()
        return scorer.score(record)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Batch scoring ─────────────────────────────────────────────────────────────

@router.post(
    "/score/batch",
    response_model=list[SAFERResult],
    tags=["Scoring"],
    summary="Score a batch of software records (dataset mode)",
    description=(
        "Accepts a list of SoftwareRecords. Builds DeveloperRegistry and "
        "PublisherRegistry from the submitted batch so cross-dataset aggregates "
        "(w_LC, E_DB, experience) are computed automatically. "
        "Each record's developer and publisher IDs must appear in "
        "developer_histories[0].developer_id and publisher_histories[0].publisher_id."
    ),
)
def score_batch(records: list[SoftwareRecord]) -> list[SAFERResult]:
    """Score a batch of records using dataset-mode registries."""
    if not records:
        raise HTTPException(status_code=422, detail="records list must not be empty")
    try:
        scorer = SAFERScorer(records=records)
        return scorer.score_all()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
