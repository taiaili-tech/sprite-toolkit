# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 -- onefile 模式
产物：dist\MJ批量生图_引擎.exe  （单文件）
外部主题：把 JSON 放进 dist\themes\ 即可，无需重新打包
"""
from PyInstaller.building.build_main import Analysis, PYZ, EXE

a = Analysis(
    ['MJ批量生图_引擎.pyw'],
    pathex=[],
    binaries=[],
    datas=[('themes', 'themes')],
    hiddenimports=['PIL', 'requests', 'tkinter'],
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
    name='MJ批量生图_引擎',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='app_icon.ico',
)
