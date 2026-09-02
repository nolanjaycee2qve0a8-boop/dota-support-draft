"""Manual draft desktop UI; pair transport is delegated to the refresh controller."""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
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
    QSplitter,
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
    CandidateSortColumn,
    DraftPairEvidenceService,
    ManualDraftSession,
    ManualImportAssessment,
    PairEvidenceContext,
    PairEvidenceInput,
    PairEvidenceResult,
    assess_pasted_manual_import,
    build_candidate_rows,
    filter_candidates,
    format_optional_rate,
    format_player_status,
    make_pair_input,
    sort_candidate_rows,
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
    layout.setSpacing(6)
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
    pair_action_label = QLabel("Pair action: Meta/Personal remain available without pair evidence.")
    pair_action_label.setObjectName("pair-refresh-action")
    pair_action_label.setWordWrap(True)
    layout.addWidget(evidence_label)
    layout.addWidget(pair_label)
    layout.addWidget(pair_context_label)
    layout.addWidget(pair_coverage_label)
    layout.addWidget(pair_action_label)
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
        widget.setMaximumHeight(110)
        column = QVBoxLayout()
        column.addWidget(QLabel(label))
        column.addWidget(widget)
        lists.addLayout(column)
    layout.addLayout(lists)
    manual_import_section = QWidget()
    manual_import_section.setObjectName("manual-import-section")
    manual_import_layout = QVBoxLayout(manual_import_section)
    manual_import_layout.setContentsMargins(0, 0, 0, 0)
    manual_import_layout.addWidget(
        QLabel("Manual draft import — pasted JSON only; never auto-detected.")
    )
    manual_import_text = QTextEdit()
    manual_import_text.setObjectName("manual-import-text")
    manual_import_text.setAcceptRichText(False)
    manual_import_text.setPlaceholderText(
        "Paste a MANUAL_IMPORT/v1 JSON document, then choose Validate / Preview."
    )
    manual_import_text.setMinimumHeight(88)
    manual_import_text.setMaximumHeight(150)
    manual_import_preview = QLabel(
        "Paste a complete MANUAL_IMPORT/v1 document to preview it. The current draft is unchanged."
    )
    manual_import_preview.setObjectName("manual-import-preview")
    manual_import_preview.setWordWrap(True)
    validate_import = QPushButton("Validate / Preview import")
    validate_import.setObjectName("validate-manual-import")
    cancel_import = QPushButton("Cancel import preview")
    cancel_import.setObjectName("cancel-manual-import")
    cancel_import.setEnabled(False)
    confirm_import = QPushButton("Confirm and replace draft")
    confirm_import.setObjectName("confirm-manual-import")
    confirm_import.setEnabled(False)
    manual_import_controls = QHBoxLayout()
    manual_import_controls.addWidget(validate_import)
    manual_import_controls.addWidget(cancel_import)
    manual_import_controls.addWidget(confirm_import)
    manual_import_layout.addWidget(manual_import_text)
    manual_import_layout.addWidget(manual_import_preview)
    manual_import_layout.addLayout(manual_import_controls)
    layout.addWidget(manual_import_section)
    composition_panel = QTextEdit()
    composition_panel.setObjectName("composition-context")
    composition_panel.setReadOnly(True)
    composition_panel.setMinimumHeight(72)
    composition_panel.setMaximumHeight(150)
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
    search = QLineEdit()
    search.setObjectName("candidate-search")
    search.setPlaceholderText("Hero search (Ctrl+F)")
    search.setAccessibleName("Candidate search")
    search.setAccessibleDescription(
        "Filters the local candidate display. Ctrl+F focuses this field; Escape clears it; "
        "Enter moves to the candidate table."
    )
    search.setToolTip(
        "Ctrl+F focuses search. Escape clears it. Enter moves to the candidate table."
    )
    clear_search = QPushButton("Clear search")
    clear_search.setObjectName("candidate-search-clear")
    clear_search.setAccessibleName("Clear candidate search")
    clear_search.setToolTip("Clear the local candidate search and return focus to search.")
    clear_search.setEnabled(False)
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
    candidates.setObjectName("candidate-table")
    candidates.setAccessibleName("Candidate table")
    candidates.setAccessibleDescription(
        "Use arrow keys to move the local candidate selection. Selection does not change the draft."
    )
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
    candidate_header = candidates.horizontalHeader()
    candidate_header.setObjectName("candidate-table-header")
    candidate_header.setSectionsClickable(True)
    candidate_header.setSortIndicatorShown(False)
    candidate_sort_status = QLabel(
        "Candidate display order: default recommendation order — display order only; "
        "does not change recommendation evidence or score."
    )
    candidate_sort_status.setObjectName("candidate-sort-status")
    candidate_filter_status = QLabel("Candidate results: loading local display…")
    candidate_filter_status.setObjectName("candidate-filter-status")
    candidates.setMinimumHeight(180)
    focus_search_shortcut = QShortcut(QKeySequence.StandardKey.Find, window)
    focus_search_shortcut.setObjectName("focus-candidate-search-shortcut")
    focus_search_shortcut.activated.connect(search.setFocus)
    clear_search_shortcut = QShortcut(QKeySequence("Escape"), search)
    clear_search_shortcut.setObjectName("clear-candidate-search-shortcut")
    clear_search_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
    clear_search_shortcut.activated.connect(search.clear)
    explanation_panel = QTextEdit()
    explanation_panel.setObjectName("recommendation-explanation")
    explanation_panel.setReadOnly(True)
    explanation_panel.setMinimumHeight(100)
    explanation_panel.setPlaceholderText("Select a candidate hero to inspect its evidence.")
    explanation_panel.setPlainText("Select a candidate hero to inspect its evidence.")

    comparison_status = QLabel("Comparison: select up to 3 legal candidates to compare locally.")
    comparison_status.setObjectName("candidate-comparison-status")
    add_comparison = QPushButton("Add selected to compare")
    add_comparison.setObjectName("add-candidate-comparison")
    remove_comparison = QPushButton("Remove selected from compare")
    remove_comparison.setObjectName("remove-candidate-comparison")
    clear_comparison_button = QPushButton("Clear comparison")
    clear_comparison_button.setObjectName("clear-candidate-comparison")
    comparison_controls = QHBoxLayout()
    comparison_controls.addWidget(add_comparison)
    comparison_controls.addWidget(remove_comparison)
    comparison_controls.addWidget(clear_comparison_button)
    comparison_cards = QHBoxLayout()
    comparison_panels: list[QTextEdit] = []
    for index in range(3):
        panel = QTextEdit()
        panel.setObjectName(f"candidate-comparison-slot-{index + 1}")
        panel.setReadOnly(True)
        panel.setPlaceholderText("Empty comparison slot")
        panel.setPlainText("Empty comparison slot")
        panel.setMinimumWidth(220)
        comparison_cards.addWidget(panel)
        comparison_panels.append(panel)

    content_splitter = QSplitter(Qt.Orientation.Vertical)
    content_splitter.setObjectName("draft-content-splitter")
    composition_section = QWidget()
    composition_section.setObjectName("composition-context-section")
    composition_layout = QVBoxLayout(composition_section)
    composition_layout.setContentsMargins(0, 0, 0, 0)
    composition_layout.addWidget(composition_panel)
    composition_layout.addLayout(composition_controls)
    candidate_section = QWidget()
    candidate_section.setObjectName("candidate-table-section")
    candidate_layout = QVBoxLayout(candidate_section)
    candidate_layout.setContentsMargins(0, 0, 0, 0)
    candidate_filter_controls = QHBoxLayout()
    candidate_filter_controls.addWidget(search)
    candidate_filter_controls.addWidget(clear_search)
    candidate_layout.addLayout(candidate_filter_controls)
    candidate_layout.addWidget(candidate_filter_status)
    candidate_layout.addWidget(candidate_sort_status)
    candidate_layout.addWidget(candidates)
    comparison_section = QWidget()
    comparison_section.setObjectName("candidate-comparison")
    comparison_layout = QVBoxLayout(comparison_section)
    comparison_layout.setContentsMargins(0, 0, 0, 0)
    comparison_layout.addWidget(QLabel("Candidate comparison — local display only"))
    comparison_layout.addWidget(comparison_status)
    comparison_layout.addLayout(comparison_controls)
    comparison_layout.addLayout(comparison_cards)
    content_splitter.addWidget(composition_section)
    content_splitter.addWidget(candidate_section)
    content_splitter.addWidget(explanation_panel)
    content_splitter.addWidget(comparison_section)
    for index in range(content_splitter.count()):
        content_splitter.setCollapsible(index, False)
    content_splitter.setStretchFactor(0, 1)
    content_splitter.setStretchFactor(1, 5)
    content_splitter.setStretchFactor(2, 2)
    content_splitter.setStretchFactor(3, 2)
    content_splitter.setSizes([120, 330, 150, 180])
    layout.addWidget(content_splitter, 1)
    if session is not None:
        rendered_rows: list[CandidateRow] = []
        scorer = ExperimentalEvidenceScoringEngine()
        hero_by_id = {hero.hero_id: hero for hero in session.heroes}
        overlay_context: PairEvidenceContext | None = None
        overlay_counters: tuple[CounterEvidence, ...] = ()
        overlay_synergies: tuple[SynergyEvidence, ...] = ()
        latest_pair_result: PairEvidenceResult | None = None
        pair_state = PairRefreshState.IDLE
        sort_column: CandidateSortColumn | None = None
        sort_descending = False
        comparison_hero_ids: list[int] = []
        comparison_rows_by_id: dict[int, CandidateRow] = {}
        pending_import: ManualImportAssessment | None = None
        last_confirmed_import_time = None

        def clear_import_preview(message: str) -> None:
            nonlocal pending_import
            pending_import = None
            confirm_import.setEnabled(False)
            cancel_import.setEnabled(False)
            manual_import_preview.setText(message)

        def describe_import_preview(assessment: ManualImportAssessment) -> str:
            assert assessment.draft is not None
            draft = assessment.draft
            role_text = "Position 4" if draft.intended_role is Role.POSITION_4 else "Position 5"
            observed_text = (
                "observed time unknown — explicit review required"
                if assessment.observed_at is None
                else f"observed at {assessment.observed_at.isoformat()}"
            )
            return (
                f"Import preview: role {role_text}; allies {len(draft.allied_picks)} "
                f"(current {len(session.allies)}); enemies {len(draft.enemy_picks)} "
                f"(current {len(session.enemies)}); bans {len(draft.banned_heroes)} "
                f"(current {len(session.bans)}); {observed_text}. "
                "Confirm atomically replaces picks, bans, and role. "
                "MANUAL_IMPORT/v1 has no ally position/lane fields, so confirmation clears "
                "all existing manual ally composition assignments."
            )

        def preview_manual_import() -> None:
            nonlocal pending_import
            assessment = assess_pasted_manual_import(
                manual_import_text.toPlainText(),
                session.heroes,
                session.patch,
                last_confirmed_import_time,
            )
            if not assessment.can_confirm:
                clear_import_preview(
                    "Import rejected: "
                    f"{assessment.issue or 'invalid document'}. Current draft unchanged."
                )
                return
            pending_import = assessment
            confirm_import.setEnabled(True)
            cancel_import.setEnabled(True)
            manual_import_preview.setText(describe_import_preview(assessment))

        def confirm_manual_import() -> None:
            nonlocal last_confirmed_import_time
            assessment = pending_import
            if assessment is None or not assessment.can_confirm or assessment.draft is None:
                clear_import_preview("No valid import preview is available to confirm.")
                return
            try:
                session.replace_from_manual_import(assessment.draft)
            except ValueError:
                clear_import_preview("Import could not be applied. Current draft unchanged.")
                return
            if assessment.observed_at is not None:
                last_confirmed_import_time = assessment.observed_at
            four.setChecked(session.role is Role.POSITION_4)
            five.setChecked(session.role is Role.POSITION_5)
            refresh()
            update_draft_action_controls("Imported draft confirmed; manual ally context cleared.")
            clear_import_preview(
                "Import confirmed: current picks, bans, and role were replaced. "
                "Manual ally position/lane context was cleared."
            )
            trigger_pair_refresh()

        def invalidate_import_preview_for_draft_change() -> None:
            if pending_import is not None:
                clear_import_preview(
                    "Draft changed; validate the pasted document again before confirming."
                )

        def invalidate_import_preview_for_text_change() -> None:
            if pending_import is not None:
                clear_import_preview("Pasted text changed; validate it again before confirming.")

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
            if not candidates.selectedItems():
                return None
            row = candidates.currentRow()
            return rendered_rows[row] if 0 <= row < len(rendered_rows) else None

        def comparison_component_text(row: CandidateRow, name: str) -> str:
            value = dict(row.experimental_components).get(name)
            if value is None:
                return "unavailable — fixed weight contributes neutral zero"
            return format_optional_rate(value)

        def update_comparison_controls() -> None:
            row = selected_candidate_row()
            hero_id = row.hero.hero_id if row is not None else None
            add_comparison.setEnabled(
                hero_id is not None
                and hero_id not in comparison_hero_ids
                and len(comparison_hero_ids) < 3
            )
            remove_comparison.setEnabled(hero_id is not None and hero_id in comparison_hero_ids)
            clear_comparison_button.setEnabled(bool(comparison_hero_ids))

        def update_comparison() -> None:
            legal_ids = {hero.hero_id for hero in session.candidates}
            comparison_hero_ids[:] = [
                hero_id
                for hero_id in comparison_hero_ids
                if hero_id in legal_ids and hero_id in comparison_rows_by_id
            ]
            role_text = "Position 4" if session.role is Role.POSITION_4 else "Position 5"
            for index, panel in enumerate(comparison_panels):
                if index >= len(comparison_hero_ids):
                    panel.setPlainText("Empty comparison slot")
                    continue
                row = comparison_rows_by_id[comparison_hero_ids[index]]
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
                component_values = {
                    name: escape(comparison_component_text(row, name))
                    for name in ("meta", "counter", "synergy", "personal")
                }
                panel.setHtml(
                    "".join(
                        (
                            f"<h3>{escape(row.display_name)}</h3>",
                            f"<p><b>Experimental score:</b> {escape(score)}</p>",
                            f"<p><b>Confidence:</b> {escape(confidence)}</p>",
                            f"<p><b>Meta:</b> {component_values['meta']}</p>",
                            f"<p><b>Counter:</b> {component_values['counter']}</p>",
                            f"<p><b>Synergy:</b> {component_values['synergy']}</p>",
                            f"<p><b>Personal:</b> {component_values['personal']}</p>",
                            f"<p><b>Role:</b> {role_text}</p>",
                        )
                    )
                )
            comparison_status.setText(
                "Comparison: "
                + (
                    f"{len(comparison_hero_ids)} / 3 legal candidates — local display only; "
                    "does not change recommendation evidence, score, shortlist, or requests."
                    if comparison_hero_ids
                    else "select up to 3 legal candidates to compare locally."
                )
            )
            update_comparison_controls()

        def add_selected_to_comparison() -> None:
            row = selected_candidate_row()
            if row is None or row.hero.hero_id in comparison_hero_ids:
                update_comparison_controls()
                return
            if len(comparison_hero_ids) < 3:
                comparison_hero_ids.append(row.hero.hero_id)
            update_comparison()

        def remove_selected_from_comparison() -> None:
            row = selected_candidate_row()
            if row is not None and row.hero.hero_id in comparison_hero_ids:
                comparison_hero_ids.remove(row.hero.hero_id)
            update_comparison()

        def clear_comparison() -> None:
            comparison_hero_ids.clear()
            update_comparison()

        def update_candidate_sort_status() -> None:
            sort_description = candidate_sort_description()
            if sort_column is None:
                candidate_sort_status.setText(
                    f"Candidate display order: {sort_description} — display order only; "
                    "does not change recommendation evidence or score."
                )
                candidate_header.setSortIndicatorShown(False)
                return

            candidate_sort_status.setText(
                f"Candidate display order: {sort_description} — display order only; "
                "does not change recommendation evidence or score."
            )
            candidate_header.setSortIndicatorShown(True)
            candidate_header.setSortIndicator(
                int(sort_column),
                Qt.SortOrder.DescendingOrder if sort_descending else Qt.SortOrder.AscendingOrder,
            )

        def candidate_sort_description() -> str:
            if sort_column is None:
                return "default recommendation order"
            labels = {
                CandidateSortColumn.HERO: "Hero",
                CandidateSortColumn.EXPERIMENTAL_SCORE: "Experimental Score",
                CandidateSortColumn.CONFIDENCE: "Confidence",
                CandidateSortColumn.META: "Meta",
                CandidateSortColumn.COUNTER: "Counter",
                CandidateSortColumn.SYNERGY: "Synergy",
                CandidateSortColumn.PERSONAL: "Personal",
                CandidateSortColumn.WHY: "Why",
            }
            direction = "descending" if sort_descending else "ascending"
            return f"{labels[sort_column]} {direction}"

        def update_candidate_filter_status(displayed_count: int) -> None:
            filter_text = search.text().strip()
            clear_search.setEnabled(bool(filter_text))
            displayed_filter = f'"{filter_text}"' if filter_text else "none"
            candidate_filter_status.setText(
                "Candidate results: "
                f"displaying {displayed_count} / {len(session.candidates)} legal candidates "
                f"| text filter: {displayed_filter} "
                f"| display sort: {candidate_sort_description()} — local display only; "
                "does not change recommendation, shortlist, or evidence."
            )

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

            def evidence_line(label: str, value: str) -> str:
                return f"<p><b>{escape(label)}:</b> {escape(value)}</p>"

            explanation_panel.setHtml(
                "".join(
                    (
                        f"<h2>Candidate: {escape(row.display_name)}</h2>",
                        "<h3>Recommendation summary</h3>",
                        evidence_line("Experimental score", score),
                        evidence_line("Confidence", confidence),
                        "<h3>Evidence</h3>",
                        evidence_line("Meta", component_text("meta")),
                        evidence_line("Counter", component_text("counter")),
                        evidence_line("Synergy", component_text("synergy")),
                        evidence_line("Personal", component_text("personal")),
                        "<h3>Why / availability</h3>",
                        f"<p><b>Why:</b> {escape(row.explanation or row.status)}</p>",
                        "<h3>Context</h3>",
                        evidence_line("Role", role_text),
                        f"<p>{escape(pair_coverage_label.text())}</p>",
                        "<p>Meta, Counter, and Synergy use current-week role evidence; "
                        "it is not patch-isolated.</p>",
                        "<p>Personal history is all-time and role-unknown.</p>",
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

        def update_pair_actionability() -> None:
            """Explain existing pair state locally; never schedule or retry work."""
            input_data = pair_input()
            context = input_data.context
            requested = (
                ("Counter", bool(context.enemy_ids)),
                ("Synergy", bool(context.ally_ids)),
            )
            if pair_service is None:
                pair_action_label.setText(
                    "Pair action: The STRATZ pair-refresh service is unavailable in this session. "
                    "Meta/Personal remain available without pair evidence."
                )
                return
            if pair_state is PairRefreshState.SHUTTING_DOWN:
                pair_action_label.setText(
                    "Pair action: Finishing the current pair refresh before closing; "
                    "no further refresh can be started."
                )
                return
            if not (context.ally_ids or context.enemy_ids):
                pair_action_label.setText(
                    "Pair action: Add an allied or enemy pick before pair evidence can run. "
                    "Meta/Personal remain available; no pair refresh is requested."
                )
                return
            if not input_data.shortlist:
                pair_action_label.setText(
                    "Pair action: No legal shortlist is available for this draft. "
                    "Meta/Personal remain available; pair refresh cannot run."
                )
                return
            if pair_state in (PairRefreshState.DEBOUNCING, PairRefreshState.LOADING):
                pair_action_label.setText(
                    "Pair action: Updating evidence for this context. Wait for completion, "
                    "or use Refresh pair evidence to queue one latest retry. "
                    "Meta/Personal remain available."
                )
                return
            current_result = (
                latest_pair_result
                if latest_pair_result is not None and latest_pair_result.context == context
                else None
            )
            errors = {
                "Counter": current_result.counter_error if current_result else None,
                "Synergy": current_result.synergy_error if current_result else None,
            }
            unavailable = [name for name, enabled in requested if enabled and errors[name]]
            available = [name for name, enabled in requested if enabled and name not in unavailable]

            def names(items: list[str]) -> str:
                if len(items) == 2:
                    return " and ".join(items)
                return items[0]

            def verb(items: list[str]) -> str:
                return "are" if len(items) == 2 else "is"

            retry = (
                "Use Refresh pair evidence to retry/recalculate this context; it may use existing "
                "caches and does not force an HTTP request."
            )
            if unavailable:
                unavailable_text = names(unavailable)
                if available:
                    pair_action_label.setText(
                        f"Pair action: {unavailable_text} {verb(unavailable)} unavailable; "
                        f"{names(available)} {verb(available)} still available. {retry} "
                        "Meta/Personal remain available."
                    )
                else:
                    pair_action_label.setText(
                        f"Pair action: {unavailable_text} {verb(unavailable)} unavailable for this "
                        f"context. {retry} "
                        "Meta/Personal remain available."
                    )
                return
            if pair_state is PairRefreshState.ERROR:
                pair_action_label.setText(
                    "Pair action: Pair evidence is unavailable for this context. "
                    f"{retry} Meta/Personal remain available."
                )
                return
            if current_result is not None:
                pair_action_label.setText(
                    f"Pair action: {names(available)} {verb(available)} available for the current "
                    "context. "
                    "Meta/Personal remain independently available."
                )
                return
            pair_action_label.setText(
                "Pair action: Pair evidence has not completed for this context. "
                f"{retry} Meta/Personal remain available."
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
                    "Retry/recalculate this current context using existing provider caches when "
                    "available; it does not force an HTTP request."
                )

        def refresh() -> None:
            previously_selected = selected_candidate_row()
            previous_hero_id = previously_selected.hero.hero_id if previously_selected else None
            search_had_focus = search.hasFocus()
            table_had_focus = candidates.hasFocus()
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
            update_pair_actionability()
            update_manual_refresh_control()
            recommendations = scorer.rank(
                session.to_draft_state(), session.candidates, effective_evidence(), personal_stats
            )
            all_rows = build_candidate_rows(session.candidates, personal_stats, recommendations)
            comparison_rows_by_id.clear()
            comparison_rows_by_id.update({row.hero.hero_id: row for row in all_rows})
            rows = filter_candidates(all_rows, search.text())
            if sort_column is not None:
                rows = sort_candidate_rows(rows, sort_column, sort_descending)
            rendered_rows[:] = rows
            update_candidate_filter_status(len(rows))
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
            if search_had_focus:
                search.setFocus()
            elif table_had_focus and rows:
                candidates.setFocus()
            update_recommendation_explanation()
            update_comparison()
            update_draft_action_controls()

        def sort_candidates(section: int) -> None:
            nonlocal sort_column, sort_descending
            try:
                selected_column = CandidateSortColumn(section)
            except ValueError:
                return
            if sort_column is selected_column:
                sort_descending = not sort_descending
            else:
                sort_column = selected_column
                sort_descending = False
            update_candidate_sort_status()
            refresh()

        def clear_candidate_search() -> None:
            search.clear()
            search.setFocus()

        def focus_candidate_table() -> None:
            if not rendered_rows:
                return
            if selected_candidate_row() is None:
                candidates.setCurrentCell(0, 0)
            candidates.setFocus()

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
            update_pair_actionability()
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
            update_pair_actionability()
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
            invalidate_import_preview_for_draft_change()
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
            invalidate_import_preview_for_draft_change()
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
            invalidate_import_preview_for_draft_change()
            refresh()
            update_draft_action_controls("Draft reset.")
            trigger_pair_refresh()

        def choose_role(role: Role, checked: bool) -> None:
            if not checked or session.role is role:
                return
            session.set_role(role)
            invalidate_import_preview_for_draft_change()
            refresh()
            update_draft_action_controls("Role changed; draft context updated.")
            trigger_pair_refresh()

        reset.clicked.connect(reset_draft)
        manual_refresh.clicked.connect(trigger_manual_pair_refresh)
        add_comparison.clicked.connect(add_selected_to_comparison)
        remove_comparison.clicked.connect(remove_selected_from_comparison)
        clear_comparison_button.clicked.connect(clear_comparison)
        save_composition.clicked.connect(save_ally_composition)
        validate_import.clicked.connect(preview_manual_import)
        cancel_import.clicked.connect(
            lambda: clear_import_preview("Import preview cancelled. Current draft unchanged.")
        )
        confirm_import.clicked.connect(confirm_manual_import)
        configure_player.clicked.connect(save_player_account)
        clear_player.clicked.connect(clear_player_account)
        four.toggled.connect(lambda checked: choose_role(Role.POSITION_4, checked))
        five.toggled.connect(lambda checked: choose_role(Role.POSITION_5, checked))
        search.textChanged.connect(lambda _: refresh())
        clear_search.clicked.connect(clear_candidate_search)
        search.returnPressed.connect(focus_candidate_table)
        manual_import_text.textChanged.connect(invalidate_import_preview_for_text_change)
        candidates.itemSelectionChanged.connect(update_recommendation_explanation)
        candidates.itemSelectionChanged.connect(update_comparison_controls)
        allies.itemSelectionChanged.connect(sync_composition_controls)
        candidates.itemSelectionChanged.connect(update_draft_action_controls)
        allies.itemSelectionChanged.connect(update_draft_action_controls)
        enemies.itemSelectionChanged.connect(update_draft_action_controls)
        bans.itemSelectionChanged.connect(update_draft_action_controls)
        candidate_header.sectionClicked.connect(sort_candidates)
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
        update_candidate_sort_status()
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
            clear_search,
            candidates,
            add_comparison,
            remove_comparison,
            clear_comparison_button,
            manual_import_text,
            validate_import,
            cancel_import,
            confirm_import,
        ):
            widget.setEnabled(False)
    window.setCentralWidget(contents)
    window.setMinimumSize(860, 600)
    window.resize(1050, 760)
    return window
