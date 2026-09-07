from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
AUDIT = PROJECT_ROOT / "docs" / "DOTA-047_NATIVE_RUNTIME_CLOSURE_AUDIT.md"


def test_dota_047_audit_preserves_the_exact_wheel_closure_stop_condition() -> None:
    """The incomplete audit must not be misread as packaging or DLL-remediation approval."""
    content = AUDIT.read_text(encoding="utf-8")

    for required_text in (
        "CPython 3.14.6",
        "PySide6 6.11.2",
        "PyInstaller 6.22.2",
        "insufficient closure evidence",
        "New build remediation is not approved",
        "No space left on device",
        "No retry was made",
        "QtCore.pyd",
        "Qt6Core.dll",
        "icuuc.dll",
        "no-workaround isolated `import PySide6.QtCore`",
        "System32",
        "add_dll_directory",
    ):
        assert required_text in content

    for official_url in (
        "https://www.python.org/downloads/release/python-3146/",
        "https://pypi.org/pypi/PySide6/6.11.2/json",
        "https://pypi.org/pypi/PyInstaller/6.22.2/json",
    ):
        assert official_url in content
