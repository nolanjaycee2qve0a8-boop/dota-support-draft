"""Manual draft desktop UI; pair transport is delegated to the refresh controller."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dota_support_draft.domain import (
    CounterEvidence,
    EvidenceSet,
    Hero,
    PersonalHeroStat,
    Role,
    RoleEvidenceBundle,
    RoleEvidenceBundles,
    SynergyEvidence,
)
from dota_support_draft.draft import (
    CandidateRow,
    DraftPairEvidenceService,
    ManualDraftSession,
    PairEvidenceContext,
    PairEvidenceInput,
    PairEvidenceResult,
    build_candidate_rows,
    filter_candidates,
    format_optional_rate,
    format_player_status,
    make_pair_input,
)
from dota_support_draft.scoring import ExperimentalEvidenceScoringEngine
from dota_support_draft.ui.pair_refresh import PairEvidenceRefreshController, PairRefreshState


class DraftMainWindow(QMainWindow):  # type: ignore[misc]  # PySide6 base is incompletely typed.
    """A QMainWindow with cooperative pair-worker shutdown on close."""

    def __init__(self) -> None:
        super().__init__()
        self.pair_refresh_controller: PairEvidenceRefreshController | None = None
        self._deferred_close_ready = False

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._deferred_close_ready:
            event.accept()
            return
        controller = self.pair_refresh_controller
        if controller is not None and controller.begin_shutdown(self._complete_deferred_close):
            event.ignore()
            return
        event.accept()

    def _complete_deferred_close(self) -> None:
        self._deferred_close_ready = True
        self.close()


def create_main_window(
    session: ManualDraftSession | None = None,
    personal_stats: tuple[PersonalHeroStat, ...] = (),
    initial_status: str = "Loading data...",
    player: object | None = None,
    personal_error: str | None = None,
    evidence_by_role: RoleEvidenceBundles | None = None,
    stratz_freshness_warning: str | None = None,
    pair_service: DraftPairEvidenceService | None = None,
    pair_debounce_ms: int = PairEvidenceRefreshController.DEBOUNCE_MS,
) -> DraftMainWindow:
    """Build the GUI; all draft mutations are local before pair refresh is scheduled."""
    evidence_by_role = evidence_by_role or RoleEvidenceBundles(
        RoleEvidenceBundle(Role.POSITION_4, EvidenceSet(), "Recommendation evidence unavailable"),
        RoleEvidenceBundle(Role.POSITION_5, EvidenceSet(), "Recommendation evidence unavailable"),
    )
    window = DraftMainWindow()
    window.setWindowTitle("Dota Support Draft Assistant")
    contents = QWidget()
    layout = QVBoxLayout(contents)
    layout.addWidget(QLabel("Dota Support Draft Assistant"))
    player_label, warning = format_player_status(player, personal_error)
    status = QLabel(
        initial_status
        if session is None
        else f"Patch: {session.patch.version} | {player_label} | Core Draft: Ready"
    )
    layout.addWidget(status)
    if warning:
        layout.addWidget(QLabel(f"Personal data unavailable: {warning}"))
    evidence_label, pair_label = QLabel(), QLabel("Pair evidence: idle")
    pair_label.setObjectName("pair-refresh-status")
    pair_context_label = QLabel("Pair refresh: idle — no related picks")
    pair_context_label.setObjectName("pair-refresh-context")
    pair_coverage_label = QLabel("Pair coverage: Meta/Personal only; no pair enrichment")
    pair_coverage_label.setObjectName("pair-refresh-coverage")
    layout.addWidget(evidence_label)
    layout.addWidget(pair_label)
    layout.addWidget(pair_context_label)
    layout.addWidget(pair_coverage_label)
    if stratz_freshness_warning:
        layout.addWidget(QLabel(stratz_freshness_warning))
    role_row = QHBoxLayout()
    four, five = QRadioButton("Position 4"), QRadioButton("Position 5")
    four.setChecked(session is None or session.role is Role.POSITION_4)
    five.setChecked(session is not None and session.role is Role.POSITION_5)
    role_row.addWidget(four)
    role_row.addWidget(five)
    layout.addLayout(role_row)
    lists = QHBoxLayout()
    allies, enemies, bans = QListWidget(), QListWidget(), QListWidget()
    for label, widget in (("Allied Picks", allies), ("Enemy Picks", enemies), ("Bans", bans)):
        column = QVBoxLayout()
        column.addWidget(QLabel(label))
        column.addWidget(widget)
        lists.addLayout(column)
    layout.addLayout(lists)
    search = QLineEdit()
    search.setPlaceholderText("Hero search")
    layout.addWidget(search)
    controls = QHBoxLayout()
    add_ally, add_enemy, ban = QPushButton("Add Ally"), QPushButton("Add Enemy"), QPushButton("Ban")
    remove_ally, remove_enemy, unban, reset = (
        QPushButton("Remove Ally"),
        QPushButton("Remove Enemy"),
        QPushButton("Unban"),
        QPushButton("Reset Draft"),
    )
    manual_refresh = QPushButton("Refresh pair evidence")
    manual_refresh.setObjectName("manual-pair-refresh")
    for button in (
        add_ally,
        add_enemy,
        ban,
        remove_ally,
        remove_enemy,
        unban,
        reset,
        manual_refresh,
    ):
        controls.addWidget(button)
    layout.addLayout(controls)
    layout.addWidget(QLabel("Personal history is ALL-TIME; ROLE UNKNOWN."))
    candidates = QTableWidget(0, 8)
    candidates.setHorizontalHeaderLabels(
        [
            "Hero",
            "Experimental Score",
            "Confidence",
            "Meta",
            "Counter",
            "Synergy",
            "Personal",
            "Why",
        ]
    )
    layout.addWidget(candidates)
    if session is not None:
        rendered_rows: list[CandidateRow] = []
        scorer = ExperimentalEvidenceScoringEngine()
        hero_by_id = {hero.hero_id: hero for hero in session.heroes}
        overlay_context: PairEvidenceContext | None = None
        overlay_counters: tuple[CounterEvidence, ...] = ()
        overlay_synergies: tuple[SynergyEvidence, ...] = ()
        latest_pair_result: PairEvidenceResult | None = None
        pair_state = PairRefreshState.IDLE

        def pair_input(generation: int = 0) -> PairEvidenceInput:
            return make_pair_input(
                generation,
                session.to_draft_state(),
                session.candidates,
                evidence_by_role.for_role(session.role).evidence,
                pair_service.rank_bracket if pair_service is not None else None,
                personal_stats,
            )

        def current_context() -> PairEvidenceContext | None:
            return pair_input().context

        def effective_evidence() -> EvidenceSet:
            base = evidence_by_role.for_role(session.role).evidence
            context = current_context()
            if overlay_context == context:
                return EvidenceSet(base.role_meta, overlay_counters, overlay_synergies)
            return EvidenceSet(role_meta=base.role_meta)

        def describe_pair_observability() -> None:
            input_data = pair_input()
            context = input_data.context
            shortlist = ", ".join(
                hero.localized_name or hero.canonical_name for hero in input_data.shortlist
            )
            shortlist_text = shortlist or "none"
            role_text = "Position 4" if context.role is Role.POSITION_4 else "Position 5"
            related = len(context.ally_ids) + len(context.enemy_ids)
            pair_context_label.setText(
                "Pair refresh: "
                f"{role_text} | allies {len(context.ally_ids)} | enemies {len(context.enemy_ids)} "
                f"| shortlist ({len(input_data.shortlist)}): {shortlist_text}"
            )
            if not related:
                pair_coverage_label.setText(
                    "Pair coverage: no related picks; Meta/Personal only; no pair enrichment"
                )
                return
            current_result = (
                latest_pair_result
                if latest_pair_result and (latest_pair_result.context == context)
                else None
            )

            def component(name: str, requested: bool, error: str | None) -> str:
                if not requested:
                    return f"{name}: not requested"
                if error:
                    return f"{name}: unavailable ({error})"
                if current_result is not None:
                    return f"{name}: available"
                if pair_state in (PairRefreshState.DEBOUNCING, PairRefreshState.LOADING):
                    return f"{name}: pending"
                if pair_state is PairRefreshState.ERROR:
                    return f"{name}: unavailable (refresh error)"
                return f"{name}: awaiting refresh"

            pair_coverage_label.setText(
                "Pair coverage: "
                + "; ".join(
                    (
                        component(
                            "Counter",
                            bool(context.enemy_ids),
                            current_result.counter_error if current_result else None,
                        ),
                        component(
                            "Synergy",
                            bool(context.ally_ids),
                            current_result.synergy_error if current_result else None,
                        ),
                    )
                )
                + ". Meta/Personal remain available without pair enrichment."
            )

        def update_manual_refresh_control() -> None:
            controller = window.pair_refresh_controller
            input_data = pair_input()
            if controller is None or pair_service is None:
                manual_refresh.setEnabled(False)
                manual_refresh.setToolTip("Pair evidence is unavailable")
            elif controller.shutting_down:
                manual_refresh.setEnabled(False)
                manual_refresh.setToolTip("Pair refresh is unavailable while closing")
            elif not input_data.shortlist:
                manual_refresh.setEnabled(False)
                manual_refresh.setToolTip("No legal pair shortlist for this draft")
            elif not (input_data.context.ally_ids or input_data.context.enemy_ids):
                manual_refresh.setEnabled(False)
                manual_refresh.setToolTip("Add an ally or enemy pick to refresh pair evidence")
            else:
                manual_refresh.setEnabled(True)
                manual_refresh.setToolTip(
                    "Recalculate current pair evidence using existing provider caches "
                    "when available"
                )

        def refresh() -> None:
            allies.clear()
            enemies.clear()
            bans.clear()
            for group, widget in (
                (session.allies, allies),
                (session.enemies, enemies),
                (session.bans, bans),
            ):
                for hero in group:
                    item = QListWidgetItem(hero.localized_name or hero.canonical_name)
                    item.setData(Qt.UserRole, hero.hero_id)
                    widget.addItem(item)
            bundle = evidence_by_role.for_role(session.role)
            evidence_label.setText(
                bundle.error
                or (
                    "Experimental recommendation — STRATZ current-week position evidence; "
                    "not a calibrated win probability; not patch-isolated."
                )
            )
            describe_pair_observability()
            update_manual_refresh_control()
            recommendations = scorer.rank(
                session.to_draft_state(), session.candidates, effective_evidence(), personal_stats
            )
            rows = filter_candidates(
                build_candidate_rows(session.candidates, personal_stats, recommendations),
                search.text(),
            )
            rendered_rows[:] = rows
            candidates.setRowCount(len(rows))
            for index, row in enumerate(rows):
                components = dict(row.experimental_components)
                values = (
                    row.display_name,
                    "—" if row.experimental_score is None else f"{row.experimental_score:.1f}",
                    "—" if row.evidence_confidence is None else f"{row.evidence_confidence:.0%}",
                    format_optional_rate(components.get("meta")),
                    format_optional_rate(components.get("counter")),
                    format_optional_rate(components.get("synergy")),
                    format_optional_rate(components.get("personal")),
                    row.explanation or row.status,
                )
                for column, value in enumerate(values):
                    candidates.setItem(index, column, QTableWidgetItem(str(value)))

        def set_pair_state(state: PairRefreshState, message: str | None) -> None:
            nonlocal pair_state
            pair_state = state
            labels = {
                PairRefreshState.IDLE: "Pair evidence: idle",
                PairRefreshState.DEBOUNCING: (
                    "Pair evidence: updating top 8 preliminary candidates…"
                ),
                PairRefreshState.LOADING: "Pair evidence: updating top 8 preliminary candidates…",
                PairRefreshState.READY: "Pair evidence ready: Counter + Synergy",
                PairRefreshState.PARTIAL: "Pair evidence partial: one component unavailable",
                PairRefreshState.ERROR: (
                    "Pair evidence unavailable; current-week Meta remains active"
                ),
                PairRefreshState.SHUTTING_DOWN: "Finishing pair refresh before closing…",
            }
            pair_label.setText(message or labels[state])
            describe_pair_observability()
            update_manual_refresh_control()

        def apply_pair_result(result: PairEvidenceResult) -> None:
            nonlocal latest_pair_result, overlay_context, overlay_counters, overlay_synergies
            latest_pair_result = result
            overlay_context = result.context
            overlay_counters, overlay_synergies = result.counters, result.synergies
            refresh()

        if pair_service is not None:
            window.pair_refresh_controller = PairEvidenceRefreshController(
                pair_service,
                current_context,
                apply_pair_result,
                set_pair_state,
                pair_debounce_ms,
                window,
            )
            pair_label.setText("Pair evidence: top 8 preliminary candidates")
            update_manual_refresh_control()

        def trigger_pair_refresh() -> None:
            if window.pair_refresh_controller is not None:
                window.pair_refresh_controller.schedule(pair_input())

        def trigger_manual_pair_refresh() -> None:
            if window.pair_refresh_controller is not None:
                window.pair_refresh_controller.refresh_now(pair_input())

        def chosen() -> Hero | None:
            row = candidates.currentRow()
            return rendered_rows[row].hero if 0 <= row < len(rendered_rows) else None

        def selected_list_hero(widget: QListWidget) -> Hero | None:
            item = widget.currentItem()
            return hero_by_id.get(item.data(Qt.UserRole)) if item is not None else None

        def apply(action: Callable[[Hero], None]) -> None:
            hero = chosen()
            if hero is None:
                status.setText("Select a candidate hero first.")
            else:
                try:
                    action(hero)
                except ValueError as error:
                    status.setText(str(error))
            refresh()
            trigger_pair_refresh()

        def remove_from(widget: QListWidget, action: Callable[[Hero], None]) -> None:
            hero = selected_list_hero(widget)
            if hero is None:
                status.setText("Select a hero from the list first.")
            else:
                action(hero)
            refresh()
            trigger_pair_refresh()

        add_ally.clicked.connect(lambda: apply(session.add_ally))
        add_enemy.clicked.connect(lambda: apply(session.add_enemy))
        ban.clicked.connect(lambda: apply(session.ban))
        remove_ally.clicked.connect(lambda: remove_from(allies, session.remove_ally))
        remove_enemy.clicked.connect(lambda: remove_from(enemies, session.remove_enemy))
        unban.clicked.connect(lambda: remove_from(bans, session.unban))

        def reset_draft() -> None:
            session.clear()
            refresh()
            trigger_pair_refresh()

        def choose_role(role: Role, checked: bool) -> None:
            if checked:
                session.set_role(role)
                refresh()
                trigger_pair_refresh()

        reset.clicked.connect(reset_draft)
        manual_refresh.clicked.connect(trigger_manual_pair_refresh)
        four.toggled.connect(lambda checked: choose_role(Role.POSITION_4, checked))
        five.toggled.connect(lambda checked: choose_role(Role.POSITION_5, checked))
        search.textChanged.connect(lambda _: refresh())
        refresh()
    else:
        for widget in (
            four,
            five,
            add_ally,
            add_enemy,
            ban,
            remove_ally,
            remove_enemy,
            unban,
            reset,
            manual_refresh,
            search,
            candidates,
        ):
            widget.setEnabled(False)
    window.setCentralWidget(contents)
    window.resize(900, 650)
    return window
