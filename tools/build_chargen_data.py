"""Build chargen-data.json — the rules/config dataset for the SR6 Forge Foundry
module (priority table, metatypes w/ creation maxima, magic/resonance paths,
skills+specializations, rule interpretations, quality metadata, lifestyles,
contact archetypes, English lifepath modules).

Separate from the item library by design: these are engine config, not compendium
documents. Reads the Commlink6 jar losslessly (deep trees preserved under `raw`).

Usage: python tools/build_chargen_data.py [--jar PATH] [--out PATH]
Default out: export/chargen-data.json (also copied into the module by build_module)."""
import argparse
import json
import sys
import zipfile
from datetime import date
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from extractor.commlink6 import DEFAULT_JAR
from extractor.gear_meta import (
    build_gear_meta, build_item_ratings, english_data_files, parse_adept_powers,
)
from extractor.chargen_xml import (
    i18n_by_prefix, parse_contacts, parse_lifepath, parse_lifestyles,
    parse_mentor_spirits, MENTOR_BOOKS,
    parse_magicreson, parse_metatypes, parse_priorities, parse_quality_meta,
    parse_rule_labels, parse_rules, parse_skills, read_category_trees, sub_i18n,
)

# (book, category, parser-key) — metatypes/qualities exist in several books
METATYPE_BOOKS = ["core", "companion", "astral_ways", "hack_slash", "other_us"]

#: Every English quality file in the Commlink6 jar. Regional variants
#: (qualities_seattle / qualities_berlin) are listed BEFORE the main books so a
#: base-book definition wins any id collision; the builder reports collisions
#: rather than silently letting load order decide.
QUALITY_FILES = [
    ("core", "qualities_seattle"), ("core", "qualities_berlin"),
    ("sif_new_orleans", "qualities_easycome"),
    ("core", "qualities"),
    ("companion", "qualities"), ("companion", "qualities-metagenetic"),
    ("companion", "qualities-infected"),
    ("astral_ways", "qualities"), ("bestial_nature", "qualities"),
    ("body_shop", "qualities"), ("deadly_arts", "qualities"),
    ("dealers_of_death", "qualities"), ("double_clutch", "qualities"),
    ("firing_squad", "qualities"), ("hack_slash", "qualities"),
    ("hack_slash", "qualities_ai"), ("hack_slash", "qualities_streams"),
    ("no_future", "qualities"), ("other_us", "qualities"),
    ("smooth_operations", "qualities"),
    ("street_wyrd", "qualities1"), ("street_wyrd", "qualities2"),
    ("tarnished_star", "qualities"),
]

#: The ten contact categories the Companion life path assigns modules to.
CONTACT_TYPE_FILES = [("companion", "contact_types"), ("astral_ways", "contact_types")]
LIFEPATH_FILES = [("companion", "lifepath"), ("companion", "lifepath2"),
                  ("companion", "lifepaths"), ("companion", "lifemods"),
                  ("companion", "LifePathModules"), ("no_future", "lifepath")]


def build(jar: _P, out: _P) -> dict:
    data: dict = {
        "version": 1,
        "generated": date.today().isoformat(),
        "source": {"jar": jar.name, "note": "personal use only — not for distribution"},
    }
    with zipfile.ZipFile(jar) as z:
        # prefix-aware: ids collide across prefixes (skill.firearms vs
        # licensetype.firearms), so every section reads its own namespace
        px = {b: i18n_by_prefix(z, b) for b in
              {"core", "companion", "astral_ways", "hack_slash", "no_future"}}

        # English rule interpretations only — "*_de" are the German ones.
        data["rules"] = {k: v for k, v in
                         parse_rules(read_category_trees(z, "core", "rules")).items()
                         if not k.endswith("_de")}
        data["ruleLabels"] = parse_rule_labels(z)
        data["priorities"] = parse_priorities(read_category_trees(z, "core", "priorities"))

        metatypes: dict = {}
        for b in METATYPE_BOOKS:
            metatypes.update(parse_metatypes(read_category_trees(z, b, "metatypes"),
                                             sub_i18n(px.get(b, {}), "metatype"), b))
        data["metatypes"] = metatypes

        data["morTypes"] = parse_magicreson(
            read_category_trees(z, "core", "magicOrResonance"),
            sub_i18n(px["core"], "mor"))
        data["skills"] = parse_skills(read_category_trees(z, "core", "skills"),
                                      sub_i18n(px["core"], "skill"))

        qmeta: dict = {}
        collisions = []
        for b, cat in QUALITY_FILES:
            batch = parse_quality_meta(read_category_trees(z, b, cat), b)
            for qid in set(batch) & set(qmeta):
                if batch[qid].get("karma") != qmeta[qid].get("karma"):
                    collisions.append(f"{qid} ({qmeta[qid]['book']} -> {b})")
            qmeta.update(batch)
        # Individual mentor spirits inherit the parent quality's cost and sign
        # (core p74) — without this they arrive priced at 0 and marked negative.
        for pid in ("mentor_spirit", "paragon"):
            parent = qmeta.get(pid)
            if not parent:
                continue
            for b in MENTOR_BOOKS:
                qmeta.update(parse_mentor_spirits(
                    read_category_trees(z, b, "mentorspirits"), b, parent))
        data["qualityMeta"] = qmeta
        if collisions:
            print(f"  ! {len(collisions)} quality id collisions with differing karma:")
            for c in collisions[:10]:
                print(f"      {c}")

        data["lifestyles"] = parse_lifestyles(
            read_category_trees(z, "core", "lifestyles"),
            sub_i18n(px["core"], "lifestyle"))
        data["contactArchetypes"] = parse_contacts(
            read_category_trees(z, "core", "contacts"), sub_i18n(px["core"], "npc"))
        # Contact categories (Academic, Corporate, ... Street) — the life path
        # ties each module's contact points to one of these.
        ctypes: dict = {}
        for b, cat in CONTACT_TYPE_FILES:
            for t in read_category_trees(z, b, cat):
                if t["tag"] != "contacttype":
                    continue
                cid = t["attrs"]["id"]
                ctypes[cid] = {"id": cid, "name": cid.replace("_", " ").title(), "book": b}
        data["contactTypes"] = ctypes

        lifepath: dict = {}
        for b, cat in LIFEPATH_FILES:
            lifepath.update(parse_lifepath(read_category_trees(z, b, cat),
                                           sub_i18n(px.get(b, {}), "lifemod"), b))
        # Commlink6's 84 life modules are German-only, so the English catalogue
        # comes from our own Companion PDF. It wins on id collisions.
        lifepath.update(companion_lifepath())
        data["lifepathModules"] = lifepath

        # Accessory mounting: hosts declare HOOK slots, accessories declare the
        # slots they fit and which host subtypes accept them.
        data["gearMounts"] = build_gear_meta(z)

        # Rated gear (Wired Reflexes 1-4, ...) prices per rating rather than
        # flat, so the rating range and the price/avail/essence rules ship too.
        data["gearRatings"] = build_item_ratings(z)

        # Adept powers: `cost` is power points PER LEVEL, so a leveled power
        # (Improved Reflexes) is bought at rank 1..n.
        powers: dict = {}
        for b, cat in english_data_files(z, r"adeptpowers"):
            powers.update(parse_adept_powers(read_category_trees(z, b, cat),
                                             sub_i18n(px.get(b, {}), "power"), b))
        data["adeptPowers"] = powers

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def companion_lifepath() -> dict:
    """English life modules read out of the Sixth World Companion PDF."""
    books = _P("data/books.json")
    if not books.exists():
        return {}
    pdf = json.loads(books.read_text(encoding="utf-8")).get("companion", {}).get("pdf")
    if not pdf or not _P(pdf).exists():
        print(f"  ! companion PDF not found ({pdf}) — English life modules skipped")
        return {}
    try:
        from extractor.lifepath_pdf import extract
        return extract(pdf)
    except Exception as err:                       # pragma: no cover - diagnostics
        print(f"  ! life-module extraction failed: {err}")
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", type=_P, default=DEFAULT_JAR)
    ap.add_argument("--out", type=_P, default=_P("export/chargen-data.json"))
    args = ap.parse_args()
    d = build(args.jar, args.out)
    print(f"chargen-data.json -> {args.out}")
    print(f"  priorities: {len(d['priorities'])} letters"
          f" | metatypes: {len(d['metatypes'])}"
          f" | morTypes: {len(d['morTypes'])}"
          f" | skills: {len(d['skills'])}"
          f" ({sum(len(s['specializations']) for s in d['skills'].values())} specs)")
    print(f"  rules: {list(d['rules'])}"
          f" | qualityMeta: {len(d['qualityMeta'])}"
          f" | lifestyles: {len(d['lifestyles'])}"
          f" | contacts: {len(d['contactArchetypes'])}"
          f" | contactTypes: {len(d['contactTypes'])}"
          f" | lifepath(EN): {len(d['lifepathModules'])}")
    print(f"  gearRatings: {len(d['gearRatings'])}")
    print(f"  gearMounts: {len(d['gearMounts'])}"
          f" | adeptPowers: {len(d['adeptPowers'])}"
          f" ({sum(1 for p in d['adeptPowers'].values() if p['hasLevel'])} leveled)")


if __name__ == "__main__":
    main()
