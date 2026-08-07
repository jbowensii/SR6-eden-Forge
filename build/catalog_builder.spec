# PyInstaller spec — Shadowrun 6th World Catalog Builder.
#
#     python build/build_release.py            # freeze, package, sign
#     pyinstaller build/catalog_builder.spec   # freeze only
#
# One-folder, not one-file: a one-file build unpacks ~144 MB to temp on every
# launch, which is slow and reliably attracts antivirus attention.
#
# Everything here that is not obvious was learned in the phase-0 spike; see
# docs/installer-phase0.md.

import site
import sys
from pathlib import Path

REPO = Path(SPECPATH).parent          # noqa: F821 — injected by PyInstaller

# Heavy and image-only. OpenCV alone is 155 MB and onnxruntime 41 MB, and both
# are reachable only from images_extract.py — the text pipeline never imports
# them. Excluding them is the difference between a 69 MB download and 250 MB+.
# Art support becomes an optional download.
EXCLUDE = [
    "cv2", "onnxruntime", "rembg", "torch", "torchvision",
    "matplotlib", "scipy", "pandas", "IPython", "notebook",
    "pytest", "_pytest",
]

datas = [
    # The book registry — without it nothing can be recognised and every folder
    # reads as "no Shadowrun books found". Shipped at the bundle root AND
    # beside the package, so either lookup path finds it.
    (str(REPO / "build" / "catalog_builder" / "books.json"), "."),
    (str(REPO / "build" / "catalog_builder" / "books.json"), "catalog_builder"),
    # the window loads this at runtime; the exe's own icon only covers Explorer
    (str(REPO / "build" / "wizard" / "app.ico"), "."),
    # the pipeline reads these at runtime
    (str(REPO / "schemas"), "schemas"),
    (str(REPO / "foundry-module" / "sr6-forge" / "data" / "creation-rules.json"),
     "foundry-module/sr6-forge/data"),
]
binaries = []
hiddenimports = [
    "referencing", "jsonschema_specifications",
    "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox",
]

try:
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules
    # pdfminer ships CMap tables; without them a page with embedded CJK or a
    # non-standard encoding fails at read time, not at import
    datas += collect_data_files("pdfminer")
    datas += collect_data_files("jsonschema_specifications")
    datas += collect_data_files("referencing")
    hiddenimports += collect_submodules("extractor")
    hiddenimports += collect_submodules("tools")
    hiddenimports += collect_submodules("build.catalog_builder")
except Exception as e:
    print(f"spec: hook collection partial: {e}", file=sys.stderr)

# charset-normalizer and chardet ship mypyc-compiled extensions whose module
# name is a bare content hash — `81d243bd2c585b0f4821__mypyc`. Nothing imports
# that name in source, so the analysis never sees it: the build SUCCEEDS and
# then dies at runtime the first time a page is decoded. Scanned rather than
# hardcoded, because the hash changes with every release and hardcoding it
# would break in exactly the same runtime-only way. (phase-0 spike)
for _sp in site.getsitepackages() + [site.getusersitepackages()]:
    _sp = Path(_sp)
    if not _sp.is_dir():
        continue
    for _pyd in _sp.glob("*__mypyc*.pyd"):
        binaries.append((str(_pyd), "."))
        hiddenimports.append(_pyd.name.split(".")[0])
    for _pyd in _sp.glob("*/**/*__mypyc*.pyd"):
        binaries.append((str(_pyd), str(_pyd.parent.relative_to(_sp))))

a = Analysis(                          # noqa: F821
    [str(REPO / "build" / "catalog_builder" / "__main__.py")],
    pathex=[str(REPO)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=EXCLUDE,
    noarchive=False,
)
pyz = PYZ(a.pure)                      # noqa: F821

exe = EXE(                             # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SR6CatalogBuilder",
    console=False,                     # windowed: the log lives in the UI
    strip=False,
    upx=False,                         # UPX-packed binaries get flagged
    # the installed application's icon, in Explorer, the taskbar and Alt-Tab
    icon=str(REPO / 'build' / 'wizard' / 'app.ico'),
)
coll = COLLECT(                        # noqa: F821
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="SR6CatalogBuilder",
)
