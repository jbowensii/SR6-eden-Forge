"""Companion gear PACKs — pre-built bundles bought as a single purchase.

A PACK is an item of ``type="PACK"`` carrying one price (and, for augmentation
packs, one ESSENCECOST) whose ``<modifications>`` block lists what the buyer
actually receives. Commlink6 sells these from its chargen gear page; the price
on the PACK replaces the sum of its parts, which is the whole point of buying
one.

Three modification forms matter:

``itemmod``  add one of ``ref`` (optionally a named ``variant``). An ``id``
             attribute is a *local handle* so later ``embed`` rows can target
             this exact copy.
``valmod``   the same, but ``value`` is a quantity — two stim patches, ten
             stealth tags.
``embed``    fit ``ref`` into a hook of an earlier row, matched by ``intoId``
             against that row's local handle.

Both carry ``<decision>`` children. A decision names a ``choice`` by UUID, and
the UUID is only meaningful against the ``<choice>`` definitions elsewhere in
the data — the same UUID means RATING on one item and GRADE on another only
because those items declare it so. Rather than hardcode the handful of UUIDs
that happen to appear, :func:`choice_kinds` reads every ``<choice>`` in the jar
and maps UUID -> what it selects, so a future book adding a new one still
resolves.

German-language PACKs (``lang="de"``) are skipped: this project imports the
English books only.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile

#: The five Companion files holding PACK definitions.
PACK_FILES = ("packs-augments", "packs-weapons", "packs-complete",
              "packs-other", "packs-vehicles")

_PACK_PATH = "de/rpgframework/shadowrun6/data/companion/data/{}.xml"
_CHOICE = re.compile(rb'<choice\b[^>]*>')
_UUID = re.compile(rb'uuid="([^"]+)"')
_REF = re.compile(rb'ref="([^"]+)"')
_TYPE = re.compile(rb'type="([^"]+)"')


def choice_kinds(z: zipfile.ZipFile) -> dict[str, str]:
    """choice UUID -> what it selects ("RATING", "GRADE", "TEXT", ...)."""
    out: dict[str, str] = {}
    for name in z.namelist():
        if not name.endswith(".xml"):
            continue
        for m in _CHOICE.finditer(z.read(name)):
            tag = m.group()
            u = _UUID.search(tag)
            if not u:
                continue
            uid = u.group(1).decode()
            ref = _REF.search(tag)
            typ = _TYPE.search(tag)
            kind = (ref.group(1) if ref else (typ.group(1) if typ else b"")).decode()
            # first definition wins; they agree in practice
            out.setdefault(uid, kind or "TEXT")
    return out


#: Augmentation grades. The grade selector is built into Commlink6 rather than
#: declared as a <choice>, so its UUID resolves to nothing and the value is the
#: only reliable signal. Confirmed against the pack data: USED, STANDARD, ALPHA.
GRADES = {"USED", "STANDARD", "ALPHA", "BETA", "DELTA", "GAMMA"}

#: Fake SIN / fake licence quality levels -> rating. These are NOT in an
#: intuitive order (superficially plausible is 4, not 1), so they are taken
#: from Commlink6's own English labels rather than inferred:
#:     ShadowrunCore.properties  "fakequality.rough_match = 2 - Rough match"
SIN_LEVELS = {
    "ROUGH_MATCH": 2,
    "GOOD_MATCH": 3,
    "SUPERFICIALLY_PLAUSIBLE": 4,
    "HIGHLY_PLAUSIBLE": 5,
    "SECOND_LIFE": 6,
}

#: What a modification row grants. Everything else in the pack files is gear.
ROW_KINDS = {"GEAR": "gear", "SIN": "sin", "LICENSE": "license",
             "LIFESTYLE": "lifestyle"}


def _decisions(el: ET.Element, kinds: dict[str, str]) -> dict:
    """Collapse <decision> children into {rating, grade, text}."""
    out: dict = {"rating": None, "grade": None, "text": None}
    for d in el.findall("decision"):
        kind = kinds.get(d.get("choice", ""), "TEXT")
        value = d.get("value")
        if value in GRADES:
            out["grade"] = value
        elif kind == "RATING":
            try:
                out["rating"] = int(value)
            except (TypeError, ValueError):
                out["text"] = value
        elif kind in ("GRADE", "QUALITY_GRADE"):
            out["grade"] = value
        elif kind == "ITEM_ATTRIBUTE":
            # a rated attribute whose ref we could not narrow further
            try:
                out["rating"] = int(value)
            except (TypeError, ValueError):
                out["text"] = value
        else:
            out["text"] = value
    return out


def parse_pack(item: ET.Element, kinds: dict[str, str]) -> dict:
    """One <item type="PACK"> -> {id, price, essence, subtype, contents}."""
    essence = 0.0
    for a in item.findall("attrdef"):
        if a.get("id") == "ESSENCECOST":
            try:
                essence = float(a.get("value") or 0)
            except ValueError:
                essence = 0.0

    rows: list[dict] = []
    by_handle: dict[str, dict] = {}
    for mods in item.findall("modifications"):
        for el in mods:
            if el.tag in ("itemmod", "valmod"):
                qty = 1
                if el.tag == "valmod":
                    try:
                        qty = int(el.get("value") or 1)
                    except ValueError:
                        qty = 1
                kind = ROW_KINDS.get(el.get("type") or "GEAR", "gear")
                ref = el.get("ref")
                row = {
                    "kind": kind,
                    "ref": ref,
                    "variant": el.get("variant"),
                    "qty": qty,
                    **_decisions(el, kinds),
                    "embeds": [],
                }
                # SINs and licences name a quality level, not a catalog item —
                # carry the rating and drop the ref, which resolves to nothing
                if kind in ("sin", "license"):
                    row["rating"] = SIN_LEVELS.get(ref)
                    row["level"] = ref
                    row["ref"] = None
                    if kind == "license":
                        row["ofSin"] = el.get("sin")     # which SIN it belongs to
                rows.append(row)
                if el.get("id"):
                    by_handle[el.get("id")] = row
            elif el.tag == "embed":
                host = by_handle.get(el.get("intoId") or "")
                embed = {
                    "ref": el.get("ref"),
                    "hook": el.get("intoRef"),
                    **_decisions(el, kinds),
                }
                if host is not None:
                    host["embeds"].append(embed)
                else:
                    # an embed whose host is not in this pack: keep it as a
                    # top-level row rather than dropping it silently
                    rows.append({"kind": "gear", "ref": embed["ref"], "variant": None,
                                 "qty": 1, "rating": embed["rating"],
                                 "grade": embed["grade"], "text": embed["text"],
                                 "embeds": [], "orphanHook": embed["hook"]})
            # selmod: a player-facing selection with no fixed answer. Recorded
            # so the count is honest, but it carries nothing to grant.
            elif el.tag == "selmod":
                rows.append({"kind": "gear", "ref": el.get("ref"),
                             "variant": el.get("variant"), "qty": 1, "rating": None,
                             "grade": None, "text": None, "embeds": [], "choose": True})

    price = 0
    try:
        price = int(item.get("price") or 0)
    except ValueError:
        price = 0
    return {
        "id": item.get("id"),
        "price": price,
        "essence": essence,
        "subtype": item.get("subtype"),
        "contents": rows,
    }


def parse_packs(z: zipfile.ZipFile, names: dict[str, str] | None = None) -> dict:
    """Every English PACK in the jar, keyed by catalog id."""
    kinds = choice_kinds(z)
    out: dict = {}
    for f in PACK_FILES:
        try:
            raw = z.read(_PACK_PATH.format(f))
        except KeyError:
            continue
        for item in ET.fromstring(raw).iter("item"):
            if item.get("type") != "PACK":
                continue
            if item.get("lang") == "de":
                continue                      # English books only
            pack = parse_pack(item, kinds)
            pack["file"] = f
            # sub_i18n yields {name, page, desc} per id; older callers pass a
            # plain string, so accept both
            entry = (names or {}).get(pack["id"])
            if isinstance(entry, dict):
                pack["name"] = entry.get("name") or pack["id"].replace("_", " ").title()
                pack["page"] = entry.get("page")
                pack["description"] = entry.get("desc")
            else:
                pack["name"] = entry or pack["id"].replace("_", " ").title()
            out[pack["id"]] = pack

    # A pack may list another pack among its contents (pack_hacker_a includes
    # pack_cyberprograms). Flatten those in, so a buyer gets the real gear
    # rather than a row naming a bundle nothing later expands.
    for pack in out.values():
        pack["contents"] = _flatten(pack["contents"], out, seen={pack["id"]})
    return out


def _flatten(rows: list[dict], packs: dict, seen: set[str], depth: int = 0) -> list[dict]:
    """Replace rows that name another pack with that pack's own contents."""
    if depth > 4:                      # cycle guard; real data nests one deep
        return rows
    out: list[dict] = []
    for r in rows:
        inner = packs.get(r.get("ref")) if r.get("kind", "gear") == "gear" else None
        if inner and r["ref"] not in seen:
            out.extend(_flatten(inner["contents"], packs, seen | {r["ref"]}, depth + 1))
        else:
            out.append(r)
    return out
