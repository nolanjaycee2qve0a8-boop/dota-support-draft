import time
from datetime import UTC, date, datetime

import pytest
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


class SlowComponentService(ComponentService):
    def refresh(self, input_data):
        time.sleep(0.2)
        return super().refresh(input_data)


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


def _empty_bundles() -> RoleEvidenceBundles:
    return RoleEvidenceBundles(
        RoleEvidenceBundle(Role.POSITION_4), RoleEvidenceBundle(Role.POSITION_5)
    )


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


def _related_session(heroes: tuple[Hero, ...], patch: Patch) -> ManualDraftSession:
    session = ManualDraftSession(heroes, patch)
    session.add_ally(heroes[0])
    session.add_enemy(heroes[1])
    return session


def _summary(window) -> QLabel:
    summary = window.findChild(QLabel, "evidence-capability-summary")
    assert summary is not None
    return summary


def _pair_status(window, name: str) -> QLabel:
    label = window.findChild(QLabel, name)
    assert label is not None
    return label


def _assert_safe_summary(text: str) -> None:
    assert all(term not in text.lower() for term in ("raw provider", "token", "realtime", "live"))


@pytest.mark.parametrize(
    ("has_meta", "has_personal", "expected_meta", "expected_personal"),
    (
        (False, False, "Meta unavailable", "Personal unavailable"),
        (False, True, "Meta unavailable", "Personal available (all-time; role unknown)"),
        (True, False, "Meta available (current-week role scope)", "Personal unavailable"),
        (
            True,
            True,
            "Meta available (current-week role scope)",
            "Personal available (all-time; role unknown)",
        ),
    ),
)
def test_no_token_pair_surfaces_reuse_independent_base_evidence_capability(
    has_meta: bool,
    has_personal: bool,
    expected_meta: str,
    expected_personal: str,
) -> None:
    """No-token Pair text reports Meta and Personal independently without side effects."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    personal = (
        (
            PersonalHeroStat(
                heroes[0],
                10,
                6,
                0.6,
                0.5,
                DataProvenance(
                    "fixture",
                    datetime.now(UTC),
                    "fixture",
                    patch.version,
                    data_kind="TEST/FIXTURE",
                ),
            ),
        )
        if has_personal
        else ()
    )
    session = _related_session(heroes, patch)
    window = create_main_window(
        session,
        evidence_by_role=_bundles(heroes, patch) if has_meta else _empty_bundles(),
        personal_stats=personal,
    )
    window.show()
    before = session.to_draft_state()
    search = window.findChild(QLineEdit, "candidate-search")
    assert search is not None and window.pair_refresh_controller is None
    search.setText("Hero")
    app.processEvents()
    assert session.to_draft_state() == before

    for label in (
        _summary(window),
        _pair_status(window, "pair-refresh-coverage"),
        _pair_status(window, "pair-refresh-action"),
    ):
        assert expected_meta in label.text()
        assert expected_personal in label.text()
        assert "Meta/Personal" not in label.text()
        _assert_safe_summary(label.text())
    window.close()


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
    assert "raw provider detail" not in _pair_status(window, "pair-refresh-coverage").text()
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


def test_capability_summary_names_service_unavailable_and_no_related_pick_states() -> None:
    """No service and no related picks are explicit local states, never retries."""
    app = QApplication.instance() or QApplication([])
    heroes = (Hero(1, "hero_one"), Hero(2, "hero_two"), Hero(3, "hero_three"))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    unavailable = create_main_window(
        _related_session(heroes, patch), evidence_by_role=_bundles(heroes, patch)
    )
    unavailable.show()
    text = _summary(unavailable).text()
    assert "Counter unavailable (pair service unavailable)" in text
    assert "Synergy unavailable (pair service unavailable)" in text
    assert "Meta available" in text and "Personal unavailable" in text
    _assert_safe_summary(text)
    unavailable.close()

    no_related = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_bundles(heroes, patch),
        pair_service=ComponentService(),  # type: ignore[arg-type]
        pair_debounce_ms=10_000,
    )
    no_related.show()
    controller = no_related.pair_refresh_controller
    assert controller is not None
    text = _summary(no_related).text()
    assert "Counter not requested" in text and "Synergy not requested" in text
    assert controller.generation == 0 and controller.findChildren(QThread) == []
    _assert_safe_summary(text)
    app.processEvents()
    no_related.close()


def test_capability_summary_names_no_shortlist_and_pending_without_extra_work() -> None:
    """No-shortlist and in-progress states are observed without the summary dispatching work."""
    app = QApplication.instance() or QApplication([])
    patch = Patch("p", "7.40", date(2026, 1, 1))
    exhausted = (Hero(1, "hero_one"), Hero(2, "hero_two"))
    no_shortlist = create_main_window(
        _related_session(exhausted, patch),
        evidence_by_role=_bundles(exhausted, patch),
        pair_service=ComponentService(),  # type: ignore[arg-type]
    )
    no_shortlist.show()
    controller = no_shortlist.pair_refresh_controller
    assert controller is not None
    text = _summary(no_shortlist).text()
    assert text.count("unavailable (no legal shortlist)") == 2
    assert controller.generation == 0 and controller.findChildren(QThread) == []
    _assert_safe_summary(text)
    no_shortlist.close()

    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 4))
    service = SlowComponentService()
    pending = create_main_window(
        _related_session(heroes, patch),
        evidence_by_role=_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    pending.show()
    controller = pending.pair_refresh_controller
    assert controller is not None
    _button(pending, "Refresh pair evidence").click()
    _wait(app, lambda: controller.active_thread is not None)
    text = _summary(pending).text()
    assert text.count("pending for current draft") == 2
    assert service.calls == 0 and controller.generation == 1
    _assert_safe_summary(text)
    _wait(app, lambda: controller.active_thread is None)
    _wait(
        app, lambda: controller.retired_worker_count == 0 and controller.findChildren(QThread) == []
    )
    pending.close()


@pytest.mark.parametrize(
    ("counter_error", "synergy_error", "expected_counter", "expected_synergy"),
    (
        (None, "raw provider detail", "available", "unavailable"),
        ("raw provider detail", None, "unavailable", "available"),
        (None, None, "available", "available"),
    ),
)
def test_capability_summary_covers_counter_synergy_result_matrix(
    counter_error: str | None,
    synergy_error: str | None,
    expected_counter: str,
    expected_synergy: str,
) -> None:
    """Each completed pair-component combination is rendered without error details or extra work."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = ComponentService(counter_error, synergy_error)
    window = create_main_window(
        _related_session(heroes, patch),
        evidence_by_role=_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    controller = window.pair_refresh_controller
    assert controller is not None
    _button(window, "Refresh pair evidence").click()
    _wait(app, lambda: service.calls == 1 and controller.active_thread is None)
    text = _summary(window).text()
    coverage = _pair_status(window, "pair-refresh-coverage").text()
    action = _pair_status(window, "pair-refresh-action").text()
    assert f"Counter {expected_counter} for current draft" in text
    assert f"Synergy {expected_synergy} for current draft" in text
    assert "raw provider detail" not in coverage and "raw provider detail" not in action
    _assert_safe_summary(coverage)
    _assert_safe_summary(action)
    assert controller.generation == 1
    _wait(
        app, lambda: controller.retired_worker_count == 0 and controller.findChildren(QThread) == []
    )
    _assert_safe_summary(text)
    window.close()
