import time
from datetime import UTC, date, datetime

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
)

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
