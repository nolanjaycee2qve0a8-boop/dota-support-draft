import time
from datetime import UTC, date, datetime

from PySide6.QtCore import QPoint, QRect, QThread
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
)

from dota_support_draft.domain import (
    DataProvenance,
    EvidenceSet,
    Hero,
    Patch,
    PersonalHeroStat,
    Role,
    RoleEvidenceBundle,
    RoleEvidenceBundles,
    RoleMetaEvidence,
)
from dota_support_draft.draft import ManualDraftSession, PairEvidenceResult
from dota_support_draft.ui.main_window import create_main_window


class ComponentService:
    rank_bracket = None

    def __init__(self, counter_error: str | None = None, synergy_error: str | None = None) -> None:
        self.calls = 0
        self.counter_error, self.synergy_error = counter_error, synergy_error

    def refresh(self, input_data):
        self.calls += 1
        return PairEvidenceResult(
            input_data.generation,
            input_data.context,
            counter_error=self.counter_error,
            synergy_error=self.synergy_error,
        )


def _bundles(heroes: tuple[Hero, ...], patch: Patch) -> RoleEvidenceBundles:
    provenance = DataProvenance(
        "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
    )

    def bundle(role: Role) -> RoleEvidenceBundle:
        return RoleEvidenceBundle(
            role,
            EvidenceSet(
                role_meta=tuple(
                    RoleMetaEvidence(hero, role, patch, 10, 6, 0.6, provenance) for hero in heroes
                )
            ),
        )

    return RoleEvidenceBundles(bundle(Role.POSITION_4), bundle(Role.POSITION_5))


def _wait(app: QApplication, predicate) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def _button(window, text: str) -> QPushButton:
    return next(button for button in window.findChildren(QPushButton) if button.text() == text)


def _global_rect(widget) -> QRect:
    return QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())


def test_capability_summary_is_honest_and_local_across_pending_partial_and_ready_states() -> None:
    """The summary observes existing state only and never starts an additional pair request."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = ComponentService(counter_error="raw provider detail")
    personal = (
        PersonalHeroStat(
            heroes[0],
            10,
            6,
            0.6,
            0.5,
            DataProvenance(
                "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
            ),
        ),
    )
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        personal_stats=personal,
        evidence_by_role=_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    summary = window.findChild(QLabel, "evidence-capability-summary")
    table = window.findChild(QTableWidget, "candidate-table")
    search = window.findChild(QLineEdit, "candidate-search")
    controller = window.pair_refresh_controller
    assert (
        summary is not None and table is not None and search is not None and controller is not None
    )
    assert "Meta available (current-week role scope)" in summary.text()
    assert "Personal available (all-time; role unknown)" in summary.text()
    assert "Counter not requested" in summary.text() and "timestamp unavailable" in summary.text()
    assert all(term not in summary.text().lower() for term in ("realtime", "raw provider", "token"))

    table.selectRow(0)
    _button(window, "Add Ally").click()
    _wait(app, lambda: controller.active_thread is not None or service.calls == 1)
    assert "Synergy pending" in summary.text() or service.calls == 1
    table.selectRow(0)
    _button(window, "Add Enemy").click()
    _wait(app, lambda: service.calls >= 2 and controller.active_thread is None)
    assert "Counter unavailable for current draft" in summary.text()
    assert "Synergy available for current draft" in summary.text()
    assert "raw provider detail" not in summary.text()
    calls, generation = service.calls, controller.generation
    search.setText("Hero")
    app.processEvents()
    assert service.calls == calls and controller.generation == generation
    assert controller.findChildren(QThread) == []
    window.close()


def test_capability_summary_does_not_overlap_controls_in_constrained_window() -> None:
    """The local summary remains scrollable and separate from manual controls at 664px height."""
    app = QApplication.instance() or QApplication([])
    heroes = (Hero(1, "hero_one"), Hero(2, "hero_two"))
    window = create_main_window(ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1))))
    window.resize(2559, 664)
    window.show()
    _button(window, "Show snapshots").click()
    app.processEvents()
    summary = window.findChild(QLabel, "evidence-capability-summary")
    scroll = window.findChild(QScrollArea, "main-window-scroll-area")
    search = window.findChild(QLineEdit, "candidate-search")
    position = window.findChild(QComboBox, "ally-team-position")
    lane = window.findChild(QComboBox, "ally-planned-lane")
    assert summary is not None and scroll is not None and search is not None
    assert position is not None and lane is not None and not summary.rect().isEmpty()
    assert scroll.verticalScrollBar().maximum() > 0
    assert not _global_rect(summary).intersects(_global_rect(search))
    assert not _global_rect(summary).intersects(_global_rect(position))
    assert not _global_rect(summary).intersects(_global_rect(lane))
    window.close()
