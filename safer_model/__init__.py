"""
SAFER: Software Analysis Framework for Evaluating Risk
Reference: arXiv:2408.02876v2

Public API:
    SAFERScorer  — main entry point for scoring software records
    SAFERConfig  — tunable parameters (Section VI)
    SoftwareRecord, DeveloperHistory, PublisherHistory  — input models
    SAFERResult, RiskBand  — output models
"""
from safer_model.schemas.input import SoftwareRecord, DeveloperHistory, PublisherHistory
from safer_model.schemas.output import SAFERResult, RiskBand
from safer_model.scorer import SAFERScorer
from safer_model.config import SAFERConfig

__all__ = [
    "SAFERScorer",
    "SAFERConfig",
    "SoftwareRecord",
    "DeveloperHistory",
    "PublisherHistory",
    "SAFERResult",
    "RiskBand",
]
