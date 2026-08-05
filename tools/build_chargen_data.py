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

from extractor.commlink6 import DEFAULT_JAR, _i18n
from extractor.chargen_xml import (
    parse_contacts, parse_lifepath, parse_lifestyles, parse_magicreson,
    parse_metatypes, parse_priorities, parse_quality_meta, parse_rules,
    parse_skills, read_category_trees,
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
        i18n = {b: _i18n(z, b) for b in
                {"core", "companion", "astral_ways", "hack_slash", "no_future"}}

        data["rules"] = parse_rules(read_category_trees(z, "core", "rules"))
        data["priorities"] = parse_priorities(read_category_trees(z, "core", "priorities"))

        metatypes: dict = {}
        for b in METATYPE_BOOKS:
            metatypes.update(parse_metatypes(read_category_trees(z, b, "metatypes"),
                                             i18n.get(b, {}), b))
        data["metatypes"] = metatypes

        data["morTypes"] = parse_magicreson(
            read_category_trees(z, "core", "magicOrResonance"), i18n["core"])
        data["skills"] = parse_skills(read_category_trees(z, "core", "skills"), i18n["core"])

        qmeta: dict = {}
        for b, cat in QUALITY_FILES:
            qmeta.update(parse_quality_meta(read_category_trees(z, b, cat), b))
        data["qualityMeta"] = qmeta

        data["lifestyles"] = parse_lifestyles(
            read_category_trees(z, "core", "lifestyles"), i18n["core"])
        data["contactArchetypes"] = parse_contacts(
            read_category_trees(z, "core", "contacts"), i18n["core"])

        lifepath: dict = {}
        for b, cat in LIFEPATH_FILES:
            lifepath.update(parse_lifepath(read_category_trees(z, b, cat),
                                           i18n.get(b, {}), b))
        data["lifepathModules"] = lifepath

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


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
