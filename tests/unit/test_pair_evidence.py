from datetime import UTC, datetime

import pytest

from dota_support_draft.domain import (
    DataProvenance,
    DraftState,
    EvidenceSet,
    Hero,
    HeroPick,
    Patch,
    PersonalHeroStat,
    Role,
    RoleMetaEvidence,
    TeamSide,
)
from dota_support_draft.draft.pair_evidence import (
    PAIR_SHORTLIST_SIZE,
    DraftPairEvidenceService,
    make_pair_input,
    select_pair_shortlist,
)
from dota_support_draft.providers.errors import ProviderTransportError


def _provenance() -> DataProvenance:
    return DataProvenance("fixture", datetime.now(UTC), "fixture", None, data_kind="TEST/FIXTURE")


def _base(heroes: tuple[Hero, ...], patch: Patch, role: Role = Role.POSITION_4) -> EvidenceSet:
    return EvidenceSet(
        role_meta=tuple(
            RoleMetaEvidence(hero, role, patch, 100, 60, 0.6, _provenance()) for hero in heroes
        )
    )


class PairProvider:
    def __init__(self, counter_error: bool = False, synergy_error: bool = False) -> None:
        self.counter_error, self.synergy_error = counter_error, synergy_error
        self.counter_calls = self.synergy_calls = 0

    def get_counter_evidence(self, request):
        self.counter_calls += 1
        if self.counter_error:
            raise ProviderTransportError("counter offline")
        return ()

    def get_synergy_evidence(self, request):
        self.synergy_calls += 1
        if self.synergy_error:
            raise ProviderTransportError("synergy offline")
        return ()


def test_shortlist_is_deterministic_bounded_and_excludes_picks_and_bans() -> None:
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 13))
    patch = Patch("p", "7.40", datetime.now(UTC))
    draft = DraftState(
        (HeroPick(heroes[0], TeamSide.ALLY),),
        (),
        Role.POSITION_4,
        patch,
        banned_heroes=frozenset({heroes[1]}),
    )
    candidates = tuple(hero for hero in heroes if hero not in {heroes[0], heroes[1]})
    shortlist = select_pair_shortlist(draft, candidates, _base(heroes, patch))
    assert len(shortlist) == PAIR_SHORTLIST_SIZE
    assert heroes[0] not in shortlist and heroes[1] not in shortlist
    assert shortlist == select_pair_shortlist(draft, candidates, _base(heroes, patch))


def test_personal_familiarity_cannot_bypass_public_shortlist_gate() -> None:
    hero = Hero(1, "hero")
    patch = Patch("p", "7.40", datetime.now(UTC))
    personal = PersonalHeroStat(hero, 100, 80, 0.8, None, _provenance())
    assert (
        select_pair_shortlist(
            DraftState((), (), Role.POSITION_4, patch), (hero,), EvidenceSet(), (personal,)
        )
        == ()
    )


def test_context_is_semantic_and_ordered() -> None:
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 5))
    patch = Patch("p", "7.40", datetime.now(UTC))
    draft = DraftState(
        (HeroPick(heroes[1], TeamSide.ALLY), HeroPick(heroes[0], TeamSide.ALLY)),
        (HeroPick(heroes[2], TeamSide.ENEMY),),
        Role.POSITION_4,
        patch,
    )
    input_data = make_pair_input(1, draft, (heroes[3],), _base(heroes, patch), "ancient")
    assert input_data.context.ally_ids == (1, 2)
    assert input_data.context.rank_scope == "ANCIENT"


@pytest.mark.parametrize(
    ("allies", "enemies", "expected"),
    [(True, False, (0, 1)), (False, True, (1, 0)), (True, True, (1, 1)), (False, False, (0, 0))],
)
def test_service_requests_only_required_polarities(allies, enemies, expected) -> None:
    candidate, ally, enemy = Hero(1, "candidate"), Hero(2, "ally"), Hero(3, "enemy")
    patch = Patch("p", "7.40", datetime.now(UTC))
    draft = DraftState(
        (HeroPick(ally, TeamSide.ALLY),) if allies else (),
        (HeroPick(enemy, TeamSide.ENEMY),) if enemies else (),
        Role.POSITION_4,
        patch,
    )
    provider = PairProvider()
    result = DraftPairEvidenceService(provider).refresh(
        make_pair_input(1, draft, (candidate,), _base((candidate,), patch), None)
    )
    assert (provider.counter_calls, provider.synergy_calls) == expected
    assert not result.counter_error and not result.synergy_error


def test_partial_failure_preserves_successful_pair_component() -> None:
    candidate, ally, enemy = Hero(1, "candidate"), Hero(2, "ally"), Hero(3, "enemy")
    patch = Patch("p", "7.40", datetime.now(UTC))
    draft = DraftState(
        (HeroPick(ally, TeamSide.ALLY),),
        (HeroPick(enemy, TeamSide.ENEMY),),
        Role.POSITION_4,
        patch,
    )
    result = DraftPairEvidenceService(PairProvider(counter_error=True)).refresh(
        make_pair_input(1, draft, (candidate,), _base((candidate,), patch), None)
    )
    assert result.counter_error == "counter offline" and result.synergy_error is None
