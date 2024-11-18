# -*- mode: python ; coding: utf-8 -*-
import sys
import docio
from pathlib import Path

# Increase the recursion limit
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

# Print the path of the Python executable
print(sys.executable)

from PyInstaller.utils.hooks import collect_all

binaries_list = []

datas_list = []

hiddenimports_list = ['multipart', 'torch']

def add_package(package_name):
    datas, binaries, hiddenimports = collect_all(package_name)
    datas_list.extend(datas)
    binaries_list.extend(binaries)
    hiddenimports_list.extend(hiddenimports)

add_package('pypdfium2')
add_package('pypdfium2_raw')
add_package('docio')

a = Analysis(
    [Path('src/docio/entrypoints/api.py').as_posix()],
    pathex=[],
    binaries=binaries_list,
    datas=datas_list,
    hiddenimports=hiddenimports_list,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='docio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='docio',
)
