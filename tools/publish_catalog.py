"""Build the catalog and install it into Foundry.

    python tools/publish_catalog.py --foundry "<...>/FoundryVTT/Data"

One command for the last step: compile the extracted library into compendium
packs, then copy the finished module where Foundry will find it. Split out of
the desktop shell so the same thing can be done from a terminal, and so the
shell has nothing to do but show the output.

Prints progress as it goes — the shell streams this straight into its log, so
anything unclear here is unclear to the user.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

REPO = _P(__file__).resolve().parent.parent
MODULE_ID = "sr6-forge-corebook"


def _py(module: str, args: list[str] | None = None) -> int:
    """Run one of our Python tools, from source OR from the frozen build.

    sys.executable is SR6CatalogBuilder.exe in a frozen build, not python.exe.
    Handing it a script path does not run the script: the exe does not recognise
    the argument, falls through to its entry point and OPENS ANOTHER COPY OF THE
    WINDOW while the step silently does nothing. import_library learned this the
    hard way — sixteen phases, sixteen windows — and dispatches through a marker
    instead. This is the same dispatch; every new subprocess call has to use it.
    """
    args = args or []
    if getattr(sys, "frozen", False):
        argv = [sys.executable, "--run-pipeline", f"tools.{module}", *args]
    else:
        argv = [sys.executable, "-u", str(REPO / "tools" / f"{module}.py"), *args]
    print(f"    $ {' '.join(argv[1:])}")
    p = subprocess.run(argv, cwd=str(REPO), text=True, check=False,
                       capture_output=True, encoding="utf-8", errors="replace")
    for line in (p.stdout or "").splitlines():
        print(f"      {line}")
    if p.returncode != 0:
        for line in (p.stderr or "").splitlines()[-12:]:
            print(f"      ! {line}")
    return p.returncode


def _node(script: str, args: list[str]) -> int:
    """Run one of the Node build scripts, streaming its output."""
    argv = ["node", str(REPO / script), *args]
    print(f"    $ {' '.join(argv[1:])}")
    p = subprocess.run(argv, cwd=str(REPO), text=True, check=False,
                       capture_output=True, encoding="utf-8", errors="replace")
    for line in (p.stdout or "").splitlines():
        print(f"      {line}")
    if p.returncode != 0:
        for line in (p.stderr or "").splitlines()[-12:]:
            print(f"      ! {line}")
    return p.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--foundry", required=True, help="Foundry's Data folder")
    # not <repo>/data: that is the developer's scratch copy, and once the
    # builder is installed the real library lives in its workspace
    ap.add_argument("--data", default=None, help="the extracted library")
    ap.add_argument("--book", default="corebook")
    ap.add_argument("--version", default="0.5.0")
    args = ap.parse_args()

    from build.catalog_builder import publish            # noqa: E402

    foundry = _P(args.foundry)
    ok, why = publish.check(foundry)
    if not ok:
        print(f"cannot publish: {why}")
        return 2

    print("[1/3] compiling compendium packs (this takes a minute)")
    # --data was accepted and then never passed on, so the export always ran
    # against <repo>/data no matter what was asked for
    from extractor.paths import data_root                # noqa: E402
    library = _P(args.data) if args.data else data_root([])
    print(f"    library: {library}")
    rc = _node("site/scripts/export_all.mjs",
               ["--book", args.book, "--status", "all", "--version", args.version,
                "--data", str(library)])
    if rc != 0:
        print("failed while compiling packs")
        return rc

    # chargen-data.json is built from the user's own Commlink6 jar, never
    # shipped. It carries priorities, metatypes, lifepaths and starting-gear
    # packs — book content. Bundling it would put Commlink6's material inside an
    # installer other people download, which is the one thing this pipeline
    # exists to avoid. So it is generated here, on the machine that owns the jar.
    chargen = REPO / "export" / "chargen-data.json"
    if not chargen.is_file():
        print("    building chargen data from your Commlink6 jar")
        rc = _py("build_chargen_data")
        if rc != 0:
            print("failed while building chargen data")
            return rc
        if not chargen.is_file():
            # The generator exiting 0 is not evidence it produced the file.
            print(f"chargen data still missing after a successful run: {chargen}")
            return 1

    print("[2/3] assembling the module")
    rc = _node("site/scripts/build_module.mjs", [])
    if rc != 0:
        print("failed while assembling")
        return rc

    print("[3/3] installing into Foundry")
    built = REPO / "export" / MODULE_ID
    if not built.is_dir():
        print(f"nothing built at {built}")
        return 1
    try:
        dest = publish.install(built, foundry, MODULE_ID)
    except Exception as e:
        print(f"install failed: {e}")
        return 1

    print(f"      -> {dest}")
    print(f"      {publish.summary(foundry, MODULE_ID)}")
    print()
    print(publish.NEXT_STEPS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
