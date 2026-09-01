# Roadmap

DOTA-001 through DOTA-018 are closed. DOTA-010 synchronized the post-merge management state; DOTA-011 added local public-account configuration; DOTA-012 and DOTA-016 closed research/gate documents; DOTA-013 added manual ally position/planned-lane context; DOTA-014 added local draft-action guardrails; DOTA-015 added typed display sorting; and DOTA-018 closed the resizable draft-layout improvement. DOTA-017 was a local pre-merge integration validation, not a separately released product milestone.

DOTA-012–016 were merged together in PR #12 at `8532745`; DOTA-018 was merged in PR #13 at `14f3c3a`.

Possible future directions include:

- team-composition and lane-fit evidence（先参阅 [DOTA-012 研究](DOTA-012_COMPOSITION_LANE_FIT_RESEARCH.md)与 [DOTA-016 provider gate](DOTA-016_LANE_FIT_PROVIDER_GATE.md)；真正 statistical lane-fit 仍未获准实施）;
- further recommendation explanation improvements beyond the completed selected-candidate panel and local layout work;
- legal adapters that produce `DraftState`;
- Windows packaging.

These are directions for later review, not commitments or approved implementation work.

DOTA-016 records the provider-evidence gate for any future lane-fit work. It does not approve implementation: until that gate is met, any team position or planned lane information must remain manual context rather than statistical lane-fit or recommendation input. No roadmap item above authorizes new provider calls, real-time collection, score changes, game automation, or Token persistence.
