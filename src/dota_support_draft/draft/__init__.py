"""Manual and future automated collection adapters feed the same DraftState model."""

from .pair_evidence import (
    PAIR_SHORTLIST_SIZE,
    DraftPairEvidenceService,
    PairEvidenceContext,
    PairEvidenceInput,
    PairEvidenceResult,
    make_pair_input,
    select_pair_shortlist,
)
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
    "PAIR_SHORTLIST_SIZE",
    "DraftPairEvidenceService",
    "PairEvidenceContext",
    "PairEvidenceInput",
    "PairEvidenceResult",
    "build_candidate_rows",
    "filter_candidates",
    "format_optional_count",
    "format_optional_rate",
    "format_player_status",
    "make_pair_input",
    "select_pair_shortlist",
]
