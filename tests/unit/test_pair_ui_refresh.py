import time
from datetime import UTC, date, datetime

from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QTableWidget

from dota_support_draft.domain import (
    DataProvenance,
    EvidenceSet,
    Hero,
    Patch,
    Role,
    RoleEvidenceBundle,
    RoleEvidenceBundles,
    RoleMetaEvidence,
)
from dota_support_draft.draft import ManualDraftSession, PairEvidenceResult
from dota_support_draft.ui.main_window import create_main_window


class CountingPairService:
    rank_bracket = None

    def __init__(self) -> None:
        self.calls = 0

    def refresh(self, input_data):
        self.calls += 1
        return PairEvidenceResult(input_data.generation, input_data.context)


class SlowPairService(CountingPairService):
    def refresh(self, input_data):
        self.calls += 1
        time.sleep(0.15)
        return PairEvidenceResult(input_data.generation, input_data.context)


def _wait(app: QApplication, predicate) -> None:
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


def test_search_and_table_selection_do_not_schedule_pair_network_work() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    provenance = DataProvenance(
        "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
    )
    bundle = RoleEvidenceBundle(
        Role.POSITION_4,
        EvidenceSet(
            role_meta=tuple(
                RoleMetaEvidence(hero, Role.POSITION_4, patch, 100, 60, 0.6, provenance)
                for hero in heroes
            )
        ),
    )
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=RoleEvidenceBundles(bundle, RoleEvidenceBundle(Role.POSITION_5)),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    add_ally = next(
        button for button in window.findChildren(QPushButton) if button.text() == "Add Ally"
    )
    assert table is not None
    table.selectRow(0)
    add_ally.click()
    _wait(app, lambda: service.calls == 1)
    search = window.findChild(QLineEdit)
    assert search is not None
    before = service.calls
    search.setText("hero")
    search.setText("hero 2")
    table.selectRow(0)
    app.processEvents()
    assert service.calls == before
    window.close()


def test_window_close_during_active_pair_refresh_is_cooperative() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = (Hero(1, "hero_one"), Hero(2, "hero_two"))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    provenance = DataProvenance(
        "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
    )
    bundle = RoleEvidenceBundle(
        Role.POSITION_4,
        EvidenceSet(
            role_meta=tuple(
                RoleMetaEvidence(hero, Role.POSITION_4, patch, 100, 60, 0.6, provenance)
                for hero in heroes
            )
        ),
    )
    service = SlowPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=RoleEvidenceBundles(bundle, RoleEvidenceBundle(Role.POSITION_5)),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    add_ally = next(
        button for button in window.findChildren(QPushButton) if button.text() == "Add Ally"
    )
    assert table is not None
    table.selectRow(0)
    add_ally.click()
    _wait(app, lambda: service.calls == 1)
    window.close()
    app.processEvents()
    assert window.pair_refresh_controller is not None
    assert window.pair_refresh_controller.active_thread is None
