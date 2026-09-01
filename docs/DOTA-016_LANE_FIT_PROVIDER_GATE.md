# DOTA-016 — 显式分路输入后的 lane-fit provider 准入门槛

状态：研究设计；不启用 provider、UI、缓存、评分或运行时 schema probe。

访问日期：2026-08-31。

## 结论

当前仓库没有足以把任何统计称为“当前同线 / lane-fit”的已验证 provider 契约。唯一建议是继续只显示诚实的 manual draft context；在 DOTA-017 的全部准入门槛通过前，不显示 lane-fit 数值、不把它写入推荐解释、更不得影响 Experimental Score。

现有 STRATZ 能力可继续称为 current-week、P4/P5、rank-scoped 的 pair Counter/Synergy；它不是已验证的实际分路匹配统计。`laneOutcome` 这一名称不能替代已证明的样本分路语义。

## 三个不能混淆的概念

| 概念 | 输入/来源 | 可以诚实地说什么 | 不能说什么 |
| --- | --- | --- | --- |
| 用户显式 team position / planned lane context | 用户手动填写的 ally position 与计划分路；`Unknown` 必须是一等状态 | “这是 manual context / 计划，不是自动检测。” | 不是 provider 样本、不是实际对线、不是胜率或 lane-fit。 |
| 当前 top-8 pair `laneOutcome` Counter/Synergy | 现有 STRATZ `laneOutcome` profile、候选 P4/P5、rank、current-week、ally/enemy hero IDs | “候选与该英雄的 current-week 条件 pair evidence”；`isWith:true` 现映射为 Synergy，`false` 映射为 Counter。 | 不证明两个英雄同线；不表达用户指定的队友位置、计划分路或对线双方。 |
| 未来 statistical lane-fit / matchup evidence | 需要 provider 明确返回且可审计的“候选角色 + 自/敌双方真实分路/位置 + matchup”样本 | 只有通过本文件 gate 后，才可称为特定 manual lane context 的统计 evidence。 | 在字段、样本与关系语义未验证时，不得由 hero 名称、pair 排序或计划分路推断。 |

当前 `DraftState` 只包含 ally/enemy hero IDs、candidate P4/P5 role、patch、ban 等。`HeroPick.player_role` 仍只接受项目中的 P4/P5 `Role`，`LaneRelation` 也不足以表达完整 P1–P5 与 Mid/Safe/Off 的人工分配；`ManualDraftSession` 不采集这类 assignment。因此“显式输入”是未来的独立 domain/UI 边界，不是已经存在的数据。

## 当前仓库中已验证的 pair 边界

`StratzProvider._lane_query` 目前向仓库已验证的 operation 传递 `heroId`、`isWith`、P4/P5 `positionIds`、可选 `bracketBasicIds`，并读取 `heroId1`、`heroId2`、`week`、`position`、`matchCount`、`matchWinCount` 等行字段。它按 top-8 candidate alias batch 请求，局部以 DraftState 的 ally/enemy IDs 过滤；role-meta 是同一 current week、同一 P4/P5/rank baseline。

这只能支持已实现的 pair 语义：

- `isWith:true`：candidate 与 allied hero 的 Synergy pair；
- `isWith:false`：candidate 与 enemy hero 的 Counter pair；
- raw `matchWinCount / matchCount` 仅是条件 match win rate，现有 effect 才会对照同 scope 的 candidate role-meta baseline；
- 零样本、week/rank/baseline 不匹配和单一 polarity 失败都必须是 unavailable/partial，不能写成 0。

该 operation 的现有请求没有 manual lane、ally position、enemy lane 或“本局实际同线的双方”变量。即使 provider 名称含 `laneOutcome`，本项目没有足够证据把筛出的 pair row 改称 lane matchup。

## 一手公开资料与外部不确定性

| 来源 | 已支持的事实 | 对 DOTA-016 的限制 |
| --- | --- | --- |
| [STRATZ Welcome](https://stratz.com/welcome)（官方，访问 2026-08-31） | STRATZ 说明 API 已转为 GraphQL，并列举 hero positions、laning outcomes、synergies 和 counters。 | 页面不定义 `laneOutcome` 的参数、返回字段、样本单位、`isWith` 语义或 lane pairing。 |
| [STRATZ GraphQL Explorer](https://api.stratz.com/graphiql)（官方，访问 2026-08-31） | 官方站点链接到 GraphQL Explorer。 | Explorer 是动态/认证后的 schema 探索入口；本任务没有携带 Token、没有执行请求，也没有把其 schema 当作已验证证据。 |

截至该访问日期，未发现可公开静态引用的一手文档来证明下表中 lane-fit 所需字段。它们都标为 **未验证**；仓库既有 live contract 也不能自动升级这些 claim。

## 真正 lane-fit claim 的字段与语义清单

| 要声明的事实 | 必须获得的 provider schema/样本证据 | 现状 |
| --- | --- | --- |
| candidate 的 P4/P5 lane-fit | candidate hero ID、明确 P4/P5 position filter/返回值、sample count、win/lane outcome 定义、current-week/时间窗口 | P4/P5 current-week role filter 已用于 pair；“lane-fit”样本含义未验证。 |
| manual ally assignment 对应的同线协作 | ally hero ID、ally 的真实 position 与 lane、candidate 的真实 position 与 lane、同队关系，且样本明确要求同 lane | **未验证**；`isWith` 只能证明现有 pair operation 的 with-polarity，不证明 same-lane。 |
| manual enemy assignment 对应的 lane matchup | enemy hero ID、candidate/enemy 的实际 lane、相对关系（同 lane/opposed lane）、side/matchup 定义 | **未验证**；`isWith:false` 不是“当前对线双方”证据。 |
| 样本可比较性 | `matchCount`、胜/负或 lane-outcome numerator、draw/stomp 的语义、去重单位、week、position、rank 过滤实际生效 | 当前代码读取计数；统计单位及 lane-specific numerator 的官方定义 **未验证**。 |
| current-week/rank 作用域 | opaque week ID、P4/P5、basic rank bucket 或明确无 rank filter，以及是否所有 lane 字段同 scope | current-week/rank 与 role-meta 对齐已实现；新 lane 字段是否同 scope **未验证**。 |
| provenance 与降级 | operation name/version、retrieval time、provider endpoint、sample count、scope、manual assignment fingerprint；每个 component 独立 partial/error | 这是项目必需设计；新 operation 字段仍 **未验证**。 |

不得把 OpenDota personal totals（all-time、role unknown）补成 lane-fit，也不得把 STRATZ current-week 说成 patch-isolated。

## DOTA-017 不可绕过的准入 gate

以下项目必须全部通过，才可开始一个独立的实现任务；任一项失败或未验证时，UI 只能展示 manual context。

1. **Schema 与语义证据**：由有授权的本地开发环境，使用最小、非敏感的官方 GraphQL schema/documentation 证据确认 exact query root、字段名、输入 enum、`isWith/isAgainst` 或替代关系、真实 lane/position 字段、样本单位及缺失/零值行为。将已审查的字段合同转写为 fake transport/schema fixtures；不得提交 Token、原始 payload 或 schema dump。
2. **统计 claim fixture**：为 same-team same-lane、opposed-lane、不同 lane、Unknown assignment、无样本、跨 week、rank mismatch、malformed row 与每个 component partial failure 建立离线 fixture。normalizer 必须拒绝含混 row，而不是猜测 lane。
3. **请求预算与缓存**：在操作可 batch 的证据出现后，冻结冷缓存最大 transport 数；若不能对 top-8 shortlist 和 normalized manual assignment 做有界 batch，则不准实施。cache key 至少包含 operation/version、candidate P4/P5、rank scope、shortlist IDs、relation polarity/target、以及 canonicalized manual assignment fingerprint；不含 Token。TTL、cache-hit 重过滤与 cold/warm budget 都要以 fake transport 测试锁定。
4. **语义 context 与 stale rejection**：assignment 进入一个不可变、排序规范化的 lane-fit context，至少覆盖 ally hero ID、manual position、planned lane、Unknown/冲突状态、candidate role、rank、shortlist。它必须加入 worker generation + context 双重 stale-rejection；assignment 变更不能复用旧结果。现有 pair context 不能被隐式假定为包含这些字段。
5. **评分关闭**：先只显示带 provenance 的 explanatory evidence。只有 provider 样本、关系语义、baseline/effect、coverage 与安全审查全部完成后，才可另行授权讨论 score；没有该授权时权重、公式与 Experimental Score 不变。
6. **Qt/Windows 生命周期**：沿用一 active worker + 一 latest pending、250 ms debounce、无 GUI-thread network、cooperative deferred close 与 retired worker cleanup。为 assignment rapid change、reset、role switch、partial/error、close during active work、新 context stale result 和无 QThread 累积增加实际 Qt runtime 回归。
7. **产品文案 gate**：全通过前不得出现 “lane-fit”、“actual lane matchup” 数值或推荐暗示；只可显示 “manual draft context / not auto-detected / not statistical lane-fit”。

## 互斥方向与建议

| 选项 | 范围 | 数据诚实性/风险 |
| --- | --- | --- |
| A. 仅 manual context | 采集/显示 ally position 与 planned lane，Unknown 与冲突可见；不请求统计数据。 | 最高；不将计划伪装为事实。 |
| B. schema-verified explanatory lane evidence | 在 gate 1–4 通过后，新增独立、partial-aware lane explanation，不入评分。 | 可审计，但需要明确 provider 与预算证据。 |
| C. lane evidence 进入 Experimental Score | 只有 B 长期验证、effect/baseline 已定义且另获评分授权后讨论。 | 当前不可选；风险最高。 |

**唯一建议：A。** 官方公开资料不足以核验真正 lane-fit 的 schema 和样本语义，因此下一步应停在 manual context；不要以现有 pair `laneOutcome` 近似或自动推断来填补证据缺口。

## 非目标与安全边界

本研究不读取 Dota 进程、屏幕或私密数据；不自动输入或控制游戏；不请求、记录或打印 Token；不运行真实 HTTP/schema probe；不修改 provider 查询、评分、缓存、UI 或测试语义。
