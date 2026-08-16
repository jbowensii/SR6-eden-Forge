# End-to-end plan: import → review → export to Foundry

Written 2026-08-15, after the first export attempt against the real workspace
failed. Nothing here is applied yet. The order matters: each phase leaves the
pipeline working, and no phase depends on a later one having been done.

## Where things actually stand

The export was run against the live library for the first time and got one pack
in before stopping. Three separate causes, established by evidence rather than
inference:

| | |
|---|---|
| 16 of 21 domains | build cleanly |
| `adept_powers`, `critters`, `gear`, `vehicles` | refuse to build — duplicate item ids |
| `commlink6_extra` | refuses to build — no Eden document type exists for it |

The empty-key error (`Key cannot be null or undefined`) was hidden for the life
of this code by a bare `rmSync` in a catch block that replaced the real error
with an EPERM about a temp folder. That masking is fixed; the causes below are
not.

## The duplicate ids are not a defect

Commlink6 carries every book, and books reprint material. Two PDFs containing
the same reprinted item legitimately produce two rows, and Commlink6 reuses one
id across both. 93 ids in the library currently sit on more than one row —
`cl6_corrosive_spit` on four.

That is correct in the library and fatal in a compendium, where the id IS the
primary key and a second row silently overwrites the first. **So this is an
export-time concern, not an import-time one.** The library should keep every
printing; the compendium gets one.

This is also the likely explanation for the seven rows that survive their
tombstone (see `deferred-code-changes.md`) — the same duplicate ids, seen from
the other end. That question stays open and is not addressed here.

## What `commlink6_extra` is

853 rows across 59 files. It is not one kind of thing, which is why it has never
had a home:

**Group A — playable content (~450 rows).** Major/Minor/Edge actions (68/35/120),
Dracogenesis powers (38), Traditions (28), Data Structures (18), Quality Paths
(18), Drake Types, Collectives, Neuromorphism, Transhumanism. These carry real
rules text and belong in a compendium a GM can browse.

**Group B — character-creation machinery (~400 rows).** `priorities.json`,
`metatypes.json` (36), `magicOrResonance.json`, `lifepath*.json`, `lifemods.json`,
`packs-*.json` (161 starting-gear packs).

**Group C — rules scaffolding.** `rules.json`, `senses.json`, `spellfeatures.json`,
`ritualfeatures.json`, `qualityFactors.json`, `consoleTypes.json`,
`licensetypes.json`, `contact_types.json`, `true_element_attributes.json`.

**Decision (John, 2026-08-15): B and C are configuration, not content.** The
Commlink6 port must read them in code; they must NOT be stored in the extracted
library, must NOT be editable in the review app, and must NOT become a
compendium. Only Group A becomes compendium content.

The machinery for B and C already exists and is the right path: they are read
from the Commlink6 jar by `tools/build_chargen_data.py` into
`export/chargen-data.json`, which the `sr6-forge` module consumes as config.
Nothing needs inventing — the fix is to stop ALSO writing them into the item
library, where they have no meaning and cause exactly the harm seen here.

---

## Phase 0 — a safety net first, no behaviour change

Nothing below is safe to attempt without a way to prove it changed only what was
intended.

1. **Record a baseline.** Row counts per domain, per category, and per
   `meta.source`, written to a file. Every later phase is diffed against it.
2. **Make the export testable end to end.** A test that builds a small library
   in a temp dir and runs `exportAll` over it, asserting pack count and document
   count. There is currently no test that exercises the compile path, which is
   how a script that would not even parse (`export_all.mjs`) sat broken.
3. **Invariant: every domain in the library has an Eden spec entry.** This is
   the check that would have caught `commlink6_extra` the day it appeared,
   rather than at the first real export months later. Add to
   `tools/verify_library.py`; test it in both directions.

**Done when:** baseline written, export covered by a test, new invariant fails
today (it should — `commlink6_extra` has no spec) and is recorded as a known
failure until Phase 2 clears it.

## Phase 1 — deduplicate at export

Unblocks `gear`, `vehicles`, `critters`, `adept_powers` — four of the largest
domains — and touches no data.

1. In `buildDocs`, replace the "duplicate id" throw with a **keep-one** rule.
2. Which copy wins, in order: `meta.source == "commlink6"` outranks a
   PDF-derived row; then the earliest book in publication order; then the row
   with the most fields populated. Deterministic, so two runs agree.
3. **Report every drop** — `id`, name, which book was kept, which skipped. A
   silent dedupe is how you lose a row that was not really a duplicate.
4. Test: two rows sharing an id produce one document, the Commlink6 one, and the
   skip is reported.

**Risk:** two genuinely different items sharing an id would silently collapse.
Mitigated by the report — the first run's output must be read, not skimmed.

**Done when:** all 20 remaining domains build, and the drop list has been read
once by a human.

## Phase 2 — split `commlink6_extra`

The largest change. Do it in this order so nothing is deleted before its
replacement is proven.

1. **Prove B and C are already fully covered by `chargen-data.json`.** For every
   file in groups B and C, confirm the same records are present in
   `export/chargen-data.json` with the same values. Write the comparison down.
   *If anything is missing, the extractor gap is fixed BEFORE any removal.*
2. **Give Group A a home.** Either a new domain per kind (`actions`,
   `traditions`, `data_structures`, …) or one `reference` domain, each with an
   `edenSpec.mjs` entry and a Foundry document type. This is a design decision
   with a real consequence — the domain determines the Foundry type — and
   deserves its own discussion before code.
3. **Stop the import writing B and C into the library.** In the Commlink6
   converter, route those record kinds to the chargen builder only.
4. **Retire the existing rows.** Move, don't delete: they go to
   `_retired_corrections`-style storage outside every scan path, so the decision
   is reversible and the record survives.
5. Re-run the Phase 0 baseline diff. The only rows that moved should be the ones
   named in step 3.

**Done when:** `commlink6_extra` no longer exists as a library domain, Group A
exports as a compendium, and `chargen-data.json` is unchanged or provably more
complete than before.

## Phase 3 — hide configuration from the review app

Once B and C are out of the library there is nothing to hide, so this phase is
mostly proving it stayed that way.

1. The review app reads whatever domains exist on disk. After Phase 2 it will
   not see B or C at all — verify that rather than assume it.
2. Add a test asserting the app's domain list contains no configuration domain.

## Phase 4 — the genesisID problem

Every one of the 853 `commlink6_extra` rows carries a `genesisID` field, and the
standing rule is that no long-term link to genesis belongs in the code or files.
Group A rows will carry it into the compendium unless it is renamed or dropped
on the way out. Decide which, then enforce it with an invariant.

## Phase 5 — the full run

Import → review → export, end to end, with the Phase 0 baseline compared at each
boundary. This is also the first honest test of the path every other user will
walk: install the app, point it at their own PDFs, correct what the reader got
wrong, build a module for their own table.

---

## Not in scope here

- **The seven rows that survive their tombstone.** Instrumented, waiting on the
  next import to report which of two causes it is.
- **The two deferred importer bugs** in `deferred-code-changes.md`.
- **Vehicle vocabulary drift** (`VEHICLE` vs `VEHICLES`), same document.

## The rule this plan is built on

A step reporting success is not evidence it worked. Every phase above states
what "done" means as something observable in the data, not as a command that
exited zero. Five failures this week took that shape — a signing tool that
exited 0 without signing, a commit that succeeded while gitignored, corrections
bundled where nothing reads them, an export reading a six-day-old library, and a
test file that never loaded while the suite reported 97 passing.
