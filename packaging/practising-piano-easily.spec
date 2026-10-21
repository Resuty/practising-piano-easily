# Build only application code and authored tutorial resources, never data/exports.
from pathlib import Path
import sys

root = Path(SPECPATH).parent
conda_bin = Path(sys.base_prefix) / "Library" / "bin"
# Conda-based venvs do not expose these stdlib dependencies to the default hook.
stdlib_binaries = [(str(conda_bin / name), ".") for name in ("ffi.dll", "sqlite3.dll", "libmpdec-4.dll")
                   if (conda_bin / name).is_file()]
a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root)],
    binaries=stdlib_binaries,
    datas=[(str(root / "practising_piano_easily" / "content"), "practising_piano_easily/content")],
    hiddenimports=["mido.backends.rtmidi", "rtmidi", "_cffi_backend"],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="practising-piano-easily",
          debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="practising-piano-easily")
