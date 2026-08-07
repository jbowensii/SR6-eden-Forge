"""Back up and restore the local environment.

    python tools/backup_env.py                     # list what is backed up
    python tools/backup_env.py --create            # take a new backup
    python tools/backup_env.py --restore <stamp>   # put one back

What is protected, and why it matters:

``data/`` minus ``_assets``
    The item libraries, ``_corrections/`` (hand-made fixes that cannot be
    regenerated), ``_ids/`` (the id lockfile — losing it re-mints every
    catalog id and orphans character links), ``_raw/`` (cached page text, so a
    rebuild does not have to re-read every PDF), and the registry. ~7 MB
    compressed.

``data/_assets/``
    2.7 GB of artwork, including images assigned and edited by hand. Copied
    with robocopy rather than tarred: at that size, mirroring is far faster
    and re-runs only move what changed.

``export/``
    The built modules, which double as a snapshot of the last published
    catalog.

Not backed up: the PDFs (they are your originals, not ours to duplicate) and
``node_modules``.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

BACKUP_ROOT = Path(r"C:\Users\johnb\SR6-Forge-Backups")
ASSETS = "_assets"


def _robocopy(src: Path, dest: Path) -> None:
    """Mirror a tree, tolerating robocopy's exit-code convention.

    Robocopy returns a bitmask, not a status: 1 means "files were copied",
    2 "extra files present", 3 both. Only 8 and above are real failures, so a
    plain non-zero check reports a perfectly good copy as broken.
    """
    r = subprocess.run(
        ["robocopy", str(src), str(dest), "/E", "/MT:16",
         "/R:1", "/W:1", "/NFL", "/NDL", "/NP", "/NJH", "/NJS"],
        capture_output=True, check=False, text=True)
    if r.returncode >= 8:
        raise RuntimeError(f"robocopy failed ({r.returncode}): {r.stdout[-400:]}")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def list_backups() -> list[Path]:
    if not BACKUP_ROOT.is_dir():
        return []
    return sorted((p for p in BACKUP_ROOT.iterdir() if p.is_dir()), reverse=True)


def _size(p: Path) -> str:
    n = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def create(repo: Path, with_assets: bool = True) -> Path:
    dest = BACKUP_ROOT / _stamp()
    dest.mkdir(parents=True, exist_ok=True)
    print(f"backing up to {dest}")

    # everything but the artwork: small enough to compress
    data = repo / "data"
    if data.is_dir():
        out = dest / "data-core.tar.gz"
        with tarfile.open(out, "w:gz") as tf:
            for p in sorted(data.rglob("*")):
                if ASSETS in p.parts or not p.is_file():
                    continue
                tf.add(p, arcname=str(p.relative_to(repo)))
        print(f"  data-core.tar.gz   {out.stat().st_size / 1e6:.1f} MB")

    exp = repo / "export"
    if exp.is_dir():
        out = dest / "export.tar.gz"
        with tarfile.open(out, "w:gz") as tf:
            tf.add(exp, arcname="export")
        print(f"  export.tar.gz      {out.stat().st_size / 1e6:.1f} MB")

    # the artwork: mirrored, because 2.7 GB through gzip is a waste of a morning
    src = data / ASSETS
    if with_assets and src.is_dir():
        print(f"  _assets            mirroring (this is the slow part)")
        _robocopy(src, dest / ASSETS)
        print(f"  _assets            {_size(dest / ASSETS)}")

    (dest / "STAMP.txt").write_text(
        f"{dest.name}\nrepo: {repo}\n", encoding="utf-8")
    return dest


def restore(repo: Path, stamp: str) -> int:
    src = BACKUP_ROOT / stamp
    if not src.is_dir():
        print(f"no such backup: {stamp}")
        return 1
    print(f"restoring {src} -> {repo}")
    for name in ("data-core.tar.gz", "export.tar.gz"):
        tgz = src / name
        if not tgz.is_file():
            continue
        with tarfile.open(tgz) as tf:
            tf.extractall(repo)
        print(f"  restored {name}")
    assets = src / ASSETS
    if assets.is_dir():
        print("  restoring _assets (slow)")
        _robocopy(assets, repo / "data" / ASSETS)
    print("done")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path,
                    default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--no-assets", action="store_true",
                    help="skip the 2.7 GB of artwork")
    ap.add_argument("--restore", metavar="STAMP")
    args = ap.parse_args()

    if args.create:
        create(args.repo, with_assets=not args.no_assets)
        return
    if args.restore:
        raise SystemExit(restore(args.repo, args.restore))

    backups = list_backups()
    if not backups:
        print(f"no backups in {BACKUP_ROOT}")
        return
    print(f"backups in {BACKUP_ROOT}:\n")
    for b in backups:
        has_assets = (b / ASSETS).is_dir()
        print(f"  {b.name}   {_size(b):>9}   {'with artwork' if has_assets else 'core only'}")
    print(f"\nrestore with:  python tools/backup_env.py --restore {backups[0].name}")


if __name__ == "__main__":
    main()
