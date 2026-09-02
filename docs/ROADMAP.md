# Roadmap

DOTA-001 through DOTA-022 are closed. DOTA-019 synchronized post-merge state; DOTA-020 added local candidate-filter clarity; DOTA-021 added an offscreen Qt workflow regression; and DOTA-022 added structured candidate-evidence readability. DOTA-017 was a local pre-merge integration validation, not a separately released product milestone.

DOTA-012–016 were merged together in PR #12 at `8532745`; DOTA-018 was merged in PR #13 at `14f3c3a`.

Possible future directions include:

- team-composition and lane-fit evidence（先参阅 [DOTA-012 研究](DOTA-012_COMPOSITION_LANE_FIT_RESEARCH.md)与 [DOTA-016 provider gate](DOTA-016_LANE_FIT_PROVIDER_GATE.md)；真正 statistical lane-fit 仍未获准实施）;
- further recommendation explanation improvements beyond the completed selected-candidate panel and local layout work;
- legal adapters that produce `DraftState`（DOTA-033 已批准且仅实现 user-pasted `MANUAL_IMPORT/v1` 的 preview/explicit confirmation；仍须参阅 [DOTA-028 adapter gate](DOTA-028_DRAFTSTATE_ADAPTER_GATE.md) 与 [DOTA-029 manual-import contract](DOTA-029_MANUAL_IMPORT_CONTRACT.md)：Dota GSI、第三方文件、watcher、listener 和任何自动 runtime adapter 均未获批准）;
- Windows packaging（先参阅 [DOTA-023 Windows packaging gate](DOTA-023_WINDOWS_PACKAGING_GATE.md) 与 [DOTA-026 PySide6/ICU gate](DOTA-026_PYSIDE_WHEEL_ICU_GATE.md)；当前 wheel/ICU 准入仍阻断，本地 onedir、安装器、签名或发布均未获批准）。

These are directions for later review, not commitments or approved implementation work.

DOTA-016 records the provider-evidence gate for any future lane-fit work. It does not approve implementation: until that gate is met, any team position or planned lane information must remain manual context rather than statistical lane-fit or recommendation input. No roadmap item above authorizes new provider calls, real-time collection, score changes, game automation, or Token persistence.
