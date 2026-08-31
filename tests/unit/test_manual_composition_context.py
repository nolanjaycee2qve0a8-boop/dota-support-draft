import time
from datetime import UTC, date, datetime

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QListWidget,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTextEdit,
)

from dota_support_draft.domain import (
    DataProvenance,
    DraftState,
    EvidenceSet,
    Hero,
    HeroPick,
    Patch,
    PlannedLane,
    Role,
    RoleEvidenceBundle,
    RoleEvidenceBundles,
    RoleMetaEvidence,
    TeamPosition,
    TeamSide,
)
from dota_support_draft.draft import ManualDraftError, ManualDraftSession, PairEvidenceResult
from dota_support_draft.ui.main_window import create_main_window


class CountingPairService:
    rank_bracket = None

    def __init__(self, delay: float = 0.0) -> None:
        self.calls, self.delay = 0, delay

    def refresh(self, input_data):
        self.calls += 1
        time.sleep(self.delay)
        return PairEvidenceResult(input_data.generation, input_data.context)


def _bundles(heroes: tuple[Hero, ...], patch: Patch) -> RoleEvidenceBundles:
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


def _wait(app: QApplication, predicate, seconds: float = 2.0) -> None:
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


def _button(window, object_name: str) -> QPushButton:
    button = window.findChild(QPushButton, object_name)
    assert button is not None
    return button


def test_manual_ally_assignment_defaults_updates_and_cleans_up() -> None:
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 4))
    session = ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1)))
    session.add_ally(heroes[0])
    default_pick = session.to_draft_state().allied_picks[0]
    assert (
        default_pick.team_position is TeamPosition.UNKNOWN
        and default_pick.planned_lane is PlannedLane.UNKNOWN
    )

    session.set_ally_assignment(heroes[0], TeamPosition.POSITION_1, PlannedLane.SAFE)
    assigned_pick = session.to_draft_state().allied_picks[0]
    assert (
        assigned_pick.team_position is TeamPosition.POSITION_1
        and assigned_pick.planned_lane is PlannedLane.SAFE
    )
    session.remove_ally(heroes[0])
    assert not session.ally_assignments
    session.add_enemy(heroes[1])
    session.ban(heroes[2])
    with pytest.raises(ManualDraftError):
        session.set_ally_assignment(heroes[1], TeamPosition.POSITION_2, PlannedLane.MID)
    with pytest.raises(ManualDraftError):
        session.set_ally_assignment(heroes[2], TeamPosition.POSITION_3, PlannedLane.OFF)
    session.clear()
    assert not session.ally_assignments


def test_draft_state_rejects_manual_assignment_for_enemy(hero, patch) -> None:
    with pytest.raises(ValueError, match="Only allied picks"):
        DraftState(
            (),
            (HeroPick(hero, TeamSide.ENEMY, team_position=TeamPosition.POSITION_1),),
            Role.POSITION_4,
            patch,
        )


def test_composition_ui_is_manual_zero_network_and_resets() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 5))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession(heroes, patch)
    session.add_ally(heroes[0])
    session.add_ally(heroes[1])
    service = CountingPairService()
    window = create_main_window(
        session,
        evidence_by_role=_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=10_000,
    )
    window.show()
    allies = window.findChild(QListWidget, "allied-picks")
    position = window.findChild(QComboBox, "ally-team-position")
    lane = window.findChild(QComboBox, "ally-planned-lane")
    panel = window.findChild(QTextEdit, "composition-context")
    assert allies is not None and position is not None and lane is not None and panel is not None
    assert "manual draft context" in panel.toPlainText().casefold()
    assert "not statistical lane-fit" in panel.toPlainText()
    allies.setCurrentRow(0)
    position.setCurrentIndex(position.findData(TeamPosition.POSITION_1))
    lane.setCurrentIndex(lane.findData(PlannedLane.SAFE))
    _button(window, "save-ally-composition").click()
    assert "Hero 1: P1, Safe (manual)" in panel.toPlainText()
    assert service.calls == 0

    allies.setCurrentRow(1)
    position.setCurrentIndex(position.findData(TeamPosition.POSITION_1))
    _button(window, "save-ally-composition").click()
    assert "Conflict: P1 assigned to Hero 1, Hero 2." in panel.toPlainText()
    radios = {radio.text(): radio for radio in window.findChildren(QRadioButton)}
    radios["Position 5"].click()
    assert "Hero 1: P1, Safe (manual)" in panel.toPlainText()
    assert service.calls == 0

    next(
        button for button in window.findChildren(QPushButton) if button.text() == "Reset Draft"
    ).click()
    assert "No allied picks have been added." in panel.toPlainText()
    assert service.calls == 0
    app.processEvents()
    window.close()


def test_assignment_update_does_not_dispatch_another_active_pair_worker() -> None:
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 4))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    service = CountingPairService(delay=0.3)
    window = create_main_window(
        ManualDraftSession(heroes, patch),
        evidence_by_role=_bundles(heroes, patch),
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    window.show()
    candidates = window.findChild(QListWidget, "allied-picks")
    table = window.findChild(QTableWidget)
    assert (
        candidates is not None and table is not None and window.pair_refresh_controller is not None
    )
    table.selectRow(0)
    next(
        button for button in window.findChildren(QPushButton) if button.text() == "Add Ally"
    ).click()
    controller = window.pair_refresh_controller
    _wait(app, lambda: service.calls == 1 and controller.active_thread is not None)

    candidates.setCurrentRow(0)
    position = window.findChild(QComboBox, "ally-team-position")
    assert position is not None
    position.setCurrentIndex(position.findData(TeamPosition.POSITION_1))
    _button(window, "save-ally-composition").click()
    assert service.calls == 1 and controller.active_thread is not None

    window.close()
    _wait(
        app,
        lambda: (
            not window.isVisible()
            and controller.active_thread is None
            and not controller.findChildren(QThread)
        ),
        seconds=3.0,
    )
    assert service.calls == 1
