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
from extractor.chargen_xml import (
    i18n_by_prefix, parse_contacts, parse_lifepath, parse_lifestyles,
    parse_magicreson, parse_metatypes, parse_priorities, parse_quality_meta,
    parse_rule_labels, parse_rules, parse_skills, read_category_trees, sub_i18n,
)

# (book, category, parser-key) — metatypes/qualities exist in several books
METATYPE_BOOKS = ["core", "companion", "astral_ways", "hack_slash"]
QUALITY_FILES = [("core", "qualities"), ("companion", "qualities"),
                 ("companion", "qualities-metagenetic"), ("companion", "qualities-infected"),
                 ("hack_slash", "qualities_ai"), ("hack_slash", "qualities_streams")]
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

        data["rules"] = parse_rules(read_category_trees(z, "core", "rules"))
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
        for b, cat in QUALITY_FILES:
            qmeta.update(parse_quality_meta(read_category_trees(z, b, cat), b))
        data["qualityMeta"] = qmeta

        data["lifestyles"] = parse_lifestyles(
            read_category_trees(z, "core", "lifestyles"),
            sub_i18n(px["core"], "lifestyle"))
        data["contactArchetypes"] = parse_contacts(
            read_category_trees(z, "core", "contacts"), sub_i18n(px["core"], "npc"))

        lifepath: dict = {}
        for b, cat in LIFEPATH_FILES:
            lifepath.update(parse_lifepath(read_category_trees(z, b, cat),
                                           sub_i18n(px.get(b, {}), "lifemod"), b))
        # Commlink6's 84 life modules are German-only, so the English catalogue
        # comes from our own Companion PDF. It wins on id collisions.
        lifepath.update(companion_lifepath())
        data["lifepathModules"] = lifepath

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
          f" | lifepath(EN): {len(d['lifepathModules'])}")


if __name__ == "__main__":
    main()
