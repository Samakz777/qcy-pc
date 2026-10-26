"""Gera dist/QCY PC/QCY PC.exe (PyInstaller, pasta única, sem console). Uso: python build.py"""
import subprocess
import sys
from pathlib import Path

from qcypc.icon import make_icon

root = Path(__file__).parent
ico = root / "assets" / "qcy.ico"
ico.parent.mkdir(exist_ok=True)
make_icon(256).save(ico, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
subprocess.run(
    [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "QCY PC",
     "--icon", str(ico), "--collect-all", "customtkinter", "--collect-submodules", "winrt",
     "--collect-submodules", "bleak", "--hidden-import", "pystray._win32", str(root / "run_gui.py")],
    check=True, cwd=root,
)
