"""Install a folder of hand-made category icons as the per-TYPE/SUBTYPE defaults.

The icons are named for the pair they belong to — ``armor-armor_body.png`` is
the default for ``ARMOR/ARMOR_BODY``, and a type with no subtype is just
``adept_way.png``. That naming is the whole matching rule; nothing here guesses.

Two things happen, and the second is the one that lasts:

  * every item currently showing an auto-picked generic (or no art at all) is
    re-pointed at its category icon, and
  * ``data/_assets/generic/defaults.json`` is rewritten to name these files, so
    the next import reuses them instead of picking its own. Without that second
    step this would be a manual fix that a re-import silently undoes.

Icons are shrunk to ``--max-px`` on the way in (see ``icon_match.MAX_ICON_PX``).
A 1024px set costs about half a gigabyte installed, all of it detail Foundry
never draws; the originals in your icon folder are left alone.

Artwork extracted from the books is never touched — a photograph of a bear is
not an icon standing in for one. Per-item icons under ``<book>/lib/`` are left
alone too, unless ``--replace-item-icons`` is given: those are name matches the
importer picked out of the icon library because a word in a file name happened
to match a word in an item name, and a consistent category icon is usually
better. An icon chosen by hand in the review app is recorded as a correction,
and corrections are re-applied after this runs, so a deliberate choice survives
either way.

    python tools/install_category_icons.py --dry-run
    python tools/install_category_icons.py
    python tools/install_category_icons.py --replace-item-icons
    python tools/install_category_icons.py --icons "D:\\icons\\Category Icons"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.icon_match import (                                    # noqa: E402
    EXTS, MAX_ICON_PX, install_icon, load_defaults, save_defaults,
)
from extractor.paths import data_root                                 # noqa: E402

DEFAULT_SUBDIR = "Category Icons"

#: Types whose items are individuals, not members of a category. A shared icon
#: for "every critter" or "every NPC" would be worse than none: each of these
#: gets its own portrait, chosen by hand. They are skipped entirely — never
#: assigned, never remembered as a default, and not reported as a missing icon,
#: because they are not missing one.
NO_CATEGORY_ICON = {"CRITTER", "NPC"}


def icon_key(itype: str, subtype: str) -> str:
    """The filename stem an icon for this pair must have."""
    return f"{itype}-{subtype}".lower() if subtype else itype.lower()


def slug_for(itype: str, subtype: str) -> str:
    """Destination name under _assets/generic/ — the same slug icon_match.py
    computes, so both agree on where a default lives."""
    return re.sub(r"[^a-z0-9]+", "_", f"{itype}_{subtype}".lower()).strip("_")


def find_icons(data: _P, given: str) -> _P | None:
    """The icon folder: what was asked for, else ``Category Icons`` inside any
    configured library root."""
    if given:
        p = _P(given)
        return p if p.is_dir() else None
    try:
        settings = json.loads((data / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    configured = settings.get("iconLibrary")
    roots = configured if isinstance(configured, list) else [configured] if configured else []
    for root in roots:
        candidate = _P(str(root)) / DEFAULT_SUBDIR
        if candidate.is_dir():
            return candidate
    return None


def index_icons(folder: _P) -> tuple[dict[str, _P], list[str]]:
    """stem -> file. Two files claiming one stem is an authoring mistake, not
    something to resolve silently, so it is reported."""
    by_stem: dict[str, _P] = {}
    clashes: list[str] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in EXTS:
            continue
        stem = path.stem.lower()
        if stem in by_stem:
            clashes.append(f"{by_stem[stem].name} / {path.name}")
            continue
        by_stem[stem] = path
    return by_stem, clashes


def payloads(data: _P):
    """Every category file in the library, book by book, domain by domain."""
    for book in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for domain in sorted(d for d in book.iterdir() if d.is_dir()):
            yield from sorted(domain.glob("*.json"))


def replaceable(img: str, item_icons: bool = False) -> bool:
    """Whether this image may be swapped for the category icon.

    Always: nothing at all, and a shared placeholder from a previous run.

    With ``item_icons``: also the per-item icons under ``<book>/lib/``. Those
    are name matches the importer picked out of the icon library — scrappy
    clipart chosen because a word in the file name happened to match a word in
    the item name — and a consistent category icon beats them. An icon picked by
    hand in the review app is recorded as a correction, and corrections are
    re-applied after this runs, so a deliberate choice still wins.

    Never: artwork extracted from the books, which is a picture of the thing
    rather than an icon standing in for it.
    """
    if not img or img.startswith("generic/"):
        return True
    return item_icons and "/lib/" in img


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--icons", default="", help=f"folder of icons (default: <library>/{DEFAULT_SUBDIR})")
    ap.add_argument("--dry-run", action="store_true", help="report, change nothing")
    ap.add_argument("--replace-item-icons", action="store_true",
                    help="also replace the importer's per-item name-matched icons "
                         "(<book>/lib/...) with the category icon; extracted book "
                         "art is still left alone")
    ap.add_argument("--max-px", type=int, default=MAX_ICON_PX,
                    help=f"shrink icons to this longest edge (default {MAX_ICON_PX}; 0 keeps the original)")
    args = ap.parse_args()

    data = args.data or data_root()
    folder = find_icons(data, args.icons)
    if folder is None:
        print(f"no icon folder found (looked for '{DEFAULT_SUBDIR}' under the configured library)")
        return 1

    by_stem, clashes = index_icons(folder)
    print(f"{len(by_stem)} icons in {folder}")
    for c in clashes:
        print(f"  ! two icons share a name: {c}")

    # pass 1 — which pairs exist in the library, and which have an icon
    pairs: Counter[tuple[str, str]] = Counter()
    portraits = 0
    for path in payloads(data):
        for item in json.loads(path.read_text(encoding="utf-8")).get("items", []):
            system = item.get("system") or {}
            pair = (str(system.get("type") or ""), str(system.get("subtype") or ""))
            if pair[0] in NO_CATEGORY_ICON:
                portraits += 1        # gets a portrait by hand; not our business
                continue
            pairs[pair] += 1
    if portraits:
        print(f"{portraits} items excluded — {', '.join(sorted(NO_CATEGORY_ICON))} "
              f"are individuals and get their own art")

    installed: dict[tuple[str, str], str] = {}
    slugs: dict[str, tuple[str, str]] = {}
    written: dict[str, str] = {}          # slug -> the file name on disk
    collisions = []
    for pair in sorted(pairs):
        source = by_stem.get(icon_key(*pair))
        if source is None:
            continue
        slug = slug_for(*pair)
        # Two pairs can slug the same: 'MANA' and the mis-cased 'mana' both
        # become mana.png. When they resolve to the SAME icon that is not a
        # conflict — they are the same category — so both get it and the file is
        # written once. Only genuinely different icons fighting over one name
        # are a problem worth reporting.
        if slug in slugs and by_stem.get(icon_key(*slugs[slug])) != source:
            collisions.append(f"{pair[0]}/{pair[1]} and {slugs[slug][0]}/{slugs[slug][1]} -> {slug}")
            continue
        first = slug not in slugs
        slugs.setdefault(slug, pair)
        # the stored path has to come from the file install_icon actually wrote:
        # it re-encodes to WebP, so the source's extension is not the one used
        if first and not args.dry_run:
            written[slug] = install_icon(source, data / "_assets" / "generic",
                                         slug, args.max_px).name
        installed[pair] = f"generic/{written.get(slug, slug + '.webp')}"
    for c in collisions:
        print(f"  ! two pairs want the same file name: {c}")

    covered = sum(pairs[p] for p in installed)
    print(f"{len(installed)} of {len(pairs)} type/subtype pairs have an icon "
          f"({covered} of {sum(pairs.values())} items)")

    # pass 2 — re-point the items that are on a placeholder
    changed_items = 0
    kept = 0
    cleared = 0
    by_pair: Counter[tuple[str, str]] = Counter()
    for path in payloads(data):
        payload = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for item in payload.get("items", []):
            system = item.get("system") or {}
            pair = (str(system.get("type") or ""), str(system.get("subtype") or ""))
            if pair[0] in NO_CATEGORY_ICON:
                # Active, not passive. Declining to ASSIGN a category icon does
                # nothing about one an earlier run already stamped on: both icon
                # passes skip an item that has an img at all, so 216 critters and
                # NPCs kept generic/critter.svg through every import and looked
                # finished instead of looking like they were waiting for a
                # portrait. A book graphic chosen by hand is never touched —
                # replaceable() only clears shared placeholders and name-matched
                # clipart.
                if item.get("img") and replaceable(str(item["img"]), True):
                    item["img"] = ""
                    cleared += 1
                    dirty = True
                continue
            img = installed.get(pair)
            if img is None:
                continue
            if not replaceable(str(item.get("img") or ""), args.replace_item_icons):
                kept += 1
                continue
            if item.get("img") == img:
                continue
            item["img"] = img
            by_pair[pair] += 1
            changed_items += 1
            dirty = True
        if dirty and not args.dry_run:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # pass 3 — remember them, so the next import does not pick its own
    if not args.dry_run and installed:
        defaults = load_defaults(data)
        defaults.update({f"{t}/{s}": img for (t, s), img in installed.items()})
        # Forget any default remembered for an excluded type. defaults.json still
        # held CRITTER/ -> generic/critter.svg from before these types were
        # excluded, and icon_match reads that file — so the exclusion in both
        # passes was undone by a third place that simply remembered the old
        # answer. Compared on the whole type, not a prefix: CRITTER_AWAKENED is
        # its own type and keeps its icon.
        for key in [k for k in defaults if k.split("/")[0] in NO_CATEGORY_ICON]:
            del defaults[key]
        save_defaults(data, defaults)

    missing = [p for p in pairs if p not in installed]
    print(f"\n{changed_items} items re-pointed, {kept} left on their own art")
    if cleared:
        print(f"{cleared} placeholder icon(s) cleared from "
              f"{', '.join(sorted(NO_CATEGORY_ICON))} — they await a portrait")
    if missing:
        print(f"\n{len(missing)} pairs without an icon "
              f"({sum(pairs[p] for p in missing)} items):")
        for pair in sorted(missing, key=lambda p: -pairs[p]):
            print(f"  {pairs[pair]:5}  {pair[0] or '(no type)'} - {pair[1] or '(no subtype)'}")
    if args.dry_run:
        print("\n(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
