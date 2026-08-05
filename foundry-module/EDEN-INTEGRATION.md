# Integration contract: shadowrun6-eden + Foundry v13/v14

What SR6 Forge depends on in `shadowrun6-eden` 4.0.3 and the Foundry client,
established by reading their source rather than their release notes. Re-check
this file when either upgrades.

## Version posture

| package | version | compatibility |
|---|---|---|
| shadowrun6-eden | 4.0.3 | min 13, **verified 14.365**, max 14 |
| sr6-forge | 0.4.0 | min 13, verified 14 |
| sr6-forge-corebook | 0.4.0 | min 13, verified 14 |

Eden branches on `game.release.generation` in several places and already ships a
v14-specific ActiveEffect data model and sheet, so it is genuinely v14-aware
rather than merely tagged.

## The actor contract — what we write, what eden derives

Eden computes attribute pools in `module/documents/actor.js`:

```js
system.attributes[attr].pool = Math.max(0, parseInt(base) + Math.min(4, parseInt(mod)));
```

Two things that are easy to get wrong: **`mod` is capped at 4**, and **`augment`
is not part of the pool at all**. Eden also forces `mag.base = 0` when the actor
is not Awakened and `res.base = 0` when not Emerged, and clamps `system.edge.value`
to 7.

Field shapes from `template.json` — writing the wrong shape loses data silently:

| attribute | shape |
|---|---|
| `bod` `agi` `rea` `str` `wil` `log` `int` `cha` | `{base, mod, modString, augment, pool}` |
| `edg` | `{current, max}` — **no `base`** |
| `mag` | `{base, mod, pool, min, initiation}` |
| `res` | `{base, mod, pool, submersion}` |

So advancement writes initiation to `system.attributes.mag.initiation` and
submersion to `system.attributes.res.submersion`, and Edge raises go through
`edg.max`/`edg.current` rather than a base. Skills are
`system.skills.<id>.{points, specialization, expertise}`.

We write none of: `pool`, `mod`, `modString`, the condition monitors, `derived`,
`initiative`, or essence.

## Data models — a live migration to watch

Eden is midway through moving types onto `TypeDataModel`:

```js
Object.assign(CONFIG.Actor.dataModels, { sprite: …, host: … });
Object.assign(CONFIG.Item.dataModels,  { mod: …, software: … });
```

**`Player` is not among them**, nor are `gear`/`quality`/`skill`/`spell`. Those
still use the permissive legacy `template.json` path, which is why our raw
writes land intact. If a future eden release gives `Player` a DataModel, unknown
keys will start being stripped on create — the `sr6-forge.commit` Quench batch
is what will catch that.

## Compendium index fields — an ordering hazard, mitigated

Eden **assigns** rather than appends:

```js
CONFIG.Item.compendiumIndexFields = ["name", "type", "system.genesisID"];
```

Anything pushed before that line is discarded. We currently win on load order —
the server orders script injection by priority in `dist/server/views/view.mjs`:

| priority | packages |
|---|---|
| 4 | `library: true` module esmodules |
| 6 | **system** esmodules (eden) |
| 8 | normal module esmodules (us) |

so eden's `init` runs before ours. That is not a thing to depend on: a library
module would load *before* the system, and eden could reorder its own init. We
therefore re-apply our fields on `setup`, after every `init` has run, which makes
the outcome independent of ordering entirely.

## Item creation

Eden registers `preCreateItem` (`module/Shadowrun6.js`). On every item created it
swaps in the system icon for the item's type, and when a translation exists for
`<type>.<genesisID>` it replaces the item's name and description with eden's
localized text. This is why the committer embeds via `createEmbeddedDocuments`
instead of inlining items into the actor's creation data — inlined items skip
the hook.

Note that eden's `genesisID`-based compendium re-import lives in its *importer*
for GENESIS/Commlink6 JSON, not in the normal creation path.

## Sheets and hooks

Eden's PC sheet (`Shadowrun6ActorSheetPC`) is still **ApplicationV1** — it uses
`static get defaultOptions` and a `template:`, and eden registers it after
`Actors.unregisterSheet("core", foundry.appv1.sheets.ActorSheet)`.

AppV1 fires header-button hooks across the whole class chain
(`this._callHooks(className => \`get${className}HeaderButtons\`)`), so
`getActorSheetHeaderButtons` reaches eden's subclass. But v13 has already
namespaced AppV1 under `foundry.appv1` and the client's own source calls it
deprecated, so the migration is coming. We register all three entry points:

| hook | covers | contract |
|---|---|---|
| `getActorSheetHeaderButtons` | today's AppV1 sheet | `(sheet, buttons)`, unshift |
| `getHeaderControls` | AppV2, whenever eden migrates | `(app, controls)`, unshift |
| `getActorContextOptions` | Actors directory, no sheet needed | `get${documentName}ContextOptions` |

A Quench assertion fails if any of the three loses its listener.

## ActiveEffects

Eden swaps its AE data model and config sheet on `game.release.generation === 14`,
because v14 introduces `foundry.data.ActiveEffectTypeDataModel` as a new base
whose schema must be spread into subclasses. This does not affect us: we define
no AE type data model, and `commitPlan().effects` is always empty — qualities
carry their own effects from the packs.

## v14 deprecations

The v13.351 client marks 26 APIs `since: 14`. None are ones we call: they cover
`documentCollection`/`documentId` on journal and drawing classes, shader
getters, `CONFIG.<Document>.layerClass`, and some canvas internals. Our surface
is entirely the modern namespaced API — `foundry.applications.api.*`,
`foundry.applications.handlebars.renderTemplate`, `foundry.utils.*` — with no
legacy globals (`mergeObject`, `duplicate`, `Dialog`, `FormApplication`,
`entity.*`, `.data.data`) anywhere in `scripts/`.
