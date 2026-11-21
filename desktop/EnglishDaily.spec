import os
from PyInstaller.utils.hooks import collect_submodules

datas = [
    ("static", "static"),
    ("bank", "bank"),
    ("config.yaml", "."),
    ("sources.yaml", "."),
    ("requirements.txt", "."),
]
if os.path.isdir("site"):
    datas.append(("site", "site"))

hiddenimports = collect_submodules("app") + collect_submodules("ingest")

a = Analysis(
    ["desktop/main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EnglishDaily",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)
