# Deferred code changes

Things worth changing in the **import** or **Foundry export** code, found while
cleaning the data by hand. Nothing here is urgent and nothing here is being done
now — the importer is frozen. Each entry records what the problem is, what the
evidence was, and what we decided the right answer is, so the work can be picked
up later without re-deriving any of it.

The distinction that puts something on this list: a *data* correction fixes the
rows that exist today, but if the extractor keeps producing the same shape then
the next book, or the next re-read, brings it straight back. That is a code
change waiting to happen.

---

## 1. Vehicle type/subtype vocabulary drift

**Status:** diagnosed, not applied. Data left as-is by decision on 2026-08-11.

### The problem

The library carries two spellings of the vehicle type and singular/plural
variants of several subtypes, for what is one category:

| value | rows | correct? |
|---|---:|---|
| type `VEHICLES` | 282 | yes |
| type `VEHICLE` | 85 | no |
| subtype `CARS` / `CAR` | 30 / 18 | `CARS` |
| subtype `BIKES` / `BIKE` | 14 / 13 | `BIKES` |
| subtype `BOATS` / `BOAT` | 24 / 2 | `BOATS` |
| subtype `SUBMARINES` / `SUBMARINE` | 10 / 2 | `SUBMARINES` |
| subtype `TRUCKS` / `TRUCK` | 8 / 1 | `TRUCKS` |

A row typed `VEHICLES/CARS` and one typed `VEHICLE/CAR` are the same kind of
thing, land in different groups in the review app, and match different category
icons — which is how this was found: two vehicles had no icon at all, because
no icon exists for a pair that should not exist.

### Which spelling is right, and how we know

Not by counting rows. Three pieces of evidence, in order of authority:

1. **`site/shared/edenSpec.mjs:51`** — `vehicles: { type: "Vehicle", actor: true }`.
   The Foundry document type is `"Vehicle"`, singular and capitalised, and it is
   derived from the **domain** (`vehicles`), never from `system.type`. So
   `system.type` does not reach Foundry as the document type at all; it is our
   own categorisation, used for icons and browsing. Neither spelling is "the
   Foundry one" — the choice is ours.
2. **`site/shared/eden_codes.json` → `vocab.subtypes`** (212 entries) contains
   `CARS`, `BIKES`, `BOATS`, `SUBMARINES`, `TRUCKS`. It does **not** contain
   `CAR`, `BIKE`, `BOAT`, `SUBMARINE`, `TRUCK`. Plural wins.
3. **The same file's `remap`** contains `VEHICLES/VTOL -> [VEHICLES, ROTORCRAFT]`
   — it maps *into* `VEHICLES`, confirming the plural type is the one the Eden
   mapping layer expects.

**Canonical: type `VEHICLES`, subtypes plural.**

### The fix, as data (what a hand correction would do)

111 items, no judgement calls:

* type `VEHICLE` -> `VEHICLES` — 85 rows
* subtype `BIKE` -> `BIKES` (13), `CAR` -> `CARS` (18), `BOAT` -> `BOATS` (2),
  `SUBMARINE` -> `SUBMARINES` (2), `TRUCK` -> `TRUCKS` (1)

Groups that collapse: CARS 30->48, BIKES 14->27, BOATS 24->26, ROTORCRAFT
27->29, FIXED_WING 18->19, SUBMARINES 10->12, TRUCKS 8->9, SPACECRAFT 1->2.
Every target is in the Eden vocabulary.

### Why it belongs in the code, not only in corrections

Correcting 111 rows fixes today's library. It does not stop the readers emitting
`VEHICLE/CAR` again on the next import or the next book. The durable fix is for
whatever writes these values to normalise against `eden_codes.json` at the point
of writing — the vocabulary file already exists and already knows the answer, it
is simply not consulted when a type/subtype is assigned.

Candidate approach: have the vehicle ingest (and the gear type/subtype repair
phases) pass every `(type, subtype)` through a normaliser that upper-cases,
resolves singular->plural against `vocab.subtypes`, and reports anything it
cannot resolve rather than writing it silently.

### Three related findings, deliberately left out of the above

* **65 rows are typed `VEHICLE/VEHICLE`** and are not mistyped vehicles at all —
  they are several vehicles mashed into one row by a bad table read
  (`Jackrabbit Honda Spirit Eurocar`, `OFF ROAD) INTERVAL Dodge Scoot Har...`,
  `GMC Bulldog Range Rover`). Retyping them would make garbage tidy. They want
  deleting, and separately, the read that produced them wants looking at.
* **Eleven subtypes stay outside the vocabulary even after the merge:**
  `TRUCK_VAN` (9), `VEHICLE_VAN`, `VEHICLES_FLYING`, `DRONE`, `JET_BOARD`,
  `MAIN_BATTLE_TANK`, `GRAVDRIVE`, `POWERBOAT`, `SECURITY_SUV`, `SUV`, `VTOL`.
  `VTOL` is already handled by the remap, so at least some of these are fine and
  need checking rather than changing.
* **Vehicles are sitting in the `gear` domain.** Most of the odd subtypes above
  are on rows in `gear`, not `vehicles` — including `Harley-Davidson Centaur`
  and `Honda Rough Rider`. Because the domain decides the Foundry document type,
  those export as **Items**, not **Vehicle actors**. That is probably wrong and
  is a bigger change than the vocabulary merge: moving a row between domains
  also moves which pack it lands in.

### Also worth knowing when this is picked up

A correction only re-applies if the import can still find its item, and an item
that a phase moves to another domain can lose its correction (14 deletions were
failing that way as of 0.9.16). So a data correction that changes an item's
type/subtype may not survive a later phase re-filing that same item.

---

## 2. A tombstone's name fallback can delete a Commlink6 row

**Status:** diagnosed, not fixed. Cost 56 rows on 2026-08-12.

### What happens

A deletion correction records the id of the row that was deleted, plus a `ref`
carrying its name and book. If the id is not found, the fallback matches on name
instead — deliberately, because ids move when a reader improves and a tombstone
whose target has been re-identified would otherwise stop working.

The failure: the user deletes a PDF-derived row (`arsenic`) as a junk duplicate.
Commlink6 also has that item, as `cl6_arsenic`. While both rows exist the
tombstone matches `arsenic` by id and removes the right one. Once the PDF row is
gone, the fallback fires and matches `cl6_arsenic` by name — and deletes the
Commlink6 row, which is the one row that should never be deleted by inference.

Arsenic, Cyanide, Caltrops, Anabolic Steroids, Armored Backpack, Baud and fifty
others went that way in one run.

### The guard

A name match must not delete an authoritative row when the tombstone's own id
was NOT authoritative. If the tombstone says `arsenic` and the only candidate is
`cl6_arsenic`, that is a different record and the deletion should be skipped and
reported, not applied. `extractor.authority.is_authoritative` already answers
the question.

Commlink6 outranks anything a reader inferred. A tombstone written against a
reader's row carries no authority over Commlink6's.

---

## 3. apply_corrections is not idempotent, and is destructive when run alone

**Status:** diagnosed, not fixed. Same incident as item 2.

Running the phase twice against the same library does not produce the same
result. The second run behaves differently precisely because the first one
succeeded: with the id-matched target now deleted, every tombstone falls through
to the name fallback and finds something else.

The evidence is stark. The same 439 corrections, on the same library:

* as the final phase of an import: `1 re-matched by name after an id change`
* run standalone afterwards: `66 re-matched by name`

The phase is safe where it is designed to run — last, immediately after the
extractor has rebuilt every row it knows about — and dangerous anywhere else,
because "the row is missing" means something completely different then.

### Options

Make the fallback idempotent (a tombstone that has already been satisfied should
do nothing), or have the phase refuse to run unless the extraction phases ran
first, or both. Until then it should not be invoked by hand — which is how the
56 rows above were lost.
