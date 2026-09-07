import time
from datetime import UTC, date, datetime

import pytest
from PySide6.QtCore import QPoint, QRect, QThread
from PySide6.QtWidgets import (
    QApplication,
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


class SlowPairService:
    rank_bracket = None

    def __init__(self, counter_error: str | None = None) -> None:
        self.calls = 0
        self.counter_error = counter_error

    def refresh(self, input_data):
        time.sleep(0.15)
        self.calls += 1
        return PairEvidenceResult(
            input_data.generation,
            input_data.context,
            counter_error=self.counter_error,
        )


def _bundles(heroes: tuple[Hero, ...], patch: Patch, has_meta: bool = True) -> RoleEvidenceBundles:
    provenance = DataProvenance(
        "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
    )

    def bundle(role: Role) -> RoleEvidenceBundle:
        evidence = EvidenceSet(
            role_meta=tuple(
                RoleMetaEvidence(hero, role, patch, 10, 6, 0.6, provenance) for hero in heroes
            )
            if has_meta
            else ()
        )
        return RoleEvidenceBundle(role, evidence)

    return RoleEvidenceBundles(bundle(Role.POSITION_4), bundle(Role.POSITION_5))


def _personal(hero: Hero, patch: Patch) -> tuple[PersonalHeroStat, ...]:
    return (
        PersonalHeroStat(
            hero,
            10,
            6,
            0.6,
            0.5,
            DataProvenance(
                "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
            ),
        ),
    )


def _label(window, name: str) -> QLabel:
    label = window.findChild(QLabel, name)
    assert label is not None
    return label


def _button(window, name: str) -> QPushButton:
    button = window.findChild(QPushButton, name)
    assert button is not None
    return button


def _wait(app: QApplication, predicate) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def _assert_safe_status(*texts: str) -> None:
    for text in texts:
        lowered = text.lower()
        assert "raw provider" not in lowered and "token" not in lowered and "live" not in lowered


def _related_session(heroes: tuple[Hero, ...], patch: Patch) -> ManualDraftSession:
    session = ManualDraftSession(heroes, patch)
    session.add_ally(heroes[0])
    session.add_enemy(heroes[1])
    return session


def test_base_and_pair_status_hierarchy_is_independent_and_local_without_token() -> None:
    """Base status names only loaded Meta/Personal while pair labels name no-service scope."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = _related_session(heroes, patch)
    window = create_main_window(
        session,
        evidence_by_role=_bundles(heroes, patch, has_meta=False),
        personal_stats=_personal(heroes[0], patch),
    )
    window.show()
    summary = _label(window, "evidence-capability-summary").text()
    coverage = _label(window, "pair-refresh-coverage").text()
    action = _label(window, "pair-refresh-action").text()
    assert "Meta unavailable" in summary
    assert "Personal available (all-time; role unknown)" in summary
    assert "freshness timestamp unavailable" in summary.lower() and "real-time guarantee" in summary
    assert "Counter" in coverage and "Synergy" in coverage
    assert "pair-refresh service is unavailable" in action
    assert "Base evidence:" not in coverage and "Base evidence:" not in action

    before = session.to_draft_state()
    search = window.findChild(QLineEdit, "candidate-search")
    table = window.findChild(QTableWidget, "candidate-table")
    assert search is not None and table is not None and window.pair_refresh_controller is None
    search.setText("hero")
    table.selectRow(0)
    app.processEvents()
    assert session.to_draft_state() == before and window.findChildren(QThread) == []
    _assert_safe_status(summary, coverage, action)
    window.close()


def test_hierarchy_keeps_meta_personal_no_related_and_no_shortlist_distinct() -> None:
    """Base availability and no-related/no-shortlist pair states remain separately readable."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    no_related = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_bundles(heroes, patch),
        personal_stats=_personal(heroes[0], patch),
        pair_service=SlowPairService(),  # type: ignore[arg-type]
        pair_debounce_ms=10_000,
    )
    no_related.show()
    assert "Meta available" in _label(no_related, "evidence-capability-summary").text()
    assert "Personal available" in _label(no_related, "evidence-capability-summary").text()
    assert "no related picks" in _label(no_related, "pair-refresh-coverage").text()
    assert "Add an allied or enemy pick" in _label(no_related, "pair-refresh-action").text()
    assert no_related.pair_refresh_controller is not None
    assert no_related.pair_refresh_controller.generation == 0
    no_related.close()

    exhausted = (Hero(1, "hero_one"), Hero(2, "hero_two"))
    no_shortlist = create_main_window(
        _related_session(exhausted, patch),
        evidence_by_role=_bundles(exhausted, patch),
        pair_service=SlowPairService(),  # type: ignore[arg-type]
        pair_debounce_ms=10_000,
    )
    no_shortlist.show()
    assert (
        _label(no_shortlist, "pair-refresh-coverage")
        .text()
        .count("unavailable (no legal shortlist)")
        == 2
    )
    assert "No legal shortlist" in _label(no_shortlist, "pair-refresh-action").text()
    assert no_shortlist.pair_refresh_controller is not None
    assert no_shortlist.pair_refresh_controller.generation == 0
    no_shortlist.close()
    app.processEvents()


@pytest.mark.parametrize(
    ("counter_error", "expected_coverage", "expected_action"),
    (
        (None, "Counter: available; Synergy: available", "Counter and Synergy are available"),
        (
            "raw provider detail",
            "Counter: unavailable for current draft; Synergy: available",
            "Counter is unavailable; Synergy is still available",
        ),
    ),
)
def test_pair_status_hierarchy_reports_pending_then_partial_or_ready(
    counter_error: str | None,
    expected_coverage: str,
    expected_action: str,
) -> None:
    """Pair labels show pending and the completed component state without exposing raw errors."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = SlowPairService(counter_error)
    window = create_main_window(
        _related_session(heroes, patch),
        evidence_by_role=_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    controller = window.pair_refresh_controller
    assert controller is not None
    _button(window, "manual-pair-refresh").click()
    _wait(app, lambda: controller.active_thread is not None)
    assert "pending" in _label(window, "pair-refresh-coverage").text()
    assert "Updating evidence" in _label(window, "pair-refresh-action").text()
    _wait(app, lambda: controller.active_thread is None and service.calls == 1)
    coverage = _label(window, "pair-refresh-coverage").text()
    action = _label(window, "pair-refresh-action").text()
    assert expected_coverage in coverage and expected_action in action
    _assert_safe_status(coverage, action)
    _wait(
        app, lambda: controller.retired_worker_count == 0 and controller.findChildren(QThread) == []
    )
    window.close()


def test_status_hierarchy_wraps_without_overlap_at_compact_and_regular_heights() -> None:
    """The grouped status labels stay ordered and separate from controls at both target heights."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    window = create_main_window(
        _related_session(heroes, patch), evidence_by_role=_bundles(heroes, patch)
    )
    scroll = window.findChild(QScrollArea, "main-window-scroll-area")
    search = window.findChild(QLineEdit, "candidate-search")
    group = window.findChild(QLabel, "base-evidence-heading")
    pair_heading = window.findChild(QLabel, "pair-evidence-heading")
    labels = (
        _label(window, "recommendation-evidence-status"),
        _label(window, "evidence-capability-summary"),
        _label(window, "pair-refresh-status"),
        _label(window, "pair-refresh-context"),
        _label(window, "pair-refresh-coverage"),
        _label(window, "pair-refresh-action"),
    )
    assert (
        scroll is not None and search is not None and group is not None and pair_heading is not None
    )
    for height in (664, 900):
        window.resize(2559, height)
        window.show()
        app.processEvents()
        assert scroll.verticalScrollBar().maximum() > 0
        ordered = (group, *labels[:2], pair_heading, *labels[2:])
        for first, second in zip(ordered[:-1], ordered[1:], strict=True):
            first_rect = QRect(first.mapToGlobal(QPoint(0, 0)), first.size())
            second_rect = QRect(second.mapToGlobal(QPoint(0, 0)), second.size())
            assert not first_rect.intersects(second_rect)
        assert not QRect(group.mapToGlobal(QPoint(0, 0)), group.size()).intersects(
            QRect(search.mapToGlobal(QPoint(0, 0)), search.size())
        )
    assert window.pair_refresh_controller is None and window.findChildren(QThread) == []
    window.close()
