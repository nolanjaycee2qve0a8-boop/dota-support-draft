# DOTA-012 — 团队阵容与分路适配 evidence 研究

状态：研究设计，不实现产品行为。研究日期：2026-08-31。

## 决策摘要

唯一建议：下一步采用**选项 B 的第一阶段**——由用户显式补充队友位置/分路计划，但 DOTA-013 先只显示已知、未知与冲突的阵容上下文，**不进入 Experimental Score，也不新增 provider 请求**。在有真实输入、可验证的 provider schema 和独立的统计语义前，不得把它称为 lane-fit evidence。

这样先解决“系统知道什么”的问题，而不把英雄名称、默认位置或历史统计伪装成当前队友的分路。它也保留了后续以独立任务验证统计能力的空间。

## 1. 当前输入边界

| 项目 | 当前可用事实 | 当前不可用或不能推断的事实 |
| --- | --- | --- |
| 候选角色 | 用户明确选择候选的 `POSITION_4` 或 `POSITION_5`。 | 不能把候选角色延伸为整队五个位置。 |
| Allied / Enemy picks | 手动 UI 保存每个已选英雄的 ID 与阵营，最多各五个。 | 没有每名 ally/enemy 的玩家身份、位置、分路、是否同一路或实际对线搭档。 |
| Bans | 已禁英雄 ID。 | Ban 不提供队伍结构或分路信息。 |
| `DraftState` | `HeroPick` 结构有可选 `player_role`、`lane_relation`，且有可选 `lane_partner`。 | `ManualDraftSession`/主窗口从不填充这些字段；`Role` 仅定义 P4/P5，不能表示 P1–P3；`lane_partner` 当前始终为 `None`。这些字段不是已采集证据。 |
| 候选 shortlist | 基于当前 P4/P5 Meta 与 Personal 的确定性 top-8，只是 pair-enrichment 的请求范围。 | shortlist、表格顺序和搜索选择不能用来推断英雄职责、分路或队友意图。 |
| Hero capabilities | domain 有可选 `HeroCapabilities` 模型。 | 没有全量加载或经验证的数据源；不能据此生成“阵容缺什么”的事实结论。 |

仓库依据：[DraftState / HeroPick](../src/dota_support_draft/domain/models.py)、[manual session](../src/dota_support_draft/draft/session.py)、[pair shortlist](../src/dota_support_draft/draft/pair_evidence.py)。因此，当前唯一可信的草稿语义是“谁已被选到哪一边、用户正在考虑 P4 还是 P5”。不得从英雄名、惯常玩法、候选排名或历史个人数据补齐未知位置。

## 2. 现有 evidence 与不应混淆的概念

| 概念 | 可否由当前实现支持 | 正确语义 |
| --- | --- | --- |
| 团队 composition | 仅能显示已选 ally/enemy ID 与未知 assignment。 | 是整队能力、职责和搭配的描述；不是自动得出的 lane-fit。 |
| Candidate-to-ally synergy | 可以，限 top-8 候选与已选 ally。 | 当前 `laneOutcome(isWith:true)` 的 current-week、候选 P4/P5、可选 rank 范围 pair effect。 |
| Candidate-vs-enemy counter | 可以，限 top-8 候选与已选 enemy。 | 当前 `laneOutcome(isWith:false)` 的同一范围 pair effect。 |
| Lane matchup | 不可以诚实地支持。 | 需要明确“谁与谁同线、各自位置/分路”以及已验证的、同义的统计口径；现有 pair API 名称不等于当前草稿实际对线。 |
| 角色适配 | 仅候选 P4/P5 Meta 已支持。 | 不能把 ally hero 当作已确认 P1–P3/P4/P5，也不能把 OpenDota personal totals 当作当前 role 表现。 |

冻结合同仍有效：STRATZ 数据为 current-week，**不是** patch-isolated；OpenDota Personal 是 all-time、role-unknown；缺失 pair component 为 unavailable/neutral，不重分配权重；Experimental Score 不是胜率预测。详见 [recommendation evidence](RECOMMENDATION_EVIDENCE.md) 与 [STRATZ integration](STRATZ_INTEGRATION.md)。

## 3. 数据可行性与来源

### 已验证、可复用的仓库能力

- STRATZ provider 已验证 `dota.heroStats.stats` 的 P4/P5 current-week Meta，以及 alias-batched `laneOutcome`；后者按候选 P4/P5、rank、`isWith` / `isWith:false` 返回 pair rows。它的当前实现没有用户分路输入，也没有把任何 pair row解释为“本局已确认同线”。
- 冷缓存时，现有 pair refresh 最多为一条 role-Meta、一条 friendly profile、一条 against profile 请求；最多八个候选；250 ms debounce、latest-state-wins、单 active worker 与安全关闭均为冻结合同。DOTA-013 不得扩大此预算。
- OpenDota 现有消费仅包括英雄/patch 常量、公共 player profile 与 `/players/{account_id}/heroes` all-time totals。它不提供当前手动草稿中其他玩家的已确认分路。

### 官方/一手来源

- [STRATZ API 页面](https://stratz.com/api)（访问：2026-08-31）公开链接到 GraphQL API。该页面并未公开可据以新增 lane/role 字段的具体 schema；任何更深的 capability 必须先通过项目的无持久化 schema probe 和人工审查验证，不能猜测字段或含义。
- [OpenDota API documentation](https://docs.opendota.com/)（访问：2026-08-31）是 OpenDota 的官方 API 文档入口。仓库已经以其 player/hero 端点作为 all-time Personal 数据来源；本研究未验证它能为当前手动草稿提供队友实时 assignment。

### 未验证或不可用的能力

- 未验证 STRATZ 是否存在与“显式给定两队完整位置/分路配置”语义一致、且能保持 current-week/rank/P4-P5 口径的统计查询。
- 未验证可用于 production 的全量 hero capability taxonomy；现有 `HeroCapabilities` 为空模型，不是证据数据集。
- 没有可靠来源可从当前 hero IDs 自动得出队友的实时位置、分路计划或是否会与候选同线。

这些未验证项在未完成独立 schema/data-quality 任务前必须显示为 unavailable，而不是零值或经验性猜测。

## 4. 三个互斥产品选项

| 选项 | 用户摩擦 | 数据诚实性 | 实现/测试复杂度 | 请求与评分影响 | 结论 |
| --- | --- | --- | --- | --- | --- |
| A. 只做团队 composition 解释，不进入评分 | 最低；不新增输入。 | 只能安全展示 hero ID、已知/未知 assignment；若声称能力覆盖则缺少已加载 taxonomy。 | 低到中；仍需定义不误导的空/未知状态。 | 可做零请求、零分数影响。 | 可作为以后低风险展示，但信息价值受当前 capability 数据缺失限制。 |
| B. 显式队友 role/lane 输入后再评估 lane-fit | 中；用户必须确认未知 assignment。 | 最高；输入来源明确，可逐项显示 unknown。 | 中；需扩展 manual adapter、校验、reset 与 context stale contract。 | 第一阶段可零请求、零分数；后续 provider capability 必须单独预算和验证。 | **推荐，且先做解释阶段。** |
| C. 自动推断队友 lane/role | 最低表面摩擦。 | 最低；会把常见英雄玩法、排名或历史数据冒充当前意图。 | 高；需模型、置信度、纠错、stale 与争议处理。 | 很容易扩大请求和隐式改变评分。 | 不推荐；无强的一手、可审计实时来源时不应启动。 |

## 5. 推荐的产品语义

推荐先展示、后研究评分。DOTA-013 应让用户为已选 ally 标记“已知位置/分路计划”或保留 Unknown，并显示：

- 当前候选 P4/P5；
- 已确认 assignment 的数量、未知的 ally，以及可见的冲突；
- 清楚的声明：这是用户输入的 draft context，不是自动侦测、不是实际对线确认、不是 statistical lane-fit；
- 现有 Counter/Synergy 继续按自己的 current-week pair 语义显示，不能因新增输入而改写其意义。

在没有已验证数据能力前，DOTA-013 不应生成“适合/不适合某条线”、数值 lane-fit、Experimental Score 分量或新的网络请求。

## 6. DOTA-013 可执行实施提案

### 范围

1. 新增仅手动的 ally assignment context：每名 ally 的可选队伍位置（P1–P5 / Unknown）与可选分路计划（Safe / Off / Mid / Roam / Unknown）。未知是默认且一等状态。
2. 保持 `Role` 专用于候选 P4/P5；新增独立的 `TeamPosition`、`PlannedLane` 类型，不将 P1–P3 塞入现有 `Role`，也不复用语义不完整的 `LaneRelation`。
3. 将 assignment 作为 `HeroPick`/DraftState 的明确、不可变上下文，或新增 composition context 值对象；ManualDraftSession 负责保存、remove/reset 清空，并只在用户提交时写入。
4. 增加只读 composition context 面板，显示每个 assignment 的 `manual` 来源、Unknown 与验证错误；不显示效果值或推荐分数变化。

### 冻结语义与非目标

- 不新增 provider、HTTP、polling、缓存 TTL、schema probe、评分权重或 Experimental Score component。
- 不改变 current-week / all-time role-unknown / pair-effect / top-8 / 最多三条冷请求合同。
- 不自动从 hero 名称、常见角色、表格排名或 Personal history 推断 assignment。
- 不持久化当前对局草稿；不读取游戏进程、屏幕、私密玩家数据，不自动输入或控制游戏。

### UI、异步与请求边界

- 输入仅在 GUI thread 修改本地 session；每次修改可更新现有 pair semantic context，但 DOTA-013 不得使 pair service 请求更多数据。
- composition panel 自己零网络；搜索与候选表选择仍零 pair-network。
- 若 assignment 将来被纳入任何异步请求，其完整 assignment context 必须先成为 generation + semantic stale-rejection 的一部分；本 DOTA-013 阶段不做该接线。
- 既有 QThread active/pending/retirement/deferred-close 状态机不改动。

### 测试矩阵

| 类别 | 必须覆盖 |
| --- | --- |
| Domain | Unknown 默认、位置/分路枚举、同一 ally 的更新、remove/reset 清理、不可为 enemy 或已移除 hero 保留 assignment。 |
| UI | stable object names；保存的 assignment/Unknown/冲突文字；P4/P5 切换不伪造队友角色；reset 清空；无输入时明确空状态。 |
| 网络 | 输入、搜索、候选选择、composition panel 均为零 provider/pair 调用；既有 manual refresh 预算不变。 |
| Async/lifecycle | rapid draft assignment 与 active pair worker 时不产生额外 worker；existing latest-wins、shutdown、retired-QThread 回归保留。 |
| Windows | 添加 ally、设置/清除 assignment、切换 P4/P5、reset、关闭正在进行的 pair refresh；确认文本不残留且窗口安全退出。 |

### 进入后续 lane-fit 研究的门槛

只有当以下全部成立，才可另开任务研究新 evidence：用户 assignment 已显式可用；官方/一手 schema 经 probe 证明字段和样本含义；current-week、rank、候选角色与 lane 定义一致；请求预算、缓存键、provenance、partial failure、score gate 与 Windows QThread 回归都有书面设计和 fake 测试。

## 7. 安全与公平边界

本研究及提案继续是手动草稿辅助：不读取 Dota 进程内存、不注入、不进行输入自动化或实时游戏控制；不收集私密数据、不要求或记录 Token。所有外部统计若未来启用，仍须经 provider 正规边界、provenance、缓存和可用性披露处理。
