# SR6-eden-Forge — Design

*2026-07-25 — approved design, v2*

## Purpose

A local, git-versioned pipeline that turns Shadowrun 6E book PDFs into reviewed,
structured game data, and packages that data as installable compendium modules for
the `shadowrun6-eden` Foundry VTT system. First deliverable: Core Rulebook
equipment. The architecture must accommodate every future content type (NPCs,
spells, qualities, critters, etc.) without restructuring.

## 1. Repository and storage

- Code and schemas live in this public repo. **Extracted game data is never
  committed** (`data/` and `export/` are gitignored) and never distributed.
- Data exists only in the local working copy on machines whose owner has the
  source books.
- The unit of organization is **book → domain → category file**:

```
data/
└── corebook/
    ├── gear/
    │   ├── weapons_firearms.json
    │   ├── weapons_close_combat.json
    │   ├── armor.json
    │   ├── electronics.json
    │   ├── cyberware.json
    │   └── ...
    ├── npcs/        ← future domains sit beside gear,
    ├── spells/         same pattern, no restructuring
    └── qualities/
```

Adding a new domain (e.g. Street Wyrd spells) means a new folder and a new
schema; nothing else moves.

## 2. Data model

Every item is a JSON object with two parts:

- **`system` block** — exactly the Eden system's fields for that document type.
  For gear: `type` discriminator (`WEAPON_FIREARMS`, `ARMOR`, `ELECTRONICS`, ...),
  damage, attack-rating array `[5]`, fire modes, availability, price, rating,
  essence, capacity, etc. This is the payload Foundry receives.
- **`meta` block** — Forge-only provenance: source book, page number, extraction
  date, extractor version, and `qaStatus` (`extracted` → `reviewed` → `approved`).
  Stripped at export time. Identical shape across all domains
  (`schemas/common.schema.json`).

Eden's known gear `type` enum (from the system's `lang/en.json`):
`ACCESSORY, AMMUNITION, ARMOR, ARMOR_ADDITION, BIOLOGY, BIOWARE, CHEMICALS,
CYBERWARE, CODEMODS, DRONES, ELECTRONICS, GENETICS, MAGICAL, NANOWARE, SOFTWARE,
SURVIVAL, TOOLS, VEHICLES, WEAPON_CLOSE_COMBAT, WEAPON_FIREARMS, WEAPON_RANGED,
WEAPON_SPECIAL, IC`.

The Eden target version (v3.3.x, Foundry v13) is pinned in the repo. When Eden
updates its schema, upgrading is a deliberate migration with a diff, not silent
drift.

## 3. Extraction — standalone tool, Claude-assisted development

The extractor is a **Python CLI** (`extractor/`) runnable with no AI involvement:

```bash
python -m extractor --book corebook --domain gear --pages 244-290
```

- pdfplumber pulls text and table structures from the specified pages; per-book
  **parser profiles** (config + parsing code per table layout) turn raw rows into
  schema-conformant JSON in `data/<book>/<domain>/`.
- **Claude's role is in the build phase, not the run phase**: identifying table
  layout quirks, helping write parser profiles, and producing an independent
  reference extraction the tool's output is compared against. Once the tool
  matches the verified reference across the Core Rulebook, it is trusted and runs
  standalone thereafter.
- Zero AI dependencies at runtime — plain Python, `requirements.txt`, README with
  exact commands. A future contributor extracts a new book by writing a parser
  profile, following documented existing profiles.
- **Correction tables live with the data, not the code.** Profiles in the repo
  contain only structure (page numbers, header regexes, column layouts).
  RENAMES/OVERRIDES/EXCLUDE/MANUAL_ITEMS reference real item names and stats,
  so they load from `data/_fixes/<book>_<domain>_fixes.py` — gitignored like
  the rest of `data/`. Every hook key must fire during a full parse; stale
  keys fail the run loudly, so the correction layer doubles as a regression
  suite when the engine changes.
- Every extraction run is a git-visible change to local data (reviewable diffs).

## 4. Validation — standalone tool

`validator/` is a separate plain-Python CLI:

```bash
python -m validator data/corebook/
```

- **Schema pass** — every file validates against its domain schema: field types,
  category enums, attack-rating array length, etc.
- **Sanity pass** — rules schemas can't express: price/availability present and
  plausible, damage codes well-formed (`3P`, `2S(e)`), no duplicate names within
  a book, page numbers within range.
- Runs standalone, is surfaced in the web app per item, and is the merge gate for
  data changes.

## 5. Review and editing web app

- **Single Node application** — Express API + React/Vite frontend, run locally.
  One runtime for site and export, since the Foundry packer is Node.
- **Reads and writes the JSON files directly** — no database. Every save is a
  file edit, visible in `git diff`. Future AI assistance can batch-edit files or
  use the same API.
- First-version features:
  - Browse/filter by book, domain, category, QA status.
  - Schema-driven form editing (new domains get UI mostly for free).
  - **Live Eden preview pane** — the exact Foundry document JSON the item exports
    as, updating during edits.
  - QA workflow (`extracted` → `reviewed` → `approved`) with a status dashboard.
  - Inline validator errors.

## 6. Module export

- Export script (Node; also a button in the web app): takes all `approved` items
  in scope, strips `meta`, wraps each in a Foundry document envelope, and invokes
  `@foundryvtt/foundryvtt-cli` to compile LevelDB compendium packs.
- Output: `export/sr6-gear-corebook/` with `module.json` (version, Eden system
  dependency) plus a zip. Deploy by copying into the Foundry server's
  `Data/modules`.
- Module version bumps each export; changelog generated from git log.
  **Never distributed publicly.**
- Future domains export the same way — e.g. NPCs become an Actor-type compendium;
  the export layer owns the domain → document-type mapping.

## 7. Testing

- **Extractor:** golden-file tests (pytest) — PDF page fixtures with known-correct
  JSON. The Claude-verified reference extraction becomes the permanent regression
  suite. (Fixtures containing book content stay local, like `data/`.)
- **Validator:** unit tests per sanity rule — good item passes, each corruption
  fails.
- **Export:** round-trip — pack, unpack, compare to input.
- **End-to-end smoke:** install the module in the Eden world, drag a weapon onto
  a test character, confirm sheet render and correct roll pools.

## 8. Delivery order

1. Repo scaffold, gear schema, validator core.
2. Extractor + parser profiles for Core Rulebook gear chapters
   (Claude-assisted verification loop).
3. Full Core Rulebook gear dataset, validated (local only).
4. Web app (browse → edit → QA → preview).
5. Export pipeline + module installed and smoke-tested.
6. Retrospective; next book or next domain.
