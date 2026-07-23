from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
frontend = ROOT / "frontend" / "out"
if not frontend.exists():
    raise SystemExit("frontend/out does not exist; run the Windows build script first")

datas = [(str(frontend), "frontend_out")]
hiddenimports = []
for package in ("py_clob_client_v2", "webview", "eth_account", "eth_utils", "certifi"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    hiddenimports += package_hidden

a = Analysis(
    [str(ROOT / "desktop_app.py")],
    pathex=[str(ROOT / "backend")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PM-KS交易桌面",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="PM-KS交易桌面",
)
