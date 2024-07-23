# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

binaries_list = []

print(Path("src/owl/entrypoints/api.py").resolve().as_posix())

datas_list = [
    (Path("src/owl/entrypoints/api.py").resolve().as_posix(), 'owl/entrypoints'),
    (Path("src/owl/configs/models.json").resolve().as_posix(), 'owl')
]

hiddenimports_list = ['multipart', "tiktoken_ext.openai_public", "tiktoken_ext"]

def add_package(package_name):
    datas, binaries, hiddenimports = collect_all(package_name)
    datas_list.extend(datas)
    binaries_list.extend(binaries)
    hiddenimports_list.extend(hiddenimports)

add_package('litellm')
# add_package('fastapi')

a = Analysis(
    ['src\\owl\\entrypoints\\api.py'],
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
    name='api',
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
    name='api',
)
