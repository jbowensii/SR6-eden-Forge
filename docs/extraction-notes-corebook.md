# Extraction notes — SR6 Core Rulebook (CAT28000, Current Printing)

Gear chapter: PDF pages **245–304**. Dump command:

```bash
python -m extractor dump --pdf "<corebook pdf>" --book corebook --pages 245-304
python -m extractor parse --book corebook --domain gear
```

## Category map (21 files, 463 items)

| Category file          | Pages   | Types                         | Items |
| ---------------------- | ------- | ----------------------------- | ----- |
| weapons_close_combat   | 250-251 | WEAPON_CLOSE_COMBAT           | 18    |
| weapons_ranged         | 251     | WEAPON_RANGED                 | 6     |
| weapons_firearms       | 251-260 | WEAPON_FIREARMS               | 52    |
| weapons_special        | 259-265 | WEAPON_SPECIAL                | 14    |
| weapon_accessories     | 262     | ACCESSORY                     | 18    |
| ammo                   | 251-263 | AMMUNITION                    | 18    |
| clothing               | 266     | ARMOR (clothes)               | 3     |
| armor                  | 267     | ARMOR                         | 10    |
| armor_additions        | 267-268 | ARMOR_ADDITION                | 8     |
| electronics            | 268-278 | ELECTRONICS                   | 72    |
| software               | 273     | SOFTWARE                      | 11    |
| security               | 279     | ELECTRONICS (security)        | 9     |
| tools                  | 275,280 | TOOLS                         | 13    |
| chemicals              | 280     | CHEMICALS                     | 3     |
| survival               | 281-282 | SURVIVAL                      | 20    |
| biotech                | 282-283 | BIOLOGY                       | 13    |
| cyberware              | 285-291 | CYBERWARE                     | 89    |
| bioware                | 294-295 | BIOWARE                       | 22    |
| magical                | 295-296 | MAGICAL                       | 15    |
| vehicles               | 302-303 | VEHICLES                      | 29    |
| drones                 | 303     | DRONES                        | 20    |

## Layout quirks encountered (and how they're handled)

1. **Wrapped names** — long names print above/below their data line
   (`Vendor Gunname` / `V 4P SS …`). The row engine picks the longest
   buffer suffix whose name looks plausible; residual fragments are fixed
   via profile `RENAMES` (~90 entries).
2. **Names wrapped AROUND the data line** (`VendorName` / data / `ModelName`)
   cannot be reassembled — the parsed partial is dropped via `EXCLUDE` and
   the item re-added exactly via `MANUAL_ITEMS`.
3. **Two-column prose interleave** — tables set in one column get prose from
   the other column glued before/after the cells. Handled by
   `RowSpec(allow_tail=True)` (discard trailing junk) and leading-junk
   trimming (drop words until the name starts with a capital/digit).
4. **Stray page numbers** inside rows — stripped via `page_numbers={p-1,p,p+1}`.
5. **Formula stats** — `Rating x 250¥`, `Rating^2 x 30,000¥`, `Force x 5,000¥`,
   `Capacity x 100¥`, `[Rating]` capacities, `1—6` spans, `(Force) L`
   availability. Numeric fields get 0 + `priceDef`/`availDef` + `needsRating`.
6. **Matrix tables** (ammo types/costs) and **dual-stat rows**
   (dual-model rows priced `X¥/Y¥`) → `MANUAL_ITEMS`.
7. **Printing typos**: one light pistol's attack rating is missing a slash
   (`9/8/6—/—`); the bodyware column header repeats EARWARE; one assault
   cannon is housed in the machine guns table.
8. **Repeated rating rows** (`Rating 2` appears under cyberjacks, cybereyes,
   cyberears) — RENAMES/OVERRIDES accept page-qualified keys
   `(category, slug, page)`.
9. **Duplicate names across categories** (Smartlink, Laser sight, Simrig … as
   both external gear and cyberware) — cyberware variants renamed with a
   `(cyberware)` suffix so ids stay unique book-wide.

## Verification

- `python -m validator data/corebook` → OK: 21 file(s), 463 item(s).
- Every category's names were diffed against the raw page text by the
  controller during profile development (docs/design.md §3 QA loop).
- `pytest` — 75 tests green (engine behaviors incl. every quirk above).
