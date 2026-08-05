"""Accessory mounting and adept-power metadata — the parts of the gear model
the item merge deliberately flattens away.

Commlink6 models accessory fitting as a two-sided contract:

* the **host** declares its mount slots
  ``<itemmod type="HOOK" ref="TOP"/>``
* the **accessory** declares which slots it fits, and optionally which host
  subtypes will take it
  ``<usage mode="EMBEDDED" slot="BARREL"/>``
  ``<requires><selreq><valuereq ref="ITEMSUBTYPE" value="PISTOLS_HEAVY"/>…``

A host may also ship with accessories already fitted
(``<embed type="GEAR" ref="smartgun_system" included="true"/>``), which cost
nothing extra and occupy their slot.

Adept powers are a separate shape entirely:
``<power id="improved_reflexes" cost="1.5" hasLevel="true" multi="yes"/>`` —
``cost`` is power points *per level*, which is why a leveled power like
Improved Reflexes can be bought at 1, 2 or 3.
"""
from __future__ import annotations

import re
import zipfile

from extractor.chargen_xml import read_category_trees

#: Books published in German; out of scope for this project.
GERMAN_BOOKS = {
    "de_alpen", "de_berlin2080", "de_bundeswehr", "de_feuerlaeufer", "de_other",
    "de_piraten", "de_revierbericht", "de_sota2081", "de_sota2082",
    "de_sota2083", "de_westphalen", "kechibi", "lofwyr", "emerald",
    "power_plays", "shadow_cast", "slip_streams", "collapsing_now",
}

_DATA_FILE = re.compile(r"de/rpgframework/shadowrun6/data/([^/]+)/data/([^/]+)\.xml$")


def english_data_files(z: zipfile.ZipFile, pattern: str = r".*") -> list[tuple[str, str]]:
    """[(book, category)] for every English data file matching `pattern`."""
    rx = re.compile(pattern)
    out = []
    for n in z.namelist():
        m = _DATA_FILE.match(n)
        if m and m.group(1) not in GERMAN_BOOKS and rx.match(m.group(2)):
            out.append((m.group(1), m.group(2)))
    return out


def _children(tree: dict, tag: str) -> list[dict]:
    return [c for c in tree.get("children", []) if c["tag"] == tag]


def _first(tree: dict, tag: str) -> dict | None:
    for c in tree.get("children", []):
        if c["tag"] == tag:
            return c
    return None


def parse_item_mounts(trees: list[dict]) -> dict:
    """One data file -> {genesisID: {hooks[], fits[], hostSubtypes[], embedded[]}}.

    Only entries that actually say something about mounting are returned, so
    the result stays small enough to ship in chargen-data.
    """
    out: dict = {}
    for t in trees:
        if t["tag"] != "item":
            continue
        gid = t["attrs"].get("id")
        if not gid:
            continue

        hooks: list[str] = []
        embedded: list[dict] = []
        mods = _first(t, "modifications")
        for m in (mods["children"] if mods else []):
            a = m.get("attrs", {})
            if m["tag"] == "itemmod" and a.get("type") == "HOOK" and a.get("ref"):
                hooks.append(a["ref"])
            elif m["tag"] == "embed" and a.get("ref"):
                embedded.append({
                    "ref": a["ref"],
                    "slot": a.get("intoRef") or "",
                    "included": a.get("included") == "true",
                    "variant": a.get("variant") or None,
                })

        # which slots this item can be fitted INTO
        fits = [u["attrs"]["slot"] for u in _children(t, "usage")
                if u["attrs"].get("slot")]

        # host subtypes that accept it (empty = no restriction)
        host_subtypes: list[str] = []
        req = _first(t, "requires")
        for sel in (req["children"] if req else []):
            for vr in sel.get("children", []) if sel["tag"] == "selreq" else []:
                a = vr.get("attrs", {})
                if a.get("ref") == "ITEMSUBTYPE" and a.get("value"):
                    host_subtypes.append(a["value"])

        # variants can fit different slots again (e.g. an internal smartgun)
        variants = {}
        for v in _children(t, "variant"):
            vslots = [u["attrs"]["slot"] for u in _children(v, "usage")
                      if u["attrs"].get("slot")]
            if vslots:
                variants[v["attrs"].get("id", "")] = vslots

        if hooks or fits or embedded or host_subtypes:
            rec = {}
            if hooks:
                rec["hooks"] = sorted(set(hooks))
            if fits:
                rec["fits"] = sorted(set(fits))
            if host_subtypes:
                rec["hostSubtypes"] = sorted(set(host_subtypes))
            if embedded:
                rec["embedded"] = embedded
            if variants:
                rec["variantSlots"] = variants
            out[gid] = rec
    return out


def parse_adept_powers(trees: list[dict], i18n: dict, book: str) -> dict:
    """adeptpowers.xml -> {id: {name, cost, hasLevel, multi, action}}.

    ``cost`` is power points PER LEVEL. A power with ``hasLevel`` may be bought
    at rank 1..n, each rank costing ``cost`` again — Improved Reflexes at 1.5
    per level is 1.5 / 3.0 / 4.5 PP for levels 1 / 2 / 3.
    """
    out: dict = {}
    for t in trees:
        if t["tag"] != "power":
            continue
        a = t["attrs"]
        pid = a.get("id")
        if not pid:
            continue
        text = i18n.get(pid) or i18n.get(pid.lower()) or {}
        try:
            cost = float(a.get("cost", 0))
        except (TypeError, ValueError):
            cost = 0.0
        out[pid] = {
            "name": text.get("name") or pid.replace("_", " ").title(),
            "cost": cost,
            "hasLevel": a.get("hasLevel") == "true",
            "multi": a.get("multi") in ("yes", "true"),
            "action": a.get("act", ""),
            "book": book,
            "page": text.get("page", ""),
        }
    return out


def build_gear_meta(z: zipfile.ZipFile) -> dict:
    """Mount metadata for every English gear/accessory file in the jar."""
    mounts: dict = {}
    for book, cat in english_data_files(z, r"(gear|weapon|armor|vehicle|drone|cyber|bio|nano|gene|accessor|electronic|software|tool|survival|chemical|magical|ammo).*"):
        mounts.update(parse_item_mounts(read_category_trees(z, book, cat)))
    return mounts
