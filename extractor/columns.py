from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Column:
    pattern: str
    convert: Callable[[str], dict]


def _dv(v: str) -> dict:
    if v == "Special":
        return {"dmg": 0, "stun": False, "dmgDef": "Special"}
    m = re.match(r"(\d{1,2})([PS])", v)
    return {"dmg": int(m.group(1)), "stun": m.group(2) == "S", "dmgDef": v}


def _modes(v: str) -> dict:
    parts = set(v.split("/"))
    return {"modes": {m: m in parts for m in ("SS", "SA", "BF", "FA")}}


def _ar(v: str) -> dict:
    slots = []
    for tok in v.split("/"):
        tok = tok.replace("*", "")
        slots.append(0 if tok in ("", "—") else int(tok))
    return {"attackRating": slots}


def _ammo(v: str) -> dict:
    out = {"ammocap": int(re.match(r"\d+", v).group())}
    if " or " in v:
        out["_note"] = f"Ammo: {v}"
    return out


def _avail(v: str) -> dict:
    if v == "—":
        return {"avail": 0, "availDef": "—"}
    if v == "Rating":
        return {"avail": 0, "availDef": "Rating", "needsRating": True}
    return {"avail": int(re.match(r"\d+", v).group()), "availDef": v}


def _cost(v: str) -> dict:
    if v.startswith(("Rating", "Force", "Capacity")):
        return {"price": 0, "priceDef": v, "needsRating": True}
    return {"price": int(v.lstrip("+").rstrip("¥").replace(",", ""))}


def _essence(v: str) -> dict:
    if v == "—":
        return {"essence": 0}
    if v.startswith("Rating"):
        return {"essence": 0, "needsRating": True, "_note": f"Essence: {v}"}
    return {"essence": float(v)}


def _capacity(v: str) -> dict:
    if v in ("[Rating]", "Rating") or "—" in v and v != "—":
        return {"capacity": 0, "needsRating": True}  # rating word or a 1—6 span
    if v.startswith("["):
        return {"capacity": int(v.strip("[]"))}
    return {"capacity": 0 if v == "—" else int(v)}


def _defense(v: str) -> dict:
    return {"defense": int(v.lstrip("+"))}


def _mount(v: str) -> dict:
    return {} if v == "—" else {"_note": f"Mount: {v}"}


def _ratingspan(v: str) -> dict:
    if v == "n/a":
        return {}
    if "—" in v:
        return {"needsRating": True}
    return {"rating": int(v)}


def _pricecap(v: str) -> dict:
    m = re.match(r"([\d,]+)¥\((\d+)\)", v)
    return {"price": int(m.group(1).replace(",", "")), "capacity": int(m.group(2))}


def _seat(v: str) -> dict:
    if v == "—":
        return {"sea": 0}
    if "/" in v:
        return {"sea": int(v.split("/")[0]), "_note": f"Seats: {v}"}
    return {"sea": int(v)}


COLUMNS: dict[str, Column] = {
    "dv": Column(r"(?:\d{1,2}[PS](?:\([a-z]+\))?(?: \+ special)?|Special)", _dv),
    "modes": Column(r"(?:SS|SA|BF|FA)(?:/(?:SS|SA|BF|FA))*", _modes),
    "ar": Column(r"[0-9*—]+(?:/[0-9*—]+){4}", _ar),
    "ammo": Column(r"\d+(?:\([a-z]+\))?(?: or \d+\([a-z]+\))?", _ammo),
    "avail": Column(r"(?:—|Rating|\d{1,2}L|\d{1,2}(?:\([A-Z]\))?)", _avail),
    "cost": Column(r"(?:(?:Rating(?:\^2)?|Force|Capacity) x [\d,]+¥|[+]?[\d,]+¥)", _cost),
    "essence": Column(r"(?:—|Rating x \d+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", _essence),
    "capacity": Column(r"(?:\[Rating\]|Rating|\[\d\]|[\d—]+)", _capacity),
    "defense": Column(r"[+]?\d+", _defense),
    "mount": Column(r"(?:—|Top or Under|Top|Under|Barrel|Stock|Internal)", _mount),
    "ratingspan": Column(r"(?:n/a|\d{1,2}—\d{1,2}|\d{1,2})", _ratingspan),
    "pricecap": Column(r"[\d,]+¥\(\d+\)", _pricecap),
    "seat": Column(r"(?:—|\d+(?:/\d+)?)", _seat),
}


def make_note_column(label: str) -> Column:
    text = label.replace("_", " ")
    return Column(r"\S+", lambda v, t=text: {"_note": f"{t}: {v}"})


def make_pricecapnote_column(label: str) -> Column:
    text = label.replace("_", " ")
    return Column(r"[\d,]+¥\(\d+\)", lambda v, t=text: {"_note": f"{t}: {v}"})


def make_int_column(field: str) -> Column:
    return Column(r"[\d—]+", lambda v, f=field: {f: 0 if v == "—" else int(v)})


def make_plusint_column(field: str) -> Column:
    return Column(r"[+]?\d+", lambda v, f=field: {f: int(v.lstrip("+"))})


def make_onoff_column(on: str, off: str) -> Column:
    def conv(v: str, on=on, off=off) -> dict:
        if "/" in v:
            a, b = v.split("/", 1)
            return {on: int(a), off: int(b)}
        return {on: int(v), off: int(v)}

    return Column(r"\d+(?:/\d+)?", conv)


def make_text_column(field: str) -> Column:
    return Column(r"\S+", lambda v, f=field: {f: v})


def resolve(key: str) -> Column:
    if key in COLUMNS:
        return COLUMNS[key]
    if key.startswith("int:"):
        return make_int_column(key[4:])
    if key.startswith("plusint:"):
        return make_plusint_column(key[8:])
    if key.startswith("onoff:"):
        _, on, off = key.split(":")
        return make_onoff_column(on, off)
    if key.startswith("text:"):
        return make_text_column(key[5:])
    if key.startswith("note:"):
        return make_note_column(key[5:])
    if key.startswith("pricecapnote:"):
        return make_pricecapnote_column(key[13:])
    raise KeyError(f"unknown column type {key!r}")
