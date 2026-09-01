# DOTA-023 — Windows 打包可行性与发布准入研究

**访问日期：2026-09-01。** 本文只定义可审查的本地 Windows 打包准入与 DOTA-024 最小实施计划；不创建产物、不安装打包工具、不发布、不引入安装器。

## 结论

**当前 `main` 不可安全声称“可复现发布构建”，也不应直接执行现有 spec。** 原因是：

- 项目只有 `PySide6>=6.7` 下限，没有锁定 Python、PySide6 或 PyInstaller；当前项目 venv 虽观察到 Python 3.14.6 / PySide6 6.11.2，但这是机器状态，不是仓库构建契约。
- PyInstaller 不在项目 venv 中；本研究未安装它。
- `packaging/dota_support_draft.spec` 是 DOTA-001 的 contract：只调用 `collect_data_files("PySide6")`，没有明确 onedir `COLLECT` 阶段、平台 plugin 收集或经验证产物。
- 默认数据目录 `.dota-support-draft/` 是当前工作目录的相对路径。若未来安装到受保护目录，SQLite/cache 写入位置必须先有明确的用户可写策略。

**DOTA-024 可在满足下列不可跳过 gate 后，安全实施“仅本地、可复现、`onedir` 的验证构建命令/脚本”。** 它不是安装器、签名或公开 release。首选 PyInstaller 的 `onedir`，因为 PyInstaller 官方将它作为默认一目录 bundle，且当前仓库已有 PyInstaller contract；`onefile` 不在 DOTA-024 范围内。

## 1. 当前仓库事实

| 项目事实 | 依据 | 对打包的含义 |
| --- | --- | --- |
| `src/` layout，入口是 `dota_support_draft.app:main`，`__main__.py` 调用该入口。 | [pyproject.toml](../pyproject.toml)、[app.py](../src/dota_support_draft/app.py)、[__main__.py](../src/dota_support_draft/__main__.py) | 打包命令必须明确入口和 `--paths .\\src`；不能依赖 editable install 才能 import。 |
| 运行时唯一声明依赖是 `PySide6>=6.7`。 | [pyproject.toml](../pyproject.toml) | 下限不是可复现 build lock；需要固定可审查的 Windows x64 Python/PySide6/PyInstaller 组合。 |
| 现有 spec 是旧 contract 而非已验证 onedir recipe。 | [dota_support_draft.spec](../packaging/dota_support_draft.spec) | DOTA-024 不得把它当发布证据；应使用经 gate 验证的命令/新 spec，或明确替换它。 |
| GUI 从环境读取 `STRATZ_API_TOKEN`，而 PowerShell launcher 使用隐藏输入、只设置当前 Process 环境变量，并在 `finally` 清除。 | [settings.py](../src/dota_support_draft/config/settings.py)、[start_dota_support_draft.ps1](../scripts/start_dota_support_draft.ps1) | Token 绝不可进入 EXE、spec、构建日志、产物、注册表或打包脚本参数。现有 launcher 定位 `.venv\\Scripts\\python.exe`，不能直接作为 release launcher。 |
| 公开 Steam32/OpenDota account ID 由 `QSettings("Dota Support Draft Assistant", "Dota Support Draft Assistant")` 保存。 | [player_preferences.py](../src/dota_support_draft/config/player_preferences.py) | 打包 EXE 应保持相同 organization/application 名称，才会读取同一 current-user 偏好；这不是 Token 存储。 |
| 默认 SQLite/cache 根来自 `DOTA_SUPPORT_DATA_DIR`，否则是相对 `.dota-support-draft`。 | [settings.py](../src/dota_support_draft/config/settings.py) | 发布前必须验证用户可写 data root；不能假设 EXE 所在目录可写。 |

## 2. 一手资料与工具选择

| 候选 | 一手资料结论 | DOTA-024 决定 |
| --- | --- | --- |
| PyInstaller | 官方 usage 文档定义 `--onedir` 为默认一目录 bundle，并提供 `--collect-all` 收集包的 submodules、data 和 binaries；其 operating-mode 文档说明产物受构建 OS 和 Python 版本约束，Windows 必须在 Windows 上构建。 | **推荐作最小 onedir 验证工具。** 明确收集 PySide6，并用干净 Windows 用户环境实测，而非假设 plugin 自动完整。 |
| `pyside6-deploy` | Qt for Python 将其作为官方部署工具，但它封装 Nuitka；Windows 高效 plugin 收集需要 MSVC 的 `dumpbin`，首次运行还会安装 deployment 依赖。 | 不作为 DOTA-024 的最小路径：当前没有已锁定 Nuitka/dumpbin 环境。可在独立评估后再比较。 |
| `onefile` | PyInstaller 支持 onefile；Qt for Python 的 PyInstaller 指引仍强调 Qt 6/plugin 部署 caveat。 | 排除：诊断和 plugin 验收更难，不符合先做可审查 onedir 的目标。 |

官方来源（均于上述日期访问）：

- [PyInstaller usage: onedir, collect-all, output options](https://pyinstaller.org/en/stable/usage.html)
- [PyInstaller operating modes: build OS/Python specificity](https://pyinstaller.org/en/stable/operating-mode.html)
- [Qt for Python deployment overview](https://doc.qt.io/qtforpython-6/deployment/index.html)
- [Qt for Python & PyInstaller caveats](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)
- [Qt for Python `pyside6-deploy`](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html)
- [Qt `QSettings` Windows NativeFormat behavior](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSettings.html)

## 3. DOTA-024 依赖和可复现环境 gate

在写或运行 build script 前，DOTA-024 必须提交并审查下列事实；本研究不替它们选择或安装版本。

1. **固定 build 平台。** 一套干净 Windows x64 venv、明确 CPython major/minor/patch，且 build 和验收使用同一 Windows 架构。PyInstaller 不是跨平台交叉编译器。
2. **提交消费型 lock。** 新的 Windows build lock 必须固定 PyInstaller 的精确版本、`PySide6` 的精确版本、`PySide6_Essentials`、`PySide6_Addons`、`shiboken6` 及所有 PyInstaller transitive dependencies，并附 hash。lock 的生成工具也应固定；消费端只能按 lock 从新 venv 安装。
3. **固定项目安装。** lock 安装完成后，用受控方式安装此仓库代码，避免从全局 site-packages 解析 PySide6。Qt 官方也警告 PyInstaller 可能意外使用系统 PySide6/Shiboken6；DOTA-024 要记录 build interpreter、`python -m pip show` 的路径和版本，但不得记录 secret。
4. **不可包含的输入。** `.env`、`.dota-support-draft/`、SQLite、cache、QSettings 导出、Token、provider payload、用户 account ID 都不能作为 build input 或 `--add-data` 输入。

当前观察到的 PySide6 6.11.2 只可作为候选起点，不能替代 lock。PyInstaller 版本在 DOTA-024 选定后才可写入 lock；本任务不猜测未安装工具的版本兼容性。

## 4. PySide6/Qt plugin gate

Qt for Python wheel 自带 Qt binaries，但 Qt 官方的 PyInstaller 指引仍要求关注 Qt plugins。DOTA-024 的保守起点应是 `--collect-all PySide6`，其语义由 PyInstaller 官方定义为收集该包的 submodules、data 和 binaries。不得仅复用现有 `collect_data_files("PySide6")` contract。

在锁定环境中，DOTA-024 可实现（但本任务未执行）类似以下命令的 script，所有路径必须从 script 自身解析：

```powershell
cd 'C:\Users\22908\Documents\ChatGPT\野生dota+\dota-support-draft'
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name DotaSupportDraft --paths .\src --collect-all PySide6 --distpath .\artifacts\windows --workpath .\artifacts\build --specpath .\artifacts\spec .\src\dota_support_draft\__main__.py
```

该命令只是 DOTA-024 的候选 recipe，不是本任务执行过的命令。DOTA-024 应将 `artifacts/` 视为 generated output 并加入 `.gitignore`；需长期审查的 spec 应放在受版本控制的 `packaging/`，不能把临时生成 spec 当成产品契约。

最小 plugin 验收必须在非 build venv、干净 Windows 用户会话中启动 onedir 的 `DotaSupportDraft.exe`，确认没有 platform-plugin 错误、主窗口可见、正常关闭。不能以 build 机器恰好安装的 Qt/IDE/venv 来证明成功。

## 5. 安全与本地数据边界

- **Token：** 打包 EXE 继续只读其启动进程的 `STRATZ_API_TOKEN`；没有 Token 时允许现有 manual/bootstrap failure-safe 行为。DOTA-024 不引入持久化、不将 Token 编译进资源、不在命令行或日志回显它。若未来提供打包版启动器，必须重新实现为启动 EXE 的隐藏输入、进程级环境变量和 finally 清理，而不能引用 `.venv`。
- **QSettings：** 使用当前 organization/application 字符串、x64 build，并在不同 Windows 用户下验证 public account ID 的保存/clear。Qt 文档说明 Windows `NativeFormat` 使用 registry，且 32/64 bit 视图可能不同；DOTA-024 不能导入或复制用户注册表内容。
- **SQLite/cache：** 使用临时、用户可写的 `DOTA_SUPPORT_DATA_DIR` 做 build acceptance。发布到受保护安装目录前，必须另行决定并实现默认用户可写 data-root 策略；这不在 DOTA-024 的 onedir command scope 内。
- **网络与游戏安全：** 任何 package acceptance 都不读取游戏进程、不自动输入、不开真实 STRATZ/OpenDota probe，也不需要真实 Token。离线启动可验证 bundle/plugin 和 no-token failure-safe 路径。

## 6. DOTA-024 最小实施与验收计划

### 允许范围

1. 新增固定 Windows build lock 和一个从脚本路径解析项目根的 onedir build script；脚本明确拒绝缺失 lock/venv/打包器。
2. 使用锁定 venv 在 Windows 生成 `artifacts/windows/DotaSupportDraft/`；不创建 MSI、安装器、签名或 release archive。
3. 新增无需 Token/HTTP 的静态或 smoke 验证：入口存在、输出目录/EXE 存在、没有把 `.env`/数据目录当作 bundle input，并复跑已有 Qt regression。
4. 在干净 Windows 用户环境做手工验收，记录成功/失败和版本矩阵，不提交 generated output。

### 不可跳过的验收 checklist

| Gate | 通过条件 |
| --- | --- |
| Lock | 新 venv 按已审查 hash lock 安装；解释器、PySide6、PyInstaller 版本与 lock 一致。 |
| Bundle | onedir 输出存在 `DotaSupportDraft.exe`；没有 source workspace、`.venv`、`.env`、SQLite/cache 或用户偏好被复制入 artifact。 |
| Qt | 在没有 build venv/Qt SDK 帮助的 Windows 用户环境启动主窗口，无 missing platform plugin 错误。 |
| No-token safety | 不提供 Token 仍能启动到现有 failure-safe/manual UI；不打印或请求 secret。 |
| Local account | 使用非敏感测试 Steam32 ID 保存、退出、重启、clear；验证 QSettings 仅为当前用户且不写 workspace。 |
| Writable data | 用临时用户可写 `DOTA_SUPPORT_DATA_DIR` 启动/关闭；不得向安装目录写 SQLite/cache。 |
| Regression | `pytest`、`ruff check .`、`ruff format --check .`、`mypy .`、`git diff --check` 全部通过。 |
| Release boundary | 仅在以上证据完整后，才单独决策 code signing、installer、versioned archive 和分发；DOTA-024 本身不得越过该边界。 |

## 7. DOTA-024 准入结论

**准入为“有条件批准”。** DOTA-024 可以实施受 lock、Windows x64 构建环境、`--collect-all PySide6`、干净用户 profile 启动验证和可写 data-root 验收约束的本地 onedir script。它必须先建立这些可复现输入；不能运行旧 spec、不能声称发布可用、不能创建安装器，也不能把 Token/用户数据加入 artifact。

若 lock 无法在新 Windows venv 重现、Qt platform plugin 不能在干净环境加载、或 data-root 仍尝试写入受保护安装目录，则停止在该证据并报告，不以手工拷贝 Qt DLL、全局 PATH 或真实 Token 绕过。
