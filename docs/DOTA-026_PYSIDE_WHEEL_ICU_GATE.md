# DOTA-026 — PySide6 Windows wheel / ICU runtime 准入研究

**访问与实验日期：2026-09-01。** 本文是 DOTA-024 失败后的只读、隔离研究记录；不修改应用、provider、评分、DOTA-024 build script 或 lock，也不把生成的 artifact 视为可交付产物。

## 结论

**当前 PySide6 6.11.2 以及候选 6.10.3 都不满足本项目“self-contained Windows onedir runtime”的准入条件。** 两个官方 Windows x64 wheel 的 `PySide6/Qt6Core.dll` 都静态导入 `icuuc.dll`，但 wheel 内没有任何 `icu*.dll`。在本机，Windows System32 提供了 `icuuc.dll` 72；这能使 isolated venv 的 QtCore import 表面成功，却不是 lock 管理的、可发布的 runtime 来源。

因此 DOTA-024 继续阻断；不能把本机 System32、Codex runtime/Poppler、Qt SDK/IDE 或手工复制的 ICU DLL 当作解决方案。DOTA-025 的 PyInstaller bootloader trace 也证明：即使 bootloader 和 PySide runtime hook 已执行，冻结 EXE 仍在加载 `PySide6.QtCore` 时失败。

## 方法与边界

- Build host：Windows x64、CPython 3.14.6 x64。
- 每个候选安装至新的临时 venv；没有复用项目 `.venv` 或 DOTA-024 build venv。
- 只从 PyPI 官方 Windows wheel 安装 `PySide6` 元包及其精确 `PySide6_Essentials`、`PySide6_Addons`、`shiboken6` 依赖。PySide6 官方 PyPI 说明该元包是 Essentials 与 Addons 的别名，且 PyPI 是推荐的 wheel 来源。
- QtCore import 运行在 `-I` 子进程，移除 `PYTHONPATH`、`PYTHONHOME`、Qt plugin/QML 变量与 Token；PATH 仅保留 Windows 系统目录。没有 provider 调用、真实 Token、应用启动或游戏交互。
- 用 `pefile` 读取 `Qt6Core.dll` 的 import table，并枚举 wheel 内的 `icu*.dll`。这不是运行时 schema probe，也没有拷贝或注入任何 DLL。

## 候选矩阵

| Wheel 组合 | Wheel 标签 | `Qt6Core.dll` ICU import | wheel 内 `icu*.dll` | 受限 PATH 的 `import PySide6.QtCore` | 准入 |
| --- | --- | --- | --- | --- | --- |
| 6.11.2（当前 DOTA-024 lock） | `cp310-abi3-win_amd64` | `icuuc.dll` | 0 | 成功，`QtCore.qVersion()` = `6.11.2` | **拒绝** |
| 6.10.3（候选） | `cp39-abi3-win_amd64` | `icuuc.dll` | 0 | 成功，`QtCore.qVersion()` = `6.10.3` | **拒绝** |

两个 import 都是 15 秒内退出、exit 0；这只说明当前 Windows host 能提供缺失依赖，**不**说明 wheel self-contained。

## 原始证据

1. 两个 wheel 的 PE import table 都包含 `icuuc.dll`，同时 wheel 内递归枚举 `icu*.dll` 为零。
2. 本机 `C:\Windows\System32\icuuc.dll` 存在，FileVersion 为 `72.1.0.4`；但 System32 中不存在 `icudt78.dll`。它不是 lock、wheel 或产品 artifact 的受控输入。
3. DOTA-025 的 PyInstaller diagnostics 显示 `PySide6/Qt6Core.dll` 导入 `icuuc.dll`，并曾从本机 Codex runtime 的 Poppler 目录收集一个 `icuuc.dll`。该文件也不在 lock 中，不能作为发布来源。
4. 同一 diagnostics 中，PyInstaller bootloader 已设置 `_internal` DLL directory，并已运行 `pyi_rth_pyside6.py`，但 no-Token onedir EXE 仍以 `ImportError: DLL load failed while importing QtCore` 退出。

## 一手来源

- [PySide6 官方 PyPI 项目说明](https://pypi.org/project/PySide6/)：说明 PySide6 为 Qt for Python 官方模块，并由 Essentials/Addons wheels 组成，推荐通过 PyPI 获取 wheels。
- [Qt for Python deployment overview](https://doc.qt.io/qtforpython-6/deployment/index.html)：将冻结/部署视为需要使应用在客户端找到全部资源的过程，并列出 PyInstaller 等工具。
- [Qt for Python Windows Python libraries](https://doc.qt.io/qtforpython-6/developer/pythonlibraries.html)：说明 Windows 不具备 Unix 式 delayed loading，CPython libraries 必须显式链接。
- [PyInstaller hooks documentation](https://pyinstaller.org/en/stable/hooks.html)：定义 hooks 的 collection 机制；hook 成功执行不等于 wheel 所需原生依赖已由受控输入提供。
- [PyInstaller usage](https://pyinstaller.org/en/stable/usage.html)：定义 onedir、collection 与 bootloader debug 选项。

## DOTA-027 准入计划（不在本任务实施）

在新的产品/packaging implementation task 中，只有同时满足下列 gate 才能提议更新 DOTA-024 lock 或 script：

1. 找到由 PySide6/Qt 官方发行且可审查的 Windows x64 wheel/version 组合；其 wheel 自己必须提供与 `Qt6Core.dll` import table 匹配的 ICU runtime，或提供官方、可锁定且明确许可的 redistributable 机制。
2. 在临时 venv 中验证 wheel 文件布局、PE imports 与实际 QtCore import；验收不得从 System32、IDE、Poppler、Qt SDK 或父进程 PATH 获得 ICU。
3. 只有通过前两项后，才重建带 hashes 的 Windows build lock，记录精确 CPython/PyInstaller/PySide6 版本，并审查 PyInstaller hook collection 来源。
4. 再运行真正 `-Recreate` onedir build；检查 bundle 的每个非系统原生 DLL 都来自 lock 管理的来源，且没有 `.env`、Token、SQLite/cache 或用户数据。
5. 在无 Token、临时可写 `DOTA_SUPPORT_DATA_DIR` 的独立进程中验证主窗口出现、正常关闭、无 QtCore/platform-plugin 错误；随后才讨论安装器、签名或发布。

在这些 gate 全部通过前，DOTA-024 artifact 不能进入人工 Windows 验证或后续合并/发布流程。
