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

## Status

Early scaffold. First slice in progress: Core Rulebook equipment (gear domain).
See [docs/design.md](docs/design.md) for the full architecture.
