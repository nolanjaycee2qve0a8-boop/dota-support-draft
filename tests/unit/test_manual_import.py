"""Production MANUAL_IMPORT/v1 assessment and atomic session replacement tests."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from dota_support_draft.domain import Hero, Patch, PlannedLane, Role, TeamPosition
from dota_support_draft.draft import (
    ManualDraftSession,
    ManualImportStatus,
    assess_pasted_manual_import,
    encode_manual_import,
)


@pytest.fixture
def heroes() -> tuple[Hero, ...]:
    return (
        Hero(1, "hero_one"),
        Hero(2, "hero_two"),
        Hero(3, "hero_three"),
        Hero(4, "hero_four"),
        Hero(5, "inactive", is_active=False),
    )


@pytest.fixture
def patch() -> Patch:
    return Patch("fixture", "7.40", date(2026, 9, 2))


def _document(
    schema_version: str = "dota-support-draft/manual-import/v1", **draft_overrides: object
) -> str:
    draft = {
        "complete": True,
        "patch_version": "7.40",
        "intended_role": "POSITION_5",
        "allied_hero_ids": [3],
        "enemy_hero_ids": [4],
        "banned_hero_ids": [2],
    }
    draft.update(draft_overrides)
    return json.dumps(
        {
            "schema_version": schema_version,
            "provenance": {"kind": "MANUAL_IMPORT", "observed_at": "2026-09-02T00:00:00Z"},
            "draft": draft,
        }
    )


def test_assessment_is_preview_only_until_explicit_confirmation(
    heroes: tuple[Hero, ...], patch: Patch
) -> None:
    session = ManualDraftSession(heroes, patch)
    session.add_ally(heroes[0])
    original = session.to_draft_state()

    assessment = assess_pasted_manual_import(_document(), heroes, patch)

    assert assessment.status is ManualImportStatus.PREVIEW
    assert assessment.can_confirm and assessment.draft is not None
    assert session.to_draft_state() == original
    assert [pick.hero.hero_id for pick in assessment.draft.allied_picks] == [3]


@pytest.mark.parametrize(
    ("text", "expected_issue"),
    (
        ("not json", "Invalid JSON"),
        (_document(schema_version="unexpected"), "Unsupported schema"),
        (_document(complete=False), "Partial snapshots"),
        (_document(patch_version="7.39"), "Patch mismatch"),
        (_document(allied_hero_ids=[999]), "Unknown hero"),
        (_document(allied_hero_ids=[5]), "Inactive hero"),
        (_document(allied_hero_ids=[3], banned_hero_ids=[3]), "picked hero"),
    ),
)
def test_rejected_documents_never_create_a_replacement(
    text: str, expected_issue: str, heroes: tuple[Hero, ...], patch: Patch
) -> None:
    assessment = assess_pasted_manual_import(text, heroes, patch)

    assert assessment.status is ManualImportStatus.REJECTED
    assert not assessment.can_confirm and assessment.draft is None
    assert assessment.issue is not None and expected_issue in assessment.issue


def test_unknown_and_stale_observed_times_follow_the_contract(
    heroes: tuple[Hero, ...], patch: Patch
) -> None:
    unknown = json.loads(_document())
    unknown["provenance"]["observed_at"] = "unknown"
    unknown_assessment = assess_pasted_manual_import(json.dumps(unknown), heroes, patch)
    stale = assess_pasted_manual_import(
        _document(),
        heroes,
        patch,
        datetime(2026, 9, 2, tzinfo=UTC),
    )

    assert unknown_assessment.status is ManualImportStatus.NEEDS_CONFIRMATION
    assert unknown_assessment.can_confirm and unknown_assessment.observed_at is None
    assert stale.status is ManualImportStatus.REJECTED
    assert stale.issue is not None and "Stale snapshot" in stale.issue


def test_confirmed_replacement_clears_manual_composition_atomically(
    heroes: tuple[Hero, ...], patch: Patch
) -> None:
    session = ManualDraftSession(heroes, patch)
    session.add_ally(heroes[0])
    session.add_enemy(heroes[1])
    session.set_ally_assignment(heroes[0], TeamPosition.POSITION_1, PlannedLane.SAFE)
    assessment = assess_pasted_manual_import(_document(), heroes, patch)
    assert assessment.draft is not None

    session.replace_from_manual_import(assessment.draft)

    assert session.role is Role.POSITION_5
    assert [hero.hero_id for hero in session.allies] == [3]
    assert [hero.hero_id for hero in session.enemies] == [4]
    assert {hero.hero_id for hero in session.bans} == {2}
    assert session.ally_assignments == {}


def test_export_encoder_is_v1_and_excludes_non_v1_context(
    heroes: tuple[Hero, ...], patch: Patch
) -> None:
    session = ManualDraftSession(heroes, patch)
    session.add_ally(heroes[0])
    session.add_enemy(heroes[1])
    session.ban(heroes[2])
    session.set_ally_assignment(heroes[0], TeamPosition.POSITION_1, PlannedLane.SAFE)

    document = json.loads(encode_manual_import(session.to_draft_state()))

    assert document == {
        "schema_version": "dota-support-draft/manual-import/v1",
        "provenance": {"kind": "MANUAL_IMPORT", "observed_at": "unknown"},
        "draft": {
            "complete": True,
            "patch_version": "7.40",
            "intended_role": "POSITION_4",
            "allied_hero_ids": [1],
            "enemy_hero_ids": [2],
            "banned_hero_ids": [3],
        },
    }
