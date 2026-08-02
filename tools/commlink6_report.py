"""Dry-run cross-reference: SR6-eden-Forge vs Commlink6 (English only), GLOBAL +
domain-aware matching. Commlink6 attribution is truth, so we match a name across
ALL English books within its domain family (not per-book) — an item we attributed
to a supplement but Commlink6 introduces in `core` still matches.

Classification (no writes):
  matched       - name found in Commlink6 (same domain family)
  our_only_cov  - not in Commlink6, our book is covered      -> HIDE candidate
  our_only_gap  - not in Commlink6, our book is a gap book   -> KEEP + convert
  cl6_only      - Commlink6 item we don't have               -> ADD candidate
Also counts subtype changes on matched items (field-mapping sizing)."""
import sys
import glob
import json
from collections import defaultdict
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from extractor.commlink6 import BOOK_ALIAS, english_books, norm, read_book

# our domain -> Commlink6 element tags that domain matches against
DOMAIN_TAGS = {
    "gear": {"item"}, "vehicles": {"item"}, "spells": {"spell"}, "rituals": {"ritual"},
    "adept_powers": {"power"}, "qualities": {"quality"}, "complexforms": {"complexform"},
    "echoes": {"metaecho"}, "critter_powers": {"critterpower"}, "foci": {"focus", "item"},
    "contacts": {"contacttype"}, "sins": {"licensetype"}, "npcs": {"npc"},
    "martial_techniques": {"technique", "martialart"}, "lifestyles": {"lifestyle"},
    "skills": {"skill"}, "metamagics": {"feature", "quality"},
    "critters": {"critter", "metatype", "npc"}, "spirits": {"critter", "spirit"},
    "sprite_powers": {"critterpower", "spritepower"},
}

cl6_books = english_books()

# GLOBAL Commlink6 index: (tag, norm_name) -> record  (first English book wins)
print("indexing Commlink6 (English)…", flush=True)
cl6_index = {}
cl6_by_tag = defaultdict(set)
for cb in sorted(cl6_books):
    for r in read_book(cb).values():
        if not r["name"]:
            continue
        key = (r["tag"], norm(r["name"]))
        cl6_index.setdefault(key, r)
        cl6_by_tag[r["tag"]].add(norm(r["name"]))

# our data
ours = defaultdict(list)                # domain -> [item]
for f in sorted(glob.glob("data/corebook/*/*.json")):
    dom = f.replace("\\", "/").split("/")[-2]
    for it in json.load(open(f, encoding="utf-8")).get("items", []):
        ours[dom].append(it)

def covered(book):
    return BOOK_ALIAS.get(book, book) in cl6_books

def match(dom, name):
    for tag in DOMAIN_TAGS.get(dom, set()):
        r = cl6_index.get((tag, norm(name)))
        if r:
            return r
    return None

stats = defaultdict(lambda: [0, 0, 0, 0, 0])  # dom -> matched, hide, keepgap, subfix, total
our_names_by_tag = defaultdict(set)
for dom, items in ours.items():
    for it in items:
        stats[dom][4] += 1
        r = match(dom, it["name"])
        for tag in DOMAIN_TAGS.get(dom, set()):
            our_names_by_tag[tag].add(norm(it["name"]))
        if r:
            stats[dom][0] += 1
            if r["subtype"] and (it["system"].get("subtype") or "") != r["subtype"]:
                stats[dom][3] += 1
        elif covered(it["meta"].get("book")):
            stats[dom][1] += 1
        else:
            stats[dom][2] += 1

# cl6-only ADD candidates per domain family
add_by_dom = {}
for dom, tags in DOMAIN_TAGS.items():
    add = sum(1 for tag in tags for nm in cl6_by_tag.get(tag, set())
              if nm not in our_names_by_tag.get(tag, set()))
    if add:
        add_by_dom[dom] = add

print("\n%-16s %7s %7s %8s %8s %8s" % ("domain", "ours", "matched", "hide", "keepgap", "subΔ"))
tot = [0, 0, 0, 0, 0]
for dom in sorted(stats):
    m, h, g, s, t = stats[dom]
    tot = [tot[i] + [m, h, g, s, t][i] for i in range(5)]
    print("%-16s %7d %7d %8d %8d %8d" % (dom, t, m, h, g, s))
print("-" * 58)
print("%-16s %7d %7d %8d %8d %8d" % ("TOTAL", tot[4], tot[0], tot[1], tot[2], tot[3]))
print(f"\nCommlink6-only ADD candidates (by our domain): total {sum(add_by_dom.values())}")
for dom, n in sorted(add_by_dom.items(), key=lambda x: -x[1]):
    print(f"   {dom:16} +{n}")
