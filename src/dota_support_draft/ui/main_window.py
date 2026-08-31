"""Manual draft desktop UI; pair transport is delegated to the refresh controller."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dota_support_draft.config import PlayerAccountPreferenceStore
from dota_support_draft.domain import (
    CounterEvidence,
    EvidenceSet,
    Hero,
    PersonalHeroStat,
    PlannedLane,
    Role,
    RoleEvidenceBundle,
    RoleEvidenceBundles,
    SynergyEvidence,
    TeamPosition,
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
    player_preferences: PlayerAccountPreferenceStore | None = None,
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
    status.setObjectName("application-status")
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
    allies.setObjectName("allied-picks")
    enemies.setObjectName("enemy-picks")
    bans.setObjectName("banned-heroes")
    for label, widget in (("Allied Picks", allies), ("Enemy Picks", enemies), ("Bans", bans)):
        column = QVBoxLayout()
        column.addWidget(QLabel(label))
        column.addWidget(widget)
        lists.addLayout(column)
    layout.addLayout(lists)
    composition_panel = QTextEdit()
    composition_panel.setObjectName("composition-context")
    composition_panel.setReadOnly(True)
    composition_panel.setPlainText(
        "Manual draft context — not statistical lane-fit; not auto-detected.\n"
        "No allied picks have been added."
    )
    composition_controls = QHBoxLayout()
    team_position_input = QComboBox()
    team_position_input.setObjectName("ally-team-position")
    for label, position_value in (
        ("Unknown position", TeamPosition.UNKNOWN),
        ("Position 1", TeamPosition.POSITION_1),
        ("Position 2", TeamPosition.POSITION_2),
        ("Position 3", TeamPosition.POSITION_3),
        ("Position 4", TeamPosition.POSITION_4),
        ("Position 5", TeamPosition.POSITION_5),
    ):
        team_position_input.addItem(label, position_value)
    planned_lane_input = QComboBox()
    planned_lane_input.setObjectName("ally-planned-lane")
    for label, lane_value in (
        ("Unknown lane", PlannedLane.UNKNOWN),
        ("Safe lane", PlannedLane.SAFE),
        ("Off lane", PlannedLane.OFF),
        ("Mid lane", PlannedLane.MID),
        ("Roam", PlannedLane.ROAM),
    ):
        planned_lane_input.addItem(label, lane_value)
    save_composition = QPushButton("Save Ally Context")
    save_composition.setObjectName("save-ally-composition")
    composition_controls.addWidget(team_position_input)
    composition_controls.addWidget(planned_lane_input)
    composition_controls.addWidget(save_composition)
    layout.addWidget(composition_panel)
    layout.addLayout(composition_controls)
    search = QLineEdit()
    search.setPlaceholderText("Hero search")
    layout.addWidget(search)
    player_config_status = QLabel(
        "Configure a public numeric Steam32/OpenDota account ID. Changes load after restart."
    )
    player_config_status.setObjectName("player-config-status")
    player_config = QHBoxLayout()
    player_account_input = QLineEdit()
    player_account_input.setObjectName("player-account-input")
    player_account_input.setPlaceholderText("Public Steam32/OpenDota account ID")
    configure_player = QPushButton("Configure Player")
    configure_player.setObjectName("configure-player")
    clear_player = QPushButton("Clear Player")
    clear_player.setObjectName("clear-player")
    player_config.addWidget(player_account_input)
    player_config.addWidget(configure_player)
    player_config.addWidget(clear_player)
    layout.addWidget(player_config_status)
    layout.addLayout(player_config)
    draft_action_status = QLabel("Draft actions: allies 0 / 5 | enemies 0 / 5 | bans 0")
    draft_action_status.setObjectName("draft-action-status")
    layout.addWidget(draft_action_status)
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
    for button, object_name in (
        (add_ally, "add-ally"),
        (add_enemy, "add-enemy"),
        (ban, "ban-hero"),
        (remove_ally, "remove-ally"),
        (remove_enemy, "remove-enemy"),
        (unban, "unban-hero"),
        (reset, "reset-draft"),
    ):
        button.setObjectName(object_name)
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
    explanation_panel = QTextEdit()
    explanation_panel.setObjectName("recommendation-explanation")
    explanation_panel.setReadOnly(True)
    explanation_panel.setPlaceholderText("Select a candidate hero to inspect its evidence.")
    explanation_panel.setPlainText("Select a candidate hero to inspect its evidence.")
    layout.addWidget(explanation_panel)
    if session is not None:
        rendered_rows: list[CandidateRow] = []
        scorer = ExperimentalEvidenceScoringEngine()
        hero_by_id = {hero.hero_id: hero for hero in session.heroes}
        overlay_context: PairEvidenceContext | None = None
        overlay_counters: tuple[CounterEvidence, ...] = ()
        overlay_synergies: tuple[SynergyEvidence, ...] = ()
        latest_pair_result: PairEvidenceResult | None = None
        pair_state = PairRefreshState.IDLE

        def update_composition_context() -> None:
            assignments = session.to_draft_state().allied_picks
            lines = [
                "Manual draft context — not statistical lane-fit; not auto-detected.",
                "Source: manual input only.",
            ]
            if not assignments:
                lines.append("No allied picks have been added.")
            else:
                positions: dict[TeamPosition, list[str]] = {}
                for pick in assignments:
                    name = pick.hero.localized_name or pick.hero.canonical_name
                    position = pick.team_position.name.replace("POSITION_", "P")
                    lane = pick.planned_lane.value.title()
                    lines.append(f"{name}: {position}, {lane} (manual)")
                    if pick.team_position is not TeamPosition.UNKNOWN:
                        positions.setdefault(pick.team_position, []).append(name)
                conflicts = [
                    f"Conflict: {position.name.replace('POSITION_', 'P')} assigned to "
                    f"{', '.join(names)}."
                    for position, names in positions.items()
                    if len(names) > 1
                ]
                lines.extend(conflicts or ["No position conflicts among manually assigned allies."])
            composition_panel.setPlainText("\n".join(lines))

        def selected_allied_hero() -> Hero | None:
            return selected_list_hero(allies)

        def sync_composition_controls() -> None:
            hero = selected_allied_hero()
            save_composition.setEnabled(hero is not None)
            if hero is None:
                return
            position, planned_lane = session.ally_assignments.get(
                hero, (TeamPosition.UNKNOWN, PlannedLane.UNKNOWN)
            )
            team_position_input.setCurrentIndex(team_position_input.findData(position))
            planned_lane_input.setCurrentIndex(planned_lane_input.findData(planned_lane))

        def save_ally_composition() -> None:
            hero = selected_allied_hero()
            if hero is None:
                composition_panel.setPlainText(
                    "Manual draft context — select a current allied pick before saving.\n"
                    "Not statistical lane-fit; not auto-detected."
                )
                return
            position = TeamPosition(str(team_position_input.currentData()))
            planned_lane = PlannedLane(str(planned_lane_input.currentData()))
            session.set_ally_assignment(hero, position, planned_lane)
            update_composition_context()
            sync_composition_controls()

        def selected_candidate_row() -> CandidateRow | None:
            row = candidates.currentRow()
            return rendered_rows[row] if 0 <= row < len(rendered_rows) else None

        def update_recommendation_explanation() -> None:
            row = selected_candidate_row()
            if row is None:
                explanation_panel.setPlainText("Select a candidate hero to inspect its evidence.")
                return
            components = dict(row.experimental_components)

            def component_text(name: str) -> str:
                value = components.get(name)
                if value is None:
                    return "unavailable — fixed weight contributes neutral zero"
                return format_optional_rate(value)

            score = (
                "unavailable — no applicable public recommendation evidence"
                if row.experimental_score is None
                else (
                    f"{row.experimental_score:.1f} "
                    "(experimental ordering score; not a win prediction)"
                )
            )
            confidence = (
                "unavailable"
                if row.evidence_confidence is None
                else f"{row.evidence_confidence:.0%}"
            )
            role_text = "Position 4" if session.role is Role.POSITION_4 else "Position 5"
            explanation_panel.setPlainText(
                "\n".join(
                    (
                        f"Candidate: {row.display_name}",
                        f"Experimental score: {score}",
                        f"Confidence: {confidence}",
                        "Evidence:",
                        f"  Meta: {component_text('meta')}",
                        f"  Counter: {component_text('counter')}",
                        f"  Synergy: {component_text('synergy')}",
                        f"  Personal: {component_text('personal')}",
                        "Why:",
                        row.explanation or row.status,
                        "Context:",
                        f"  Role: {role_text}",
                        f"  {pair_coverage_label.text()}",
                        "  Meta, Counter, and Synergy use current-week role evidence; "
                        "it is not patch-isolated.",
                        "  Personal history is all-time and role-unknown.",
                    )
                )
            )

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
            previously_selected = selected_candidate_row()
            previous_hero_id = previously_selected.hero.hero_id if previously_selected else None
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
            update_composition_context()
            sync_composition_controls()
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
            selected_index = next(
                (index for index, row in enumerate(rows) if row.hero.hero_id == previous_hero_id),
                None,
            )
            if selected_index is None:
                candidates.clearSelection()
            else:
                candidates.setCurrentCell(selected_index, 0)
            update_recommendation_explanation()
            update_draft_action_controls()

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
            update_recommendation_explanation()

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

        def set_player_config_status(message: str) -> None:
            status.setText(f"Patch: {session.patch.version} | {message} | Core Draft: Ready")
            player_config_status.setText(message)

        def save_player_account() -> None:
            if player_preferences is None:
                return
            try:
                account_id = player_preferences.save_account_id(player_account_input.text())
            except ValueError as error:
                player_config_status.setText(str(error))
                return
            player_account_input.setText(account_id)
            set_player_config_status(
                "Player account saved; restart required to load Personal history."
            )

        def clear_player_account() -> None:
            if player_preferences is None:
                return
            player_preferences.clear_account_id()
            player_account_input.clear()
            set_player_config_status(
                "Player account cleared; restart required. "
                "An environment override still takes priority."
            )

        def chosen() -> Hero | None:
            if not candidates.selectedItems():
                return None
            row = selected_candidate_row()
            return row.hero if row is not None else None

        def selected_list_hero(widget: QListWidget) -> Hero | None:
            item = widget.currentItem()
            return hero_by_id.get(item.data(Qt.UserRole)) if item is not None else None

        draft_action_hint = "Select a candidate hero to add an ally, enemy, or ban."

        def update_draft_action_controls(message: str | None = None) -> None:
            nonlocal draft_action_hint
            if message is not None:
                draft_action_hint = message
            hero = chosen()
            ally_full = len(session.allies) >= 5
            enemy_full = len(session.enemies) >= 5
            add_ally.setEnabled(hero is not None and not ally_full)
            add_enemy.setEnabled(hero is not None and not enemy_full)
            ban.setEnabled(hero is not None)
            remove_ally.setEnabled(allies.currentItem() is not None)
            remove_enemy.setEnabled(enemies.currentItem() is not None)
            unban.setEnabled(bans.currentItem() is not None)
            reset.setEnabled(bool(session.allies or session.enemies or session.bans))
            if ally_full:
                hint = "Allied pick capacity is full. Remove an allied pick to continue."
            elif enemy_full:
                hint = "Enemy pick capacity is full. Remove an enemy pick to continue."
            elif hero is None:
                hint = "Select a candidate hero to add an ally, enemy, or ban."
            else:
                hint = draft_action_hint
            draft_action_status.setText(
                "Draft actions: "
                f"allies {len(session.allies)} / 5 | enemies {len(session.enemies)} / 5 "
                f"| bans {len(session.bans)} — {hint}"
            )

        def apply(action: Callable[[Hero], None], action_name: str) -> None:
            hero = chosen()
            if hero is None:
                update_draft_action_controls("Select a candidate hero first.")
                return
            try:
                action(hero)
            except ValueError as error:
                update_draft_action_controls(str(error))
                return
            refresh()
            update_draft_action_controls(
                f"{action_name}: {hero.localized_name or hero.canonical_name}."
            )
            trigger_pair_refresh()

        def remove_from(
            widget: QListWidget, action: Callable[[Hero], None], action_name: str
        ) -> None:
            hero = selected_list_hero(widget)
            if hero is None:
                update_draft_action_controls("Select a hero from the relevant list first.")
                return
            try:
                action(hero)
            except ValueError as error:
                update_draft_action_controls(str(error))
                return
            refresh()
            update_draft_action_controls(
                f"{action_name}: {hero.localized_name or hero.canonical_name}."
            )
            trigger_pair_refresh()

        add_ally.clicked.connect(lambda: apply(session.add_ally, "Added allied pick"))
        add_enemy.clicked.connect(lambda: apply(session.add_enemy, "Added enemy pick"))
        ban.clicked.connect(lambda: apply(session.ban, "Banned hero"))
        remove_ally.clicked.connect(
            lambda: remove_from(allies, session.remove_ally, "Removed allied pick")
        )
        remove_enemy.clicked.connect(
            lambda: remove_from(enemies, session.remove_enemy, "Removed enemy pick")
        )
        unban.clicked.connect(lambda: remove_from(bans, session.unban, "Unbanned hero"))

        def reset_draft() -> None:
            if not (session.allies or session.enemies or session.bans):
                update_draft_action_controls("Draft is already empty.")
                return
            session.clear()
            refresh()
            update_draft_action_controls("Draft reset.")
            trigger_pair_refresh()

        def choose_role(role: Role, checked: bool) -> None:
            if not checked or session.role is role:
                return
            session.set_role(role)
            refresh()
            update_draft_action_controls("Role changed; draft context updated.")
            trigger_pair_refresh()

        reset.clicked.connect(reset_draft)
        manual_refresh.clicked.connect(trigger_manual_pair_refresh)
        save_composition.clicked.connect(save_ally_composition)
        configure_player.clicked.connect(save_player_account)
        clear_player.clicked.connect(clear_player_account)
        four.toggled.connect(lambda checked: choose_role(Role.POSITION_4, checked))
        five.toggled.connect(lambda checked: choose_role(Role.POSITION_5, checked))
        search.textChanged.connect(lambda _: refresh())
        candidates.itemSelectionChanged.connect(update_recommendation_explanation)
        allies.itemSelectionChanged.connect(sync_composition_controls)
        candidates.itemSelectionChanged.connect(update_draft_action_controls)
        allies.itemSelectionChanged.connect(update_draft_action_controls)
        enemies.itemSelectionChanged.connect(update_draft_action_controls)
        bans.itemSelectionChanged.connect(update_draft_action_controls)
        if player_preferences is None:
            player_account_input.setEnabled(False)
            configure_player.setEnabled(False)
            clear_player.setEnabled(False)
            player_config_status.setText(
                "Local player configuration is unavailable in this window."
            )
        else:
            saved_account_id = player_preferences.load_account_id()
            if saved_account_id is not None:
                player_account_input.setText(saved_account_id)
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
            team_position_input,
            planned_lane_input,
            save_composition,
            player_account_input,
            configure_player,
            clear_player,
            search,
            candidates,
        ):
            widget.setEnabled(False)
    window.setCentralWidget(contents)
    window.resize(900, 650)
    return window
