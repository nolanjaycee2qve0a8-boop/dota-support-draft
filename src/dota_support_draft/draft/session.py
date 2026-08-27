from __future__ import annotations

from dota_support_draft.domain import DraftState, Hero, HeroPick, Patch, Role, TeamSide


class ManualDraftError(ValueError):
    pass


class ManualDraftSession:
    """Mutable UI adapter that explicitly converts to canonical immutable DraftState."""

    def __init__(
        self, heroes: tuple[Hero, ...], patch: Patch, role: Role = Role.POSITION_4
    ) -> None:
        self.heroes, self.patch, self.role = (
            tuple(sorted(heroes, key=lambda hero: hero.hero_id)),
            patch,
            role,
        )
        self.allies: list[Hero] = []
        self.enemies: list[Hero] = []
        self.bans: set[Hero] = set()

    def set_role(self, role: Role) -> None:
        if role not in (Role.POSITION_4, Role.POSITION_5):
            raise ManualDraftError("Only Position 4 and Position 5 are supported")
        self.role = role

    def _check_available(self, hero: Hero) -> None:
        if hero not in self.heroes or not hero.is_active:
            raise ManualDraftError("Hero is not an active catalog candidate")
        if hero in self.allies or hero in self.enemies:
            raise ManualDraftError("Hero is already picked")
        if hero in self.bans:
            raise ManualDraftError("Hero is banned")

    def add_ally(self, hero: Hero) -> None:
        if len(self.allies) >= 5:
            raise ManualDraftError("Maximum five allied picks")
        self._check_available(hero)
        self.allies.append(hero)

    def add_enemy(self, hero: Hero) -> None:
        if len(self.enemies) >= 5:
            raise ManualDraftError("Maximum five enemy picks")
        self._check_available(hero)
        self.enemies.append(hero)

    def ban(self, hero: Hero) -> None:
        if hero in self.allies or hero in self.enemies:
            raise ManualDraftError("Picked hero cannot be banned")
        if hero not in self.heroes:
            raise ManualDraftError("Unknown hero")
        self.bans.add(hero)

    def unban(self, hero: Hero) -> None:
        self.bans.discard(hero)

    def remove_ally(self, hero: Hero) -> None:
        self.allies.remove(hero)

    def remove_enemy(self, hero: Hero) -> None:
        self.enemies.remove(hero)

    def clear(self) -> None:
        self.allies.clear()
        self.enemies.clear()
        self.bans.clear()

    @property
    def candidates(self) -> tuple[Hero, ...]:
        excluded = {*self.allies, *self.enemies, *self.bans}
        return tuple(hero for hero in self.heroes if hero.is_active and hero not in excluded)

    def to_draft_state(self) -> DraftState:
        return DraftState(
            tuple(HeroPick(hero, TeamSide.ALLY) for hero in self.allies),
            tuple(HeroPick(hero, TeamSide.ENEMY) for hero in self.enemies),
            self.role,
            self.patch,
            banned_heroes=frozenset(self.bans),
        )
