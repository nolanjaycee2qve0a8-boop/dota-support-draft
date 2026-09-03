"""Manual and future automated collection adapters feed the same DraftState model."""

from .manual_import import (
    MANUAL_IMPORT_SCHEMA_VERSION,
    ManualImportAssessment,
    ManualImportStatus,
    assess_pasted_manual_import,
)
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
    CandidateSortColumn,
    build_candidate_rows,
    filter_candidates,
    format_optional_count,
    format_optional_rate,
    format_player_status,
    sort_candidate_rows,
)
from .session import ManualDraftError, ManualDraftSession
from .summary import format_manual_draft_summary

__all__ = [
    "CandidateRow",
    "CandidateSortColumn",
    "ManualDraftError",
    "ManualDraftSession",
    "MANUAL_IMPORT_SCHEMA_VERSION",
    "ManualImportAssessment",
    "ManualImportStatus",
    "PAIR_SHORTLIST_SIZE",
    "DraftPairEvidenceService",
    "PairEvidenceContext",
    "PairEvidenceInput",
    "PairEvidenceResult",
    "build_candidate_rows",
    "assess_pasted_manual_import",
    "filter_candidates",
    "format_optional_count",
    "format_optional_rate",
    "format_player_status",
    "format_manual_draft_summary",
    "make_pair_input",
    "select_pair_shortlist",
    "sort_candidate_rows",
]
