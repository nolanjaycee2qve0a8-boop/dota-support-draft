# PyInstaller contract only; not proof of a published executable.
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(["../src/dota_support_draft/__main__.py"], datas=collect_data_files("PySide6"))
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="DotaSupportDraft", console=False)
