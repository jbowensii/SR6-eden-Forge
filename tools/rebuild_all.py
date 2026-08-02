"""One-command rebuild of the whole site library from the registered books, in
the exact order that reproduces the curated corebook state.

Phases:
  1. Extract      — gear, content, new item types, vehicles (Eden-aligned on write)
  2. Graphics     — dump book images, auto-pair artwork
  3. Reclassify   — fix systematic type/subtype mis-filing from the bulk merge
  4. Describe     — precision writeup extractor, list-layout fills, tail fills,
                    recover malformed descriptions frozen in corrections
  5. Subtypes     — infer blank gear subtypes (verified sources, then keywords)
  6. Corrections  — re-overlay every manual correction LAST (always wins)

Each post-extraction tool is idempotent and skips manually corrected items, so
this is safe to re-run. Triggered from the site Setup panel (POST /api/rebuild)
or run directly: `python tools/rebuild_all.py`."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (label, script, [args])
STEPS = [
    # 1. extract ----------------------------------------------------------------
    ("Gear (all books)", "ingest_all.py", []),
    ("Content: spells, qualities, NPCs, critters, spirits, …", "ingest_content_all.py", []),
    ("New item types: complex forms, foci, contacts, …", "ingest_new_types.py", []),
    ("Vehicles + drones", "ingest_vehicles.py", []),
    # 2. graphics ---------------------------------------------------------------
    ("Book graphics", "dump_book_images.py", []),
    ("Auto-pair artwork", "pair_art.py", []),
    # 3. reclassify (fix systematic mis-filing from the merge) -------------------
    ("Reclassify over-typed electronics", "reclassify_electronics.py", ["--apply"]),
    ("Repair gear type/subtype (bioware, weapons, clothing, casing)", "fix_gear_types.py", ["--apply"]),
    ("Fix cyberware CYBER_BODYWARE type", "fix_cyberware_bodyware.py", ["--apply"]),
    ("Re-file mis-filed weapons (railguns, lasers, bows)", "refile_misfiled_weapons.py", ["--apply"]),
    # 4. describe ---------------------------------------------------------------
    ("Descriptions: precision writeup extractor (replace-all)", "rebuild_descriptions.py", ["--apply"]),
    ("Descriptions: spell list layout", "fill_list_descriptions.py", ["--domain=spells", "--apply"]),
    ("Descriptions: complex-form list layout", "fill_list_descriptions.py", ["--domain=complexforms", "--apply"]),
    ("Descriptions: critter-power list layout", "fill_list_descriptions.py", ["--domain=critter_powers", "--apply"]),
    ("Descriptions: ritual list layout", "fill_list_descriptions.py", ["--domain=rituals", "--apply"]),
    ("Descriptions: notes fallback + prose glossary tail", "fill_prose_tail.py", ["--apply"]),
    ("Descriptions: recover malformed corrected entries", "fix_corrected_descriptions.py", ["--apply"]),
    # 5. subtypes (use descriptions; run after describe) -------------------------
    ("Subtypes: firearms from verified source tables", "subtype_firearms_from_book.py", ["--apply"]),
    ("Subtypes: infer blank gear subtypes (name -> keywords)", "infer_gear_subtypes.py", ["--apply"]),
    # 6. corrections LAST -------------------------------------------------------
    ("Re-apply manual corrections", "apply_corrections.py", []),
]

failed = []
for label, script, args in STEPS:
    print(f"\n===== {label} =====", flush=True)
    r = subprocess.run([sys.executable, "-u", f"tools/{script}", *args], cwd=str(ROOT))
    if r.returncode != 0:
        print(f"  !! {script} exited {r.returncode}", flush=True)
        failed.append(script)

print("\n" + ("REBUILD COMPLETE" if not failed else f"REBUILD FINISHED WITH ERRORS: {failed}"), flush=True)
print("done", flush=True)
