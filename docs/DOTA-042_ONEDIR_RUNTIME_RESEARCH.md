# DOTA-042 — Windows onedir 打包运行时兼容性研究与准入 gate

**访问日期：2026-09-07。** 本文仅记录 DOTA-024 失败后的证据、可审查路线和后续实施准入条件。它不运行 build、不生成 EXE、不修改 lock、build script、PATH、DLL、依赖或应用行为。

## 结论

**DOTA-024 的 Windows onedir runtime 仍然阻断，且尚未确认单一根因。** 后续工作不得以手工复制 DLL、修改全局/进程 PATH、使用 Token、或把本机 Qt SDK、IDE、Poppler/Codex runtime、System32 内容当作发布依赖来绕过。

现有最强的工程证据是：DOTA-024 的 locked `PySide6 6.11.2` no-token onedir 程序在导入 `PySide6.QtCore` 时失败；DOTA-026 隔离检查发现其 `Qt6Core.dll` 导入 `icuuc.dll`，但 wheel 内没有 `icu*.dll`。这使“原生依赖闭包不受 lock 管理”成为需要验证的方向，**不是**已经由官方资料确认的唯一根因。

## 已知仓库与失败事实

| 事实 | 状态 | 可追溯依据 |
| --- | --- | --- |
| DOTA-024 曾锁定 Windows x64 / CPython 3.14.6 / PyInstaller 6.22.2 / PySide6 6.11.2，使用 `--onedir --collect-all PySide6`。 | 仓库历史事实 | historical commit `9dcdc26`（不在当前 `main`）的 `requirements/windows-build.lock` 与 `scripts/build_windows_onedir.ps1`。 |
| 失败不涉及 Token：no-token onedir 启动导入 `PySide6.QtCore` 时出现 `ImportError: DLL load failed while importing QtCore: 找不到指定的程序。`。 | 仓库诊断事实 | [DOTA-026](DOTA-026_PYSIDE_WHEEL_ICU_GATE.md) 的 DOTA-025 diagnostic record。 |
| 当时没有以 Token、PATH 注入、补充 DLL 或绕过失败继续验证。 | 仓库诊断事实 | [DOTA-026](DOTA-026_PYSIDE_WHEEL_ICU_GATE.md)。 |
| 6.11.2 和 6.10.3 官方 Windows wheels 的本地 PE/wheel 检查都观察到 `Qt6Core.dll` 依赖 `icuuc.dll`，wheel 内无 `icu*.dll`。 | 工程观测，非官方根因声明 | [DOTA-026](DOTA-026_PYSIDE_WHEEL_ICU_GATE.md)。 |
| 当前 `main` 未包含 DOTA-024 build script 或 lock；当前的旧 `packaging/dota_support_draft.spec` 仍只是 contract，非已验证 recipe。 | 仓库事实 | [DOTA-023](DOTA-023_WINDOWS_PACKAGING_GATE.md)、[spec](../packaging/dota_support_draft.spec)。 |

Windows 的 “DLL load failed” 只说明导入扩展模块所需的某个 DLL 未能加载；它并不标识缺失 DLL 的名称。CPython 官方说明，`*.pyd` 的 Python import 搜索与其 DLL 依赖的 Windows DLL 搜索是不同问题。因此，不能从该错误文本推断“只是 Qt plugin 缺失”、也不能仅凭 `QtCore.dll` 文件存在推断运行时闭包完整。

## 官方一手资料与结论标签

| 一手来源（直接链接） | 官方确认 | 本研究使用方式 |
| --- | --- | --- |
| [Python 3.14 Windows FAQ](https://docs.python.org/3/faq/windows.html) | `*.pyd` 本身的 import 搜索路径不同于其 DLL 依赖的 Windows DLL 搜索。 | **官方确认**：解释为何错误文本不能定位依赖；不确认本项目缺的是哪一个 DLL。 |
| [Python 3.14 Windows DLL API](https://docs.python.org/3/library/os.html#os.add_dll_directory) | `os.add_dll_directory()` 会影响 extension-module dependency resolution；3.8 起该行为有明确的 Windows 规则。 | **官方确认**：DLL 搜索受显式路径影响；**工程推断**：以 PATH/DLL-directory 调整通过测试会掩盖 artifact 缺依赖，故不能作为本项目发布修复。 |
| [PyInstaller 6.22.2 changelog](https://pyinstaller.org/en/latest/CHANGES.html) | PyInstaller 自 6.15 起加入 Python 3.14 支持。 | **官方确认**：当前 3.14/PyInstaller 路线不是因 Python 主版本完全不受支持而自动失效；不确认 PySide6 runtime 闭包。 |
| [PyInstaller operating modes](https://pyinstaller.org/en/stable/operating-mode.html) | Windows artifact 必须在 Windows 上构建；bundle 针对构建 OS/Python 环境。 | **官方确认**：后续每条路线都要在受控 Windows x64 环境真实验证。 |
| [PyInstaller usage](https://pyinstaller.org/en/stable/usage.html) | `--onedir` 与 `--collect-all` 的语义由工具定义。 | **官方确认**：collection 选项存在；不保证上游 wheel 未提供的原生依赖会被凭空收集。 |
| [Qt for Python package details](https://doc.qt.io/qtforpython-6/package_details.html) | `PySide6` 由 `PySide6_Essentials`、`PySide6_Addons`、`shiboken6` 组成，Essentials/Addons 包含 Qt binaries。 | **官方确认**：lock 必须锁定这组同版本 wheel；不确认它们对任意 Windows native dependency 都 self-contained。 |
| [Qt for Python PyInstaller guidance](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html) | PyInstaller 可能意外使用 system PySide6/Shiboken6；Qt plugin/resource 部署需要额外关注。 | **官方确认**：build interpreter/site-packages provenance 与 plugin 验收不可省略；在 `QtCore` import 前的 DLL 失败不能直接归因为 plugin。 |
| [Qt for Python 6.8 release notes](https://doc.qt.io/qtforpython-6.8/release_notes/pyside6_release_notes.html) | 6.8.6 明确写有 Python 3.14 support。 | **官方确认**：至少存在一条官方声明过 Python 3.14 支持的 PySide6 release line；不确认该 line 解决 ICU/QtCore failure。 |
| [Qt for Windows deployment](https://doc.qt.io/qt-6/windows-deployment.html) | `windeployqt` 可收集 Qt libraries/plugins/runtime dependencies；额外第三方 libraries 仍需另行处理，Windows QPA 需要 `platforms/qwindows.dll`。 | **官方确认**：Qt native deployment 包含 runtime 与 plugin 两个独立验收层；**未知**：该 C++/SDK tool 是否可直接、合法且可锁定地修复本项目 PySide wheel 依赖。 |
| [Qt for Python pyside6-deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html) | 官方部署工具封装 Nuitka，首次运行会安装 deployment dependencies；Windows 高效 plugin collection 依赖 MSVC `dumpbin`。 | **官方确认**：这是独立工具链，不是仅修改 PyInstaller collection 的同义操作。 |

除非上表明确标为“官方确认”，其他判断均为**工程推断**或**未知**。链接均在 2026-09-07 访问。

## 互斥后续路线

### A. 保持 CPython 3.14.6 / PySide6 6.11.2，只重做受控 runtime 审计

- **证据：** PyInstaller 官方已支持 Python 3.14；DOTA-024 的组合、lock 和失败记录可复现审查。
- **是否足以解释 DLL 故障：** 否。DOTA-026 的 ICU observation 表明要先证明依赖来源闭包，但不构成官方根因归属。
- **真实 Windows 验证：** 新建隔离 venv，验证 lock 的 wheel 文件布局、PE imports、restricted-environment `import PySide6.QtCore`；只在每个非系统 DLL 有 lock 管理来源后，才生成新的 onedir，并验证 no-token launch、Qt platform plugin、正常关闭和可写 data-root。
- **风险：** 当前组合仍可能依赖构建机/Windows 组件；重做同一 build 若不隔离 DLL 来源可能得到假阳性。
- **停止条件：** 找不到每个非系统 native dependency 的官方、可锁定来源；或只靠 PATH/System32/IDE/手工 copied DLL 才能导入。

### B. 采用有官方 Python 兼容声明的 CPython/PySide6 组合

- **证据：** PySide6 6.8.6 release notes 明确支持 Python 3.14；PyInstaller changelog 亦声明 3.14 support。
- **是否足以解释 DLL 故障：** 否。Python ABI compatibility 与 wheel/Qt native dependency closure 是不同主张。即使选择官方支持组合，也必须重新证明 wheel 的实际 Windows DLL 来源。
- **真实 Windows 验证：** 先以专门授权下载精确 official wheels，在临时隔离环境审计每个候选；通过后才生成新的 hash lock、再做 A 所列 onedir acceptance。
- **风险：** 更换 PySide6 可能影响 Qt behavior、binary layout、hooks、plugins、许可/redistributable 边界；不得把“supports Python 3.14”误称为“portable onedir runtime verified”。
- **停止条件：** 官方 source 无法提供可审查/可锁定的 native dependency mechanism，或候选仍只能借用宿主 DLL。

### C. 只调整 PyInstaller/Qt 收集配置

- **证据：** PyInstaller 提供 `--collect-all`；Qt for Python 文档要求关注 plugin/resource collection，Qt Windows docs 要求 `qwindows.dll` 等 QPA plugin 位于正确位置。
- **是否足以解释 DLL 故障：** 不足。已知故障发生在 `PySide6.QtCore` import，早于 Qt GUI platform-plugin 初始化；plugin collection 可以是后续验收项，不能替代 native dependency closure 证据。
- **真实 Windows 验证：** 仅在 A 或 B 已证明 wheel/runtime closure 后，比较最小 collection 与明确 Qt collection，在独立进程验证 import、主窗口、platform plugin、关闭；记录 bundle provenance。
- **风险：** `--collect-all` 可能掩盖来源混入或扩大 artifact；SDK `windeployqt`/`pyside6-deploy` 不是“只改 PyInstaller 配置”，引入它们必须走新工具链评估。
- **停止条件：** collection 仍需要外部 DLL，或需改 PATH/复制未知 DLL 才能启动。

## 唯一建议

**推荐路线 A 的“runtime closure 审计”作为下一步，而不是立即重建或换版本。** 这是唯一能先区分“官方可锁定的 wheel/runtime 输入是否完整”与“PyInstaller collection/plugin 配置问题”的低假设行动。它必须由新的、明确授权的 remediation task 执行；本研究不做任何下载、安装、PE 重新检查、build 或 EXE 运行。

如果 A 未通过，才以路线 B 的候选矩阵寻找有官方兼容声明且依赖来源可审计的组合。C 只能在 native closure 已证明后作为 Qt plugin 收集优化，不能作为独立修复。

## 后续 remediation task 的不可跳过准入合同

开始任何下载、安装、依赖/lock/script 修改或生成 EXE 前，必须取得单独授权，并先批准下列合同：

1. **输入与来源：** 固定 Windows x64 CPython、PyInstaller、PySide6 / Essentials / Addons / shiboken6 的精确版本、hash 与官方下载来源；记录 build interpreter 和 package paths，但不记录 Token、用户 account ID、payload 或 registry export。
2. **native closure：** 用隔离环境审计 wheel/bundle 的 import table 与实际 `QtCore` import。每个非系统 native DLL 必须能追溯到 lock 管理或明确官方许可的 redistributable；System32、PATH、Qt SDK/IDE、Poppler/Codex runtime、手工 copied DLL 都不能作为满足条件的来源。
3. **build boundary：** 只有 closure 通过后才可生成 Windows onedir artifact。不得把 `.env`、Token、QSettings、SQLite、cache、data-root 或用户文件加入 artifact；不得生成 installer、签名或 release archive。
4. **Windows acceptance：** 在不使用 Token、没有 build venv/Qt SDK 辅助的独立 Windows 用户会话中，验证 EXE 启动到 failure-safe/manual UI、主窗口可见、正常关闭、无 `QtCore`/QPA platform-plugin failure。另用临时用户可写 `DOTA_SUPPORT_DATA_DIR` 验证写入不落入安装目录。
5. **regression：** 保留现有 Qt lifecycle、network-zero UI、Token local-only 与 data semantics 回归；执行 `pytest -q`、`ruff check .`、`ruff format --check .`、`mypy .`、`git diff --check`。
6. **停止与报告：** 任一 closure、no-token launch、plugin、close 或 writable-data-root 验收失败即停止，报告版本与非敏感错误；不得以 DLL/PATH workaround 或真实网络/Token 绕过。

在这些 gate 全部通过之前，Windows onedir、installer、签名和发布仍未获准。
