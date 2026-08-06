# Import workflow — ownership-gated, Commlink6 first

Replaces the current PDF-only sweep in `tools/ingest_all.py`.

## The rule

**A PDF is proof of ownership, and nothing imports without one.**

For every book in the registry, in publication order:

```
pdf_present = books.json[book].pdf exists on disk
jar_book    = COMMLINK6_ALIAS.get(book, book)
jar_present = commlink6 configured AND jar has data for jar_book

if not pdf_present:
    skip the book entirely          # even if Commlink6 has it
elif jar_present:
    import Commlink6 data for that book     # structured, machine-readable
    then scan the PDF to fill what is missing
else:
    scan the PDF normally                   # today's behaviour, unchanged
```

Three consequences worth stating plainly:

- **Commlink6 data for a book you do not own is never imported.** The jar holds
  all of it; the gate is the PDF beside it.
- **A PDF with no Commlink6 counterpart still imports**, through the existing
  path. Newer releases work the day you buy them.
- **No Commlink6 at all** and the whole thing degrades to what it does today.

## Book matching

Mostly one-to-one. Four aliases close the gap:

| Commlink6 | Ours | Items |
|---|---|---|
| `core` | `corebook` | 533 |
| `krime` | `krime_katalog` | 55 |
| `sif_new_orleans` | `shadows_new_orleans` | 15 |
| `kechibi` | `kechibi_code` | 8 |

Fourteen more match by name already: companion, double_clutch, body_shop,
deadly_arts, firing_squad, hack_slash, street_wyrd, smooth_operations,
tarnished_star, no_future, dealers_of_death, astral_ways, bestial_nature,
collapsing_now.

**Grab-bags are skipped.** `other_us` (21) and `de_other` (102) are not tied to
a single publication, so no PDF can prove ownership of them. German books
(`de_*`) remain excluded as before.

## Precedence — the question this raises

Importing Commlink6 first and letting the PDF "fill gaps" is clear when only
one side has a value. It needs a rule when both do and they differ.

| Field | Wins | Why |
|---|---|---|
| Mechanisms — mounts, grants, rating tables, PACK contents | **Commlink6** | Declared in machine-readable form; the page states these only in prose, if at all |
| Descriptions and prose | **PDF** | The book is the text |
| Rules constants — karma costs, caps, priority table | **PDF** | Already the rule, via the separate `build_chargen_data` path, each cited to a page |
| Plain stats — damage, price, availability | **Commlink6 first, PDF fills absences** | Both are reliable; the jar is already parsed and typed |

**Disagreements get recorded, not silently resolved.** When both sides have a
value for the same field and they differ, the item carries a
`meta.conflicts[]` entry naming the field and both values. The review app
surfaces those as a queue. This turns the overlap into a QA asset: two
independent transcriptions of the same book, and the places they disagree are
exactly where a human should look.

## Identity — genesisID

Eden keys localisation and icons off `<type>.<genesisID>`, so every exported
record needs one.

**Commlink6 ids are preserved.** They already are: jar-sourced items carry
`cl6_<id>` and record `meta.source: "commlink6"`. Those cross-reference the
catalog eden itself matches on and must never be regenerated.

**PDF-only records get a minted id**, and the algorithm has one hard
requirement: it must be **stable across re-ingest and across later edits**. An
id that changes when someone fixes a typo in the review app orphans every
character's link to that item.

```
<cat>_<domain>_<slug>          e.g.  cat28000_gear_ares_predator_vi
```

- `cat` — the Catalyst product code already in `books.json` (`CAT28000`).
  Durable, per-product, and exactly the anchor you suggested.
- `domain` — gear, spells, qualities…
- `slug` — the normalised name.

**Page numbers are deliberately not in the id.** They are recorded in
`meta.page`, which is useful, but they move between printings — our own corebook
PDF is a "Current Printing" — so building them into identity would break ids on
the next edition.

**A lockfile makes it survive edits.** First time an id is minted it is written
to `data/_ids/<book>.json` keyed by the record's origin (book, domain, page,
original extracted name). Later runs look there first. So when a name is
corrected from "Ares Predatar" to "Ares Predator" in the review app, the id
does not move, and neither do the links to it.

Collisions — two records slugging to the same string — take a discriminator
from subtype, then a counter, and that resolution is recorded in the same
lockfile so it never re-shuffles.

## Work

| Phase | Work |
|---|---|
| 1 | Alias table + ownership gate; `ingest_all` skips books with no PDF |
| 2 | Per-book Commlink6 import (the readers exist; this is orchestration) |
| 3 | PDF gap-fill pass over the imported set, with field precedence |
| 4 | Conflict recording + a review-app queue for them |
| 5 | Id minting, the `_ids/` lockfile, and a backfill for existing records |
| 6 | Re-ingest, diff against the current library, review the deltas |

Phase 5 also closes the three domains exporting zero today — `vehicles`,
`commlink6_extra` and `sins` — which are roughly 1,300 items missing from the
catalog for want of ids and eden mappings.
