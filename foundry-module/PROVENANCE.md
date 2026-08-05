# Provenance — where SR6 Forge's code and numbers come from

Personal-use build. This file records what was written here, what was read from
elsewhere, and how the boundary between the two is kept.

## Code

**No code from Commlink6 is present in this module.** Nothing was decompiled and
transcribed, and no class, method or algorithm was ported. The module is written
against Foundry VTT's ApplicationV2 API and the `shadowrun6-eden` system's data
model, in the idiom of those two projects.

Commlink6 was used in exactly two ways, both of them reading rather than copying:

1. **As a data source.** `extractor/commlink6.py` and `extractor/chargen_xml.py`
   read the XML and `.properties` files bundled in its jar — the same statistics
   the books contain. The readers are this project's own code.
2. **As a reference for one number.** The Karma-build method is not described in
   any English rulebook we own. Its 1000-karma budget was read out of the
   application's compiled `KarmaCharacterGenerator` and is labelled as such in
   `data/creation-rules.json` (`karmaBuild._source`), shown to the user on the
   Karma Pool step, and overridable from the options screen.

### Identifier boundary

The source data labels its optional rules with `SCREAMING_SNAKE` constants
(`CHARGEN_MAX_AVAILABILITY`, …). That is the upstream application's identifier
namespace, not ours. It is translated **once**, at the import boundary, by
`RULE_SETTING_NAMES` in `extractor/chargen_xml.py`:

| upstream rule id | our setting name |
|---|---|
| `CHARGEN_MAX_AVAILABILITY` | `maxAvailability` |
| `CHARGEN_MAX_KARMA_REMAIN` | `maxKarmaRemaining` |
| `CHARGEN_NEGATIVE_NUYEN` | `allowNegativeNuyen` |
| `CHARGEN_SUM_TO_TEN_ELITE` | `sumToTenTarget` |
| … | … (27 in total) |

Everything downstream — `chargen-data.json`, the engine, the options screen, the
world settings — speaks only the camelCase names. A Quench test
(`sr6-forge.data`) asserts that no untranslated id ever reaches the shipped data.

### Names that are deliberately *not* ours

These come from `shadowrun6-eden` and Foundry, and must match them exactly:

- `system.genesisID` — eden's cross-compendium item identity
- `system.mortype`, `system.metatype`, `system.karma`, `system.nuyen`
- `system.attributes.<attr>.base`, `.max`, `.current`, `.initiation`, `.submersion`
- `system.skills.<id>.{points,specialization,expertise}`
- `DEFAULT_OPTIONS`, `PARTS`, `_prepareContext`, `_onRender` — ApplicationV2

## Rule values

Every number in `data/creation-rules.json` carries either a `verified` string
quoting the rulebook and page, or an explicit `_source` note when no English
book we own covers it. There are currently **no unverified values** — the
`verify:` placeholders from the planning phase are all resolved.

Books used, all owned in PDF (paths in `data/books.json`, never committed):

- *Shadowrun, Sixth World* core rulebook (CAT28000) — pp. 58–70
- *Sixth World Companion* (CAT28005) — pp. 27–48

Two corrections came out of that verification pass and are worth calling out,
because the implementation had been wrong:

- **Spells at creation are free.** Core p66: a full magician gets *priority*
  Magic × 2 spells or rituals, a technomancer Resonance × 2 complex forms, and
  both use the priority-table rating "not as altered with any points, Karma, or
  any other adjustments". The engine had been charging 5 Karma each from the
  first spell.
- **Mystic adept power points are not bought with Karma.** Core p67: they
  "split their Magic between spells and adept powers", buying power points out
  of the priority Magic and doubling the remainder for spells.

## Game data and copyright

`data/` is gitignored and no game data is committed. The compendium packs are
built locally from the user's own books and the Commlink6 install, and the
module manifest states it is a personal-use build, not for distribution.
Shadowrun is a registered trademark of The Topps Company, Inc.; Catalyst Game
Labs publishes under licence. This project is unaffiliated with either.
