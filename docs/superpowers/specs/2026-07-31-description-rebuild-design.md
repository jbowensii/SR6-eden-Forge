# Description Rebuild — Design

**Date:** 2026-07-31
**Status:** Approved (design), pending implementation plan

## Problem

`system.description` for items (gear, critters, npcs, spirits, …) is frequently
wrong. Observed failure modes in the current data:

- **Wrong-section attach** — "Regular Ammo (Rifles)" carries electrochromic-clothing
  prose; "Injection Arrow" carries a crossbow stat row. The heading matcher attaches
  an item to a section that isn't its writeup.
- **Table fragments** — "Crossbow, Light 2P Crossbow, Standard 3P" captured as prose.
- **Column-bleed garble** — "based on the Gas rules, p. 116. smoke Similar to the gas g".
- **Mid-word / mid-sentence truncation** — "…against a target with any fo".
- **Mid-sentence start** — "enhancement An implanted version of…" (tail of prior line).

The current pipeline (`extractor/describe.py` + `extractor/enrich.py`) keys on an
exact font-heading within a page window and under-matches while also mis-attaching.

## Goal

One robust extractor that produces a correct `system.description` for every item and
**replaces all existing descriptions**. Precision over recall: **empty is better than
wrong.**

## Anchoring model (decided)

Text search is the **primary anchor**; font/position are **corroborating signals**,
not gates. Both methods work together.

1. **Anchor — find the name in the book text.** Scan the source book's text for
   occurrences of the item's name, normalized and tolerant of hyphenation and column
   splits. Each occurrence is a candidate location.
2. **Rank candidates** using font + position together:
   - name set in a heading font (≥ ~1.25× body) → strong signal it *starts* the writeup
   - name at line start → good signal
   - occurrence near the item's stat page (`meta.page`, ± window) → preferred
   - followed by prose rather than a stat row → keep; followed by stats / another item
     name → likely a table mention, skip
   - exact full-name match preferred over partial/base-name match
   The best-ranked candidate wins. Font is **not required** — a strong text match with
   prose after it still qualifies when there is no large heading.
3. **Block = the associated text, whatever its length.** From the anchor, capture
   forward until a real boundary — the **next item/heading, a stat/table row, or a
   clear section end**. Result may be a single sentence or several paragraphs; capture
   it whole (up to a generous char cap). **No one-sentence cap.**

## Cleaning

Applied to the captured block:

- **Dehyphenate** line-break hyphens (`enhance-\nment` → `enhancement`).
- **Join columns** in reading order (no left/right bleed on the same visual row).
- **Strip a stray leading fragment** — if the block starts with a lowercase word that is
  the tail of the heading line, drop it so the text starts at a sentence.
- **End on a complete sentence** — trim a trailing partial sentence; cap total length at
  a generous limit (e.g. ~3500 chars) but only at a sentence boundary.

## Fallback chain (decided)

Per item, in order:

1. Confident writeup from the book (above) → use it.
2. Else the item's existing `notes` field, **only if it is real prose** → use it.
3. Else leave `description` empty.

`notes` is **read-only** in this rebuild — never rewritten, only read as a fallback
source.

## Replace scope & safety

- **Overwrite** `description` for **all items EXCEPT** those with a correction file
  (`data/_corrections/<domain>/<id>.json`) — corrected items are never touched.
- Run `tools/apply_corrections.py` **last** (belt-and-suspenders re-overlay of the 173
  manual corrections).
- **Dry run by default**, printing before/after diffs and a summary; `--apply` writes.
- Corebook is the curated seed and is not re-imported; editing its JSON in place is the
  persistent change. This tool edits `data/corebook/<domain>/*.json` directly.

## Stat/boundary detection (shared rules)

A line is a **stat/table row or boundary** (ends a block, never enters prose) when it
matches any of:

- contains `¥` (nuyen), or a price like `1,500` in a stat context
- damage/dice codes: `\d+[PS]`, `\d/\d`, sequences like `2P 3P 4P`
- ALL-CAPS column headers of table width (e.g. `HAND ACC SPD … AVAIL COST`, `AVAIL COST`)
- a bare page number / running header
- the next detected heading (name of another item)

Blocks whose content is **dominated** by such tokens are rejected (→ fallback), which
kills the table-fragment failure mode.

## Components

- **`extractor/writeups.py`** — extraction core, pure and unit-tested. Public surface:
  - `book_headings(pages) -> HeadingTable` — font-aware headings + text index for a book.
  - `find_block(name, meta_page, book_model) -> str | None` — anchor → rank → capture →
    clean; returns cleaned prose or `None`.
  - `clean_block(lines) -> str` — dehyphenate, column-join, strip leading fragment,
    sentence-trim. Independently testable.
  - `is_stat_line(text) -> bool`, `is_boundary(...)` — the shared rules above.
- **`tools/rebuild_descriptions.py`** — driver: iterate domains/items, open each source
  book once, call the core, apply the fallback chain, skip corrected items, dry-run/apply,
  print the summary and smell-check.

The existing `describe.py` / `enrich.py` remain for the importer; `writeups.py`
supersedes them for the bulk description rebuild.

## Testing & verification

- **Unit tests** on the core with synthetic line streams:
  - heading + multi-paragraph prose + next heading → full block captured
  - heading + stat row → stat row rejected, prose only
  - hyphenated line break → dehyphenated
  - two-column visual row → joined in order, no bleed
  - leading lowercase fragment → stripped
  - block ends mid-sentence in source → trimmed to last complete sentence
  - name appears only in a table (no prose) → returns `None` (→ fallback)
- **Dataset smell-check** (run after `--apply`): count descriptions still containing `¥`
  or dice codes → **target 0** (currently high). Also report length distribution to spot
  over-truncation.
- **Summary metrics:** filled-from-book / from-notes / left-empty / skipped-corrected.

## Non-goals

- Recovering the mangled item *names* (tracked separately in
  `docs/gear-subtype-worklist.md`).
- Rewriting `notes`.
- Changing the importer's own enrichment path.
