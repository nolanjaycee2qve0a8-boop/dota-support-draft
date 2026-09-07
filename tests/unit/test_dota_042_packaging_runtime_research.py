from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
RESEARCH = PROJECT_ROOT / "docs" / "DOTA-042_ONEDIR_RUNTIME_RESEARCH.md"


def test_dota_042_research_preserves_the_packaging_stop_contract() -> None:
    """The research keeps build/remediation behind explicit native-runtime evidence gates."""
    content = RESEARCH.read_text(encoding="utf-8")

    for required_text in (
        "ImportError: DLL load failed while importing QtCore",
        "官方确认",
        "工程推断",
        "未知",
        "保持 CPython 3.14.6 / PySide6 6.11.2",
        "采用有官方 Python 兼容声明的 CPython/PySide6 组合",
        "只调整 PyInstaller/Qt 收集配置",
        "不使用 Token",
        "正常关闭",
        "DOTA_SUPPORT_DATA_DIR",
        "不得以 DLL/PATH workaround",
    ):
        assert required_text in content

    for official_url in (
        "https://docs.python.org/",
        "https://pyinstaller.org/",
        "https://doc.qt.io/",
    ):
        assert official_url in content
