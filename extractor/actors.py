"""Reader for actor stat blocks (NPC archetypes, and later spirits/critters).

Each archetype is a 21pt name, a description, "metatype:", an attribute array
(B A R S W L I C EDG M/RES ESS), and labelled fields (Active Skills, Qualities,
Gear, Weapons, …). Labels are unique, so the block is parsed by splitting on
them. No book content lives here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

# labelled fields -> (header regex, system key). Order doesn't matter; positions
# are found and the text between consecutive labels is the value.
_LABELS = [
    (r"metatype:", "metatype"), (r"Initiative/Actions:", "initiative"),
    (r"Condition Monitors\s*\([^)]*\):", "conditionMonitors"), (r"Defense Rating:", "defenseRating"),
    (r"Active Skills:", "activeSkills"), (r"Knowledge Skills:", "knowledgeSkills"),
    (r"Languages:", "languages"), (r"Qualities:", "qualities"), (r"Spells:", "spells"),
    (r"Complex Forms:", "complexForms"), (r"Adept Powers:", "adeptPowers"),
    (r"Powers:", "powers"), (r"Bioware:", "bioware"), (r"Cyberware:", "cyberware"),
    (r"Augmentations:", "augmentations"), (r"Contacts:", "contacts"),
    (r"Lifestyle:", "lifestyle"), (r"Gear:", "gear"), (r"Starting Nuyen:", "nuyen"),
    (r"Weapons:", "weapons"),
]
# the attribute array; Magic/Resonance is absent for mundane actors (10 values)
_ATTR_HEADER = re.compile(r"\bB\s+A\s+R\s+S\s+W\s+L\s+I\s+C\s+EDG\s+((?:M|RES|R)\s+)?ESS\b")
_ATTR_KEYS = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha", "edg", "magres", "ess"]


def _name_of(page):
    words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
    if not words:
        return None
    top = max(round(w["size"], 1) for w in words)
    if top < 17:
        return None
    line = sorted((w for w in words if round(w["size"], 1) == top), key=lambda w: (round(w["top"]), w["x0"]))
    name = normalize_text(" ".join(w["text"] for w in line)).strip()
    return name if 2 <= len(name) <= 40 and not name[0].isdigit() else None


def _labelled(text: str) -> dict:
    positions = []
    for pattern, key in _LABELS:
        m = re.search(rf"(?:^|\s){pattern}\s*", text)
        if m:
            positions.append((m.start(), m.end(), key))
    positions.sort()
    out = {}
    for i, (_s, e, key) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        val = re.sub(r"\s+", " ", text[e:end]).strip().strip(",")
        if key == "metatype":  # a single word; the attribute array follows it
            mm = re.match(r"[A-Za-z]+", val)
            val = mm.group(0) if mm else val
        if val:
            out[key] = val
    return out


def _attributes(text: str) -> dict:
    m = _ATTR_HEADER.search(text)
    if not m:
        return {}
    has_mag = bool(m.group(1))
    keys = _ATTR_KEYS if has_mag else [k for k in _ATTR_KEYS if k != "magres"]
    nums = re.findall(r"\d+(?:\.\d+)?(?:\(\d+\))?", text[m.end():m.end() + 90])[:len(keys)]
    if len(nums) < len(keys):
        return {}
    attrs = {}
    for k, v in zip(keys, nums):
        base = v.split("(")[0]  # keep the base value; augmented is in parens
        attrs[k] = float(base) if k == "ess" else int(float(base))
    return attrs


def read_actors(pdf_path, pages, category="NPC") -> list[dict]:
    import pdfplumber

    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            name = _name_of(page)
            text = normalize_text(page.extract_text() or "")
            if not name or "metatype:" not in text.lower():
                continue
            system = {"category": category}
            attrs = _attributes(text)
            if attrs:
                system["attributes"] = attrs
            system.update(_labelled(text))
            # description = prose before the metatype line
            head = text[:re.search(r"metatype:", text, re.I).start()]
            desc = _dehyphenate([l for l in head.splitlines() if l.strip()][1:])  # drop the name line
            if len(desc) > 40:
                system["description"] = desc
            items.append({"name": name, "system": system, "page": page_no})
    return items
