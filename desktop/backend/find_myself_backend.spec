# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("insightface") + collect_data_files("pillow_heif")
binaries = []
hiddenimports = [
    "pillow_heif",
    "pillow_heif.HeifImagePlugin",
]

hiddenimports += collect_submodules("insightface.app")
hiddenimports += collect_submodules("insightface.model_zoo")
hiddenimports += collect_submodules("insightface.utils")

a = Analysis(
    ["engine_cli.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "_tkinter",
        "altair",
        "insightface.commands",
        "insightface.gui",
        "matplotlib",
        "onnxruntime.backend",
        "onnxruntime.datasets",
        "onnxruntime.quantization",
        "onnxruntime.tools",
        "onnxruntime.transformers",
        "pandas",
        "pyarrow",
        "pydeck",
        "tkinter",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="find-myself-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="find-myself-backend",
)
