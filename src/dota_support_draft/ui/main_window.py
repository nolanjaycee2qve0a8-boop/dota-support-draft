from collections.abc import Callable

from dota_support_draft.domain import Hero, PersonalHeroStat, Role
from dota_support_draft.draft import ManualDraftSession, build_candidate_rows, filter_candidates


def create_main_window(
    session: ManualDraftSession | None = None,
    personal_stats: tuple[PersonalHeroStat, ...] = (),
    initial_status: str = "Loading data...",
) -> object:
    """Thin UI binding; session owns all draft invariants and candidate eligibility."""
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
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
    status = QLabel(
        initial_status if session is None else f"Patch: {session.patch.version} | Ready"
    )
    layout.addWidget(status)
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
    reset = QPushButton("Reset Draft")
    for button in (add_ally, add_enemy, ban, reset):
        controls.addWidget(button)
    layout.addLayout(controls)
    layout.addWidget(
        QLabel("Candidate list — scoring not enabled. Personal history is ALL-TIME; ROLE UNKNOWN.")
    )
    candidates = QTableWidget(0, 5)
    candidates.setHorizontalHeaderLabels(["Hero", "Games", "Wins", "Win Rate", "Status"])
    layout.addWidget(candidates)
    if session is not None:

        def refresh() -> None:
            allies.clear()
            enemies.clear()
            bans.clear()
            for hero in session.allies:
                allies.addItem(hero.localized_name or hero.canonical_name)
            for hero in session.enemies:
                enemies.addItem(hero.localized_name or hero.canonical_name)
            for hero in session.bans:
                bans.addItem(hero.localized_name or hero.canonical_name)
            rows = filter_candidates(
                build_candidate_rows(session.candidates, personal_stats), search.text()
            )
            candidates.setRowCount(len(rows))
            for index, row in enumerate(rows):
                for column, value in enumerate(
                    (
                        row.display_name,
                        row.personal_matches or "—",
                        row.personal_wins or "—",
                        f"{row.personal_win_rate:.0%}"
                        if row.personal_win_rate is not None
                        else "—",
                        row.status,
                    )
                ):
                    candidates.setItem(index, column, QTableWidgetItem(str(value)))

        def chosen() -> Hero | None:
            row = candidates.currentRow()
            rows = filter_candidates(
                build_candidate_rows(session.candidates, personal_stats), search.text()
            )
            return rows[row].hero if 0 <= row < len(rows) else None

        def apply(action: Callable[[Hero], None]) -> None:
            hero = chosen()
            if hero is not None:
                try:
                    action(hero)
                except ValueError as error:
                    status.setText(str(error))
            refresh()

        add_ally.clicked.connect(lambda: apply(session.add_ally))
        add_enemy.clicked.connect(lambda: apply(session.add_enemy))
        ban.clicked.connect(lambda: apply(session.ban))

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
        for widget in (four, five, add_ally, add_enemy, ban, reset, search, candidates):
            widget.setEnabled(False)
    window.setCentralWidget(contents)
    window.resize(420, 160)
    return window
