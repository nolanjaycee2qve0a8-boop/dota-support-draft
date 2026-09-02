"""DOTA-029 contract-only preview fixtures; this is not a production import adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from dota_support_draft.domain import DraftState, Hero, HeroPick, Patch, Role, TeamSide

SCHEMA_VERSION = "dota-support-draft/manual-import/v1"
FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "manual_import_contract_cases.json"


class ContractError(ValueError):
    """A future preview must surface this error without changing the current draft."""


@dataclass(frozen=True)
class ContractAssessment:
    status: str
    issue: str | None = None
    preview: DraftState | None = None


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContractError(f"missing or invalid {name} root")
    return value


def _hero_ids(value: object, name: str) -> tuple[int, ...]:
    if not isinstance(value, list) or any(type(hero_id) is not int for hero_id in value):
        raise ContractError(f"{name} must be an integer array")
    hero_ids = tuple(value)
    if len(hero_ids) != len(set(hero_ids)):
        raise ContractError(f"duplicate {name} hero")
    return hero_ids


def _observed_at(value: object) -> datetime | None:
    if value == "unknown":
        return None
    if not isinstance(value, str):
        raise ContractError("observed_at must be an ISO-8601 timestamp or unknown")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("invalid observed_at") from error
    if parsed.tzinfo is None:
        raise ContractError("observed_at must include a timezone")
    return parsed


def _map_heroes(hero_ids: tuple[int, ...], catalog: dict[int, Hero], name: str) -> tuple[Hero, ...]:
    mapped: list[Hero] = []
    for hero_id in hero_ids:
        hero = catalog.get(hero_id)
        if hero is None:
            raise ContractError(f"unknown hero in {name}")
        if not hero.is_active:
            raise ContractError(f"inactive hero in {name}")
        mapped.append(hero)
    return tuple(mapped)


def assess_manual_import_contract(
    document: dict[str, object],
    catalog: dict[int, Hero],
    patch: Patch,
    last_confirmed_observed_at: datetime | None = None,
) -> ContractAssessment:
    """Test-local mapping for a future preview only; it performs no session replacement."""
    try:
        if document.get("schema_version") != SCHEMA_VERSION:
            raise ContractError("unknown schema version")
        provenance = _mapping(document.get("provenance"), "provenance")
        if provenance.get("kind") != "MANUAL_IMPORT":
            raise ContractError("unsupported provenance kind")
        observed_at = _observed_at(provenance.get("observed_at"))
        if last_confirmed_observed_at is not None and observed_at is not None:
            if observed_at <= last_confirmed_observed_at:
                raise ContractError("stale snapshot")
        draft = _mapping(document.get("draft"), "draft")
        if draft.get("complete") is not True:
            raise ContractError("partial snapshot")
        if draft.get("patch_version") != patch.version:
            raise ContractError("patch mismatch")
        role_name = draft.get("intended_role")
        if role_name not in (Role.POSITION_4.value, Role.POSITION_5.value):
            raise ContractError("unsupported intended role")
        allied_ids = _hero_ids(draft.get("allied_hero_ids"), "allied")
        enemy_ids = _hero_ids(draft.get("enemy_hero_ids"), "enemy")
        banned_ids = _hero_ids(draft.get("banned_hero_ids"), "banned")
        if len(allied_ids) > 5 or len(enemy_ids) > 5:
            raise ContractError("too many picked heroes")
        allies = _map_heroes(allied_ids, catalog, "allied")
        enemies = _map_heroes(enemy_ids, catalog, "enemy")
        banned = _map_heroes(banned_ids, catalog, "banned")
        if (set(allied_ids) | set(enemy_ids)) & set(banned_ids):
            raise ContractError("hero cannot be picked and banned")
        preview = DraftState(
            tuple(HeroPick(hero, TeamSide.ALLY) for hero in allies),
            tuple(HeroPick(hero, TeamSide.ENEMY) for hero in enemies),
            Role(role_name),
            patch,
            banned_heroes=frozenset(banned),
        )
    except ContractError as error:
        return ContractAssessment("REJECTED", str(error))
    except ValueError as error:
        return ContractAssessment("REJECTED", str(error))
    if observed_at is None:
        return ContractAssessment("NEEDS_CONFIRMATION", "observed_at is unknown", preview)
    return ContractAssessment("PREVIEW", preview=preview)


@pytest.fixture
def fixture_cases() -> dict[str, dict[str, object]]:
    loaded = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert loaded["fixture_kind"] == "TEST_FIXTURE_ONLY"
    cases = loaded["cases"]
    assert isinstance(cases, dict)
    return {name: _mapping(case, name) for name, case in cases.items()}


@pytest.fixture
def catalog() -> dict[int, Hero]:
    return {
        1: Hero(1, "fixture_hero_one"),
        2: Hero(2, "fixture_hero_two"),
        3: Hero(3, "fixture_hero_three"),
        4: Hero(4, "fixture_inactive", is_active=False),
    }


@pytest.fixture
def contract_patch() -> Patch:
    return Patch("fixture-patch", "7.40", date(2026, 9, 1))


def test_complete_manual_fixture_creates_preview_only(
    fixture_cases: dict[str, dict[str, object]], catalog: dict[int, Hero], contract_patch: Patch
) -> None:
    assessment = assess_manual_import_contract(
        fixture_cases["valid_complete"], catalog, contract_patch
    )
    assert assessment.status == "PREVIEW"
    assert assessment.preview is not None
    assert assessment.preview.intended_role is Role.POSITION_4
    assert [pick.hero.hero_id for pick in assessment.preview.allied_picks] == [1]
    assert [pick.hero.hero_id for pick in assessment.preview.enemy_picks] == [2]
    assert {hero.hero_id for hero in assessment.preview.banned_heroes} == {3}


@pytest.mark.parametrize(
    ("case_name", "expected_issue"),
    (
        ("unknown_schema", "schema version"),
        ("missing_root", "draft root"),
        ("unknown_hero", "unknown hero"),
        ("duplicate_hero", "duplicate"),
        ("inactive_hero", "inactive hero"),
        ("cross_side_conflict", "both teams"),
        ("pick_ban_conflict", "picked and banned"),
        ("patch_mismatch", "patch mismatch"),
        ("partial_snapshot", "partial snapshot"),
    ),
)
def test_invalid_contract_fixtures_are_rejected_without_preview(
    case_name: str,
    expected_issue: str,
    fixture_cases: dict[str, dict[str, object]],
    catalog: dict[int, Hero],
    contract_patch: Patch,
) -> None:
    assessment = assess_manual_import_contract(fixture_cases[case_name], catalog, contract_patch)
    assert assessment.status == "REJECTED"
    assert assessment.preview is None
    assert assessment.issue is not None and expected_issue in assessment.issue


def test_unknown_time_requires_explicit_future_confirmation(
    fixture_cases: dict[str, dict[str, object]], catalog: dict[int, Hero], contract_patch: Patch
) -> None:
    assessment = assess_manual_import_contract(
        fixture_cases["unknown_time"], catalog, contract_patch
    )
    assert assessment.status == "NEEDS_CONFIRMATION"
    assert assessment.preview is not None
    assert assessment.issue == "observed_at is unknown"


def test_stale_snapshot_is_rejected_against_last_confirmed_time(
    fixture_cases: dict[str, dict[str, object]], catalog: dict[int, Hero], contract_patch: Patch
) -> None:
    assessment = assess_manual_import_contract(
        fixture_cases["stale_snapshot"],
        catalog,
        contract_patch,
        datetime(2026, 9, 2, tzinfo=UTC),
    )
    assert (assessment.status, assessment.issue, assessment.preview) == (
        "REJECTED",
        "stale snapshot",
        None,
    )


def test_contract_preview_cancellation_and_rejection_do_not_mutate_current_draft(
    fixture_cases: dict[str, dict[str, object]], catalog: dict[int, Hero], contract_patch: Patch
) -> None:
    current_draft = DraftState(
        (HeroPick(catalog[2], TeamSide.ALLY),), (), Role.POSITION_5, contract_patch
    )
    original = current_draft
    preview = assess_manual_import_contract(
        fixture_cases["valid_complete"], catalog, contract_patch
    )
    rejected = assess_manual_import_contract(fixture_cases["unknown_hero"], catalog, contract_patch)

    # Cancellation is deliberately the absence of an apply operation in this contract-only test.
    assert preview.status == "PREVIEW" and preview.preview is not None
    assert rejected.status == "REJECTED" and rejected.preview is None
    assert current_draft is original
    assert current_draft.intended_role is Role.POSITION_5
    assert [pick.hero.hero_id for pick in current_draft.allied_picks] == [2]
