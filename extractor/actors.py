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


# ── book-agnostic NPC/grunt stat-block reader ────────────────────────────────
# Splatbooks pack several NPCs per page as stat blocks (name heading, an EDG
# attribute array, then labelled fields) with no "metatype:" line and no one-per-
# page layout. Read each page as a left-then-right column stream (like critters),
# detect names body-relative, and key off the EDG attribute header.
from collections import Counter as _Counter

_NPC_LABELS = [(re.compile(rf"^{p}\s*", re.I), k) for p, k in _LABELS]
# a bare attribute value line (header dropped): 10 or 11 numbers ending in a
# decimal ESS, some augmented like "5(7)"; no letters/slashes (rules out the
# "DR I/ID AC CM MOVE" line that follows it).
_NPC_VALUES = re.compile(r"^\d{1,2}(?:\(\d+\))?(?: \d{1,2}(?:\(\d+\))?){8,9} \d+\.\d+$")
_NPC_NOT = {"npcs", "grunts", "contacts", "powers", "skills", "gear", "weapons",
            "qualities", "the awakened world", "spirits", "critters",
            "dr i/id ac cm move", "initiative", "condition monitor"}


def _npc_name_ok(text, sz, body):
    # supplement NPC names are short ALL-CAPS headings (BODYGUARD, FAST-TALKER),
    # so all-caps is allowed; "/" rules out the "DR I/ID AC CM MOVE" stat header.
    return (sz >= body * 1.18 and 1 <= len(text.split()) <= 5 and text[0:1].isupper()
            and text.lower() not in _NPC_NOT and not text[0].isdigit()
            and "//" not in text and ":" not in text and "." not in text and "/" not in text
            and not _ATTR_HEADER.search(text))


def _npc_attrs_from_values(line):
    nums = re.findall(r"\d+(?:\.\d+)?(?:\(\d+\))?", line)
    n = len(nums)
    if n not in (10, 11):            # mundane = 10 (EDG, no Magic); awakened = 11
        return {}
    keys = _ATTR_KEYS if n == 11 else [k for k in _ATTR_KEYS if k != "magres"]
    return {k: (float(v.split("(")[0]) if k == "ess" else int(float(v.split("(")[0])))
            for k, v in zip(keys, nums[:len(keys)])}


_METATYPE = re.compile(r"^Metatype:\s*(.+)", re.I)
# grunt/contact blocks (adventure books) label the metatype as "Male human" /
# "Female dwarf" instead of a "Metatype:" line, and anchor on the EDG header.
_GENDER_META = re.compile(r"^(?:Male|Female)\s+([A-Za-z]+)\b")
# a short demographics line naming the metatype: "Human", "Human male",
# "Male human", "A dwarf", "Elf, age 34". Only trusted on short lines with a
# single metatype word (ambiguous multi-metatype lines are left blank).
_METAS = ("human", "elf", "ork", "orc", "dwarf", "troll", "pixie", "gnome", "giant",
          "nartaki", "menehune", "hobgoblin", "oni", "koborokuru", "dryad",
          "sasquatch", "centaur", "naga", "changeling")
_META_WORD = re.compile(r"^(?:An?\s+)?(?:(?:male|female)\s+)?(" + "|".join(_METAS) + r")\b", re.I)


def _infer_metatype(text):
    """Return a metatype from a short demographics line, or None. Requires exactly
    one metatype word in the line (so 'elf … Human' ambiguity yields nothing)."""
    if len(text.split()) > 5:
        return None
    found = [w for w in re.findall(r"[A-Za-z]+", text) if w.lower() in _METAS]
    if len(found) != 1:
        return None
    m = _META_WORD.match(text)
    return m.group(1).lower() if m else None


def _name_candidate(text):
    """A stat-block title (BODYGUARD / Bodyguard / Fast-talker): a short line that
    is title-cased or all-caps, no colon/slash, not the attribute header. Stat-
    block names aren't reliably large fonts (they sit inline next to prose), so
    the name is found by looking back for the last such line before 'Metatype:'."""
    if not text or ":" in text or "/" in text or "(" in text or ")" in text:
        return False
    if text[0].isdigit() or text[0:1].islower() or any(c.isdigit() for c in text):
        return False
    words = text.split()
    if not (1 <= len(words) <= 5) or text.lower() in _NPC_NOT or _ATTR_HEADER.search(text):
        return False
    return all(w[0].isupper() or not w[0].isalpha() for w in words)


def read_npc_blocks(pdf_path, pages, category="NPC") -> list[dict]:
    """Anchor each NPC on its 'Metatype:' line (exactly one per stat block); the
    name is the last title-like line seen before it. Then read the EDG attribute
    array and the labelled fields (Skills, Gear, Weapons, …). Book-agnostic and
    multi-per-page."""
    # pylint: disable=unsubscriptable-object
    #   st["cur"] is None between blocks and a dict inside one, and every read
    #   is guarded by `if cur`. Pylint infers only the None arm and calls each
    #   subscript an error. The alternative is a class per block, which buys a
    #   clean report and nothing else.
    # pylint: disable=cell-var-from-loop
    #   flush() closes over the `st` of its own column and is called before the
    #   next iteration rebinds it. Late binding is never reached.
    import pdfplumber
    items = []

    def new_state():
        return {"cur": None, "pending": None, "pending_meta": None, "want_hdr": False}

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
            if not words:
                continue
            mid = page.width / 2
            for lo, hi in ((0, mid), (mid, page.width)):
                st = new_state()

                def flush():
                    cur = st["cur"]
                    if cur and "attributes" in cur["sys"]:
                        desc = _dehyphenate(cur["buf"])
                        system = {"category": category, **{k: v for k, v in cur["sys"].items() if k != "_last"}}
                        if len(desc) > 40:
                            system["description"] = desc
                        items.append({"name": cur["name"], "system": system, "page": cur["page"]})
                    st["cur"] = None

                for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
                    text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                    if not text:
                        continue
                    m = _METATYPE.match(text)
                    if m:
                        flush()
                        meta = re.match(r"[A-Za-z]+", m.group(1))
                        st["cur"] = {"name": st["pending"] or "NPC", "page": page_no, "buf": [],
                                     "sys": {"metatype": (meta.group(0) if meta else m.group(1).strip()).lower()}}
                        st["want_hdr"] = False
                        st["pending"] = None
                        continue
                    cur = st["cur"]
                    # the EDG attribute header also anchors a block — grunt/contact
                    # stat blocks have no "Metatype:" line. Start one if we aren't
                    # already mid-block (or the current block is already complete).
                    if _ATTR_HEADER.search(text):
                        if cur is None or "attributes" in cur["sys"]:
                            flush()
                            sysd = {"metatype": st["pending_meta"]} if st["pending_meta"] else {}
                            st["cur"] = {"name": st["pending"] or "NPC", "page": page_no,
                                         "buf": [], "sys": sysd}
                            st["pending"] = None
                            st["pending_meta"] = None
                        st["want_hdr"] = True
                        continue
                    if cur is None:
                        mt0 = _infer_metatype(text)
                        if mt0:
                            st["pending_meta"] = mt0
                        elif _name_candidate(text):
                            st["pending"] = text
                        continue
                    mt = _infer_metatype(text)       # "Male human" / "Human" -> metatype
                    if mt and "metatype" not in cur["sys"]:
                        cur["sys"]["metatype"] = mt
                        continue
                    if "attributes" not in cur["sys"]:
                        a = _npc_attrs_from_values(text) if (st["want_hdr"] or _NPC_VALUES.match(text)) else {}
                        st["want_hdr"] = False
                        if a:
                            cur["sys"]["attributes"] = a
                            continue
                    hit = next((k for rx, k in _NPC_LABELS if rx.match(text)), None)
                    if hit:
                        cur["sys"][hit] = re.sub(r"^[\w /]+:\s*", "", text).strip()
                        cur["sys"]["_last"] = hit
                    elif cur["sys"].get("_last") and text[:1].islower():
                        cur["sys"][cur["sys"]["_last"]] += " " + text
                    else:
                        cur["buf"].append(text)
                        cur["sys"].pop("_last", None)
                        if _name_candidate(text):     # could be the next block's name
                            st["pending"] = text
                flush()
    return items
