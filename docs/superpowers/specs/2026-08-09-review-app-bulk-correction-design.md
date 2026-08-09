# Review app: safe, fast bulk correction

**Date:** 2026-08-09
**Status:** approved, ready for planning
**Scope:** `site/` only — React front end, two Express routes, one Python
correction change. No change to the extraction pipeline or the export format.

## Why

The review app is where manual corrections happen, and manual corrections are
the one thing in this project that cannot be regenerated. Two problems make
that work slower and riskier than it should be:

1. **Unsaved edits are discarded silently.** `App.jsx` passes
   `key={editing.id}` to `ItemEditor`, and the editor builds its draft with
   `useState(() => structuredClone(item))`. Selecting another row remounts the
   component and rebuilds the draft. Type a description, click the next item
   without saving, and it is gone — no prompt, no warning, no trace. There is
   no dirty flag, no `beforeunload`, no confirm anywhere in the app.

2. **Every correction is one item at a time.** The 0.9.5 import left a known
   backlog — 24 vehicles with mangled names, 47 duplicate rows, 134 gear items
   with no subtype, 39 critter powers with no description. All of it is
   repetitive: the same subtype on fourteen rows, the same junk deleted twenty
   times. One-at-a-time editing makes a mechanical job into an afternoon.

A third problem is adjacent and cheap to fix while we are here: the Setup
panel's Rebuild button runs the pipeline against the wrong library.

## What we are building

### 1. Selection and the bulk-edit model

`App.jsx` owns a `selectedIds` Set. `CategoryTable` gains checkbox selection
with shift-range and ctrl-toggle; clicking a row still opens it on its own.

`ItemEditor` takes `items: [...]` instead of `item`. A single selection is a
list of one, so there is no second code path to keep in step — the bulk case
and the single case are the same case.

The editor's draft changes shape. Today it is a full clone of the item; it
becomes a **`touched` map** of `{field → value}`, empty until you type.

- A field whose value is the same across the selection shows that value.
- A field whose value differs shows `— mixed —` as a placeholder.
- Typing sets that field for every selected item.
- **Untouched fields are never written.**

That last rule is the one the user asked for in as many words ("only touch the
fields I change"), and it happens to match the delta shape `recordCorrection`
already stores, so bulk edits and single edits produce the same kind of
correction record.

**Save posts once** to a new `PATCH /api/items`, rather than N requests from
the browser. The server applies the delta to each item and writes one
correction record per item, so a bulk edit replays on re-import exactly like a
single one.

The payload carries a full locator per item, not bare ids:

```json
{ "targets": [{ "book": "corebook", "domain": "gear",
                "category": "weapons_firearms", "id": "ares_predator_vi" }],
  "changes": { "system": { "subtype": "PISTOLS_HEAVY" } } }
```

`store.writeItem` needs `book/domain/category/id` to find a file, and a
selection made from search results can span books and domains. Sending ids
alone would force the server to guess, or to scan every domain.

### 2. Edit safety

`touched.size > 0` is the dirty flag.

- Changing selection while dirty prompts before discarding.
- `beforeunload` guards closing the tab.
- The status bar shows an unsaved marker.

All selection changes route through a single `requestSelection()` in
`App.jsx`. One chokepoint, so a future caller cannot bypass the guard by
setting state directly — the bug being fixed exists precisely because there
was no such chokepoint.

### 3. The "needs attention" filter

A checkbox above the table. An item needs attention when **a required Eden
field is blank, or validation reports an issue**.

`qaStatus: extracted` deliberately does NOT count. Most of the library is
`extracted`, so counting it would flag nearly everything and the filter would
mean nothing.

`ItemEditor` already computes Eden required-field gaps for its readiness
panel. That logic moves into `shared/edenSpec.mjs` so the table and the editor
share one definition rather than drifting apart.

### 4. Bulk delete

Right-click the table → "Delete N selected". The confirmation names up to
twelve items and gives the total.

Deletion gets a heavier confirmation than editing on purpose: it is the one
correction that cannot be verified by looking at the library afterwards,
because the evidence of a mistake is an absence.

One `DELETE /api/items` with `{targets}` — the same locator shape as the
patch route, for the same reason. Each writes a tombstone.

**Tombstones gain `ref: {name, book}`, and `apply_corrections.py` gains a
matching fallback: id first, then name+book.**

This is not optional. Tombstones currently match on `id` alone:

```js
rec = { domain, category, id, deleted: true, correctedAt }   // no ref
```

Edits already carry `ref` so an item can be re-found when its id moves. Today
that exact failure occurred: fixing wrapped vehicle names changed
`krupp_bentley` into `cl6_saeder_krupp_bentley_concordat`, and three
corrections lost their target.

It matters more for deletions than for edits, because the junk worth deleting
has the least stable ids of anything in the library. `OFF ROAD) INTERVAL Dodge
Scoot Harley-Davidson` slugs to `off_road_interval_dodge_scoot_harley_davidson`;
any future reader improvement changes that string, the tombstone stops
matching, and a row deleted months ago quietly returns.

### 5. Two fixes outside the UI

**`/api/rebuild` runs against the wrong library.** It spawns
`tools/rebuild_all.py` with `cwd: repoRoot` and no `SR6_DATA`, so it rebuilds
the repo's development copy rather than the workspace the server is serving.
The route immediately below it, `/api/corrections/apply`, passes
`env: { SR6_DATA: dataRoot }` and carries a comment explaining why. Rebuild
missed it. Same fix.

**CSS.** Findings from the review, all verified rather than eyeballed:

| Issue | Detail |
|---|---|
| `.modal` declared twice | lines 210 and 506, conflicting border, radius and `clip-path` |
| Two backdrops | `.modal-backdrop` (z 50) and `.modal-overlay` (z 100) doing one job |
| Dead duplicates | `.art-row`, `.cell-ref`, `.editor textarea`, `.editor` |
| Clipped scroller | `.modal` has `clip-path` and `overflow-y: auto`; content and scrollbar cut at the chamfer |
| Contrast: primary button | white on `#e5177b` = **4.43**, just under AA's 4.5 |
| Contrast: `.empty-glyph` | `#3a4157` on `#0b0d12` = **1.92** |
| Focus rings | several inputs set `outline: none` with only a border-colour change |

Everything else measured 5.6–14.1 and is fine. The theme is in good shape;
these are the exceptions.

## Out of scope

**No undo.** A mistaken bulk edit is corrected by editing again; a mistaken
bulk delete is recovered from the backup. Undo is a real feature with its own
design — an inverse-operation log, or snapshots — not a detail to slip in
here.

**No effects.** Eden's ActiveEffect system, and the 2,239 Commlink6
`<modifications>` entries the extractor currently discards, are Spec 2. That
work touches the Python extractor, the merge, the authority guard, the
correction format and the exporter; it does not belong in a front-end spec.

Spec 1 comes first because the edit-loss bug destroys work today, and because
the effects editor will want multi-select and the needs-attention filter
anyway — building them first means Spec 2 inherits them.

## Testing

**Vitest**, `site/tests/`:

- `PATCH /api/items` applies only the fields present in `changes`, across targets in different books
- it writes one correction record per item, in the delta shape
- `DELETE /api/items` writes a tombstone per item, each carrying `ref`
- one bad id in a batch does not prevent the rest from applying
- the needs-attention predicate agrees with the editor's readiness panel

**Pytest**, `tests/`:

- `apply_corrections` matches a tombstone by `ref` when the id has changed —
  the failure actually observed on 2026-08-08
- an id-matched tombstone still works, so old records keep functioning

**Manual**, because there is no UI test rig: run the app, edit and switch
without saving (must prompt), bulk-set a subtype across a selection, bulk
delete, re-import and confirm the deletions stay deleted.

A source-level check guards the regression being fixed: `App.jsx` must contain
no call to the selection setter outside `requestSelection`. Parsing the source
for that is exact and cheap, in the same spirit as the test added for `app.py`
that asserts the window only calls functions its modules define. It catches
the thing that actually goes wrong — someone adding a new way to change
selection and not knowing the guard exists.

## Files

| File | Change |
|---|---|
| `site/src/App.jsx` | `selectedIds`, `requestSelection`, dirty guard, `beforeunload` |
| `site/src/components/CategoryTable.jsx` | checkbox selection, shift/ctrl, right-click menu, filter checkbox |
| `site/src/components/ItemEditor.jsx` | `items[]`, `touched` map, mixed-value display, bulk save/delete |
| `site/src/api.js` | `patchItems`, `deleteItems` |
| `site/server/app.mjs` | `PATCH /api/items`, `DELETE /api/items`, `SR6_DATA` on rebuild |
| `site/server/store.mjs` | bulk apply, tombstone `ref` |
| `site/shared/edenSpec.mjs` | shared needs-attention predicate |
| `site/src/styles.css` | duplicate and contrast fixes |
| `tools/apply_corrections.py` | tombstone `ref` fallback |
