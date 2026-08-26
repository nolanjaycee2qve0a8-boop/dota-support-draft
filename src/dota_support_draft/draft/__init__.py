"""Manual and future automated collection adapters feed the same DraftState model."""

from .presentation import (
    CandidateRow,
    build_candidate_rows,
    filter_candidates,
    format_optional_count,
    format_optional_rate,
    format_player_status,
)
from .session import ManualDraftError, ManualDraftSession

__all__ = [
    "CandidateRow",
    "ManualDraftError",
    "ManualDraftSession",
    "build_candidate_rows",
    "filter_candidates",
    "format_optional_count",
    "format_optional_rate",
    "format_player_status",
]
