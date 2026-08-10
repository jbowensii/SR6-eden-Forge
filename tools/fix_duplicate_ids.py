"""Resolve items that share a catalog id, so a domain can be exported.

An id has to be unique within its domain — the export compiles a domain into one
compendium pack and refuses a pack with two documents claiming the same id. It
refuses the WHOLE pack, so ten collisions were enough to drop gear, vehicles and
the Commlink6 tables out of the module entirely while the build still reported
"done".

Two quite different things produce a collision, and they want opposite fixes:

*same item, filed twice* — same name, same book, same page. One row is a stray
    copy (the naval weapons were written into both ``weapons_firearms`` and
    ``weapons_special``). The fuller row is kept and the other is dropped.

*different items, same id* — Commlink6 derives ids from names, so the Edge
    action "Focus" and the spell feature "Focus" arrive with the same id despite
    having nothing to do with each other. Neither may be deleted; the row from
    the earlier book keeps the id and the other is re-minted.

The bias is deliberate: re-minting is reversible and losing an item is not, so
anything short of "same name, same book, same page" is treated as two items.

    python tools/fix_duplicate_ids.py --dry-run
    python tools/fix_duplicate_ids.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root                 # noqa: E402


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").casefold())


def book_order(data: _P) -> dict[str, str]:
    """book -> publication date, for deciding which row keeps the id."""
    try:
        books = json.loads((data / "books.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: str(v.get("date") or "") for k, v in books.items() if isinstance(v, dict)}


def filled(item: dict) -> int:
    """How much this row actually carries — used to pick the survivor."""
    system = item.get("system") or {}
    return sum(1 for v in system.values() if v not in (None, "", [], {}, 0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = args.data or data_root()
    dates = book_order(data)

    for book_dir in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for domain in sorted(d for d in book_dir.iterdir() if d.is_dir()):
            payloads = {p: json.loads(p.read_text(encoding="utf-8"))
                        for p in sorted(domain.glob("*.json"))}
            rows: dict[str, list[tuple[_P, dict]]] = defaultdict(list)
            for path, payload in payloads.items():
                for item in payload.get("items", []):
                    if item.get("id"):
                        rows[item["id"]].append((path, item))
            taken = set(rows)
            dupes = {i: r for i, r in rows.items() if len(r) > 1}
            if not dupes:
                continue

            print(f"\n{domain.name}: {len(dupes)} duplicate id(s)")
            touched: set[_P] = set()
            for item_id, group in sorted(dupes.items()):
                # earliest book keeps the id; unknown dates sort last
                group = sorted(group, key=lambda pi: (
                    dates.get((pi[1].get("meta") or {}).get("book", ""), "9999"),
                    (pi[1].get("meta") or {}).get("book", "")))
                keeper_path, keeper = group[0]
                for path, item in group[1:]:
                    same_thing = (
                        norm(item.get("name")) == norm(keeper.get("name"))
                        and (item.get("meta") or {}).get("book") == (keeper.get("meta") or {}).get("book")
                        and (item.get("meta") or {}).get("page") == (keeper.get("meta") or {}).get("page"))
                    if same_thing:
                        # one of them is a stray copy: keep whichever carries more
                        drop_path, drop = ((keeper_path, keeper) if filled(item) > filled(keeper)
                                           else (path, item))
                        if drop is keeper:
                            keeper_path, keeper = path, item
                        payloads[drop_path]["items"] = [
                            i for i in payloads[drop_path]["items"] if i is not drop]
                        touched.add(drop_path)
                        print(f"  {item_id}: dropped the copy in {drop_path.name} "
                              f"({drop.get('name')!r})")
                        continue
                    n = 2
                    while f"{item_id}_{n}" in taken:
                        n += 1
                    new_id = f"{item_id}_{n}"
                    taken.add(new_id)
                    item["id"] = new_id
                    touched.add(path)
                    print(f"  {item_id}: {item.get('name')!r} in {path.name} -> {new_id}")

            if not args.dry_run:
                for path in touched:
                    path.write_text(json.dumps(payloads[path], indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8")

    if args.dry_run:
        print("\n(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
