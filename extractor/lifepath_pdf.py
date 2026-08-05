"""Extract the English life modules from the Sixth World Companion PDF.

Commlink6 ships 84 life modules but every one of them is German (German ids,
no English i18n), and this project imports English books only. The English set
therefore has to come from our own copy of the Companion.

The layout is regular enough to parse from font metrics rather than guesswork:

    17.8pt LiberationSans    module name (may wrap over two spans)
    13.0pt LiberationSerif   bullet label ("Choose one:", "Resources:", ...)
    14.6pt LiberationSerif   body text — description, or a bullet's value

Every bullet is kept verbatim in ``bullets`` so nothing is lost; ``grants`` and
``choices`` are the machine-readable projection the chargen engine consumes.
"""
from __future__ import annotations

import re
import unicodedata

HEADER_SIZE = 17.8
LABEL_SIZE = 13.0
BODY_SIZE = 14.6
SIZE_EPS = 0.35
BULLET = "•"

#: Pages of the adult/event life-module catalogue (0-based, inclusive).
MODULE_PAGES = range(33, 49)

ATTRIBUTES = {
    "body", "agility", "reaction", "strength", "willpower", "logic",
    "intuition", "charisma", "edge", "magic", "resonance",
}

#: Companion skill names -> the eden/actor skill ids we store.
SKILLS = {
    "astral": "astral", "athletics": "athletics", "biotech": "biotech",
    "close combat": "close_combat", "con": "con", "conjuring": "conjuring",
    "cracking": "cracking", "electronics": "electronics",
    "enchanting": "enchanting", "engineering": "engineering",
    "exotic weapons": "exotic_weapons", "firearms": "firearms",
    "influence": "influence", "outdoors": "outdoors",
    "perception": "perception", "piloting": "piloting", "sorcery": "sorcery",
    "stealth": "stealth", "tasking": "tasking",
}

_LABEL_RE = re.compile(r"^(.*?):\s*$")
_CHOOSE_RE = re.compile(r"choose\s+(one|two|three)", re.I)
#: "+1 to Edge", "+ 1 to Charisma" (stray space), "+1 Edge or ..." (no "to")
_PLUS_RE = re.compile(r"^\+\s*(\d+)\s+(?:to\s+)?", re.I)
_COUNT = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
#: "+1 to four different skills" — N separate ranks, not a choice between them.
_SPREAD_RE = re.compile(
    r"^\+(\d+)\s+to\s+(one|two|three|four|five)\s+different\s+(skill|attribute)s?", re.I)
#: "+1 to any attribute or special attribute"
_ANY_ATTR_RE = re.compile(r"^\+(\d+)\s+to\s+any\s+(attribute|skill)", re.I)


def _norm(text: str) -> str:
    """Flatten the PDF's ligatures and curly punctuation to plain ASCII-ish."""
    out = unicodedata.normalize("NFKC", text)
    return out.replace("’", "'").replace("—", "-").replace("–", "-")


def _near(size: float, target: float) -> bool:
    return abs(size - target) < SIZE_EPS


def parse_page(page, carry: dict | None = None) -> list[dict]:
    """Split one page into raw module records: {name, desc, bullets:[{label, value}]}.

    The bullet glyph is its own tiny span, which is what actually delimits a
    module's grants — the 13pt label span is optional. Career modules use
    "Choose one:" labels; the Event modules write bare "+2 to Agility, ..."
    lines with no label at all, and both have to land in ``bullets``.
    """
    modules: list[dict] = []
    # A module can straddle a page break (Office Manager runs from p43 to p44),
    # so the caller hands back the record that was still open.
    cur: dict | None = carry
    bullet: dict | None = (carry["bullets"][-1] if carry and carry["bullets"] else None)
    in_header = False

    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = _norm(span["text"])
                if not text.strip():
                    continue
                size = span["size"]
                stripped = text.strip()

                if _near(size, HEADER_SIZE):
                    if in_header and cur:            # module name wrapped
                        cur["name"] += " " + stripped
                        continue
                    cur = {"name": stripped, "desc": "", "bullets": [],
                           "page": page.number + 1}
                    modules.append(cur)
                    carry = None
                    bullet = None
                    in_header = True
                    continue

                if stripped == BULLET:                # start of a new grant line
                    in_header = False
                    if cur is not None:
                        bullet = {"label": "", "value": ""}
                        cur["bullets"].append(bullet)
                    continue

                in_header = False
                if "Sans" in span["font"]:
                    continue      # running head / folio / spine — bodies are Serif
                if cur is None:
                    continue                          # furniture before the first module

                if _near(size, LABEL_SIZE) and bullet is not None:
                    m = _LABEL_RE.match(stripped)
                    if m:
                        bullet["label"] = m.group(1).strip()
                        continue
                if bullet is not None:
                    bullet["value"] += (" " if bullet["value"] else "") + stripped
                else:
                    cur["desc"] += (" " if cur["desc"] else "") + stripped

    return _merge_wrapped(modules), cur


def _merge_wrapped(modules: list[dict]) -> list[dict]:
    """Fold a bullet-less record into the next one's name.

    "Adept Training" and "(Adepts only)" are laid out as two header runs in
    separate blocks, so the walk above sees them as two modules — the first
    with no bullets at all.
    """
    out: list[dict] = []
    pending = ""
    for mod in modules:
        if not mod["bullets"]:
            pending = (pending + " " + mod["name"]).strip()
            continue
        if pending:
            mod = {**mod, "name": f"{pending} {mod['name']}".strip()}
            pending = ""
        out.append(mod)
    return out


#: A comma between digits is a thousands separator, not an option separator —
#: "+1 to Edge, Resonance, or +25,000 nuyen" has three options, not four.
_SPLIT_RE = re.compile(r"(?<!\d),(?!\d)|\bor\b")


def _options(value: str) -> list[str]:
    """"+1 to Astral, Enchanting, Influence, or Perception" -> the four names."""
    body = re.sub(r"^\s*\+\s*\d*\s*(?:to\s+)?", "", value.strip(), flags=re.I)
    body = re.sub(r"\((?:awakened|emerged)[^)]*\)", "", body, flags=re.I)
    parts = _SPLIT_RE.split(body)
    return [p.strip(" .+").strip() for p in parts if p.strip(" .+").strip()]


def classify(options: list[str]) -> tuple[str, list[str]]:
    """Return ("attribute" | "skill" | "mixed", canonical option ids)."""
    kinds, ids = set(), []
    for opt in options:
        low = opt.lower().strip()
        if low in ATTRIBUTES:
            kinds.add("attribute")
            ids.append(low[:3] if low != "resonance" else "res")
        elif low in SKILLS:
            kinds.add("skill")
            ids.append(SKILLS[low])
        elif re.search(r"[\d,]+\s*nuyen", low):
            kinds.add("nuyen")
            m = re.search(r"([\d,]+)\s*nuyen", low)
            ids.append(f"nuyen:{m.group(1).replace(',', '')}")
        elif "attribute" in low:
            # "your other drain attribute", "any attribute or special attribute"
            kinds.add("attribute")
            ids.append(low)
        else:
            kinds.add("other")
            ids.append(low)
    if kinds == {"attribute"}:
        return "attribute", ids
    if kinds == {"skill"}:
        return "skill", ids
    return "mixed", ids


def interpret(raw: dict, page_no: int) -> dict:
    """Raw record -> the module shape chargen-data ships."""
    grants: dict[str, int] = {}
    choices: list[dict] = []
    contact_types: list[str] = []
    knowledge = 0

    for b in raw["bullets"]:
        label, value = b["label"], b["value"]
        if not label:
            # Event modules write the label inside the bullet text rather than
            # as its own span: "Contact Points: 4", "+2 to Agility, Body, ...".
            m = re.match(r"^([A-Za-z][A-Za-z /()]*?):\s*(.*)$", value)
            if m:
                label, value = m.group(1).strip(), m.group(2).strip()
        low = label.lower()

        if low.startswith("resources"):
            m = re.search(r"([\d,]+)", value)
            if m:
                grants["nuyen"] = grants.get("nuyen", 0) + int(m.group(1).replace(",", ""))
        elif low.startswith("contact points"):
            m = re.match(r"\s*(\d+)", value)      # prose may follow the number
            if m:
                grants["contactPoints"] = grants.get("contactPoints", 0) + int(m.group(1))
        elif low.startswith("contact types"):
            contact_types = [t.strip() for t in re.split(r",", value) if t.strip()]
        elif low.startswith("knowledge"):
            m = _CHOOSE_RE.search(label)
            knowledge += _COUNT.get(m.group(1).lower(), 1) if m else 1
        elif _SPREAD_RE.match(value):
            m = _SPREAD_RE.match(value)
            n = int(m.group(1)) * _COUNT.get(m.group(2).lower(), 1)
            field = "skillPoints" if m.group(3).lower() == "skill" else "attributePoints"
            grants[field] = grants.get(field, 0) + n
        elif _ANY_ATTR_RE.match(value):
            m = _ANY_ATTR_RE.match(value)
            field = "attributePoints" if m.group(2).lower() == "attribute" else "skillPoints"
            grants[field] = grants.get(field, 0) + int(m.group(1))
        elif _CHOOSE_RE.search(label) or _PLUS_RE.match(value):
            # events grant more than one point at a time ("+2 to Agility, ...")
            m = _PLUS_RE.match(value)
            points = int(m.group(1)) if m else 1
            kind, ids = classify(_options(value))
            choices.append({"kind": kind, "options": ids, "points": points,
                            "text": value.strip()})
            if kind == "attribute":
                grants["attributePoints"] = grants.get("attributePoints", 0) + points
            elif kind == "skill":
                grants["skillPoints"] = grants.get("skillPoints", 0) + points
            # "mixed" spends into whichever pool the player picks, so it is not
            # counted here — the wizard resolves it and adds the point then.

    # "(Awakened only)", and the parenthesis-less variant the PDF produces when
    # the qualifier is typeset as its own header run ("Adept Training Adepts only")
    raw_name = raw["name"]
    m = re.search(r"\(?\b([A-Za-z]+)s? only\)?\s*$", raw_name, re.I)
    requires = m.group(1).lower().rstrip("s") if m else None
    name = raw_name[:m.start()].strip() if m else raw_name.strip()

    return {
        "id": re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
        "name": name,
        "stage": "ADULT",
        "page": page_no,
        "book": "companion",
        "desc": raw["desc"],
        "requires": requires,
        "grants": {k: v for k, v in grants.items() if v},
        "choices": choices,
        "knowledgeSkills": knowledge,
        "contactTypes": contact_types,
        "bullets": raw["bullets"],
    }


#: Headings on the module pages that are section furniture, not modules.
_NOT_MODULES = {
    "adult life modules", "life path", "building a shadow", "starting down",
    "real life", "events", "life modules",
}


def extract(pdf_path: str, pages=MODULE_PAGES) -> dict:
    """{module_id: module} for every English adult/event life module."""
    import fitz

    doc = fitz.open(pdf_path)
    # Parse every page first: a module that straddles a page break is not
    # complete until the following page has been read, so interpreting as we
    # went would price it from a truncated bullet list.
    raws: list[dict] = []
    carry: dict | None = None
    for pno in pages:
        page_modules, carry = parse_page(doc[pno], carry)
        raws.extend(page_modules)

    out: dict = {}
    for raw in raws:
        if not raw["bullets"]:
            continue                        # prose heading, not a module
        name_low = raw["name"].lower().strip()
        if name_low in _NOT_MODULES or len(name_low) < 3:
            continue
        mod = interpret(raw, raw.get("page", 0))
        if mod["id"]:
            out[mod["id"]] = mod
    return out
