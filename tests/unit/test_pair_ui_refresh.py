import json
import time
from datetime import UTC, date, datetime

from PySide6.QtCore import QPoint, QRect, Qt, QThread, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTableWidget,
    QTextEdit,
    QWidget,
)

from dota_support_draft.domain import (
    CounterEvidence,
    DataProvenance,
    EvidenceSet,
    Hero,
    Patch,
    PlannedLane,
    Role,
    RoleEvidenceBundle,
    RoleEvidenceBundles,
    RoleMetaEvidence,
    TeamPosition,
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


class RecordingSlowPairService(CountingPairService):
    def __init__(self, delay: float = 0.15) -> None:
        super().__init__()
        self.delay, self.inputs = delay, []

    def refresh(self, input_data):
        self.calls += 1
        self.inputs.append(input_data)
        time.sleep(self.delay)
        return PairEvidenceResult(input_data.generation, input_data.context)


class BlockingPairService(CountingPairService):
    def refresh(self, input_data):
        self.calls += 1
        time.sleep(1.7)
        return PairEvidenceResult(input_data.generation, input_data.context)


class ComponentPairService(CountingPairService):
    def __init__(self, counter_error: str | None = None, synergy_error: str | None = None) -> None:
        super().__init__()
        self.counter_error, self.synergy_error = counter_error, synergy_error

    def refresh(self, input_data):
        self.calls += 1
        return PairEvidenceResult(
            input_data.generation,
            input_data.context,
            counter_error=self.counter_error,
            synergy_error=self.synergy_error,
        )


class CounterPairService(CountingPairService):
    """Fixture service proving a completed pair overlay only rerenders local cards."""

    def refresh(self, input_data):
        self.calls += 1
        enemy = input_data.draft.enemy_picks[0].hero
        provenance = DataProvenance(
            "fixture",
            datetime.now(UTC),
            "fixture",
            input_data.draft.patch.version,
            data_kind="TEST/FIXTURE",
        )
        counters = tuple(
            CounterEvidence(
                candidate,
                enemy,
                input_data.context.role,
                input_data.draft.patch,
                1_000,
                provenance,
                effect=0.1,
            )
            for candidate in input_data.shortlist
        )
        return PairEvidenceResult(input_data.generation, input_data.context, counters=counters)


def _role_bundles(heroes: tuple[Hero, ...], patch: Patch) -> RoleEvidenceBundles:
    provenance = DataProvenance(
        "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
    )

    def bundle(role: Role) -> RoleEvidenceBundle:
        return RoleEvidenceBundle(
            role,
            EvidenceSet(
                role_meta=tuple(
                    RoleMetaEvidence(hero, role, patch, 100, 60, 0.6, provenance) for hero in heroes
                )
            ),
        )

    return RoleEvidenceBundles(bundle(Role.POSITION_4), bundle(Role.POSITION_5))


def _button(window, label: str) -> QPushButton:
    return next(button for button in window.findChildren(QPushButton) if button.text() == label)


def _label(window, object_name: str) -> QLabel:
    label = window.findChild(QLabel, object_name)
    assert label is not None
    return label


def _explanation(window) -> QTextEdit:
    panel = window.findChild(QTextEdit, "recommendation-explanation")
    assert panel is not None
    return panel


def _wait(app: QApplication, predicate, seconds: float = 2) -> None:
    deadline = time.monotonic() + seconds
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
    add_ally = _button(window, "Add Ally")
    assert table is not None
    table.selectRow(0)
    add_ally.click()
    _wait(
        app,
        lambda: (
            _label(window, "pair-refresh-coverage")
            .text()
            .startswith("Pair coverage: Counter: not requested; Synergy: available")
        ),
    )
    search = window.findChild(QLineEdit, "candidate-search")
    assert search is not None
    before = service.calls
    search.setText("hero")
    search.setText("hero 2")
    table.selectRow(0)
    app.processEvents()
    assert service.calls == before
    window.close()


def test_resizable_content_layout_preserves_controls_without_pair_work() -> None:
    """Splitter resizing is presentation-only and leaves pair refresh idle."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.resize(1000, 720)
    window.show()
    app.processEvents()

    splitter = window.findChild(QSplitter, "draft-content-splitter")
    composition = window.findChild(QTextEdit, "composition-context")
    table = window.findChild(QTableWidget, "candidate-table")
    explanation = _explanation(window)
    comparison = window.findChild(QWidget, "candidate-comparison")
    assert splitter is not None
    assert composition is not None
    assert table is not None
    assert splitter.count() == 5
    assert splitter.sizes()[0] == 0
    assert all(size > 0 for size in splitter.sizes()[1:])
    assert composition.isVisible() and table.isVisible() and explanation.isVisible()
    assert comparison is not None and comparison.isVisible()
    assert table.viewport().height() >= 120

    splitter.setSizes([0, 100, 320, 140, 170])
    window.resize(920, 680)
    app.processEvents()
    assert table.viewport().height() >= 100
    assert _button(window, "Add Ally").isVisible()
    assert _button(window, "Refresh pair evidence").isVisible()
    assert service.calls == 0
    assert window.pair_refresh_controller is not None
    assert window.pair_refresh_controller.active_thread is None
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
    add_ally = _button(window, "Add Ally")
    assert table is not None
    table.selectRow(0)
    add_ally.click()
    _wait(app, lambda: service.calls == 1)
    window.close()
    _wait(app, lambda: not window.isVisible())
    assert window.pair_refresh_controller is not None
    assert window.pair_refresh_controller.active_thread is None


def test_first_close_defers_long_pair_worker_and_auto_closes_after_retirement() -> None:
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
    service = BlockingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=RoleEvidenceBundles(bundle, RoleEvidenceBundle(Role.POSITION_5)),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    add_ally = _button(window, "Add Ally")
    assert table is not None
    table.selectRow(0)
    add_ally.click()
    _wait(app, lambda: service.calls == 1)
    beats = [0]
    timer = QTimer()
    timer.timeout.connect(lambda: beats.__setitem__(0, beats[0] + 1))
    timer.start(20)
    window.close()
    assert window.isVisible()
    _wait(app, lambda: beats[0] >= 3)
    assert window.pair_refresh_controller is not None
    _wait(app, lambda: not window.isVisible(), seconds=4)
    timer.stop()
    assert service.calls == 1 and window.pair_refresh_controller.active_thread is None


def test_pair_observability_tracks_context_shortlist_role_and_reset() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 11))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    service = ComponentPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    assert table is not None
    table.selectRow(0)
    _button(window, "Add Ally").click()
    _wait(
        app,
        lambda: (
            _label(window, "pair-refresh-coverage")
            .text()
            .startswith("Pair coverage: Counter: not requested; Synergy: available")
        ),
    )
    context = _label(window, "pair-refresh-context").text()
    assert "Position 4 | allies 1 | enemies 0 | shortlist (8):" in context
    assert "Hero 1," not in context and not context.endswith("Hero 1")

    radios = {radio.text(): radio for radio in window.findChildren(QRadioButton)}
    radios["Position 5"].click()
    _wait(app, lambda: service.calls == 2)
    assert (
        "Position 5 | allies 1 | enemies 0 | shortlist (8):"
        in _label(window, "pair-refresh-context").text()
    )

    _button(window, "Reset Draft").click()
    app.processEvents()
    assert "Position 5 | allies 0 | enemies 0" in _label(window, "pair-refresh-context").text()
    assert _label(window, "pair-refresh-coverage").text() == (
        "Pair coverage: no related picks; Meta/Personal only; no pair enrichment"
    )
    window.close()


def test_pair_observability_names_partial_and_error_components() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 5))
    patch = Patch("p", "7.40", date(2026, 1, 1))

    for counter_error, synergy_error, expected in (
        ("counter offline", None, "Counter: unavailable (counter offline); Synergy: available"),
        (
            "counter offline",
            "synergy offline",
            "Counter: unavailable (counter offline); Synergy: unavailable (synergy offline)",
        ),
    ):
        session = ManualDraftSession(heroes, patch)
        service = ComponentPairService(counter_error, synergy_error)
        window = create_main_window(
            session,
            evidence_by_role=_role_bundles(heroes, patch),
            pair_service=service,  # type: ignore[arg-type]
            pair_debounce_ms=0,
        )
        window.show()
        table = window.findChild(QTableWidget)
        assert table is not None
        table.selectRow(0)
        _button(window, "Add Ally").click()
        table.selectRow(0)
        _button(window, "Add Enemy").click()
        _wait(
            app,
            lambda expected=expected, current_window=window: (
                expected in _label(current_window, "pair-refresh-coverage").text()
            ),
        )
        window.close()


def test_pair_actionability_explains_unavailable_service_and_no_related_picks_locally() -> None:
    """Action guidance is display-only when pair work is unavailable or not applicable."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))

    unavailable = create_main_window(
        ManualDraftSession(heroes, patch), evidence_by_role=_role_bundles(heroes, patch)
    )
    unavailable.show()
    assert (
        "STRATZ pair-refresh service is unavailable in this session"
        in _label(unavailable, "pair-refresh-action").text()
    )
    unavailable.close()

    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    search = window.findChild(QLineEdit, "candidate-search")
    controller = window.pair_refresh_controller
    assert table is not None and search is not None and controller is not None
    action = _label(window, "pair-refresh-action")
    assert "Add an allied or enemy pick" in action.text()
    assert "Meta/Personal remain available" in action.text()

    table.selectRow(0)
    search.setText("hero")
    table.horizontalHeader().sectionClicked.emit(0)
    app.processEvents()
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None
    assert "Add an allied or enemy pick" in action.text()
    window.close()


def test_pair_actionability_explains_loading_partial_retry_and_zero_extra_dispatch() -> None:
    """Existing state transitions change guidance only; retry remains the existing button action."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 5))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    session.add_ally(heroes[0])
    session.add_enemy(heroes[1])
    service = ComponentPairService(counter_error="counter offline")
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    manual = window.findChild(QPushButton, "manual-pair-refresh")
    table = window.findChild(QTableWidget, "candidate-table")
    search = window.findChild(QLineEdit, "candidate-search")
    controller = window.pair_refresh_controller
    assert (
        manual is not None and table is not None and search is not None and controller is not None
    )
    assert manual.isEnabled()

    manual.click()
    _wait(
        app,
        lambda: (
            "Counter is unavailable; Synergy is still available"
            in _label(window, "pair-refresh-action").text()
        ),
    )
    action = _label(window, "pair-refresh-action").text()
    assert "Refresh pair evidence to retry/recalculate this context" in action
    assert "Meta/Personal remain available" in action
    assert "counter offline" not in action
    calls, generation = service.calls, controller.generation

    table.selectRow(0)
    search.setText("hero")
    table.horizontalHeader().sectionClicked.emit(0)
    app.processEvents()
    assert service.calls == calls and controller.generation == generation
    window.close()


def test_pair_actionability_names_both_successful_components() -> None:
    """Ready guidance identifies Counter and Synergy without requesting another evaluation."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    session.add_ally(heroes[0])
    session.add_enemy(heroes[1])
    service = ComponentPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    manual = window.findChild(QPushButton, "manual-pair-refresh")
    assert manual is not None
    manual.click()
    _wait(
        app,
        lambda: "Counter and Synergy are available" in _label(window, "pair-refresh-action").text(),
    )
    assert service.calls == 1
    assert (
        "Meta/Personal remain independently available"
        in _label(window, "pair-refresh-action").text()
    )
    window.close()


def test_pair_actionability_names_in_progress_state_without_starting_extra_work() -> None:
    """The updating message observes the active worker and does not create another one."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    session.add_enemy(heroes[0])
    service = SlowPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    manual = window.findChild(QPushButton, "manual-pair-refresh")
    controller = window.pair_refresh_controller
    assert manual is not None and controller is not None
    manual.click()
    _wait(
        app,
        lambda: (
            service.calls == 1
            and "Updating evidence for this context" in _label(window, "pair-refresh-action").text()
        ),
    )
    assert controller.active_thread is not None
    assert "Meta/Personal remain available" in _label(window, "pair-refresh-action").text()
    window.close()


def test_reset_discards_stale_pair_result_without_leaving_old_observability() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = SlowPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    assert table is not None
    table.selectRow(0)
    _button(window, "Add Ally").click()
    _wait(app, lambda: service.calls == 1)
    _button(window, "Reset Draft").click()
    _wait(
        app,
        lambda: (
            window.pair_refresh_controller is not None
            and window.pair_refresh_controller.active_thread is None
        ),
    )
    assert "allies 0 | enemies 0" in _label(window, "pair-refresh-context").text()
    assert _label(window, "pair-refresh-coverage").text() == (
        "Pair coverage: no related picks; Meta/Personal only; no pair enrichment"
    )
    window.close()


def test_visible_window_survives_rapid_enemy_edits_and_retires_pair_threads() -> None:
    app = QApplication.instance() or QApplication([])
    original_quit_on_last_window_closed = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(True)
    try:
        heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 10))
        patch = Patch("p", "7.40", date(2026, 1, 1))
        service = RecordingSlowPairService()
        window = create_main_window(
            ManualDraftSession(heroes, patch),
            evidence_by_role=_role_bundles(heroes, patch),
            pair_service=service,  # type: ignore[arg-type]
            pair_debounce_ms=0,
        )
        window.show()
        table = window.findChild(QTableWidget)
        assert table is not None and window.pair_refresh_controller is not None
        controller = window.pair_refresh_controller
        table.selectRow(0)
        _button(window, "Add Enemy").click()
        outcome = []
        deadline = time.monotonic() + 3

        def queue_latest_enemies() -> None:
            if not service.inputs:
                QTimer.singleShot(10, queue_latest_enemies)
                return
            for _ in range(3):
                table.selectRow(0)
                _button(window, "Add Enemy").click()

        def finish_after_retirement() -> None:
            if (
                len(service.inputs) == 2
                and controller.active_thread is None
                and not controller.findChildren(QThread)
                and controller.retired_worker_count == 0
            ):
                outcome.append(
                    window.isVisible()
                    and "enemies 4" in _label(window, "pair-refresh-context").text()
                    and len(service.inputs[-1].context.enemy_ids) == 4
                    and controller.retired_worker_cleanup_thread == app.thread()
                )
                window.close()
                return
            if time.monotonic() >= deadline:
                outcome.append(False)
                controller.begin_shutdown()
                window.close()
                return
            QTimer.singleShot(10, finish_after_retirement)

        QTimer.singleShot(10, queue_latest_enemies)
        QTimer.singleShot(10, finish_after_retirement)
        app.exec()
        assert outcome == [True]
        assert [len(input_data.context.enemy_ids) for input_data in service.inputs] == [1, 4]
    finally:
        app.setQuitOnLastWindowClosed(original_quit_on_last_window_closed)


def test_reset_then_close_during_active_pair_work_retires_without_restarting() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = RecordingSlowPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    assert table is not None and window.pair_refresh_controller is not None
    controller = window.pair_refresh_controller
    table.selectRow(0)
    _button(window, "Add Enemy").click()
    _wait(app, lambda: len(service.inputs) == 1)
    _button(window, "Reset Draft").click()
    window.close()
    _wait(
        app,
        lambda: (
            not window.isVisible()
            and controller.active_thread is None
            and controller.retired_worker_count == 0
        ),
    )
    app.processEvents()
    assert (
        len(service.inputs) == 1
        and controller.findChildren(QThread) == []
        and controller.retired_worker_cleanup_thread == app.thread()
    )


def test_manual_refresh_immediately_dispatches_current_context() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 5))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = RecordingSlowPairService(0.02)
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=1000,
    )
    window.show()
    table = window.findChild(QTableWidget)
    manual = window.findChild(QPushButton, "manual-pair-refresh")
    assert table is not None and manual is not None and not manual.isEnabled()
    table.selectRow(0)
    _button(window, "Add Enemy").click()
    assert manual.isEnabled() and service.calls == 0
    manual.click()
    _wait(app, lambda: len(service.inputs) == 1, seconds=0.4)
    _wait(
        app,
        lambda: (
            _label(window, "pair-refresh-status").text() == "Manual pair refresh complete: Counter"
        ),
    )
    assert len(service.inputs[0].context.enemy_ids) == 1
    window.close()


def test_manual_clicks_keep_only_latest_pending_and_close_drops_it() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 5))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = RecordingSlowPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    manual = window.findChild(QPushButton, "manual-pair-refresh")
    assert table is not None and manual is not None and window.pair_refresh_controller is not None
    controller = window.pair_refresh_controller
    table.selectRow(0)
    _button(window, "Add Enemy").click()
    _wait(app, lambda: len(service.inputs) == 1)
    for _ in range(3):
        manual.click()
    _wait(
        app,
        lambda: (
            len(service.inputs) == 2
            and controller.active_thread is None
            and controller.retired_worker_count == 0
        ),
    )
    assert [input_data.generation for input_data in service.inputs] == [1, 4]
    assert _label(window, "pair-refresh-status").text() == ("Manual pair refresh complete: Counter")

    manual.click()
    window.close()
    _wait(
        app,
        lambda: (
            not window.isVisible()
            and controller.active_thread is None
            and controller.retired_worker_count == 0
        ),
    )
    assert len(service.inputs) == 3 and not manual.isEnabled()


def test_close_drops_manual_pending_behind_active_pair_worker() -> None:
    """A deferred close retires, rather than dispatches, a manual pending refresh."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 3))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = RecordingSlowPairService(delay=0.3)
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    manual = window.findChild(QPushButton, "manual-pair-refresh")
    assert table is not None and manual is not None and window.pair_refresh_controller is not None
    controller = window.pair_refresh_controller

    table.selectRow(0)
    _button(window, "Add Enemy").click()
    _wait(app, lambda: len(service.inputs) == 1 and controller.active_thread is not None)

    manual.click()
    app.processEvents()
    assert len(service.inputs) == 1
    assert controller.active_thread is not None

    window.close()
    assert window.isVisible()
    _wait(
        app,
        lambda: (
            not window.isVisible()
            and controller.active_thread is None
            and controller.retired_worker_count == 0
        ),
        seconds=3.0,
    )
    app.processEvents()

    assert len(service.inputs) == 1
    assert service.inputs[0].context.enemy_ids == (1,)
    assert controller.findChildren(QThread) == []


def test_recommendation_explanation_tracks_selection_and_search_without_pair_network() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    search = window.findChild(QLineEdit, "candidate-search")
    panel = _explanation(window)
    assert table is not None and search is not None and panel.isReadOnly()
    assert panel.toPlainText() == "Select a candidate hero to inspect its evidence."

    table.selectRow(0)
    panel_text = panel.toPlainText()
    assert "Candidate: Hero 1" in panel_text
    assert "Recommendation summary" in panel_text
    assert "Experimental score:" in panel_text
    assert "experimental ordering score; not a win prediction" in panel_text
    assert (
        "Evidence" in panel_text and "Why / availability" in panel_text and "Context" in panel_text
    )
    assert "Personal: unavailable — fixed weight contributes neutral zero" in panel_text

    search.setText("Hero 2")
    app.processEvents()
    assert panel.toPlainText() == "Select a candidate hero to inspect its evidence."
    table.selectRow(0)
    assert "Candidate: Hero 2" in panel.toPlainText()
    assert service.calls == 0
    window.close()


def test_candidate_filter_status_and_clear_are_local_and_keep_display_sort() -> None:
    """Search feedback and clearing rerender only local candidate presentation."""
    app = QApplication.instance() or QApplication([])
    heroes = (
        Hero(1, "zulu", "Zulu"),
        Hero(2, "bravo", "Bravo"),
        Hero(3, "alpha", "Alpha"),
    )
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    search = window.findChild(QLineEdit, "candidate-search")
    clear = window.findChild(QPushButton, "candidate-search-clear")
    filter_status = _label(window, "candidate-filter-status")
    assert table is not None and search is not None and clear is not None
    assert "displaying 3 / 3 legal candidates" in filter_status.text()
    assert "text filter: none" in filter_status.text()
    assert "display sort: default recommendation order" in filter_status.text()
    assert not clear.isEnabled()

    table.horizontalHeader().sectionClicked.emit(0)
    bravo_index = next(
        index for index in range(table.rowCount()) if table.item(index, 0).text() == "Bravo"
    )
    table.selectRow(bravo_index)
    search.setText("Bravo")
    app.processEvents()
    assert table.rowCount() == 1 and table.item(0, 0).text() == "Bravo"
    assert "Candidate: Bravo" in _explanation(window).toPlainText()
    assert "displaying 1 / 3 legal candidates" in filter_status.text()
    assert 'text filter: "Bravo"' in filter_status.text()
    assert "display sort: Hero ascending" in filter_status.text()
    assert clear.isEnabled()

    clear.click()
    app.processEvents()
    assert search.text() == "" and table.rowCount() == 3
    assert "Candidate: Bravo" in _explanation(window).toPlainText()
    assert "text filter: none" in filter_status.text()
    assert "display sort: Hero ascending" in filter_status.text()
    assert not clear.isEnabled()

    search.setText("missing")
    app.processEvents()
    assert table.rowCount() == 0
    assert _explanation(window).toPlainText() == "Select a candidate hero to inspect its evidence."
    assert service.calls == 0
    assert window.pair_refresh_controller is not None
    assert window.pair_refresh_controller.generation == 0
    assert window.pair_refresh_controller.active_thread is None
    window.close()


def test_recommendation_explanation_uses_current_role_and_discards_pair_error_on_reset() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    provenance = DataProvenance(
        "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
    )
    position_four = RoleEvidenceBundle(
        Role.POSITION_4,
        EvidenceSet(
            role_meta=tuple(
                RoleMetaEvidence(hero, Role.POSITION_4, patch, 100, 60, 0.6, provenance)
                for hero in heroes
            )
        ),
    )
    position_five = RoleEvidenceBundle(
        Role.POSITION_5,
        EvidenceSet(
            role_meta=tuple(
                RoleMetaEvidence(hero, Role.POSITION_5, patch, 100, 70, 0.7, provenance)
                for hero in heroes
            )
        ),
    )
    service = ComponentPairService(counter_error="counter offline")
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=RoleEvidenceBundles(position_four, position_five),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    assert table is not None
    table.selectRow(0)
    panel = _explanation(window)
    assert "Role: Position 4" in panel.toPlainText()
    assert "Meta: 5%" in panel.toPlainText()

    radios = {radio.text(): radio for radio in window.findChildren(QRadioButton)}
    radios["Position 5"].click()
    assert "Role: Position 5" in panel.toPlainText()
    assert "Meta: 10%" in panel.toPlainText()

    table.selectRow(0)
    _button(window, "Add Enemy").click()
    _wait(
        app,
        lambda: (
            "Counter: unavailable (counter offline)"
            in _label(window, "pair-refresh-coverage").text()
        ),
    )
    assert panel.toPlainText() == "Select a candidate hero to inspect its evidence."
    table.selectRow(0)
    assert "Counter: unavailable — fixed weight contributes neutral zero" in panel.toPlainText()
    assert "Why:" in panel.toPlainText()

    _button(window, "Reset Draft").click()
    app.processEvents()
    assert "Pair coverage: no related picks" in panel.toPlainText()
    assert "counter offline" not in panel.toPlainText()
    assert "Counter: unavailable — fixed weight contributes neutral zero" in panel.toPlainText()
    window.close()


def test_candidate_table_sorting_preserves_visible_selection_without_pair_work() -> None:
    """Header sorting is local display state and retains a selected visible candidate."""
    app = QApplication.instance() or QApplication([])
    heroes = (
        Hero(1, "zulu", "Zulu"),
        Hero(2, "bravo", "Bravo"),
        Hero(3, "alpha", "Alpha"),
    )
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    search = window.findChild(QLineEdit, "candidate-search")
    sort_status = _label(window, "candidate-sort-status")
    assert table is not None and search is not None and window.pair_refresh_controller is not None
    controller = window.pair_refresh_controller
    assert [table.item(index, 0).text() for index in range(table.rowCount())] == [
        "Alpha",
        "Bravo",
        "Zulu",
    ]
    table.selectRow(1)
    assert "Candidate: Bravo" in _explanation(window).toPlainText()

    table.horizontalHeader().sectionClicked.emit(0)
    app.processEvents()
    assert table.item(0, 0) is not None and table.item(0, 0).text() == "Alpha"
    assert "Hero ascending" in sort_status.text()
    assert "Candidate: Bravo" in _explanation(window).toPlainText()

    table.horizontalHeader().sectionClicked.emit(0)
    app.processEvents()
    assert table.item(0, 0) is not None and table.item(0, 0).text() == "Zulu"
    assert "Hero descending" in sort_status.text()
    assert "Candidate: Bravo" in _explanation(window).toPlainText()

    search.setText("Alpha")
    app.processEvents()
    assert _explanation(window).toPlainText() == "Select a candidate hero to inspect its evidence."
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None
    window.close()


def test_candidate_keyboard_search_table_and_comparison_are_local_only() -> None:
    """Ctrl+F, Escape, Enter, and arrows change local presentation but never mutate a draft."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    search = window.findChild(QLineEdit, "candidate-search")
    add_comparison = window.findChild(QPushButton, "add-candidate-comparison")
    comparison = window.findChild(QTextEdit, "candidate-comparison-slot-1")
    controller = window.pair_refresh_controller
    assert (
        table is not None
        and search is not None
        and add_comparison is not None
        and comparison is not None
        and controller is not None
    )
    assert search.accessibleName() == "Candidate search"
    assert "Escape clears it" in search.accessibleDescription()
    assert table.accessibleName() == "Candidate table"

    window.activateWindow()
    table.setFocus()
    app.processEvents()
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert search.hasFocus()
    QTest.keyClicks(search, "hero")
    QTest.keyClick(search, Qt.Key.Key_Return)
    app.processEvents()
    assert table.hasFocus() and table.currentRow() == 0
    QTest.keyClick(table, Qt.Key.Key_Down)
    app.processEvents()
    assert table.currentRow() == 1
    assert "Candidate: Hero 2" in _explanation(window).toPlainText()

    assert add_comparison.isEnabled()
    add_comparison.click()
    assert "Hero 2" in comparison.toPlainText()
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert search.hasFocus()
    QTest.keyClick(search, Qt.Key.Key_Escape)
    app.processEvents()
    assert search.text() == "" and search.hasFocus()
    assert "Candidate: Hero 2" in _explanation(window).toPlainText()
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None
    window.close()


def test_manual_import_preview_cancel_and_confirm_follow_local_pair_contract() -> None:
    """Preview/cancel are inert; confirmation atomically replaces draft and schedules once."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 6))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    session.add_ally(heroes[0])
    session.add_enemy(heroes[1])
    session.set_ally_assignment(heroes[0], TeamPosition.POSITION_1, PlannedLane.SAFE)
    service = CountingPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=10_000,
    )
    window.show()
    text = window.findChild(QTextEdit, "manual-import-text")
    preview = _label(window, "manual-import-preview")
    validate = window.findChild(QPushButton, "validate-manual-import")
    cancel = window.findChild(QPushButton, "cancel-manual-import")
    confirm = window.findChild(QPushButton, "confirm-manual-import")
    composition = window.findChild(QTextEdit, "composition-context")
    controller = window.pair_refresh_controller
    assert (
        text is not None
        and validate is not None
        and cancel is not None
        and confirm is not None
        and composition is not None
        and controller is not None
    )
    payload = json.dumps(
        {
            "schema_version": "dota-support-draft/manual-import/v1",
            "provenance": {"kind": "MANUAL_IMPORT", "observed_at": "2026-09-02T00:00:00Z"},
            "draft": {
                "complete": True,
                "patch_version": "7.40",
                "intended_role": "POSITION_5",
                "allied_hero_ids": [3],
                "enemy_hero_ids": [4],
                "banned_hero_ids": [5],
            },
        }
    )
    original = session.to_draft_state()
    text.setPlainText(payload)
    validate.click()
    app.processEvents()
    assert confirm.isEnabled() and cancel.isEnabled()
    assert "current 1" in preview.text() and "clears all existing manual ally" in preview.text()
    assert session.to_draft_state() == original
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None

    cancel.click()
    assert not confirm.isEnabled() and session.to_draft_state() == original
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None

    validate.click()
    confirm.click()
    app.processEvents()
    assert session.role is Role.POSITION_5
    assert [hero.hero_id for hero in session.allies] == [3]
    assert [hero.hero_id for hero in session.enemies] == [4]
    assert {hero.hero_id for hero in session.bans} == {5}
    assert session.ally_assignments == {}
    assert "Hero 1" not in composition.toPlainText()
    assert "Import confirmed" in preview.text()
    assert controller.generation == 1 and service.calls == 0 and controller.active_thread is None
    window.close()


def test_manual_import_rejection_and_unknown_time_do_not_dispatch_before_confirmation() -> None:
    """Bad input is inert, while unknown time remains an explicitly confirmable preview."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    service = CountingPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    text = window.findChild(QTextEdit, "manual-import-text")
    preview = _label(window, "manual-import-preview")
    validate = window.findChild(QPushButton, "validate-manual-import")
    confirm = window.findChild(QPushButton, "confirm-manual-import")
    controller = window.pair_refresh_controller
    assert (
        text is not None and validate is not None and confirm is not None and controller is not None
    )
    original = session.to_draft_state()
    text.setPlainText('{"schema_version":"unsupported"}')
    validate.click()
    app.processEvents()
    assert "Import rejected" in preview.text() and not confirm.isEnabled()
    assert session.to_draft_state() == original
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None

    text.setPlainText(
        json.dumps(
            {
                "schema_version": "dota-support-draft/manual-import/v1",
                "provenance": {"kind": "MANUAL_IMPORT", "observed_at": "unknown"},
                "draft": {
                    "complete": True,
                    "patch_version": "7.40",
                    "intended_role": "POSITION_4",
                    "allied_hero_ids": [],
                    "enemy_hero_ids": [],
                    "banned_hero_ids": [],
                },
            }
        )
    )
    validate.click()
    assert confirm.isEnabled() and "observed time unknown" in preview.text()
    assert session.to_draft_state() == original
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None
    window.close()


def test_close_with_pending_import_preview_keeps_pair_shutdown_cooperative() -> None:
    """A pending preview is inert while an active worker completes the normal deferred close."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 5))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    session.add_enemy(heroes[0])
    service = SlowPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    manual = window.findChild(QPushButton, "manual-pair-refresh")
    text = window.findChild(QTextEdit, "manual-import-text")
    validate = window.findChild(QPushButton, "validate-manual-import")
    confirm = window.findChild(QPushButton, "confirm-manual-import")
    controller = window.pair_refresh_controller
    assert (
        manual is not None
        and text is not None
        and validate is not None
        and confirm is not None
        and controller is not None
    )
    original = session.to_draft_state()
    manual.click()
    _wait(app, lambda: service.calls == 1 and controller.active_thread is not None)
    text.setPlainText(
        json.dumps(
            {
                "schema_version": "dota-support-draft/manual-import/v1",
                "provenance": {"kind": "MANUAL_IMPORT", "observed_at": "2026-09-02T00:00:00Z"},
                "draft": {
                    "complete": True,
                    "patch_version": "7.40",
                    "intended_role": "POSITION_5",
                    "allied_hero_ids": [2],
                    "enemy_hero_ids": [],
                    "banned_hero_ids": [],
                },
            }
        )
    )
    validate.click()
    assert confirm.isEnabled() and session.to_draft_state() == original

    window.close()
    assert window.isVisible()
    _wait(
        app,
        lambda: (
            not window.isVisible()
            and controller.active_thread is None
            and controller.retired_worker_count == 0
        ),
    )
    assert session.to_draft_state() == original
    assert service.calls == 1 and controller.findChildren(QThread) == []


def test_manual_import_layout_is_collapsed_and_keeps_draft_controls_accessible() -> None:
    """The low-frequency import panel cannot overlap or consume the draft workspace by default."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.resize(1920, 1080)
    window.show()
    entry = window.findChild(QWidget, "manual-import-entry")
    panel = window.findChild(QWidget, "manual-import-section")
    toggle = window.findChild(QPushButton, "toggle-manual-import")
    text = window.findChild(QTextEdit, "manual-import-text")
    validate = window.findChild(QPushButton, "validate-manual-import")
    cancel = window.findChild(QPushButton, "cancel-manual-import")
    candidates = window.findChild(QTableWidget, "candidate-table")
    allies = window.findChild(QListWidget, "allied-picks")
    save_context = window.findChild(QPushButton, "save-ally-composition")
    controller = window.pair_refresh_controller
    assert (
        entry is not None
        and panel is not None
        and toggle is not None
        and text is not None
        and validate is not None
        and cancel is not None
        and candidates is not None
        and allies is not None
        and save_context is not None
        and controller is not None
    )

    def bounds(widget: QWidget) -> QRect:
        return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())

    def assert_accessible(expanded: bool) -> None:
        app.processEvents()
        for widget in (entry, candidates, allies, save_context):
            assert widget.isVisible() and widget.width() > 0 and widget.height() > 0
        assert candidates.viewport().height() > 0
        assert not bounds(entry).intersects(bounds(candidates))
        assert not bounds(allies).intersects(bounds(candidates))
        assert panel.isVisible() is expanded
        if expanded:
            assert not bounds(panel).intersects(bounds(candidates))

    assert_accessible(False)
    window.resize(900, 700)
    assert_accessible(False)
    toggle.click()
    assert_accessible(True)
    text.setPlainText(
        json.dumps(
            {
                "schema_version": "dota-support-draft/manual-import/v1",
                "provenance": {"kind": "MANUAL_IMPORT", "observed_at": "2026-09-02T00:00:00Z"},
                "draft": {
                    "complete": True,
                    "patch_version": "7.40",
                    "intended_role": "POSITION_4",
                    "allied_hero_ids": [],
                    "enemy_hero_ids": [],
                    "banned_hero_ids": [],
                },
            }
        )
    )
    validate.click()
    assert not toggle.isEnabled() and candidates.viewport().height() > 0
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None
    cancel.click()
    assert not toggle.isChecked()
    assert_accessible(False)
    window.close()


def test_manual_import_template_and_clear_are_editor_only_local_actions() -> None:
    """Template/clear edit only text and invalidate previews without draft or pair side effects."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    service = CountingPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    toggle = window.findChild(QPushButton, "toggle-manual-import")
    text = window.findChild(QTextEdit, "manual-import-text")
    template = window.findChild(QPushButton, "insert-manual-import-template")
    clear = window.findChild(QPushButton, "clear-manual-import-text")
    validate = window.findChild(QPushButton, "validate-manual-import")
    confirm = window.findChild(QPushButton, "confirm-manual-import")
    table = window.findChild(QTableWidget, "candidate-table")
    controller = window.pair_refresh_controller
    assert (
        toggle is not None
        and text is not None
        and template is not None
        and clear is not None
        and validate is not None
        and confirm is not None
        and table is not None
        and controller is not None
    )
    original = session.to_draft_state()
    assert not toggle.isChecked()
    window.activateWindow()
    app.processEvents()
    toggle.click()
    template.click()
    document = json.loads(text.toPlainText())
    assert document["schema_version"] == "dota-support-draft/manual-import/v1"
    assert document["draft"] == {
        "complete": True,
        "patch_version": "7.40",
        "intended_role": "POSITION_4",
        "allied_hero_ids": [],
        "enemy_hero_ids": [],
        "banned_hero_ids": [],
    }
    assert text.hasFocus() and table.viewport().height() > 0
    assert session.to_draft_state() == original
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None

    validate.click()
    assert confirm.isEnabled()
    template.click()
    assert not confirm.isEnabled() and session.to_draft_state() == original
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None

    validate.click()
    assert confirm.isEnabled()
    clear.click()
    app.processEvents()
    assert text.toPlainText() == "" and not confirm.isEnabled()
    assert session.to_draft_state() == original
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None
    window.close()


def test_copy_draft_summary_writes_only_manual_context_without_pair_side_effects() -> None:
    """Copy is an explicit local clipboard write and does not mutate or refresh the draft."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    session.add_ally(heroes[0])
    session.set_ally_assignment(heroes[0], TeamPosition.POSITION_1, PlannedLane.SAFE)
    session.add_enemy(heroes[1])
    session.ban(heroes[2])
    service = CountingPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    copy = window.findChild(QPushButton, "copy-draft-summary")
    status = _label(window, "draft-summary-status")
    controller = window.pair_refresh_controller
    assert copy is not None and controller is not None
    original = session.to_draft_state()

    copy.click()
    payload = app.clipboard().text()
    assert "Manual draft summary — not auto-detected" in payload
    assert "Patch: 7.40" in payload and "Intended role: Position 4" in payload
    assert "Allied picks: Hero 1" in payload and "Enemy picks: Hero 2" in payload
    assert "Bans: Hero 3" in payload and "- Hero 1: P1, Safe" in payload
    assert all(term not in payload.casefold() for term in ("token", "account", "score", "evidence"))
    assert "copied" in status.text().lower()
    assert session.to_draft_state() == original
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None
    assert controller.findChildren(QThread) == []
    window.close()


def test_local_candidate_display_matrix_has_no_draft_or_pair_side_effects() -> None:
    """Presentation-only candidate controls preserve draft, canonical evidence, and pair state."""
    app = QApplication.instance() or QApplication([])
    heroes = (
        Hero(1, "zulu", "Zulu"),
        Hero(2, "bravo", "Bravo"),
        Hero(3, "alpha", "Alpha"),
    )
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    service = CountingPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    search = window.findChild(QLineEdit, "candidate-search")
    clear_search = window.findChild(QPushButton, "candidate-search-clear")
    add = window.findChild(QPushButton, "add-candidate-comparison")
    remove = window.findChild(QPushButton, "remove-candidate-comparison")
    clear_comparison = window.findChild(QPushButton, "clear-candidate-comparison")
    comparison = window.findChild(QTextEdit, "candidate-comparison-slot-1")
    controller = window.pair_refresh_controller
    assert (
        table is not None
        and search is not None
        and clear_search is not None
        and add is not None
        and remove is not None
        and clear_comparison is not None
        and comparison is not None
        and controller is not None
    )

    def displayed_values() -> dict[str, tuple[str, ...]]:
        return {
            table.item(index, 0).text(): tuple(
                table.item(index, column).text() for column in range(1, table.columnCount())
            )
            for index in range(table.rowCount())
        }

    initial_draft = session.to_draft_state()
    initial_values = displayed_values()
    initial_pair_context = _label(window, "pair-refresh-context").text()

    def assert_local_only() -> None:
        """Every matrix action may alter display state, never semantic input or pair work."""
        assert session.to_draft_state() == initial_draft
        assert _label(window, "pair-refresh-context").text() == initial_pair_context
        assert all(initial_values[name] == values for name, values in displayed_values().items())
        assert service.calls == 0
        assert controller.generation == 0
        assert controller.active_thread is None
        assert controller.findChildren(QThread) == []

    # Typed filtering and its explicit clear only alter the local visible subset.
    window.activateWindow()
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(search, "Bravo")
    app.processEvents()
    assert table.rowCount() == 1 and table.item(0, 0).text() == "Bravo"
    assert_local_only()
    clear_search.click()
    app.processEvents()
    assert search.text() == "" and table.rowCount() == len(initial_values)
    assert_local_only()

    # Sorting and selection re-order or explain existing rows without changing canonical evidence.
    table.horizontalHeader().sectionClicked.emit(0)
    table.selectRow(1)
    app.processEvents()
    assert "Candidate: Bravo" in _explanation(window).toPlainText()
    assert_local_only()

    # Comparison add/remove/clear consumes the selected local row only.
    add.click()
    assert "Bravo" in comparison.toPlainText()
    assert_local_only()
    remove.click()
    assert "Empty comparison slot" in comparison.toPlainText()
    assert_local_only()
    add.click()
    clear_comparison.click()
    assert "Empty comparison slot" in comparison.toPlainText()
    assert_local_only()

    # Keyboard focus and arrow navigation remain within search/table presentation state.
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(search, "Bravo")
    QTest.keyClick(search, Qt.Key.Key_Return)
    assert table.hasFocus() and table.currentRow() == 0
    QTest.keyClick(table, Qt.Key.Key_Down)
    QTest.keyClick(table, Qt.Key.Key_Up)
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(search, Qt.Key.Key_Escape)
    app.processEvents()
    assert search.text() == "" and search.hasFocus()
    assert "Candidate: Bravo" in _explanation(window).toPlainText()
    assert_local_only()
    window.close()


def test_candidate_table_focus_and_selection_survive_pair_result_rerender() -> None:
    """A pair result preserves a legal table selection and table focus for arrow navigation."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 5))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    session.add_enemy(heroes[0])
    service = SlowPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    manual = window.findChild(QPushButton, "manual-pair-refresh")
    controller = window.pair_refresh_controller
    assert table is not None and manual is not None and controller is not None
    table.setCurrentCell(0, 0)
    selected = table.item(0, 0)
    assert selected is not None
    selected_name = selected.text()
    table.setFocus()

    manual.click()
    table.setFocus()
    _wait(app, lambda: service.calls == 1 and controller.active_thread is None)
    assert table.hasFocus()
    current = table.item(table.currentRow(), 0)
    assert current is not None and current.text() == selected_name
    QTest.keyClick(table, Qt.Key.Key_Down)
    app.processEvents()
    assert table.currentRow() == 1
    window.close()


def test_candidate_sorting_survives_role_and_pair_overlay_refreshes() -> None:
    """A local sort persists across semantic rerenders without adding pair work itself."""
    app = QApplication.instance() or QApplication([])
    heroes = (
        Hero(1, "zulu", "Zulu"),
        Hero(2, "bravo", "Bravo"),
        Hero(3, "alpha", "Alpha"),
        Hero(4, "delta", "Delta"),
    )
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    session.add_enemy(heroes[0])
    service = CountingPairService()
    window = create_main_window(
        session,
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    manual = window.findChild(QPushButton, "manual-pair-refresh")
    assert table is not None and manual is not None
    table.selectRow(1)
    selected_hero = table.item(1, 0)
    assert selected_hero is not None
    selected_name = selected_hero.text()
    manual.click()
    _wait(app, lambda: service.calls == 1)
    _wait(
        app,
        lambda: "Counter: available" in _label(window, "pair-refresh-coverage").text(),
    )

    table.horizontalHeader().sectionClicked.emit(0)
    app.processEvents()
    assert f"Candidate: {selected_name}" in _explanation(window).toPlainText()
    assert service.calls == 1

    radios = {radio.text(): radio for radio in window.findChildren(QRadioButton)}
    radios["Position 5"].click()
    _wait(app, lambda: service.calls == 2)
    assert f"Candidate: {selected_name}" in _explanation(window).toPlainText()
    window.close()


def test_manual_refresh_is_disabled_without_related_picks_or_shortlist() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = (Hero(1, "hero_one"), Hero(2, "hero_two"))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    no_related = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    no_related.show()
    button = no_related.findChild(QPushButton, "manual-pair-refresh")
    assert button is not None and not button.isEnabled()
    button.click()
    app.processEvents()
    assert service.calls == 0
    no_related.close()

    no_shortlist = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=RoleEvidenceBundles(
            RoleEvidenceBundle(Role.POSITION_4), RoleEvidenceBundle(Role.POSITION_5)
        ),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=1000,
    )
    no_shortlist.show()
    table = no_shortlist.findChild(QTableWidget)
    button = no_shortlist.findChild(QPushButton, "manual-pair-refresh")
    assert table is not None and button is not None
    table.selectRow(0)
    _button(no_shortlist, "Add Enemy").click()
    assert not button.isEnabled()
    button.click()
    app.processEvents()
    assert service.calls == 0
    no_shortlist.close()


def test_draft_action_guardrails_show_capacity_and_keep_invalid_clicks_local() -> None:
    """Disabled or invalid draft actions never advance the pair-refresh controller."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 8))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=10_000,
    )
    window.show()
    table = window.findChild(QTableWidget)
    status = _label(window, "draft-action-status")
    add_ally = window.findChild(QPushButton, "add-ally")
    remove_ally = window.findChild(QPushButton, "remove-ally")
    reset = window.findChild(QPushButton, "reset-draft")
    assert (
        table is not None and add_ally is not None and remove_ally is not None and reset is not None
    )
    assert "allies 0 / 5 | enemies 0 / 5 | bans 0" in status.text()
    assert not add_ally.isEnabled() and not remove_ally.isEnabled() and not reset.isEnabled()
    add_ally.click()
    remove_ally.click()
    reset.click()
    app.processEvents()
    assert service.calls == 0

    for _ in range(5):
        table.selectRow(0)
        assert add_ally.isEnabled()
        add_ally.click()

    controller = window.pair_refresh_controller
    assert controller is not None
    generation_after_valid_adds = controller.generation
    assert not add_ally.isEnabled()
    assert "allies 5 / 5" in status.text()
    assert "capacity is full" in status.text()
    add_ally.click()
    remove_ally.click()
    app.processEvents()
    assert service.calls == 0
    assert controller.generation == generation_after_valid_adds
    assert controller.active_thread is None and controller.findChildren(QThread) == []
    window.close()


def test_bans_over_five_remain_legal_and_do_not_create_pair_work() -> None:
    """The guardrail reports ban count without imposing an unapproved draft cap."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 8))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    ban = window.findChild(QPushButton, "ban-hero")
    status = _label(window, "draft-action-status")
    assert table is not None and ban is not None
    for _ in range(6):
        table.selectRow(0)
        assert ban.isEnabled()
        ban.click()
    controller = window.pair_refresh_controller
    assert controller is not None
    app.processEvents()
    assert "bans 6" in status.text()
    assert service.calls == 0
    assert controller.active_thread is None and controller.findChildren(QThread) == []
    window.close()


def test_only_a_successful_draft_mutation_schedules_pair_refresh() -> None:
    """A valid add schedules once; unselected actions do not create another worker."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget)
    add_ally = window.findChild(QPushButton, "add-ally")
    remove_ally = window.findChild(QPushButton, "remove-ally")
    assert table is not None and add_ally is not None and remove_ally is not None
    table.selectRow(0)
    add_ally.click()
    _wait(app, lambda: service.calls == 1)
    controller = window.pair_refresh_controller
    assert controller is not None
    _wait(app, lambda: controller.active_thread is None)
    generation_after_add = controller.generation

    table.clearSelection()
    app.processEvents()
    assert not add_ally.isEnabled() and not remove_ally.isEnabled()
    add_ally.click()
    remove_ally.click()
    app.processEvents()
    assert service.calls == 1
    assert controller.generation == generation_after_add
    assert controller.active_thread is None and controller.findChildren(QThread) == []
    window.close()


def test_full_offscreen_user_workflow_preserves_local_and_shutdown_contracts() -> None:
    """Exercise draft, local presentation, latest-wins refresh, reset, and deferred close."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 7))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = RecordingSlowPairService(delay=0.15)
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    search = window.findChild(QLineEdit, "candidate-search")
    clear_search = window.findChild(QPushButton, "candidate-search-clear")
    allies = window.findChild(QListWidget, "allied-picks")
    position = window.findChild(QComboBox, "ally-team-position")
    lane = window.findChild(QComboBox, "ally-planned-lane")
    manual_refresh = window.findChild(QPushButton, "manual-pair-refresh")
    assert (
        table is not None
        and search is not None
        and clear_search is not None
        and allies is not None
        and position is not None
        and lane is not None
        and manual_refresh is not None
        and window.pair_refresh_controller is not None
    )
    controller = window.pair_refresh_controller

    def select_candidate(name: str) -> None:
        index = next(row for row in range(table.rowCount()) if table.item(row, 0).text() == name)
        table.selectRow(index)

    table.horizontalHeader().sectionClicked.emit(0)
    select_candidate("Hero 1")
    search.setText("Hero 1")
    app.processEvents()
    assert table.rowCount() == 1 and "Candidate: Hero 1" in _explanation(window).toPlainText()
    clear_search.click()
    app.processEvents()
    assert table.rowCount() == 6 and not clear_search.isEnabled()
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None

    select_candidate("Hero 1")
    _button(window, "Add Ally").click()
    _wait(app, lambda: len(service.inputs) == 1 and controller.active_thread is not None)
    generation_after_ally = controller.generation
    _button(window, "Add Ally").click()
    app.processEvents()
    assert controller.generation == generation_after_ally and len(service.inputs) == 1

    allies.setCurrentRow(0)
    position.setCurrentIndex(position.findData(TeamPosition.POSITION_1))
    lane.setCurrentIndex(lane.findData(PlannedLane.SAFE))
    _button(window, "Save Ally Context").click()
    assert (
        "Hero 1: P1, Safe (manual)"
        in window.findChild(QTextEdit, "composition-context").toPlainText()
    )
    assert len(service.inputs) == 1 and controller.active_thread is not None

    select_candidate("Hero 2")
    _button(window, "Add Enemy").click()
    select_candidate("Hero 3")
    _button(window, "Ban").click()
    radios = {radio.text(): radio for radio in window.findChildren(QRadioButton)}
    radios["Position 5"].click()
    manual_refresh.click()
    assert controller.generation == 5
    _wait(
        app,
        lambda: (
            len(service.inputs) == 2
            and controller.active_thread is None
            and controller.retired_worker_count == 0
        ),
    )
    assert [input_data.generation for input_data in service.inputs] == [1, 5]
    latest = service.inputs[-1]
    assert latest.context.role is Role.POSITION_5
    assert latest.context.ally_ids == (1,) and latest.context.enemy_ids == (2,)
    assert {hero.hero_id for hero in latest.draft.banned_heroes} == {3}

    _button(window, "Reset Draft").click()
    app.processEvents()
    assert controller.generation == 6 and len(service.inputs) == 2
    assert (
        "No allied picks have been added."
        in window.findChild(QTextEdit, "composition-context").toPlainText()
    )
    assert "allies 0 | enemies 0" in _label(window, "pair-refresh-context").text()

    select_candidate("Hero 4")
    _button(window, "Add Enemy").click()
    _wait(app, lambda: len(service.inputs) == 3 and controller.active_thread is not None)
    manual_refresh.click()
    assert controller.generation == 8 and controller.active_thread is not None
    window.close()
    assert window.isVisible()
    _wait(
        app,
        lambda: (
            not window.isVisible()
            and controller.active_thread is None
            and controller.retired_worker_count == 0
        ),
        seconds=3.0,
    )
    app.processEvents()
    assert [input_data.generation for input_data in service.inputs] == [1, 5, 7]
    assert controller.generation == 9 and controller.findChildren(QThread) == []


def test_candidate_comparison_is_bounded_local_and_tracks_role_rerender() -> None:
    """Comparison consumes rendered rows without dispatching pair work."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 5))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=10_000,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    add = window.findChild(QPushButton, "add-candidate-comparison")
    remove = window.findChild(QPushButton, "remove-candidate-comparison")
    clear = window.findChild(QPushButton, "clear-candidate-comparison")
    status = _label(window, "candidate-comparison-status")
    first = window.findChild(QTextEdit, "candidate-comparison-slot-1")
    assert (
        table is not None
        and add is not None
        and remove is not None
        and clear is not None
        and first is not None
    )

    for index in range(3):
        table.selectRow(index)
        add.click()
    table.selectRow(0)
    add.click()
    app.processEvents()
    assert "3 / 3 legal candidates" in status.text()
    assert "Hero 1" in first.toPlainText()
    assert "Experimental score" in first.toPlainText()
    assert "not a win prediction" in first.toPlainText()
    assert service.calls == 0
    assert window.pair_refresh_controller is not None
    assert window.pair_refresh_controller.generation == 0

    table.selectRow(1)
    remove.click()
    assert "2 / 3 legal candidates" in status.text()
    add.click()
    assert "3 / 3 legal candidates" in status.text()

    radios = {radio.text(): radio for radio in window.findChildren(QRadioButton)}
    radios["Position 5"].click()
    app.processEvents()
    assert "Role: Position 5" in first.toPlainText()
    assert service.calls == 0 and window.pair_refresh_controller.generation == 1
    clear.click()
    assert "Empty comparison slot" in first.toPlainText()
    assert "select up to 3 legal candidates" in status.text()
    window.close()


def test_candidate_comparison_removes_hero_that_becomes_illegal_without_extra_work() -> None:
    """A draft mutation purges an illegal compared hero; comparison adds no dispatch."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=10_000,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    add = window.findChild(QPushButton, "add-candidate-comparison")
    first = window.findChild(QTextEdit, "candidate-comparison-slot-1")
    controller = window.pair_refresh_controller
    assert table is not None and add is not None and first is not None and controller is not None
    table.selectRow(0)
    add.click()
    assert "Hero 1" in first.toPlainText()
    generation_before_draft = controller.generation
    _button(window, "Add Enemy").click()
    app.processEvents()
    assert "Empty comparison slot" in first.toPlainText()
    assert controller.generation == generation_before_draft + 1
    assert service.calls == 0 and controller.active_thread is None
    window.close()


def test_candidate_comparison_rerenders_current_pair_overlay_locally() -> None:
    """A completed current-context pair result updates the card without a comparison dispatch."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CounterPairService()
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_role_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    add = window.findChild(QPushButton, "add-candidate-comparison")
    first = window.findChild(QTextEdit, "candidate-comparison-slot-1")
    assert table is not None and add is not None and first is not None

    table.selectRow(0)
    add.click()
    assert "Counter: unavailable" in first.toPlainText()
    table.selectRow(1)
    _button(window, "Add Enemy").click()
    _wait(app, lambda: service.calls == 1 and "Counter: unavailable" not in first.toPlainText())
    assert "Hero 1" in first.toPlainText()
    assert "Counter:" in first.toPlainText()
    window.close()
