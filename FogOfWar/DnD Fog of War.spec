# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['fogofwar.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pygame',
        'pygame.display',
        'pygame._sdl2',
        'pygame.examples',              # sometimes helps if examples are indirectly used
        'multiprocessing',
        'multiprocessing.context',      # common for freeze issues
        'multiprocessing.spawn',
        '_tkinter',
        'multiprocessing.managers',
        'tkinter',
        'tkinter.filedialog',
        '_tkinter',                     # low-level tkinter
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'numpy', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Fog of War',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
