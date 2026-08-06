# SR6 Forge

**Turn the Shadowrun PDF books into a live Foundry VTT library — then roll characters against it in minutes.**

[![License: MIT](https://img.shields.io/badge/license-MIT-00d4c8.svg)](LICENSE)
![Foundry v14](https://img.shields.io/badge/Foundry-v14-c4183c.svg)
![System: shadowrun6-eden](https://img.shields.io/badge/system-shadowrun6--eden%204.0%2B-1b1f2a.svg)

---

Rolling a runner by hand is an hour of arithmetic before anyone touches a die. Priority columns, adjustment points, karma at five times the *new* rating, essence bleeding out of every implant, availability caps, the nuyen you forgot to convert. Get one number wrong on the Attributes page and you find out three steps later, at the gear table, with no idea which number it was.

Two halves fix that, and you need both.

| | | |
|---|---|---|
| **Part 1** | **The Catalog Builder** | Reads your PDFs, extracts the tables, lets you correct and illustrate every entry, and compiles the **Shadowrun 6th World Catalog** — a Foundry compendium built on your machine |
| **Part 2** | **SR6 Forge** | The character generator that shops from that catalog, and the karma ledger that keeps running long after creation |

They are separate on purpose. Part 1 handles content that isn't ours to give away. Part 2 is rules logic, and that we hand out freely.

---

## Your PDFs are the licence

**This repository contains no game data. None. Not one weapon, not one spell.**

The pipeline reads the books **you already bought**. The PDF on your drive is what entitles you to the data the extractor produces from it — that is the whole arrangement, and it is why nothing is bundled here. No PDF, no data. Buy the books.

Shadowrun is a registered trademark of The Topps Company, Inc.; Catalyst Game Labs publishes the Sixth World under licence. `data/`, `export/` and every PDF are gitignored, and `git log` will confirm they were never committed — not buried in an old commit, never there at all. The handful of sample files under `examples/` and `site/shared/` each carry an explicit `_notice`; the "Example Autopistol" is invented, and exists only to show a record's shape.

**Do not redistribute what comes out the far end.** It is the books, in another format.

---

# Part 1 — The Catalog Builder

### What you need

| | |
|---|---|
| **The PDFs** | Core Rulebook, Sixth World Companion, and whatever supplements you own. Required. |
| **Python 3.11+** | `pip install -r requirements.txt` |
| **Node 20+** | for the review app and the pack compiler |
| **Commlink6** *(optional)* | the Java generator from [rpgframework.de](https://rpgframework.de) |

## Reading the books

The extractor is the part that matters, because the books are the only complete source. **Commlink6 has been slow to pick up newer releases**, and a rules engine that can only see what someone else has already transcribed will always trail the books. This one reads the PDFs directly, so a supplement is available the day you buy it.

That is harder than it sounds. A Shadowrun page is a designed artefact, not a database dump: three columns that break for a sidebar, tables with no ruled lines, headers that only differ from body text by a point and a half, dual damage codes, ranges printed as five numbers in a row that mean five different things.

So the extractor works the way a person reads a page, and there is a module for each part of that:

- **Layout first** — `columns.py`, `textcols.py` and `segment.py` recover the column structure, then `toc.py` and `hierarchy.py` rebuild the section tree, so an item lands under the right heading and carries its real page number.
- **Tables by geometry** — `xtable.py` and `rowengine.py` read columns by x-position rather than by whitespace, which is what makes an unruled stat block parse at all.
- **Typography as meaning** — `spell_layout.py` and `lifepath_pdf.py` identify records by font metrics: a 17.8pt Sans line is a module header, 13pt is a label, that particular bullet glyph starts a benefit. It is how the Companion's life modules were recovered when nothing else had them.
- **Domain readers** — separate passes for gear, weapons, armour, vehicles, spells, rituals, adept powers, qualities, critters, spirits, contacts, lifestyles, toxins and drugs. Each knows its own table shape.
- **Repair and inference** — `demangle.py` fixes ligatures and OCR damage, `normalize.py` regularises units and codes, `subtype_infer.py` and `autodetect.py` classify what the page left implicit, `words.py` and `glossary.py` catch the rest.
- **Prose too** — `describe.py` and `writeups.py` pull the flavour text, so an item arrives with its description rather than a bare stat line.
- **Art** — `images_extract.py` lifts illustrations off the page and `icon_match.py` pairs items with icons.
- **Alignment** — `eden_align.py` and `eden_codes.py` translate everything into the type and subtype vocabulary the Foundry system already speaks.

### Where Commlink6 helps

If you have it installed, the pipeline reads it too — not for the content, but for the **structure the printed page leaves implicit**:

- **Counted mounts.** Glasses declare `<valmod type="HOOK" ref="OPTICAL" value="$RATING"/>` — rating *is* how many accessories fit. The book never says so; 290 items depend on it.
- **What a quality hands over.** SINner declares `<itemmod type="SIN" ref="REAL_SIN"/>`; Shifter hands out four more qualities. Twenty-six qualities grant something, each saying so in its own data.
- **PACKs** — the Companion's pre-built kits with their true contents, 177 of them.
- **Orderings you would guess wrong.** Fake SIN quality levels run *rough match 2, good match 3, superficially plausible 4*.

Without Commlink6 you still get a full catalog from the PDFs. With it, those mechanisms are read from a declaration instead of inferred. Where the two ever disagree on a rule, **the book wins** — every rules constant is cited to a page.

## Correcting it: the review app

No extractor is perfect on a designed page, and you should never ship data you haven't looked at. So the pipeline's centre of gravity is a **local web app**, not a command line.

```bash
cd site && npm install && npm run serve     # http://localhost:8347
```

Express and React, running only on your machine. From it you can:

- **Browse everything** by book, domain and category, with search and filters
- **Edit any field** — fix a price the OCR fumbled, correct a damage code, retype a mangled name
- **Write and repair descriptions**, including the flavour text pulled off the page
- **Assign icons and artwork** — search a local icon library, pull illustrations lifted from the book, crop and background-strip renders, and preview them exactly as the sheet will show them
- **See the real output** — the exact Foundry document JSON an item will become, live beside the record
- **Mark QA status**, so nothing reaches a character sheet before a human has approved it
- **Apply bulk corrections** from a correction file, and re-run them after a re-extract

**The website builds the module.** When the data looks right, export from the app (or `node site/scripts/build_module.mjs --deploy`) and it compiles the approved records into LevelDB compendium packs with the official `@foundryvtt/foundryvtt-cli`, writes the manifest, and drops the finished module into your Foundry `Data/modules`.

That module is the **Shadowrun 6th World Catalog**. Enable it in your world and Part 2 has shelves to shop from.

### The short version

```bash
pip install -r requirements.txt
python tools/ingest_all.py            # PDFs -> data/<book>/<domain>/*.json
python tools/build_chargen_data.py    # rules tables and mechanisms
cd site && npm run serve              # review, correct, illustrate, export
```

---

# Part 2 — SR6 Forge (the module)

The character generator. Install from a release; it carries no game data.

### Install

In Foundry: **Add-on Modules → Install Module**, paste:

```
https://github.com/jbowensii/SR6-eden-Forge/releases/latest/download/module.json
```

| Requires | |
|---|---|
| **Foundry VTT** | v14 |
| **shadowrun6-eden** | 4.0.0+ — [yjeroen/foundry-shadowrun6-eden](https://github.com/yjeroen/foundry-shadowrun6-eden) |
| **Shadowrun 6th World Catalog** | built by Part 1. Foundry won't block you without it, but the wizard opens onto empty shelves and says so. |

### What it does

**Five ways to build a runner** — Priority, Sum-to-Ten, Point Buy, Karma, and the Companion's Life Path. One engine, a different budget provider on top of each.

**It shows the maths.** Every budget is itemised. Karma doesn't just say *85 spent* — it names the raise:

```
Customization karma            50
 +30  Negative qualities
 −25  STR 1 → 3 (2 ranks by karma)
 −35  WIL 2 → 4 (2 ranks by karma)
 −10  Positive qualities
 −15  Spells beyond the free ones
 −10  Converted to nuyen
────
  −5  remaining
```

Because a rank costs five times the *new* rating, and that is where budgets quietly die.

**It knows the fiddly rules**, and cites them:

- Mystic adepts split priority Magic between power points and spells (core p67) — spend it all on powers and your spells cost karma
- Fake SIN rating × 2,500¥; fake licence rating × 200¥, assigned to one SIN and never out-rating it (core p274)
- Contact points are Charisma × 6, neither rating above Charisma at creation (core p68)
- Six qualities maximum, net bonus karma capped at 20 (core p67)
- Availability caps, essence floors, one-attribute-at-maximum

**The system does the derivation.** SR6 Forge writes raw inputs only — attribute bases, skill ranks, embedded items, nuyen. Pools, condition monitors and essence are computed by shadowrun6-eden at runtime, exactly as for a character built by hand. That is the architecture, and there is a test named after it.

**Karma advancement** continues after creation: raise attributes and skills, buy qualities, learn spells, initiate, convert karma to nuyen. Every purchase lands in an append-only ledger with a strict undo.

**Homebrew fits.** Anything the books don't cover goes in as a custom item at a price you set.

### Rule interpretations

Tables disagree. Set yours in **⚙ Optional Rules**: Core Rulebook, Standard (Seattle), Shadowrun Missions or House Rules, with per-switch overrides on top. The engine reads the interpretation rather than hardcoding one.

---

## Layout

| Path | Part | What |
|---|---|---|
| `extractor/`, `tools/` | 1 | PDF readers, layout and table engines, domain passes, jar readers |
| `schemas/`, `validator/` | 1 | JSON Schemas and the sanity checker |
| `site/` | 1 | Review app, pack compiler, deploy scripts |
| `foundry-module/sr6-forge/` | 2 | The module: engine, wizard, advancement, services |
| `data/`, `export/` | — | **Gitignored.** Your books, your machine. |

## Testing

```bash
python -m pytest -q                       # 211  extraction and rules data
cd foundry-module && npm test             # 173  engine, budgets, commit plan
cd site && npm test                       #  43  export and API
```

Inside Foundry, with [Quench](https://foundryvtt.com/packages/quench) enabled:

```js
quench.runBatches("sr6-forge.*")
```

Seven batches covering what only exists in a live world — that eden derives the pools from what we wrote, that our data survives document creation, that every window class loads.

## Credits

**[shadowrun6-eden](https://github.com/yjeroen/foundry-shadowrun6-eden)** — Yeroon, with Stefan & Anja Prelle. The system this is built on. It owns the data models and derives every computed value, which is why SR6 Forge writes raw inputs and gets out of the way.

**Commlink6 / Genesis** — Stefan Prelle, [rpgframework.de](https://rpgframework.de). The Java generator whose data settles what the printed page leaves implicit, and whose editor set the workflow this wizard follows.

Shadowrun is a registered trademark of The Topps Company, Inc. Game content © Catalyst Game Labs. This project is unaffiliated with either, and ships neither.

## Licence

[MIT](LICENSE) — the code, verbatim, so tooling reads it correctly.
[NOTICE](NOTICE) — what that licence does *not* cover. The data was never
ours to license, and isn't here.
