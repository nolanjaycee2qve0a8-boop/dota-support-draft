# DOTA-028 — 合法 DraftState 输入适配边界研究

状态：研究设计；不实现产品行为。研究日期：2026-09-02。

## 结论

当前唯一已实现且可信的输入适配器是 `ManualDraftSession`。下一步不应实现 Dota GSI、第三方文件监听或自动采集：Dota GSI 的公开一手 draft payload schema、事件时序和 hero/patch 映射合同尚未得到足够验证。

唯一推荐的后续工作是 **docs/fixture-only** 合同任务：定义版本化、显式标为 `MANUAL` 的本地 DraftState 导入预览格式和离线失败 fixture。它不读取游戏目录、不监听文件、不启动 HTTP server，也不替换当前草稿。只有在独立的官方 Dota GSI 合同与人工确认 UX 都通过 gate 后，才可讨论真实 GSI adapter。

## 当前代码事实

| 边界 | 当前事实 | 不能据此推断 |
| --- | --- | --- |
| `ManualDraftSession` | 维护本地 ally/enemy/ban、候选 P4/P5 和手动 ally composition，再构造不可变 `DraftState`。 | 它不是外部输入协议，也不带输入时间、来源或完整性证明。 |
| `DraftState` | 有 Allied/Enemy `HeroPick`、ban、候选 intended role（只允许 P4/P5）和 `Patch`；拒绝跨阵营重复英雄及 enemy composition assignment。 | 没有输入-source provenance、payload schema version、观测时间、序列号或外部 player/lane 真相。 |
| `DraftStateCollector` | 仅是返回 `DraftState` 的抽象类；没有 GSI、文件或网络实现。 | 抽象类不验证任何来源被批准，也不授权自动替换 UI session。 |
| Pair refresh | 只消费已授权的本地草稿语义，保留 250 ms debounce、one-active/latest-pending、generation + context stale rejection 与协作关闭。 | 它不是采集器，不可被 adapter 当作轮询或后台输入入口。 |

代码依据：[domain models](../src/dota_support_draft/domain/models.py)、[manual session](../src/dota_support_draft/draft/session.py)、[collector abstraction](../src/dota_support_draft/draft/collector.py)、[pair evidence](../src/dota_support_draft/draft/pair_evidence.py)。

## 来源审计：确认与未确认的界线

本任务只把一手来源用于判断“已证实”与“未证实”，不把第三方库、逆向工程、截图或经验性 config 当作协议规范。

| 来源 | 可确认的最小事实 | 不能据此确认的事实 |
| --- | --- | --- |
| [ValveSoftware/Dota-2 issue #1023](https://github.com/ValveSoftware/Dota-2/issues/1023)（Valve 官方仓库，访问 2026-09-02） | Valve 的 Dota 2 官方问题跟踪器包含关于 Game State Integration 的用户报告。 | issue body 是报告者提供的配置，不是 Valve 发布的 schema；不能证明目录、字段、`draft` payload、token 行为、触发频率或 Windows 支持合同。 |
| [ValveSoftware/Dota-2 issue #2826](https://github.com/ValveSoftware/Dota-2/issues/2826)（Valve 官方仓库，访问 2026-09-02） | 官方问题跟踪器仍有 GSI 无数据报告，说明交付可靠性不能被假定。 | 该报告没有维护者给出的 payload/schema 说明；其字段样例不能升级为本项目生产契约。 |
| [Valve Developer Community 的 CS:GO GSI 页面](https://developer.valvesoftware.com/wiki/Counter-Strike:_Global_Offensive_Game_State_Integration)（Valve 社区站点，访问 2026-09-02） | Valve 生态存在其他游戏的 GSI 文档。 | CS:GO 的协议、字段和语义**不能**外推到 Dota 2。该来源不用于定义 Dota adapter。 |

截至该日期，未找到能静态、公开且由 Valve 明确维护的 Dota 2 GSI draft schema、完整 payload sample、版本兼容规则或 hero/patch identity 合同。因此以下内容均为 **未验证**：GSI 是否提供可用的 draft phase/pick/ban 事件；任何 `draft` 字段的精确名字和类型；是否可获得双方完整 picks/bans；事件是否初始完整、增量、可重放或有序；本机 loopback POST 的安全与生命周期语义；以及游戏版本变更时的兼容性。它们不得实现、不得在 UI 中暗示可用。

## Provider-neutral adapter boundary（设计，不实现）

任何未来适配器都必须位于外部输入与 domain 之间，不能让原始 payload、文件路径或 transport DTO 进入 scoring、provider 或 Qt presentation。

```text
source-specific DTO / local document
  → validate + normalize against local catalog/patch
  → DraftInputAssessment
  → explicit human confirmation
  → one atomic DraftState replacement
```

| 概念 | 必需内容 | 规则 |
| --- | --- | --- |
| `DraftInputSource` | `MANUAL_IMPORT`、`DOTA_GSI`、`THIRD_PARTY_READONLY_FILE` 或 future source ID | source ID 是 provenance，不代表 source 已获准。未知 source 直接拒绝。 |
| source DTO | source-specific schema version、字段值、可选 observed time / sequence | DTO 只在 adapter 内；原始 payload 不进入 domain、日志或持久化。 |
| `DraftInputProvenance` | source ID、received/observed time（或明确 `unknown`）、schema/version、完整性状态、非敏感 source reference | 与 statistics 的 `DataProvenance` 分离；draft input 不是统计 evidence。 |
| `DraftInputAssessment` | `accepted preview`、`needs confirmation` 或 `rejected`，以及结构化可恢复问题 | 只在所有字段通过时才含完整 candidate `DraftState`；禁止 partial state。 |
| commit operation | 用户明确确认后的 session replacement | 一次性替换完整 DraftState 对应的 session；失败、取消或 stale input 必须保持原 session 不变。 |

### 验证与标准化顺序

1. **边界/版本**：先识别受批准的 source 与显式 schema version。未登记版本、缺失 root 或未知枚举拒绝，不作 best-effort 猜测。
2. **时间与完整性**：保留 source 报告的 observed time/sequence；无可靠时间时标为 `unknown`。过期、倒退或不足以构成完整草稿的 snapshot 只可提示/拒绝，不能覆盖较新的用户确认状态。
3. **本地映射**：每个外部 hero identity 必须能唯一映射到当前本地 active hero catalog；patch identity 必须映射到当前已加载 `Patch` 或显示 mismatch。未知、歧义、inactive hero 或未证实 alias 一律不自动替换。
4. **Draft invariants**：ally/enemy 各最多五个；禁止同英雄跨 sides、pick/ban 冲突、重复项、非法 intended role；enemy 不得带 manual ally composition assignment。必须复用 `DraftState` invariants，而非复制一套较宽松规则。
5. **人工确认**：预览必须展示 source、观测时间/unknown、patch mapping、picks、bans、所有警告和“这不是自动检测的真相”。用户可确认、取消或回到手动修正。
6. **原子提交与恢复**：仅确认后的完整 assessment 才可替换；任一 validation error 保持当前 draft、显示可恢复原因，并允许重新选择/重新导入。不得混合半新半旧 picks。

未来实现如需通知现有 pair-refresh 控制器，只能在一次成功的、用户确认的 semantic mutation 后使用既有路径；不得新建轮询、并行 worker 或跳过 generation/context stale rejection。本研究没有授权该接线。

## 输入源决策

| 来源 | 可行性现状 | 接受条件 | 当前结论 |
| --- | --- | --- | --- |
| 手动导入 | 可在将来设计成用户主动选择的本地、版本化文档；无需游戏或网络。 | 严格 schema、catalog/patch mapping、预览和明确确认；`MANUAL_IMPORT` provenance；无自动文件 watcher。 | 唯一可安全研究的方向，但本任务不实现。 |
| Dota GSI | 存在 GSI 用户报告，但没有足够官方 Dota draft schema / 时序合同。 | 先取得官方一手字段与版本证据、离线 fixture、loopback安全模型、完整性和确认 UX；另开任务审查。 | **拒绝实现。** |
| 第三方只读文件 | 文件格式、来源完整性、更新时序和授权范围均未知。 | 每一文件格式须有其发布者的一手 schema、用户显式选择、snapshot-only read、完整性/时间语义、fixture 与确认。 | **拒绝自动读取或监听。** |

“只读”并不自动等于可信：它不能替代 schema、source provenance、user confirmation 或原子替换。也不能把本机路径、文件修改时间或英雄名称当作 game-authoritative state。

## 不可绕过的准入 gate

开始任何 adapter runtime 实现前，以下全部必须通过：

1. **一手契约**：目标 source 的发布者提供可访问、版本化、可审查的 schema 与字段语义；对 Dota GSI 还必须包括 draft/pick/ban、初始/增量、时间或序列、payload 认证与版本兼容性。没有证据即不实现。
2. **离线 fixtures**：覆盖有效完整 snapshot、缺失 root、未知字段/version、未知/duplicate hero、跨 side 冲突、pick/ban 冲突、inactive hero、patch mismatch、out-of-order/stale、partial update、取消、拒绝和恢复；绝不含用户数据、token 或真实 payload dump。
3. **映射审查**：hero 与 patch 映射只引用本地受审查 catalog；不能按显示名称模糊匹配，不能猜 patch。
4. **确认与可见性**：UI 在提交前显示 provenance、时间/unknown、完整性和全部 diff；默认不自动应用，任何失败无副作用。
5. **生命周期与预算**：不增加 provider request、网络 polling、cache key、评分权重或 GUI-thread network。若成功替换将触发现有 pair 流程，必须以 Qt runtime 测试证明 one-active/latest-pending、stale rejection、reset 与 deferred close 不回归。
6. **安全审查**：local endpoint/file access 的最小权限、loopback binding、非敏感日志和 token exclusion 都需单独批准。禁止 game memory、injection、input automation、screen-recognition bypass、process inspection 和自动 gameplay control。
7. **产品文案**：通过前只称为“manual draft import proposal”或“unavailable adapter”；不得称 real-time、auto-detected、authoritative 或 live draft。

## 建议的下一安全任务：DOTA-029（提案，未批准）

**名称：Manual Draft Import Contract Fixtures（docs/test-only）**

- 只新增一个版本化 `MANUAL_IMPORT` document grammar、redacted fixture 与 parser/validation contract tests；不新增 GUI 入口、生产 parser、file I/O、watcher、HTTP listener 或 DraftState replacement。
- 明确 input 必须由用户主动粘贴/选择，preview/confirmation 仍是未来需求；测试只验证 contract examples，不能声称应用已可导入草稿。
- 复用现有 `DraftState` invariants，测试所有 reject/no-mutation cases；不改 scoring、providers、pair shortlists、cache、QThread、token 或 runtime dependencies。
- Dota GSI 和第三方文件保持 out of scope，直到上方 gate 1–7 全部满足并获得单独授权。

这项提案的价值是先固定“合法输入是什么”和“坏输入绝不改草稿”，而不杜撰一个未证实的游戏采集协议。

## 安全与公平边界

- 不读 Dota 进程内存、不注入、不自动输入、不控制游戏，不用 screen recognition 绕过未发布的 input contract。
- 不启动网络轮询、真实 GSI endpoint、provider 请求或 schema probe。
- 不持久化 Token、Cookie、Steam 凭据、原始 payload、个人数据或 source file contents；诊断只记录结构化、非敏感错误类别。
- 不改变 Experimental Score、当前 current-week/all-time evidence 语义、pair request budget、cache 或 QThread lifecycle。
