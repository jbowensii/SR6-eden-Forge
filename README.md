# SR6-eden-Forge

A local pipeline that turns Shadowrun 6th World book PDFs into reviewed, structured
game data and packages it as compendium modules for the
[shadowrun6-eden](https://github.com/yjeroen/foundry-shadowrun6-eden) Foundry VTT system.

**This repository contains tooling only. It contains no Shadowrun game content.**

## What it does

```
PDF (you own it) ──► extractor ──► data/*.json ──► review web app ──► Foundry module
                                       ▲                │
                                       └── validator ◄──┘
```

1. **Extract** — a standalone Python CLI reads gear tables from book PDFs you own
   and emits schema-conformant JSON. No AI required at runtime.
2. **Validate** — a standalone checker enforces the JSON Schemas plus domain sanity
   rules (damage codes, attack-rating arrays, price/availability plausibility).
3. **Review** — a local Node web app (Express + React) for browsing, editing, and
   QA-ing every item, with a live preview of the exact Foundry document JSON.
4. **Export** — approved items are compiled into LevelDB compendium packs with the
   official `@foundryvtt/foundryvtt-cli`, producing an installable module for your
   own Foundry server.

## Content policy

Shadowrun is © The Topps Company, Inc.; Catalyst Game Labs publishes SR6 under license.
Extracted game data is **never committed to this repository and never distributed**.
The `data/` and `export/` directories are gitignored; they exist only on machines
belonging to someone who owns the source books. This project is a personal-use tool,
in the same spirit as a character generator's user-supplied data directory.

## Repository layout

| Path         | Purpose                                                        | In git? |
| ------------ | -------------------------------------------------------------- | :-----: |
| `schemas/`   | JSON Schemas, one per content domain (gear, npcs, spells, ...) | yes     |
| `extractor/` | Standalone PDF → JSON CLI (Python)                             | yes     |
| `validator/` | Standalone schema + sanity checker (Python)                    | yes     |
| `site/`      | Review/edit web app (Node: Express + React)                    | yes     |
| `docs/`      | Design docs, per-book extraction notes                         | yes     |
| `data/`      | Extracted game data (book → domain → category)                 | **no**  |
| `export/`    | Built Foundry modules                                          | **no**  |

## Target versions

| Component            | Version  |
| -------------------- | -------- |
| Foundry VTT          | v13      |
| shadowrun6-eden      | 3.3.x    |
| Python (extractor)   | 3.12+    |
| Node (site/export)   | 20+      |

## Using the extractor

```bash
# one-time: cache normalized page text from YOUR pdf (never committed)
python -m extractor dump --pdf "path/to/corebook.pdf" --book corebook --pages 245-304

# parse the cache into data/corebook/gear/*.json
python -m extractor parse --book corebook --domain gear
```

**Enrichment** (writeups + artwork, all output stays in gitignored `data/`):

```bash
# add --columns to dump: caches column-ordered text for the passes below
python -m extractor dump --pdf "…" --book corebook --pages 245-304 --columns

# attribute per-item prose writeups into system.description (skips items
# that already have one; --force overwrites)
python -m extractor enrich --book corebook --domain gear --pages 245-304

# extract item artwork as alpha PNGs; confident matches are named
# data/_assets/<book>/<item_id>.png and wired to the item; ambiguous ones
# land in data/_assets/<book>/_inbox/ for manual assignment in the app
python -m extractor images --pdf "…" --book corebook --domain gear --pages 245-304
```

No AI involved at runtime. Parser profiles live in `extractor/profiles/`
(`corebook_gear.py` covers the Core Rulebook's 21 gear categories, 463 items).
To extract a new book, write a profile module: a list of `TableSpec`s (page,
header regex, column layout). Corrections for rows the PDF layout mangles
(`RENAMES`/`EXCLUDE`/`OVERRIDES`/`MANUAL_ITEMS`) reference real book content,
so they live in gitignored `data/_fixes/<book>_<domain>_fixes.py`; the parser
loads them automatically and fails loudly on stale correction keys. See
[docs/extraction-notes-corebook.md](docs/extraction-notes-corebook.md) for the
quirks catalog.

## Using the review app

Requires Node 20+.

```bash
cd site
npm install          # once
npm run build        # build the UI
npm run serve        # http://localhost:8347
```

Browse categories in the sidebar, click a row to edit (fields, QA status,
description, image), Save writes the JSON file and shows the exact Foundry
document the item will export as. "Validate all" runs the Python validator
(`FORGE_PYTHON` overrides the interpreter; defaults to the repo `.venv`, then
`python3`). For UI development: `npm run dev` (Vite on :5173, proxying `/api`).

**Source references**: every item carries its book + printed page (`meta`),
shown in the table and exported into the Foundry document (`system.product`,
`system.page`). Create `data/books.json` (local-only) to name your books and
wire up "Open PDF" jumps to the item's page:

```json
{ "corebook": { "title": "Sixth World Core Rulebook", "pdf": "C:/path/to/your.pdf" } }
```

**Item images**: drop files under `data/_assets/<book>/…` and set an item's
Image field to the relative path (e.g. `corebook/predator.webp`). The editor
previews it and the export bundles it into the module's `icons/` folder.
Paths starting `icons/`, `systems/`, or `modules/` pass through to Foundry
core/system art unchanged.

## Exporting a module

```bash
node site/scripts/export.mjs --book corebook --status approved
# or --status reviewed|all while QA is in progress; --version x.y.z to bump
```

(Or the "Export" button in the review app — exports the selected category's
book/domain.) Output: `export/sr6-forge-<book>/` with `module.json` and a
LevelDB compendium pack. **Install**: copy that folder into your Foundry
server's `Data/modules/`, restart/refresh, enable the module in your
shadowrun6-eden world, and the items appear under the Compendium tab.
Re-exports overwrite in place with stable document ids. The built module
contains game data — **never distribute it**; `export/` is gitignored.

## Using the validator

```bash
pip install -r requirements-dev.txt
python -m validator data/corebook     # validate your local data
python -m validator examples          # validate the committed format examples
pytest                                # run the test suite
```

Every data file must pass two layers: its domain JSON Schema
(`schemas/<domain>.schema.json`) and the domain sanity rules
(duplicate ids, damage-code format, weapon required fields,
plausibility bounds, path/envelope agreement).

## Status

- [x] Gear schema (`schemas/gear.schema.json`) + shared defs (`schemas/common.schema.json`)
- [x] Validator CLI: `python -m validator <path>` — schema pass + sanity pass
- [x] Format examples: `examples/corebook/gear/` (synthetic items only)
- [x] Extractor CLI: `python -m extractor` (dump + parse), AI-free at runtime
- [x] Core Rulebook gear dataset: 463 items / 21 categories (local only, never committed)
- [x] Review web app: `site/` — browse/edit/QA + live Foundry-doc preview + validate
- [x] Module export: CLI + app button → `export/sr6-forge-<book>/` (LevelDB pack, module.json)

**The first slice is complete**: Core Rulebook gear flows PDF → extract →
validate → review → installable shadowrun6-eden module. Next up: more books
(Firing Squad, Body Shop, Double Clutch, …) and new domains (npcs, spells).

See [docs/design.md](docs/design.md) for the full architecture.
