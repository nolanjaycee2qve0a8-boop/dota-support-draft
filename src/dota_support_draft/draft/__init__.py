"""Manual and future automated collection adapters feed the same DraftState model."""

from .presentation import CandidateRow, build_candidate_rows, filter_candidates
from .session import ManualDraftError, ManualDraftSession

__all__ = [
    "CandidateRow",
    "ManualDraftError",
    "ManualDraftSession",
    "build_candidate_rows",
    "filter_candidates",
]
