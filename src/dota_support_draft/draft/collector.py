from abc import ABC, abstractmethod

from dota_support_draft.domain import DraftState


class DraftStateCollector(ABC):
    """Implemented later by manual input, GSI, or screen-recognition adapters."""

    @abstractmethod
    def collect(self) -> DraftState: ...
