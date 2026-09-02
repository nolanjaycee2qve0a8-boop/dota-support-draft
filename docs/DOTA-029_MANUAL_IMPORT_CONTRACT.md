# DOTA-029 — Manual Draft Import Contract Fixtures

状态：DOTA-029 的 docs/test-only contract；DOTA-033 已实现受限的用户粘贴 preview/explicit-confirmation UI。
日期：2026-09-02。

## 目的与非目标

本文件定义人工 preview/confirmation 可审查的离线 document grammar，及其脱敏 test fixtures。DOTA-033 仅允许用户主动粘贴 JSON、先 preview、再显式 Confirm；它不是 Dota GSI、真实游戏输入、自动检测、文件读取、watcher 或自动导入功能。

此 contract 的唯一来源标识是 `MANUAL_IMPORT`：用户将来主动粘贴或选择的本地文档仍必须经过 preview 和明确确认。contract 不授权生产 parser、文件选择/read/watcher、HTTP listener、GSI、第三方文件 adapter、DraftState replacement 或自动应用。

## v1 document grammar

JSON document 必须有下列根字段；未知 schema version 一律拒绝。

```json
{
  "schema_version": "dota-support-draft/manual-import/v1",
  "provenance": {
    "kind": "MANUAL_IMPORT",
    "observed_at": "2026-09-02T00:00:00Z"
  },
  "draft": {
    "complete": true,
    "patch_version": "7.40",
    "intended_role": "POSITION_4",
    "allied_hero_ids": [1],
    "enemy_hero_ids": [2],
    "banned_hero_ids": [3]
  }
}
```

| 字段 | 规则 |
| --- | --- |
| `schema_version` | 必须精确为 `dota-support-draft/manual-import/v1`。 |
| `provenance.kind` | 必须精确为 `MANUAL_IMPORT`；不接受 `GSI`、第三方 source 或自动检测名称。 |
| `provenance.observed_at` | 时区明确的 ISO-8601 timestamp，或字面量 `unknown`。unknown 只能产生带警告的 future confirmation preview，不能假称为新鲜状态。 |
| `draft.complete` | 必须是 `true`。任何 partial/incremental snapshot 都拒绝，不与现有草稿拼接。 |
| `patch_version` | 必须精确映射到当前已加载的本地 `Patch`，不猜测或跨 patch 替换。 |
| `intended_role` | 仅 `POSITION_4` 或 `POSITION_5`。它是候选角色，不能声明整队其他位置。 |
| hero ID arrays | 仅整数、每项唯一；ally/enemy 各最多 5；所有 ID 必须唯一映射到 active local catalog hero。不得跨阵营、不得 pick-ban 冲突。 |

该 grammar 没有 token、cookie、玩家身份、文件路径、屏幕/进程数据或 raw provider payload 字段。

## Preview 与 no-mutation contract

contract-level validation 只产生下列结果，不执行任何 commit：

- `PREVIEW`：完整、已知时间且通过本地 catalog/patch/DraftState invariants 的候选草稿；仍需用户确认。
- `NEEDS_CONFIRMATION`：结构完整但 `observed_at` 为 `unknown`；future UI 必须显式显示未知时间并要求人工决定。
- `REJECTED`：schema、完整性、时间、hero、patch 或 DraftState 不变量错误；当前手动草稿保持原样。

若 future caller 有已确认的观察时间，timestamp 小于或等于该时间的 document 是 stale，必须拒绝。取消 preview 与 rejection 都不能改变当前 session；本 contract 不定义 apply operation。

## Test fixtures 与覆盖

[fixture](../tests/fixtures/manual_import_contract_cases.json) 仅供测试读取，根标识为 `TEST_FIXTURE_ONLY`，hero ID 均为合成值。测试模块中的 mapper 仅复用 domain `DraftState` 的构造校验来证明 contract，不能被 production import。

覆盖：valid complete snapshot、unknown schema version、missing root、unknown/duplicate/inactive hero、跨 side 冲突、pick-ban 冲突、patch mismatch、partial snapshot、stale/unknown time、取消及 rejection 的 no-mutation 语义。

## 冻结边界

- 不改 Experimental Score、evidence 语义、provider、cache、pair shortlist/request budget 或 QThread lifecycle。
- 不运行真实 HTTP、GSI、provider、游戏、第三方文件、进程或屏幕读取；不使用或记录 Token。
- Dota GSI 与第三方只读文件继续受 [DOTA-028 admission gate](DOTA-028_DRAFTSTATE_ADAPTER_GATE.md) 阻止，直到一手 schema 和独立授权齐备。
