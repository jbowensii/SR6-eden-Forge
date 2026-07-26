# Decisions

## 2026-07-25 — Correction tables live in data/, not the repo

Parser correction hooks (RENAMES/OVERRIDES/EXCLUDE/MANUAL_ITEMS) contain real
item names and stat blocks, so committing them would put book content in a
public repo. They load from gitignored `data/_fixes/<book>_<domain>_fixes.py`.
Consequence: the public repo alone cannot reproduce a fully-corrected dataset —
by design. Stale hook keys fail the parse loudly so the correction layer
self-checks against engine changes. **Back up `data/` separately.**

## 2026-07-25 — Editor renders by value type, not schema (v1)

design.md §5 envisioned schema-driven forms. The shipped editor renders each
`system` field by its VALUE type (bool/number/string + widgets for
`modes`/`attackRating`), and `/api/schema/:domain` exists but the UI does not
consume it yet. Accepted for the gear-only v1 because every extracted item
already carries its relevant fields. Known limitation: **a field absent from
an item (e.g. optional `description`) cannot be added through the UI** — it
needs a JSON edit or a future "add field" control fed by the schema route.
Revisit when a second domain (npcs/spells) lands.

## 2026-07-25 — Integral-float formatting drift accepted

Python writes `1.0` where Node writes `1` (e.g. cyberware `essence`). The first
app save of such an item produces cosmetic numeric reformatting in the
(untracked) data file. Harmless to schema, validator, and Eden; not worth a
normalization pass.
