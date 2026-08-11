"""Check the finished library against the things that have silently broken it.

WHY THIS EXISTS
---------------
Every defect this pipeline has shipped was the same shape: a phase that reported
success while doing nothing, or while undoing something. The art ledger put
3,115 deleted images back and said "done". The extractor wrote 1,001 duplicates
into folders nobody reads and said "done". Auto-pairing reported "0 items" for
four separate reasons and that read as a result. The signing tool exits 0
whether or not it signs. The icon exclusion declined to ADD a placeholder while
leaving 216 already stamped on. The Commlink6 guard put back 29 vehicles the
user had deleted on purpose, on the very run whose log said "left out 30".

Every one of those was found days later, by a human reading a library and
noticing something wrong — never by the import, which had already declared
success. Fixing them one at a time does not end the cycle, because the next one
is written the same way and hides the same way.

So the import now finishes by CHECKING ITS OWN WORK. Each rule below is one bug
that actually happened, expressed as a fact that must be true afterwards. A rule
that fails prints what is wrong, names the phase responsible, and makes the
import exit non-zero. "done" stops being something a phase says about itself.

Add a rule here whenever a defect of this kind is found. That is the whole
protocol: fix the phase, then encode the outcome so it cannot come back quietly.

    python tools/verify_library.py            # check, print a report
    python tools/verify_library.py --strict   # exit 1 on any failure
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root                       # noqa: E402

#: Types that get a hand-picked portrait and must never carry a shared icon.
NO_AUTO_ICON = {"CRITTER", "NPC"}

#: An image that stands in for a category rather than being a picture of the
#: thing itself.
PLACEHOLDER = ("generic/", "iconsets/")


def _items(data: _P):
    """(domain, item) for every real library record."""
    for path in data.rglob("*/*.json"):
        parts = path.parts
        if path.parent.name.startswith("_") or "_corrections" in parts or "_ids" in parts:
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        for item in doc.get("items") or []:
            if isinstance(item, dict) and item.get("id"):
                yield path.parent.name, item


def _corrections(data: _P):
    for path in (data / "_corrections").rglob("*.json"):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict):
            yield rec


def _placeholder(img: str) -> bool:
    return img.startswith(PLACEHOLDER) or "/lib/" in img


# --------------------------------------------------------------------------
# the rules. each returns (ok, message, offenders)
# --------------------------------------------------------------------------

def rule_deletions_stick(data: _P, items, corrections):
    """A row deleted in the review app must not be in the library.

    ingest_vehicles rebuilt them from Commlink6, and the guard put them back
    after the ingest correctly left them out. 29 of 30 returned.
    """
    buried = {r["id"] for r in corrections if r.get("deleted") and r.get("id")}
    present = [it["id"] for _, it in items if it["id"] in buried]
    return (not present,
            f"{len(present)} deleted record(s) are back in the library",
            present[:8])


def rule_portraits_are_not_guessed(data: _P, items, corrections):
    """Critters and NPCs get a portrait by hand, never a shared icon.

    Both icon passes excluded them and 216 still carried generic/critter.svg,
    because declining to assign one does nothing about one already stamped on.
    """
    bad = [it["name"] for dom, it in items
           if str((it.get("system") or {}).get("type", "")) in NO_AUTO_ICON
           and _placeholder(str(it.get("img") or ""))]
    return (not bad,
            f"{len(bad)} critter/NPC record(s) carry a placeholder icon",
            bad[:8])


def rule_no_remembered_default_for_excluded_types(data: _P, items, corrections):
    """_assets/generic/defaults.json is a third place that must agree.

    It still held CRITTER/ -> generic/critter.svg from before the exclusion, and
    icon_match reads it — so the remembered answer undid both passes.
    """
    path = data / "_assets" / "generic" / "defaults.json"
    try:
        defaults = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True, "no defaults file", []
    bad = [k for k in defaults if k.split("/")[0] in NO_AUTO_ICON]
    return (not bad,
            f"{len(bad)} remembered icon default(s) for a hand-portrait type",
            bad)


def rule_no_art_nobody_references(data: _P, items, corrections):
    """No phase may write art into a folder nothing reads.

    Two bugs share this shape. The extractor wrote _assets/<book>/ while the
    library was flat, so its already-on-disk check never matched and it
    re-extracted 1,001 files into 48 recreated folders while reporting success.
    And match_icons installs a per-item icon under <book>/lib/ for every name it
    matches, which install_category_icons then re-points away from — leaving 651
    files that nothing in the library refers to, rewritten every import.

    Flat storage is not the rule; being referenced is. A <book>/lib folder whose
    icons are actually in use is fine.
    """
    assets = data / "_assets"
    if not assets.is_dir():
        return True, "no _assets yet", []
    used = {str(it.get("img") or "") for _, it in items}
    orphans: dict[str, int] = {}
    for book in (p for p in assets.iterdir() if p.is_dir() and p.name != "generic"):
        loose = [f for f in book.rglob("*.*")
                 if f.relative_to(assets).as_posix() not in used]
        if loose:
            orphans[book.name] = len(loose)
    total = sum(orphans.values())
    return (not orphans,
            f"{total} art file(s) in {len(orphans)} per-book folder(s) that "
            f"nothing references — written every import and then discarded",
            [f"_assets/{b}/ — {n} unreferenced file(s)" for b, n in
             sorted(orphans.items(), key=lambda kv: -kv[1])[:8]])


def rule_pruned_art_stays_deleted(data: _P, items, corrections):
    """A graphic thrown away on purpose must not be back.

    "Is the file already there?" was the only skip rule, so deleting a useless
    illustration achieved nothing: one import restored 3,115 of them.
    """
    assets = data / "_assets"
    try:
        ledger = json.loads((assets / "_pruned.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True, "no pruned ledger", []
    on_disk = {p.name for p in assets.glob("*.*")}
    back = [tag for tags in ledger.values() for tag in tags
            if any(n.endswith(f"{tag}.png") or n.endswith(f"{tag}.webp")
                   or n == f"{tag}.png" or n == f"{tag}.webp" for n in on_disk)]
    return (not back,
            f"{len(back)} pruned graphic(s) were extracted again",
            back[:8])


def rule_every_image_reference_resolves(data: _P, items, corrections):
    """An item pointing at a file that is not there shows a broken image.

    The WebP migration moved every file; anything whose reference did not move
    with it points at nothing.
    """
    assets = data / "_assets"
    missing = []
    for dom, it in items:
        img = str(it.get("img") or "")
        if not img or img.startswith("iconsets/"):
            continue
        if not (assets / img).is_file():
            missing.append(f"{it['name']} -> {img}")
    return (not missing,
            f"{len(missing)} item(s) reference an image file that is not there",
            missing[:8])


def rule_graphics_know_their_book(data: _P, items, corrections):
    """Flat storage threw the book away, so pairing could not key on it.

    p048_x1029.webp could be from any of fifty PDFs. Auto-pairing reported
    "0 items" for four reasons at once and that looked like an answer.
    """
    assets = data / "_assets"
    if not assets.is_dir():
        return True, "no _assets yet", []
    graphics = {p.name for p in assets.glob("*.*") if p.suffix.lower() in
                (".png", ".webp", ".jpg", ".jpeg") and not p.name.startswith("_")}
    if not graphics:
        return True, "no extracted graphics", []
    try:
        index = json.loads((assets / "_index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, f"no _index.json — none of {len(graphics)} graphics know their book", []
    unknown = sorted(graphics - set(index))
    # a curated library gets renamed by hand; require the bulk, not every file
    ok = len(unknown) <= max(10, len(graphics) // 20)
    return (ok,
            f"{len(unknown)} of {len(graphics)} graphic(s) are not in the "
            f"book/page index",
            unknown[:8])


RULES = [
    ("deletions stick", rule_deletions_stick),
    ("critters and NPCs await a portrait", rule_portraits_are_not_guessed),
    ("no remembered default for those types", rule_no_remembered_default_for_excluded_types),
    ("no art nobody references", rule_no_art_nobody_references),
    ("pruned art stays deleted", rule_pruned_art_stays_deleted),
    ("every image reference resolves", rule_every_image_reference_resolves),
    ("graphics know their book", rule_graphics_know_their_book),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any rule fails (used by the import)")
    args = ap.parse_args()

    data = args.data or data_root()
    print(f"verifying {data}", flush=True)
    items = list(_items(data))
    corrections = list(_corrections(data))
    print(f"  {len(items)} item(s), {len(corrections)} correction(s)", flush=True)

    failed = 0
    for name, rule in RULES:
        try:
            ok, message, offenders = rule(data, items, corrections)
        except Exception as e:                  # a broken rule is a failed rule
            ok, message, offenders = False, f"the check itself failed — {e!r}", []
        if ok:
            print(f"  OK    {name}")
            continue
        failed += 1
        print(f"  FAIL  {name}: {message}")
        for line in offenders:
            print(f"          {line}")

    if failed:
        print(f"\n{failed} of {len(RULES)} check(s) FAILED — the import finished "
              f"but the library is not what it should be.")
        print("Nothing above was caught by a phase; every one of these shipped "
              "once as a successful run.")
    else:
        print(f"\nall {len(RULES)} check(s) passed")
    return 1 if (failed and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
