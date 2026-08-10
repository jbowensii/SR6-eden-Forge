"""Find artwork the library points at but does not have, and put it back.

An item's ``img`` is a path relative to ``data/_assets``. When that file is not
there the review app shows a broken tile and the export ships a document whose
picture does not exist — while the item looks perfectly fine in the JSON, which
is why this goes unnoticed.

The usual cause is not a wrong path. It is a file that was extracted into one
library and never reached another: the developer's ``<repo>/data`` and the
installed builder's workspace are separate trees, and art produced in one does
not appear in the other. So the repair is to locate the same file elsewhere and
copy it in, leaving the recorded path exactly as it is.

Searched, in order: any ``--from`` roots given, the repo's own ``data/_assets``,
then the backups newest-first. An exact relative-path match is taken first; a
match on file name alone is used only when it is unambiguous, so two different
pictures called ``bear.jpg`` never get silently swapped.

    python tools/repair_missing_art.py --dry-run
    python tools/repair_missing_art.py
    python tools/repair_missing_art.py --from D:\\old-library\\_assets
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import REPO, data_root       # noqa: E402

BACKUP_ROOT = _P(r"C:\Users\johnb\SR6-Forge-Backups")


def payloads(data: _P):
    """Every category file in the library."""
    for book in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for domain in sorted(d for d in book.iterdir() if d.is_dir()):
            yield from sorted(domain.glob("*.json"))


def missing_art(data: _P) -> dict[str, list[str]]:
    """``img`` path -> names of the items pointing at it, for paths with no file."""
    assets = data / "_assets"
    out: dict[str, list[str]] = defaultdict(list)
    for path in payloads(data):
        for item in json.loads(path.read_text(encoding="utf-8")).get("items", []):
            img = str(item.get("img") or "")
            if img and not (assets / img).is_file():
                out[img].append(item.get("name", item.get("id", "?")))
    return dict(out)


def search_roots(extra: list[str], only: bool = False) -> list[_P]:
    roots = [_P(e) for e in extra]
    if only:
        return [r for r in roots if r.is_dir()]
    roots.append(REPO / "data" / "_assets")
    if BACKUP_ROOT.is_dir():
        # newest first: a recent backup is likelier to hold the current file
        roots += [b / "_assets" for b in sorted(BACKUP_ROOT.iterdir(), reverse=True)
                  if (b / "_assets").is_dir()]
    return [r for r in roots if r.is_dir()]


def find(rel: str, roots: list[_P], by_name: dict[_P, dict[str, list[_P]]]) -> _P | None:
    """The file for ``rel``: same relative path if any root has it, else a
    uniquely-named candidate."""
    for root in roots:
        candidate = root / rel
        if candidate.is_file():
            return candidate
    name = _P(rel).name.lower()
    for root in roots:
        hits = by_name[root].get(name, [])
        if len(hits) == 1:                 # ambiguous means we do not guess
            return hits[0]
    return None


def index_names(roots: list[_P], wanted: set[str]) -> dict[_P, dict[str, list[_P]]]:
    """file name -> paths, per root, limited to the names actually being looked
    for (walking whole asset trees for everything else would be wasted work)."""
    out: dict[_P, dict[str, list[_P]]] = {}
    for root in roots:
        found: dict[str, list[_P]] = defaultdict(list)
        for p in root.rglob("*"):
            if p.is_file() and p.name.lower() in wanted:
                found[p.name.lower()].append(p)
        out[root] = found
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--from", dest="extra", action="append", default=[],
                    metavar="DIR", help="another _assets tree to search (repeatable)")
    ap.add_argument("--only-from", action="store_true",
                    help="search ONLY the --from roots, not the repo or the backups")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--clear-unfound", action="store_true",
                    help="blank the img of items whose art cannot be found, so they "
                         "fall back to their category default instead of a broken tile")
    args = ap.parse_args()

    data = args.data or data_root()
    assets = data / "_assets"
    wanted = missing_art(data)
    print(f"library: {data}")
    if not wanted:
        print("every item's artwork is present — nothing to repair")
        return 0
    print(f"{len(wanted)} missing files, referenced by {sum(len(v) for v in wanted.values())} items")

    roots = search_roots(args.extra, args.only_from)
    for r in roots[:6]:
        print(f"  searching {r}")
    names = index_names(roots, {_P(w).name.lower() for w in wanted})

    restored, unfound = {}, []
    for rel in sorted(wanted):
        source = find(rel, roots, names)
        if source is None:
            unfound.append(rel)
            continue
        restored[rel] = source
        if not args.dry_run:
            dest = assets / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)

    print(f"\nrestored {len(restored)} of {len(wanted)}")
    for rel, src in list(restored.items())[:4]:
        print(f"  {rel}  <-  {src}")
    if len(restored) > 4:
        print(f"  ... and {len(restored) - 4} more")

    if unfound:
        print(f"\n{len(unfound)} could not be found anywhere:")
        for rel in unfound[:20]:
            print(f"  {rel}   ({', '.join(wanted[rel][:2])})")
        if args.clear_unfound and not args.dry_run:
            gone = set(unfound)
            cleared = 0
            for path in payloads(data):
                payload = json.loads(path.read_text(encoding="utf-8"))
                dirty = False
                for item in payload.get("items", []):
                    if str(item.get("img") or "") in gone:
                        item.pop("img", None)
                        cleared += 1
                        dirty = True
                if dirty:
                    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8")
            print(f"cleared {cleared} broken references "
                  f"(re-run install_category_icons.py to give them their category icon)")

    if args.dry_run:
        print("\n(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
