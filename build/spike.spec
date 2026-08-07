# PyInstaller spec — phase-0 spike.
#
#     pyinstaller build/spike.spec --noconfirm
#
# One-folder, not one-file. A one-file build unpacks the whole bundle to a temp
# directory on every launch, which at this size is slow and is a reliable way
# to attract antivirus attention. One-folder starts immediately and lets the
# installer compress it properly.
#
# The exclusions are the whole point of the measurement. OpenCV is 155 MB and
# onnxruntime 41 MB, and both are reachable only from images_extract.py — the
# text pipeline never imports them, verified by loading the ingest chain and
# checking sys.modules. Excluding them is what decides whether the installer is
# ~130 MB or ~360 MB, so the spike measures with them out and the art path
# becomes an optional download.

import site
import sys
from pathlib import Path

REPO = Path(SPECPATH).parent          # noqa: F821 — PyInstaller injects SPECPATH

# Heavy, and only ever used for artwork.
EXCLUDE = [
    "cv2", "onnxruntime", "rembg", "torch", "torchvision",
    "matplotlib", "scipy", "pandas", "IPython", "notebook",
    "tkinter",                        # the shell comes later; not needed here
    "pytest", "_pytest",
]

# pdfminer ships CMap tables as package data; pdfplumber reads them when a page
# uses embedded CJK or non-standard encodings. A default freeze leaves them out
# and the failure appears only on such a page.
datas = []
binaries = []
hiddenimports = ["referencing", "jsonschema_specifications"]

try:
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules
    datas += collect_data_files("pdfminer")
    datas += collect_data_files("jsonschema_specifications")
    datas += collect_data_files("referencing")
    hiddenimports += collect_submodules("extractor")
except Exception as e:                # keep the spec readable if a hook moves
    print(f"spec: hook collection partial: {e}", file=sys.stderr)

# charset-normalizer (and chardet) ship mypyc-compiled extensions whose module
# name is a bare content hash — `81d243bd2c585b0f4821__mypyc`. Nothing imports
# that name in source, so PyInstaller's analysis never sees it and the freeze
# succeeds; the failure surfaces only when pdfminer decodes a page and asks
# charset-normalizer to sniff an encoding. Collect the .pyd by scanning for it
# rather than hardcoding the hash, which changes with every release.
for _sp in site.getsitepackages() + [site.getusersitepackages()]:
    for _pyd in Path(_sp).glob("*__mypyc*.pyd"):
        binaries.append((str(_pyd), "."))
        hiddenimports.append(_pyd.name.split(".")[0])
    for _pyd in Path(_sp).glob("*/**/*__mypyc*.pyd"):
        rel = _pyd.parent.relative_to(_sp)
        binaries.append((str(_pyd), str(rel)))

a = Analysis(                          # noqa: F821
    [str(REPO / "build" / "spike_entry.py")],
    pathex=[str(REPO)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=EXCLUDE,
    noarchive=False,
)
pyz = PYZ(a.pure)                      # noqa: F821

exe = EXE(                             # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="sr6-spike",
    console=True,
    strip=False,
    upx=False,                         # UPX-packed binaries get flagged
)
coll = COLLECT(                        # noqa: F821
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="sr6-spike",
)
