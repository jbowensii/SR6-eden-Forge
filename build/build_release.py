"""Build, package and sign the Catalog Builder.

    python build/build_release.py                 # everything
    python build/build_release.py --no-installer  # freeze only
    python build/build_release.py --no-sign       # skip signing
    python build/build_release.py --skip-freeze   # reuse the last freeze

Four steps, each of which stops the build if it fails:

1.  **Freeze** the app with PyInstaller (one-folder).
2.  **Sign** the executable. Unsigned PyInstaller output draws a SmartScreen
    warning, and signing the exe before it is wrapped means the file the user
    eventually runs is signed too, not just the installer.
3.  **Compile** the installer with Inno Setup.
4.  **Sign** the installer, which is what SmartScreen actually inspects.

Signing uses the existing SSL.com eSigner wrapper. It is skipped with a warning
rather than failing the build when the tool is absent, so a developer without
the certificate can still produce a working — if unsigned — installer.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "build"
DIST = BUILD / "dist"
OUT = REPO / "export" / "dist"

SIGN_TOOL = Path(r"C:\Users\johnb\Tools\CodeSignTool\sign.bat")
# A winget install of Inno Setup lands per-user under %LOCALAPPDATA%\Programs,
# not in Program Files, so the machine-wide paths alone miss it.
ISCC_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 7" / "ISCC.exe",
    Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
]


def version() -> str:
    m = REPO / "foundry-module" / "sr6-forge" / "module.json"
    try:
        return json.loads(m.read_text(encoding="utf-8"))["version"]
    except Exception:
        return "0.0.0"


def step(n: int, total: int, what: str) -> None:
    print(f"\n[{n}/{total}] {what}")


def run(argv: list[str], cwd: Path | None = None) -> int:
    print(f"    $ {' '.join(str(a) for a in argv)}")
    p = subprocess.run([str(a) for a in argv], cwd=str(cwd or REPO),
                       text=True, capture_output=True,
                       encoding="utf-8", errors="replace")
    tail = (p.stdout or "").strip().splitlines()[-6:]
    for line in tail:
        print(f"      {line}")
    if p.returncode != 0:
        for line in (p.stderr or "").strip().splitlines()[-15:]:
            print(f"      ! {line}")
    return p.returncode


def find_iscc() -> Path | None:
    for c in ISCC_CANDIDATES:
        if c.is_file():
            return c
    found = shutil.which("ISCC")
    return Path(found) if found else None


def sign(target: Path) -> bool:
    """Sign one file. Returns False when signing was skipped or failed."""
    if not SIGN_TOOL.is_file():
        print(f"      ! signing tool not found at {SIGN_TOOL} — leaving unsigned")
        return False
    rc = run(["powershell", "-NoProfile", "-Command",
              f"& '{SIGN_TOOL}' '{target}'"])
    if rc == 0:
        print(f"      signed {target.name}")
        return True
    print(f"      ! signing failed for {target.name} (exit {rc})")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-installer", action="store_true")
    ap.add_argument("--no-sign", action="store_true")
    ap.add_argument("--skip-freeze", action="store_true")
    args = ap.parse_args()

    v = version()
    total = 4 if not args.no_installer else 2
    print(f"Shadowrun 6th World Catalog Builder — build v{v}")

    app_dir = DIST / "SR6CatalogBuilder"
    exe = app_dir / "SR6CatalogBuilder.exe"

    # 1. freeze
    if args.skip_freeze and exe.is_file():
        print("\n[1/{}] reusing the existing freeze".format(total))
    else:
        step(1, total, "freezing with PyInstaller")
        shutil.rmtree(app_dir, ignore_errors=True)
        rc = run([sys.executable, "-m", "PyInstaller",
                  BUILD / "catalog_builder.spec", "--noconfirm",
                  "--distpath", DIST, "--workpath", BUILD / "work"])
        if rc != 0 or not exe.is_file():
            print("\nfreeze failed")
            return 1
        size = sum(f.stat().st_size for f in app_dir.rglob("*") if f.is_file())
        print(f"      {size / 1e6:.0f} MB, {sum(1 for _ in app_dir.rglob('*'))} files")

    # 2. sign the application
    if args.no_sign:
        print(f"\n[2/{total}] signing skipped (--no-sign)")
    else:
        step(2, total, "signing the application")
        sign(exe)

    if args.no_installer:
        print(f"\ndone — {app_dir}")
        return 0

    # 3. installer
    step(3, total, "compiling the installer")
    iscc = find_iscc()
    if not iscc:
        print("      ! Inno Setup not found. Install it from jrsoftware.org,")
        print("        then re-run with --skip-freeze.")
        print(f"\npartial — the frozen app is at {app_dir}")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    rc = run([iscc, f"/DAppVersion={v}", BUILD / "installer.iss"], cwd=BUILD)
    if rc != 0:
        print("\ninstaller compilation failed")
        return 1

    setup = OUT / f"SR6CatalogBuilder_Setup_v{v}.exe"
    if not setup.is_file():
        print(f"\nexpected {setup}, which is not there")
        return 1

    # 4. sign the installer
    if args.no_sign:
        print(f"\n[4/{total}] signing skipped (--no-sign)")
    else:
        step(4, total, "signing the installer")
        sign(setup)

    print(f"\ndone — {setup}  ({setup.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
