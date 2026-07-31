"""List-layout description extraction for spells (and similarly-formatted power
lists). Unlike prose writeups, these sections pack each entry as:

    <Name>
    (Category)
    RANGE TYPE DURATION DV DAMAGE      <- stat column header (the anchor)
    LOS (A) S                          <- stat values
    <description prose>                 <- frequently shared by a GROUP of entries

Entries with no prose between them share the prose that follows the last one
(e.g. Clout + Blast, Flamestrike + Fireball). The name line is not reliably in a
heading font and column bleed drops stray words ("the", "Bolt") near it, so the
name is resolved by matching lines against the KNOWN entry-name set rather than
by font. Pure core over LineRec lists — unit-tested without a PDF."""
from __future__ import annotations

import re

from extractor.enrich import norm
from extractor.writeups import LineRec, clean_block

# stat column headers that anchor each list entry. Non-combat spells omit DAMAGE,
# so anchor on the stem. Critter powers use a different column order.
SPELL_HEADER = re.compile(r"^RANGE\s+TYPE\s+DURATION\b")
CRITTER_POWER_HEADER = re.compile(r"^TYPE\s+ACTION\s+RANGE\s+DURATION\b")


def _anywhere(header_re):
    """Same header un-anchored — column bleed can merge a prose tail with the next
    entry's header onto one visual row ("Light tar- RANGE TYPE DURATION DV")."""
    return re.compile(header_re.pattern.lstrip("^"))


def _entries(lines, known_norms, header_re):
    """Locate each stat header and the known name that precedes it (within 4
    lines, to skip the '(Category)' line and any column-bleed stray)."""
    out = []
    for i, ln in enumerate(lines):
        if not header_re.match(ln.text.strip()):
            continue
        name_i = name = None
        for j in range(i - 1, max(-1, i - 6), -1):
            if norm(lines[j].text) in known_norms:
                name_i, name = j, lines[j].text.strip()
                break
        if name_i is not None:
            out.append({"name": name, "name_i": name_i, "values_i": i + 1, "col": ln.col})
    return out


def parse_list_descriptions(lines, known_norms, header_re=SPELL_HEADER) -> dict:
    """Return {normalized_name: description} for every entry whose prose block is
    recoverable. Grouped entries (no prose between them) share the prose that
    follows the group's last entry."""
    ents = _entries(lines, known_norms, header_re)
    anywhere = _anywhere(header_re)
    result = {}
    n = len(ents)
    i = 0
    while i < n:
        run = [ents[i]]
        # extend the run while the next entry's name immediately follows (no prose)
        while i + 1 < n:
            gap = [g for g in lines[ents[i]["values_i"] + 1:ents[i + 1]["name_i"]]
                   if g.text.strip()]
            if gap:
                break
            run.append(ents[i + 1])
            i += 1
        # prose after the last entry's values row, same column, until the next
        # entry's name / a heading / another stat header
        last = ents[i]
        end = ents[i + 1]["name_i"] if i + 1 < n else len(lines)
        prose = []
        for k in range(last["values_i"] + 1, end):
            ln = lines[k]
            if ln.col != last["col"] or ln.is_head:
                break
            m = anywhere.search(ln.text)   # header may be merged mid-line by bleed
            if m:
                pre = ln.text[:m.start()].strip()
                if pre:
                    prose.append(pre)
                break
            if ln.text.strip():
                prose.append(ln.text)
        desc = clean_block(prose)
        if len(desc) >= 40:
            for e in run:
                result[norm(e["name"])] = desc
        i += 1
    return result
