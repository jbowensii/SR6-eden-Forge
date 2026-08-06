/** In-Foundry integration tests, run through Quench.
 *
 *  The vitest suite covers the engine as pure functions — it deliberately has
 *  no Foundry available. These batches cover exactly what that cannot reach:
 *  the live compendium indices, the actor the committer really creates, and
 *  whether shadowrun6-eden derives the stats we expect from the raw inputs we
 *  write. Every batch that creates a document deletes it again in teardown.
 *
 *  Enable the Quench module and open its window, or run from the console —
 *  note the method is runBatches (plural) and takes a glob:
 *
 *      quench.runBatches("sr6-forge.*")        every batch here
 *      quench.runBatches("sr6-forge.commit")   just the commit path
 */
import { MODULE_ID, SETTINGS, ACTOR_SKILLS, catalogIdOf } from "../config.mjs";
import { chargenData } from "../main.mjs";
import { ChargenEngine, blankState } from "../engine/chargen-engine.mjs";
import { freeSpellSlots } from "../engine/budgets.mjs";
import { preview, snapshot } from "../engine/advancement-engine.mjs";
import { PackCatalog } from "../services/pack-catalog.mjs";
import { commitCharacter } from "../services/actor-committer.mjs";
import { Ledger } from "../services/ledger.mjs";

const rulesPromise = fetch(`modules/${MODULE_ID}/data/creation-rules.json`).then((r) => r.json());

/** A street-sam-ish human, fully specified and legal. */
async function sampleEngine() {
  const rules = await rulesPromise;
  const e = new ChargenEngine(chargenData(), rules, { state: blankState("priority") });
  for (const [col, letter] of Object.entries({
    METATYPE: "C", ATTRIBUTE: "A", MAGIC: "E", SKILLS: "B", RESOURCES: "D",
  })) e.setPriority(col, letter);
  e.setMetatype("human");
  e.setMagicPath("mundane");
  e.state.name = "Quench Testrunner";
  e.spend({ kind: "attribute", target: "bod", delta: 3 });
  e.spend({ kind: "attribute", target: "agi", delta: 4 });
  e.spend({ kind: "skill", target: "firearms", delta: 4 });
  e.spend({ kind: "spec", target: "firearms", spec: "Pistols" });
  e.spend({ kind: "knowledge", name: "English", type: "language", native: true });
  return e;
}

export function registerQuenchBatches(quench) {
  /* ------------------------------------------------------------------ data */
  quench.registerBatch(`${MODULE_ID}.data`, (context) => {
    const { describe, it, assert } = context;

    describe("module wiring", function () {
      it("exposes its API", function () {
        const api = game.modules.get(MODULE_ID)?.api;
        assert.ok(api, "module API missing");
        for (const fn of ["open", "openWizard", "openOptions", "openAdvancement"]) {
          assert.isFunction(api[fn], `api.${fn} is not a function`);
        }
      });

      it("registers its world settings", function () {
        for (const key of Object.values(SETTINGS)) {
          assert.ok(game.settings.settings.has(`${MODULE_ID}.${key}`), `setting ${key} missing`);
        }
      });

      it("adds a settings menu that opens the options app", function () {
        assert.ok(game.settings.menus.has(`${MODULE_ID}.config`), "settings menu not registered");
      });

      it("loads chargen-data with the expected shape", function () {
        const d = chargenData();
        assert.equal(Object.keys(d.priorities).length, 5, "five priority letters");
        assert.isAbove(Object.keys(d.metatypes).length, 30, "metatypes loaded");
        assert.equal(Object.keys(d.skills).length, 21, "skills loaded");
        assert.isAbove(Object.keys(d.lifepathModules).length, 70, "English life modules loaded");
      });

      it("speaks its own setting vocabulary, not the source data's", function () {
        const settings = chargenData().rules.core.settings;
        assert.ok("maxAvailability" in settings, "translated names expected");
        for (const key of Object.keys(settings)) {
          assert.notMatch(key, /^[A-Z_]+$/, `untranslated rule id leaked: ${key}`);
        }
      });

      it("registers an advancement entry point for both sheet generations", function () {
        // eden's PC sheet is AppV1 today and may migrate; the directory
        // context menu is the fallback that works either way
        for (const hook of ["getActorSheetHeaderButtons", "getHeaderControls",
          "getActorContextOptions"]) {
          const fns = Hooks.events[hook] ?? [];
          assert.isAbove(fns.length, 0, `nothing listening on ${hook}`);
        }
      });

      it("keeps the upstream catalog field behind its one boundary", async function () {
        // eden owns `system.genesisID`; our code calls it catalogId and reads
        // it through catalogIdOf(). This checks the plumbing still resolves.
        const { EDEN_CATALOG_FIELD } = await import(`../config.mjs`);
        assert.equal(EDEN_CATALOG_FIELD, "system.genesisID",
          "eden's field name must not be changed — eden is never modified");
        const rows = await PackCatalog.index("qualities");
        const withId = rows.filter((r) => catalogIdOf(r));
        assert.isAbove(withId.length, rows.length * 0.9,
          "catalogIdOf() no longer resolves eden's field");
      });

      it("pushes the index fields the browse lists need", function () {
        for (const f of ["system.type", "system.price", "system.avail"]) {
          assert.include(CONFIG.Item.compendiumIndexFields, f, `${f} not indexed`);
        }
      });
    });
  }, { displayName: "SR6 Forge: Module & Data" });

  /* ----------------------------------------------------------------- packs */
  quench.registerBatch(`${MODULE_ID}.packs`, (context) => {
    const { describe, it, assert } = context;

    describe("compendium catalog", function () {
      it("finds the data module's packs", function () {
        const packs = game.packs.filter((p) => p.metadata.packageName.startsWith("sr6-forge-"));
        assert.isAbove(packs.length, 10, "data module packs not found — is it enabled?");
      });

      it("indexes gear with the fields the shop needs", async function () {
        const rows = await PackCatalog.index("gear");
        assert.isAbove(rows.length, 1000, "gear index looks short");
        const priced = rows.filter((r) => r.system?.price != null);
        assert.isAbove(priced.length, 0, "no gear row carries a price");
      });

      it("can reach the items that looked missing in the browser", async function () {
        // these were reported as absent when the search bar only filtered the
        // rendered rows; the query now narrows the full set first
        const rows = await PackCatalog.index("gear");
        const byName = (needle) =>
          rows.filter((r) => r.name.toLowerCase().includes(needle.toLowerCase()));
        assert.isAbove(byName("silencer").length, 0, "silencer not reachable");
        assert.isAbove(byName("predator").length, 0, "Ares Predator not reachable");
        assert.isAbove(byName("wired reflexes").length, 0, "wired reflexes not reachable");
      });

      it("covers every gear type with a shop tab", async function () {
        const rows = await PackCatalog.index("gear");
        const types = new Set(rows.map((r) => r.system?.type).filter(Boolean));
        const tabbed = new Set(["WEAPON_FIREARMS", "WEAPON_CLOSE_COMBAT", "WEAPON_RANGED",
          "WEAPON_SPECIAL", "WEAPON_VEHICLE", "AMMUNITION", "ACCESSORY", "ARMOR",
          "ARMOR_ADDITION", "ELECTRONICS", "SOFTWARE", "CYBERDECK", "CODEMODS",
          "CYBERWARE", "BIOWARE", "GENEWARE", "NANOWARE", "BIOLOGY", "CHEMICALS",
          "MAGICAL", "SURVIVAL", "TOOLS", "VEHICLES", "DRONES"]);
        const orphans = [...types].filter((t) => !tabbed.has(t));
        assert.deepEqual(orphans, [], `gear types with no shop tab: ${orphans.join(", ")}`);
      });

      it("carries eden's catalogId so items match across compendia", async function () {
        const rows = await PackCatalog.index("qualities");
        const withId = rows.filter((r) => catalogIdOf(r));
        assert.isAbove(withId.length, rows.length * 0.9, "most qualities should carry a catalogId");
      });
    });
  }, { displayName: "SR6 Forge: Compendium Packs" });

  /* ---------------------------------------------------------------- commit */
  quench.registerBatch(`${MODULE_ID}.commit`, (context) => {
    const { describe, it, assert, before, after } = context;
    let actor = null;

    describe("committing a character to an eden actor", function () {
      before(async function () {
        const e = await sampleEngine();
        actor = await commitCharacter(e.commitPlan(), { engineState: e.toDraft() });
      });

      after(async function () {
        if (actor) await actor.delete();
        actor = null;
      });

      it("creates a Player the system understands", function () {
        assert.ok(actor, "no actor was created");
        assert.equal(actor.type, "Player");
        assert.equal(actor.name, "Quench Testrunner");
      });

      it("writes the raw inputs we intended", function () {
        assert.equal(actor.system.attributes.bod.base, 4);
        assert.equal(actor.system.attributes.agi.base, 5);
        assert.equal(actor.system.skills.firearms.points, 4);
        assert.equal(actor.system.metatype.toLowerCase(), "human");
        assert.equal(actor.system.mortype, "mundane");
      });

      it("lets EDEN derive the pools — this is the whole architecture", function () {
        // We never write .pool. Eden's formula (documents/actor.js) is
        //   pool = max(0, base + min(4, mod))
        // note: mod is capped at 4 and `augment` is NOT part of it.
        for (const attr of ["bod", "agi", "rea", "str", "wil", "log", "int", "cha"]) {
          const a = actor.system.attributes[attr];
          const expected = Math.max(0, a.base + Math.min(4, a.mod ?? 0));
          assert.equal(a.pool, expected, `eden did not derive ${attr}.pool`);
        }
        assert.isNumber(actor.system.physical?.max, "no derived physical monitor");
        assert.isAbove(actor.system.physical.max, 0);
        assert.isNumber(actor.system.stun?.max, "no derived stun monitor");
      });

      it("matches eden's attribute field shapes exactly", function () {
        // template.json: core attrs are {base,mod,modString,augment,pool};
        // edg is {current,max} with NO base; mag adds min+initiation; res adds
        // submersion. Writing the wrong shape silently loses data.
        assert.property(actor.system.attributes.bod, "base");
        assert.property(actor.system.attributes.edg, "max");
        assert.property(actor.system.attributes.edg, "current");
        assert.notProperty(actor.system.attributes.edg, "base",
          "edge has no base in eden's template");
      });

      it("zeroes Magic for a mundane, as eden insists", function () {
        // eden forces mag.base = 0 when !isAwakened, res.base = 0 when !isTechno
        assert.equal(actor.system.attributes.mag.base, 0);
        assert.equal(actor.system.attributes.res.base, 0);
      });

      it("keeps system.sr6forge alive through document creation", async function () {
        // Foundry's TypeDataField._cleanType merges template.json with the
        // source using insertKeys = !system.strictDataCleaning. Eden does not
        // set that flag, so our namespace survives — but that is a property of
        // eden's configuration, not a guarantee, so assert it rather than
        // assume it.
        const rows = await PackCatalog.index("gear");
        const rated = rows.find((r) => r.system?.sr6forge?.priceByRating?.length);
        assert.ok(rated, "no rated item carries sr6forge in the pack index");

        const doc = await fromUuid(rated.uuid);
        assert.ok(doc.system.sr6forge, "sr6forge missing on the pack document");

        // the real test: create it on an actor and see what survives
        const [created] = await actor.createEmbeddedDocuments("Item", [doc.toObject()]);
        try {
          assert.ok(created.system.sr6forge,
            "sr6forge was stripped when the item was embedded — eden may have "
            + "enabled strictDataCleaning, or given gear a DataModel");
          assert.deepEqual(created.system.sr6forge.priceByRating,
            rated.system.sr6forge.priceByRating, "price ladder did not survive");
        } finally {
          await created.delete();
        }
      });

      it("records the chargen snapshot for later reference", function () {
        const snap = actor.getFlag(MODULE_ID, "chargen");
        assert.ok(snap, "chargen flag missing");
        assert.equal(snap.method, "priority");
      });

      it("embeds the knowledge/language skills as eden items", function () {
        const langs = actor.items.filter((i) => i.type === "skill");
        assert.isAbove(langs.length, 0, "no knowledge/language items embedded");
      });
    });
  }, { displayName: "SR6 Forge: Commit to Actor" });

  /* ----------------------------------------------------------- advancement */
  quench.registerBatch(`${MODULE_ID}.advancement`, (context) => {
    const { describe, it, assert, before, after } = context;
    let actor = null;

    describe("karma advancement against a live actor", function () {
      before(async function () {
        const e = await sampleEngine();
        actor = await commitCharacter(e.commitPlan(), { engineState: e.toDraft() });
        await actor.update({ "system.karma": 100 });
      });

      after(async function () {
        if (actor) await actor.delete();
        actor = null;
      });

      it("reads the actor through the engine's snapshot", function () {
        const snap = snapshot(actor);
        assert.equal(snap.karma, 100);
        assert.equal(snap.attributes.bod.base, 4);
        assert.equal(snap.skills.firearms.points, 4);
      });

      it("prices a raise off the live actor at 5 x the new rank", async function () {
        const rules = await rulesPromise;
        const pv = preview({ kind: "raiseSkill", target: "firearms" },
          snapshot(actor), rules, { data: chargenData() });
        assert.equal(pv.karma, 25, "firearms 4 -> 5 should cost 25");
        assert.isTrue(pv.ok);
      });

      it("applies, logs and reverses a purchase exactly", async function () {
        const rules = await rulesPromise;
        const before = snapshot(actor);
        const ledgerBefore = Ledger.entries(actor).length;
        const pv = preview({ kind: "raiseAttribute", target: "bod" },
          before, rules, { data: chargenData() });

        await actor.update({
          ...pv.patch,
          "system.karma": before.karma - pv.karma,
        });
        await Ledger.append(actor, {
          op: "raiseAttribute", label: pv.label, karma: pv.karma,
          before: { "system.attributes.bod.base": before.attributes.bod.base },
        });

        assert.equal(actor.system.attributes.bod.base, 5);
        assert.equal(actor.system.karma, before.karma - pv.karma);
        // a delta, not an absolute: the actor may carry entries from an
        // earlier purchase, and what is under test is that append adds ONE
        assert.equal(Ledger.entries(actor).length, ledgerBefore + 1);

        const entry = await Ledger.popLast(actor);
        await actor.update({
          ...entry.before,
          "system.karma": actor.system.karma + entry.karma,
        });
        assert.equal(actor.system.attributes.bod.base, 4, "undo did not restore the attribute");
        assert.equal(actor.system.karma, before.karma, "undo did not refund the karma");
        assert.equal(Ledger.entries(actor).length, ledgerBefore,
          "undo did not remove exactly the entry it added");
      });
    });
  }, { displayName: "SR6 Forge: Advancement" });

  /* ------------------------------------------------------- window memory */
  quench.registerBatch(`${MODULE_ID}.windows`, (context) => {
    const { describe, it, assert, after } = context;
    let saved = null;

    describe("remembering window geometry", function () {
      after(async function () {
        if (saved !== null) await game.settings.set(MODULE_ID, SETTINGS.WINDOW_STATE, saved);
      });

      it("registers a client-scoped store", function () {
        const cfg = game.settings.settings.get(`${MODULE_ID}.${SETTINGS.WINDOW_STATE}`);
        assert.ok(cfg, "windowState setting missing");
        assert.equal(cfg.scope, "client", "geometry is a per-user preference");
      });

      it("every window class loads — catches a broken import path", async function () {
        // node --check validates syntax but not module resolution, so a wrong
        // relative path only shows up here
        const mods = await Promise.all([
          import(`../apps/wizard/wizard-app.mjs`),
          import(`../apps/advancement/advancement-app.mjs`),
          import(`../apps/options-app.mjs`),
          import(`../apps/launcher.mjs`),
        ]);
        assert.isFunction(mods[0].SR6ForgeWizard);
        assert.isFunction(mods[1].SR6AdvancementApp);
        assert.isFunction(mods[2].SR6ForgeOptions);
        assert.isFunction(mods[3].SR6ForgeLauncher);
      });

      it("reopens a window at the size it was left", async function () {
        saved = foundry.utils.deepClone(game.settings.get(MODULE_ID, SETTINGS.WINDOW_STATE) ?? {});
        const { SR6ForgeOptions } = await import(`../apps/options-app.mjs`);

        const first = new SR6ForgeOptions();
        await first.render({ force: true });
        await first.setPosition({ width: 733, height: 521 });
        await first.close();

        const store = game.settings.get(MODULE_ID, SETTINGS.WINDOW_STATE);
        assert.equal(store.options?.width, 733, "width was not remembered");
        assert.equal(store.options?.height, 521, "height was not remembered");

        // a fresh instance must pick the remembered size up before it renders
        const second = new SR6ForgeOptions();
        assert.equal(second.options.position.width, 733);
        assert.equal(second.options.position.height, 521);
        await second.close();
      });
    });
  }, { displayName: "SR6 Forge: Window Memory" });

  /* --------------------------------------------------------------- engine */
  quench.registerBatch(`${MODULE_ID}.rules`, (context) => {
    const { describe, it, assert } = context;

    describe("creation rules against the shipped data", function () {
      it("agrees with the priority table the book prints", async function () {
        const rules = await rulesPromise;
        const e = new ChargenEngine(chargenData(), rules, { state: blankState("priority") });
        for (const [col, letter] of Object.entries({
          METATYPE: "C", ATTRIBUTE: "A", MAGIC: "E", SKILLS: "B", RESOURCES: "D",
        })) e.setPriority(col, letter);
        e.setMetatype("human");
        const b = e.budgets();
        assert.equal(b.attributePoints.max, 24, "priority A attributes");
        assert.equal(b.skillPoints.max, 24, "priority B skills");
        assert.equal(b.nuyen.max, 50000, "priority D resources");
      });

      it("gives a magician priority Magic x 2 free spells (core p66)", async function () {
        const rules = await rulesPromise;
        const e = new ChargenEngine(chargenData(), rules, { state: blankState("priority") });
        for (const [col, letter] of Object.entries({
          METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A", SKILLS: "C", RESOURCES: "E",
        })) e.setPriority(col, letter);
        e.setMetatype("human");
        e.setMagicPath("magician");
        const priority = e.provider.magicRating(e.state);
        assert.equal(freeSpellSlots(e.state, chargenData(), e.provider), priority * 2);
      });

      it("honours a world optional-rule override", async function () {
        const rules = await rulesPromise;
        const e = new ChargenEngine(chargenData(), rules, { state: blankState("priority") });
        for (const [col, letter] of Object.entries({
          METATYPE: "C", ATTRIBUTE: "A", MAGIC: "E", SKILLS: "B", RESOURCES: "D",
        })) e.setPriority(col, letter);
        e.setMetatype("human");
        e.state.purchases.push({ uuid: "x", name: "Test", price: 0, avail: 12, qty: 1 });
        assert.include(e.validate().map((i) => i.id), "gear.availCap");
        e.setOptionalRules({ maxAvailability: 12 });
        assert.notInclude(e.validate().map((i) => i.id), "gear.availCap");
      });

      it("has every actor skill present in chargen-data", function () {
        const d = chargenData();
        const missing = ACTOR_SKILLS.filter((id) => !d.skills[id]);
        assert.deepEqual(missing, [], `skills missing from chargen-data: ${missing.join(", ")}`);
      });
    });
  }, { displayName: "SR6 Forge: Creation Rules" });
}
