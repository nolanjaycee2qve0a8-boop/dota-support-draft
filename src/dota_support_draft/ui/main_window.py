from collections.abc import Callable
from typing import Any

from dota_support_draft.domain import Hero, PersonalHeroStat, Role
from dota_support_draft.draft import (
    CandidateRow,
    ManualDraftSession,
    build_candidate_rows,
    filter_candidates,
    format_optional_count,
    format_optional_rate,
    format_player_status,
)


def create_main_window(
    session: ManualDraftSession | None = None,
    personal_stats: tuple[PersonalHeroStat, ...] = (),
    initial_status: str = "Loading data...",
    player: object | None = None,
    personal_error: str | None = None,
) -> object:
    """Thin UI binding; session owns all draft invariants and candidate eligibility."""
    from PySide6.QtCore import Qt
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

    window = QMainWindow()
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
    role_row = QHBoxLayout()
    four = QRadioButton("Position 4")
    five = QRadioButton("Position 5")
    four.setChecked(True)
    role_row.addWidget(four)
    role_row.addWidget(five)
    layout.addLayout(role_row)
    lists = QHBoxLayout()
    allies = QListWidget()
    enemies = QListWidget()
    bans = QListWidget()
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
    add_ally = QPushButton("Add Ally")
    add_enemy = QPushButton("Add Enemy")
    ban = QPushButton("Ban")
    remove_ally = QPushButton("Remove Ally")
    remove_enemy = QPushButton("Remove Enemy")
    unban = QPushButton("Unban")
    reset = QPushButton("Reset Draft")
    for button in (add_ally, add_enemy, ban, remove_ally, remove_enemy, unban, reset):
        controls.addWidget(button)
    layout.addLayout(controls)
    layout.addWidget(
        QLabel("Candidate list — scoring not enabled. Personal history is ALL-TIME; ROLE UNKNOWN.")
    )
    candidates = QTableWidget(0, 5)
    candidates.setHorizontalHeaderLabels(["Hero", "Games", "Wins", "Win Rate", "Status"])
    layout.addWidget(candidates)
    if session is not None:
        rendered_rows: list[CandidateRow] = []
        hero_by_id = {hero.hero_id: hero for hero in session.heroes}

        def refresh() -> None:
            allies.clear()
            enemies.clear()
            bans.clear()
            for hero in session.allies:
                item = QListWidgetItem(hero.localized_name or hero.canonical_name)
                item.setData(Qt.UserRole, hero.hero_id)
                allies.addItem(item)
            for hero in session.enemies:
                item = QListWidgetItem(hero.localized_name or hero.canonical_name)
                item.setData(Qt.UserRole, hero.hero_id)
                enemies.addItem(item)
            for hero in session.bans:
                item = QListWidgetItem(hero.localized_name or hero.canonical_name)
                item.setData(Qt.UserRole, hero.hero_id)
                bans.addItem(item)
            rows = filter_candidates(
                build_candidate_rows(session.candidates, personal_stats), search.text()
            )
            rendered_rows[:] = rows
            candidates.setRowCount(len(rows))
            for index, row in enumerate(rows):
                for column, value in enumerate(
                    (
                        row.display_name,
                        format_optional_count(row.personal_matches),
                        format_optional_count(row.personal_wins),
                        format_optional_rate(row.personal_win_rate),
                        row.status,
                    )
                ):
                    candidates.setItem(index, column, QTableWidgetItem(str(value)))

        def chosen() -> Hero | None:
            row = candidates.currentRow()
            return rendered_rows[row].hero if 0 <= row < len(rendered_rows) else None

        def selected_list_hero(widget: Any) -> Hero | None:
            item = widget.currentItem()
            return hero_by_id.get(item.data(Qt.UserRole)) if item is not None else None

        def apply(action: Callable[[Hero], None]) -> None:
            hero = chosen()
            if hero is not None:
                try:
                    action(hero)
                except ValueError as error:
                    status.setText(str(error))
            else:
                status.setText("Select a candidate hero first.")
            refresh()

        def remove_from(widget: Any, action: Callable[[Hero], None]) -> None:
            hero = selected_list_hero(widget)
            if hero is None:
                status.setText("Select a hero from the list first.")
            else:
                action(hero)
            refresh()

        add_ally.clicked.connect(lambda: apply(session.add_ally))
        add_enemy.clicked.connect(lambda: apply(session.add_enemy))
        ban.clicked.connect(lambda: apply(session.ban))
        remove_ally.clicked.connect(lambda: remove_from(allies, session.remove_ally))
        remove_enemy.clicked.connect(lambda: remove_from(enemies, session.remove_enemy))
        unban.clicked.connect(lambda: remove_from(bans, session.unban))

        def reset_draft() -> None:
            session.clear()
            refresh()

        def choose_four(checked: bool) -> None:
            if checked:
                session.set_role(Role.POSITION_4)

        def choose_five(checked: bool) -> None:
            if checked:
                session.set_role(Role.POSITION_5)

        reset.clicked.connect(reset_draft)
        four.toggled.connect(choose_four)
        five.toggled.connect(choose_five)
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
            search,
            candidates,
        ):
            widget.setEnabled(False)
    window.setCentralWidget(contents)
    window.resize(900, 650)
    return window
