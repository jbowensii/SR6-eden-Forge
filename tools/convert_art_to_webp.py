"""Re-encode the extracted book artwork as WebP and repoint everything at it.

The illustrations lifted out of the PDFs are full-resolution PNG and JPEG —
single files up to 17 MB, about 850 MB in total, all of which ends up inside the
exported Foundry module. At quality 90 WebP that becomes roughly a tenth of the
size with no visible difference at any size the art is actually viewed.

Changing the encoding changes the file name, so this is a migration, not a
conversion: four things have to move together or the library breaks.

  1. the file itself                    ``corebook/p42_1.png`` -> ``.webp``
  2. every item's ``img``               in the book/domain payloads
  3. every saved correction's ``img``   in ``_corrections/``
  4. every remembered category default  in ``_assets/generic/defaults.json``

Point 3 is the one that bites. A correction records the whole item, image path
included, and the import re-applies corrections as its last phase — so a
migration that skipped them would put the old ``.png`` paths back on the next
import and every one of those items would show a broken picture.

Everything under ``_assets`` is converted, icons included. The icon tooling
writes WebP too (``icon_match.install_icon``), so a later import re-installing
an icon lands on the same name this migration produced.

    python tools/convert_art_to_webp.py --dry-run
    python tools/convert_art_to_webp.py
    python tools/convert_art_to_webp.py --quality 80 --keep-originals
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root                 # noqa: E402

SOURCE_EXTS = {".png", ".jpg", ".jpeg"}

DEFAULT_QUALITY = 90


def convertible(rel: _P) -> bool:
    return rel.suffix.lower() in SOURCE_EXTS


def kind(path: _P) -> str:
    """What the file actually is, by its leading bytes rather than its name.

    Downloaded art is not always art: a fetch that got an error page saved the
    HTML with a ``.jpg`` on the end, and it sat in the library looking like a
    picture. And a file can be WebP already and simply misnamed, which wants a
    rename, not a re-encode.
    """
    head = path.read_bytes()[:16]
    if head[:3] == b"\xff\xd8\xff" or head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return "not-an-image"


def encode(source: _P, dest: _P, quality: int) -> int | None:
    """Write ``source`` to ``dest`` as WebP. Returns the new size, or None if
    the file could not be read or WebP came out bigger than what we already had
    (a real outcome for very small images, and not worth a worse file)."""
    try:
        from PIL import Image
        with Image.open(source) as im:
            im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
            im.save(dest, format="WEBP", quality=quality, method=4)
    except Exception as e:                              # noqa: BLE001
        print(f"  ! {source.name}: {type(e).__name__}: {e}")
        if dest.exists():
            dest.unlink()
        return None
    if dest.stat().st_size >= source.stat().st_size:
        dest.unlink()
        return None
    return dest.stat().st_size


def payload_files(data: _P):
    for book in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for domain in sorted(d for d in book.iterdir() if d.is_dir()):
            yield from sorted(domain.glob("*.json"))


def correction_files(data: _P):
    corrections = data / "_corrections"
    if corrections.is_dir():
        yield from sorted(corrections.rglob("*.json"))


def repoint(path: _P, moved: dict[str, str]) -> int:
    """Rewrite every ``img`` in one JSON file. Handles both shapes we store: a
    payload with an ``items`` list, and a single-item correction."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    changed = 0

    def fix(obj) -> None:
        nonlocal changed
        img = obj.get("img")
        if isinstance(img, str) and img in moved:
            new = moved[img]
            if new:
                obj["img"] = new
            else:
                obj.pop("img", None)   # the file was never an image; let the
                                       # item fall back to its category icon
            changed += 1

    if isinstance(doc, dict):
        for item in doc.get("items", []):
            if isinstance(item, dict):
                fix(item)
        fix(doc)                       # a correction is the item itself
    if changed:
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed


def repoint_defaults(assets: _P, moved: dict[str, str]) -> int:
    """Rewrite ``generic/defaults.json``, which remembers the icon chosen for
    each type/subtype. Left stale, the next import would reinstate a path whose
    file this migration renamed."""
    path = assets / "generic" / "defaults.json"
    try:
        defaults = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    changed = 0
    for key, img in list(defaults.items()):
        if isinstance(img, str) and moved.get(img):
            defaults[key] = moved[img]
            changed += 1
    if changed:
        path.write_text(json.dumps(defaults, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--quality", type=int, default=DEFAULT_QUALITY)
    ap.add_argument("--keep-originals", action="store_true",
                    help="leave the PNG/JPEG in place after converting")
    ap.add_argument("--drop-broken", action="store_true",
                    help="delete files that are not images at all and clear the "
                         "items pointing at them")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = args.data or data_root()
    assets = data / "_assets"
    if not assets.is_dir():
        print(f"no artwork folder at {assets}")
        return 1

    todo = [p for p in sorted(assets.rglob("*"))
            if p.is_file() and convertible(p.relative_to(assets))]
    before = sum(p.stat().st_size for p in todo)
    print(f"library: {data}")
    print(f"{len(todo)} files to convert, {before / 1e6:.0f} MB, quality {args.quality}")
    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    # 1. encode. Nothing is deleted and no reference moves until the whole set
    #    has been written, so a failure part-way leaves a working library.
    moved: dict[str, str] = {}
    renamed: list[str] = []
    broken: list[_P] = []
    after = 0
    failed = 0
    for source in todo:
        rel = source.relative_to(assets)
        dest = source.with_suffix(".webp")
        what = kind(source)
        if what == "not-an-image":
            broken.append(source)
            continue
        if what == "webp":                     # already WebP, just misnamed
            if not dest.exists():
                source.rename(dest)
                moved[rel.as_posix()] = dest.relative_to(assets).as_posix()
                renamed.append(rel.as_posix())
                after += dest.stat().st_size
            continue
        size = encode(source, dest, args.quality)
        if size is None:
            failed += 1
            continue
        moved[rel.as_posix()] = dest.relative_to(assets).as_posix()
        after += size
    # "of the original size" is meaningless when there was no original: on a
    # library that is already fully WebP nothing is read, before is 0, and this
    # line divided by it and took the whole import down at phase 20 of 23 —
    # after forty minutes of work, for a phase that had correctly decided it had
    # nothing to do. A phase with no work must finish, not crash.
    ratio = f"{after / before * 100:.0f}% of {before / 1e6:.0f} MB" if before else "nothing to convert"
    print(f"converted {len(moved) - len(renamed)}, renamed {len(renamed)} already-WebP, "
          f"{after / 1e6:.0f} MB ({ratio}); "
          f"{failed} left as they were")

    if broken:
        print(f"\n{len(broken)} files are not images at all "
              f"(a failed download saved the error page):")
        for p in broken:
            print(f"  {p.relative_to(assets).as_posix()}  ({p.stat().st_size} bytes)")
        if args.drop_broken:
            for p in broken:
                moved[p.relative_to(assets).as_posix()] = ""      # "" clears the img
                p.unlink()
            print("  dropped — those items fall back to their category icon")
        else:
            print("  left in place; re-run with --drop-broken to remove them")

    # 2. repoint the library, the corrections and the remembered icon defaults
    items = sum(repoint(p, moved) for p in payload_files(data))
    fixed = sum(repoint(p, moved) for p in correction_files(data))
    defaults_changed = repoint_defaults(assets, moved)
    print(f"repointed {items} items, {fixed} saved corrections "
          f"and {defaults_changed} category defaults")

    # 3. only now, with nothing pointing at them, remove the originals
    if args.keep_originals:
        print("originals kept (--keep-originals)")
    else:
        removed = 0
        for rel in moved:
            old = assets / rel
            if old.is_file():
                old.unlink()
                removed += 1
        print(f"removed {removed} original files")

    # 4. anything still pointing at a file that is not there
    dangling = 0
    for path in payload_files(data):
        for item in json.loads(path.read_text(encoding="utf-8")).get("items", []):
            img = item.get("img")
            if img and not (assets / img).is_file():
                dangling += 1
    print(f"broken image links after migration: {dangling}")
    return 1 if dangling else 0


if __name__ == "__main__":
    raise SystemExit(main())
