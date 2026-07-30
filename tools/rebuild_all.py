"""One-command rebuild of the whole site library from the registered books.
Runs the proven cross-book extractors in order (gear -> content -> new item
types -> book graphics). Content ingest already Eden-aligns at write time, so no
separate alignment step is needed. Each step streams its own output. Triggered
from the site's Setup panel (POST /api/rebuild) or run directly."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    ("Gear (all books)", "ingest_all.py"),
    ("Content: spells, qualities, NPCs, critters, spirits, …", "ingest_content_all.py"),
    ("New item types: complex forms, foci, contacts, …", "ingest_new_types.py"),
    ("Vehicles + drones", "ingest_vehicles.py"),
    ("Book graphics", "dump_book_images.py"),
    ("Auto-pair artwork", "pair_art.py"),
    ("Re-apply manual corrections", "apply_corrections.py"),
]

failed = []
for label, script in STEPS:
    print(f"\n===== {label} =====", flush=True)
    r = subprocess.run([sys.executable, "-u", f"tools/{script}"], cwd=str(ROOT))
    if r.returncode != 0:
        print(f"  !! {script} exited {r.returncode}", flush=True)
        failed.append(script)

print("\n" + ("REBUILD COMPLETE" if not failed else f"REBUILD FINISHED WITH ERRORS: {failed}"), flush=True)
print("done", flush=True)
