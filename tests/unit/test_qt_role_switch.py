from datetime import UTC, date, datetime

from PySide6.QtWidgets import QApplication, QLabel, QRadioButton, QTableWidget

from dota_support_draft.domain import (
    EvidenceSet,
    Hero,
    Patch,
    Role,
    RoleEvidenceBundle,
    RoleEvidenceBundles,
    RoleMetaEvidence,
)
from dota_support_draft.domain.models import DataProvenance
from dota_support_draft.draft import ManualDraftSession
from dota_support_draft.ui.main_window import create_main_window


def _bundles(hero: Hero, patch: Patch) -> RoleEvidenceBundles:
    provenance = DataProvenance(
        "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
    )
    p4 = RoleEvidenceBundle(
        Role.POSITION_4,
        EvidenceSet(
            role_meta=(RoleMetaEvidence(hero, Role.POSITION_4, patch, 1000, 600, 0.6, provenance),)
        ),
    )
    p5 = RoleEvidenceBundle(Role.POSITION_5, error="P5 evidence unavailable")
    return RoleEvidenceBundles(p4, p5)


def test_role_switch_refreshes_real_widgets_without_provider_calls() -> None:
    app = QApplication.instance() or QApplication([])
    hero = Hero(1, "hero", "Hero")
    other = Hero(2, "other", "Other")
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession((hero, other), patch)
    window = create_main_window(session, evidence_by_role=_bundles(hero, patch))
    window.show()
    app.processEvents()
    table = window.findChild(QTableWidget)
    radios = {radio.text(): radio for radio in window.findChildren(QRadioButton)}
    assert table is not None and radios["Position 4"].isChecked()
    assert table.item(0, 1).text() != "—"
    radios["Position 5"].click()
    app.processEvents()
    assert table.item(0, 1).text() == "—"
    assert any(label.text() == "P5 evidence unavailable" for label in window.findChildren(QLabel))
    radios["Position 4"].click()
    app.processEvents()
    assert table.item(0, 1).text() != "—"
    window.close()


def test_initial_position_five_radio_matches_session() -> None:
    QApplication.instance() or QApplication([])
    hero = Hero(1, "hero", "Hero")
    patch = Patch("p", "7.40", date(2026, 1, 1))
    session = ManualDraftSession((hero,), patch, Role.POSITION_5)
    window = create_main_window(session, evidence_by_role=_bundles(hero, patch))
    radios = {radio.text(): radio for radio in window.findChildren(QRadioButton)}
    assert radios["Position 5"].isChecked() and not radios["Position 4"].isChecked()
    window.close()
