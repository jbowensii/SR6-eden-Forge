"""Stable catalog ids.

Eden matches items on ``system.genesisID`` and keys localisation and icons off
``<type>.<genesisID>``, so every exported record needs one that does not move.

Two sources:

**Commlink6 records already have one.** They carry ``cl6_<id>`` and record
``meta.source: "commlink6"``. That id is the cross-reference eden itself
matches on, and it is never regenerated.

**PDF-only records get one minted** as ``<cat>_<domain>_<slug>`` — the Catalyst
product code from ``books.json`` (CAT28000), the domain, and the name slug.

Page numbers are deliberately *not* part of the id. They are worth recording in
``meta.page``, but they shift between printings — the corebook PDF here is a
"Current Printing" — so an id built on them would break on the next edition.

The lockfile is what makes this survive editing. An id is minted once and
written to ``data/_ids/<book>.json`` against the record's *origin*, so
correcting a name in the review app afterwards does not move the id, and does
not orphan the character sheets pointing at it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

LOCK_DIR = "_ids"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """A name reduced to its stable core: lowercase, ascii, underscores."""
    s = (name or "").lower()
    # smart quotes and dashes appear constantly in extracted text
    s = s.replace("’", "").replace("‘", "").replace("'", "")
    s = _SLUG_STRIP.sub("_", s).strip("_")
    return s or "unnamed"


def origin_key(book: str, domain: str, item: dict) -> str:
    """What a record *is*, independent of what it is currently called.

    Uses the name it had when first extracted, so a later correction in the
    review app still resolves to the same lock entry. Page is included because
    two genuinely different items can share a name within a book, and their
    pages will not.
    """
    meta = item.get("meta") or {}
    first = meta.get("originalName") or item.get("name") or ""
    page = meta.get("page") or 0
    return f"{book}/{domain}/{page}/{slugify(first)}"


class IdLock:
    """The per-book id lockfile: origin -> assigned catalog id."""

    def __init__(self, data_root: Path, book: str):
        self.path = Path(data_root) / LOCK_DIR / f"{book}.json"
        self.book = book
        self._map: dict[str, str] = {}
        self._taken: set[str] = set()
        if self.path.is_file():
            try:
                self._map = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._map = {}
            self._taken = set(self._map.values())

    def get(self, key: str) -> str | None:
        return self._map.get(key)

    def assign(self, key: str, candidate: str) -> str:
        """Return the id for ``key``, minting ``candidate`` if it has none.

        A candidate already taken by a different origin gets a numeric suffix,
        and that resolution is recorded — so the pair never swap on a later run
        just because extraction order changed.
        """
        existing = self._map.get(key)
        if existing:
            return existing
        cid = candidate
        n = 2
        while cid in self._taken:
            cid = f"{candidate}_{n}"
            n += 1
        self._map[key] = cid
        self._taken.add(cid)
        return cid

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(dict(sorted(self._map.items())), indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")


def catalog_id(item: dict, book: str, domain: str, cat: str, lock: IdLock) -> str:
    """The catalog id for one record, minting and locking it if needed."""
    sysd = item.setdefault("system", {})
    meta = item.setdefault("meta", {})

    # 1. an upstream id always wins and is never regenerated
    upstream = sysd.get("genesisID") or sysd.get("catalogId")
    if upstream:
        return upstream
    if meta.get("source") == "commlink6":
        # jar-sourced rows carry the id in the record id as cl6_<id>
        rid = str(item.get("id") or "")
        if rid.startswith("cl6_"):
            return rid[4:]

    # 2. mint from the product code, and lock it
    prefix = (cat or book).lower().replace("-", "")
    candidate = f"{prefix}_{domain}_{slugify(item.get('name', ''))}"
    return lock.assign(origin_key(book, domain, item), candidate)


def stamp_catalog_ids(items: list[dict], book: str, domain: str, cat: str,
                      lock: IdLock) -> int:
    """Give every record in ``items`` a catalog id. Returns how many were new."""
    minted = 0
    for it in items:
        sysd = it.setdefault("system", {})
        if sysd.get("genesisID"):
            continue
        # remember the name it arrived with, so edits cannot move its identity
        meta = it.setdefault("meta", {})
        meta.setdefault("originalName", it.get("name"))
        sysd["genesisID"] = catalog_id(it, book, domain, cat, lock)
        minted += 1
    return minted
