from __future__ import annotations

import importlib.util
from pathlib import Path

import extractor
from extractor.cache import read_page
from extractor.emit import build_item, slugify, write_category
from extractor.profiles import get_profile
from extractor.rowengine import parse_block
from extractor.segment import block_after_header


def _load_fixes(data_root: Path, book: str, domain: str):
    """Correction tables (RENAMES/OVERRIDES/EXCLUDE/MANUAL_ITEMS) reference
    real item names and stats, so they live beside the data they correct —
    in the gitignored data tree — not in the public repo."""
    path = data_root / "_fixes" / f"{book}_{domain}_fixes.py"
    if not path.is_file():
        print(f"WARNING: {path} not found — output will contain uncorrected names/stats")
        return None
    spec = importlib.util.spec_from_file_location(f"{book}_{domain}_fixes", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _merged_hooks(profile, fixes):
    renames: dict = dict(getattr(profile, "RENAMES", {}))
    overrides: dict = dict(getattr(profile, "OVERRIDES", {}))
    exclude: set = set(getattr(profile, "EXCLUDE", set()))
    manual: list = list(getattr(profile, "MANUAL_ITEMS", []))
    if fixes:
        renames.update(getattr(fixes, "RENAMES", {}))
        overrides.update(getattr(fixes, "OVERRIDES", {}))
        exclude |= set(getattr(fixes, "EXCLUDE", set()))
        manual += list(getattr(fixes, "MANUAL_ITEMS", []))
    return renames, overrides, exclude, manual


def parse_book(book: str, domain: str, data_root: Path, categories: list[str]) -> int:
    """Parse cached pages into category JSON files.

    Profile modules provide TABLES (list[TableSpec]); correction hooks come
    from the profile and/or a local fixes module (data/_fixes/):
    - EXCLUDE: set of (category, id-slug) parsed rows to drop
    - RENAMES: {(category, id-slug[, page]): corrected item name}
    - OVERRIDES: {(category, id-slug[, page]): dict merged into system}
    - MANUAL_ITEMS: [{category, name, system, page}] for unparseable rows

    Every hook key must fire during a full parse; stale keys (typos, or
    orphaned by engine changes) fail the run loudly.
    """
    profile = get_profile(book, domain)
    fixes = _load_fixes(data_root, book, domain)
    specs = list(profile.TABLES)
    renames, overrides, exclude, manual = _merged_hooks(profile, fixes)
    if categories:
        specs = [s for s in specs if s.category in categories]
        manual = [m for m in manual if m["category"] in categories]
    if not specs and not manual:
        print("no categories matched")
        return 1
    used_keys: set = set()
    by_category: dict[str, list[dict]] = {s.category: [] for s in specs}
    for entry in manual:
        by_category.setdefault(entry["category"], [])
    for spec in specs:
        for page in spec.pages:
            text = read_page(data_root, book, page)
            lines = block_after_header(text, spec.header_regex, spec.stop_regexes)
            noise = {page - 1, page, page + 1}
            for name, system in parse_block(lines, spec.row_spec, page_numbers=noise):
                slug = slugify(name)
                if (spec.category, slug) in exclude:
                    used_keys.add((spec.category, slug))
                    continue
                # page-qualified keys win over category-wide ones (rating-row
                # names like "Rating 2" repeat across tables on different pages)
                for key in ((spec.category, slug, page), (spec.category, slug)):
                    if key in renames:
                        name = renames[key]
                        used_keys.add(key)
                        break
                for key in ((spec.category, slug, page), (spec.category, slug)):
                    if key in overrides:
                        system = {**system, **overrides[key]}
                        used_keys.add(key)
                        break
                meta_page = spec.page_override or page
                by_category[spec.category].append(
                    build_item(name, system, book, meta_page, extractor.__version__)
                )
    for entry in manual:
        by_category[entry["category"]].append(
            build_item(entry["name"], entry["system"], book, entry["page"], extractor.__version__)
        )
    empty = []
    for category, items in sorted(by_category.items()):
        write_category(data_root, book, domain, category, items)
        print(f"{category}: {len(items)} item(s)")
        if not items:
            empty.append(category)
    rc = 0
    if empty:
        print(f"EMPTY: {', '.join(empty)}")
        rc = 1
    in_scope = lambda key: not categories or key[0] in categories
    stale = [k for k in (set(renames) | set(overrides) | exclude) - used_keys if in_scope(k)]
    for key in sorted(stale, key=str):
        print(f"STALE HOOK KEY: {key}")
    if stale:
        rc = 1
    return rc
