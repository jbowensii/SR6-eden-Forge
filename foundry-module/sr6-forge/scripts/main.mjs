/* -------------------------------------------- */
/*  SR6 Forge — Foundry VTT Initialization       */
/* -------------------------------------------- */

/**
 * SR6 Forge — character generation and karma advancement for Shadowrun 6th
 * World on Foundry VTT.
 *
 * Entry point: registers settings, loads chargen-data.json, extends the
 * compendium index fields, exposes the module API and adds the launcher to the
 * Actors directory.
 *
 * ## Acknowledgements
 *
 * **shadowrun6-eden** — the Shadowrun 6 system this module is built on, by
 * Yeroon with Stefan & Anja Prelle
 * (https://github.com/yjeroen/foundry-shadowrun6-eden).
 * Eden does the real work: it owns the actor and item data models and derives
 * every computed value at runtime — attribute pools, condition monitors,
 * essence from ware. SR6 Forge deliberately writes only raw inputs and lets
 * eden derive the rest, which is why a character built here behaves exactly
 * like one built by hand on an eden sheet. This module reads eden's schema and
 * conventions; it never modifies the system.
 *
 * **Commlink6 / Genesis** — the Java character generator by Stefan Prelle
 * (https://rpgframework.de), whose data files describe the Sixth World in
 * a structured form and whose editor established the workflow this wizard
 * follows. Where the printed rules are ambiguous, Commlink6's own declarations
 * settled the question — counted accessory mounts, quality grants, fake SIN
 * quality levels and the per-attribute point pools were all read from its data
 * rather than guessed. The stable per-item identifiers our compendia share
 * with eden originate there.
 *
 * Shadowrun is a registered trademark of The Topps Company, Inc. Game content
 * belongs to Catalyst Game Labs. This module ships rules logic only; the game
 * data it reads is generated locally from books the user owns and is not
 * distributed with it.
 */
import { MODULE_ID, SETTINGS, EXTRA_INDEX_FIELDS, LOG_PREFIX } from "./config.mjs";
// Static so it can back the settings menu registered during "init". The cycle
// with this file is safe: options-app only calls chargenData() at render time,
// and function declarations hoist.
import { SR6ForgeOptions } from "./apps/options-app.mjs";

const state = { chargenData: null };

/** Public accessor used across the module. */
export function chargenData() {
  if (!state.chargenData) throw new Error(`${MODULE_ID}: chargen-data.json not loaded`);
  return state.chargenData;
}

Hooks.once("init", () => {
  game.settings.register(MODULE_ID, SETTINGS.DRAFTS, {
    scope: "world", config: false, type: Object, default: {},
  });
  game.settings.register(MODULE_ID, SETTINGS.OPTIONAL_RULES, {
    scope: "world", config: false, type: Object, default: {},
  });
  // Empty = keep drafts in the world settings database (the default, and what
  // every existing world already uses). Set a path and they move to a readable
  // JSON file there instead. Changed through the options app, which performs
  // the move — writing this setting directly relocates nothing.
  game.settings.register(MODULE_ID, SETTINGS.DRAFT_FOLDER, {
    scope: "world", config: false, type: String, default: "",
  });
  // Window geometry is a per-user preference, not a world rule.
  game.settings.register(MODULE_ID, SETTINGS.WINDOW_STATE, {
    scope: "client", config: false, type: Object, default: {},
  });
  // config:false — the interpretation dropdown lives in the options app, so
  // Foundry's settings pane and the launcher's gear open the same one screen
  // rather than offering two half-configurations.
  game.settings.register(MODULE_ID, SETTINGS.RULESET, {
    name: "SR6FORGE.Settings.Ruleset",
    hint: "SR6FORGE.Settings.RulesetHint",
    scope: "world", config: false, type: String, default: "core",
    choices: { core: "Core Rulebook", core_seattle: "Standard (Seattle)", srm: "Shadowrun Missions", houserules: "House Rules" },
  });

  /* The module's entry in Configure Settings → Module Settings. */
  game.settings.registerMenu(MODULE_ID, "config", {
    name: "SR6FORGE.Settings.MenuName",
    label: "SR6FORGE.Settings.MenuLabel",
    hint: "SR6FORGE.Settings.MenuHint",
    icon: "fas fa-sliders-h",
    type: SR6ForgeOptions,
    restricted: true,                 // world rules — GM only
  });

  addIndexFields();

  // Serialise a value into a data- attribute. Rated gear carries its pricing
  // tables on the item, and the shop row has to hand them to the click handler.
  Handlebars.registerHelper("json", (v) =>
    new Handlebars.SafeString(foundry.utils.escapeHTML(JSON.stringify(v ?? null))));

  // Thousands separators for nuyen. Handlebars stringifies numbers raw, and
  // "12000" beside "8000" is much harder to reconcile than "12,000" vs "8,000".
  Handlebars.registerHelper("fmt", (v) =>
    typeof v === "number" ? v.toLocaleString() : (v ?? ""));
});

/**
 * The wizard's browse lists need price/avail/type indexed on top of eden's
 * eden's own three index fields (see EDEN_CATALOG_FIELD in config.mjs).
 *
 * Eden *assigns* that array in its own `init` rather than appending, so any
 * field pushed before it is discarded. Today we win on ordering — the server
 * loads system esmodules at priority 6 and normal module esmodules at 8
 * (dist/server/views/view.mjs), so eden's init runs first and our push lands
 * after it. That is not something to rely on: a `library: true` module loads at
 * priority 4, and eden could reorder its own init at any time. Re-applying at
 * `setup` (after every init has run) makes the outcome independent of all that.
 */
function addIndexFields() {
  for (const f of EXTRA_INDEX_FIELDS) {
    if (!CONFIG.Item.compendiumIndexFields.includes(f)) {
      CONFIG.Item.compendiumIndexFields.push(f);
    }
  }
}

Hooks.once("setup", addIndexFields);

Hooks.once("ready", async () => {
  try {
    const resp = await fetch(`modules/${MODULE_ID}/data/chargen-data.json`);
    state.chargenData = await resp.json();
    console.log(`${LOG_PREFIX} chargen-data loaded:`,
      Object.keys(state.chargenData.metatypes ?? {}).length, "metatypes,",
      Object.keys(state.chargenData.skills ?? {}).length, "skills");
  } catch (err) {
    console.error(`${LOG_PREFIX} failed to load chargen-data.json`, err);
    ui.notifications?.error("SR6 Forge: chargen-data.json missing — rebuild the module.");
  }

  // A fresh install has the app but no data: the compendium module is built
  // locally from books the user owns and is never distributed. Say so plainly
  // once, rather than letting the wizard open onto empty shelves.
  const { PackCatalog } = await import("./services/pack-catalog.mjs");
  if (!PackCatalog.list().length) {
    console.warn(`${LOG_PREFIX} no sr6-forge-* data packs found — the wizard has nothing to shop from`);
    ui.notifications?.warn(
      "SR6 Forge: no data module found. Build one from your own books with the "
      + "import pipeline (see the README), then enable it in this world.",
      { permanent: false });
  }

  // module API: macros / other modules / console
  const mod = game.modules.get(MODULE_ID);
  mod.api = {
    chargenData,
    /** Launcher: new character or resume a saved draft. */
    open: async () => {
      const { SR6ForgeLauncher } = await import("./apps/launcher.mjs");
      return new SR6ForgeLauncher().render({ force: true });
    },
    openWizard: async (draftId) => {
      const { SR6ForgeWizard } = await import("./apps/wizard/wizard-app.mjs");
      return new SR6ForgeWizard(draftId ? { draftId } : {}).render({ force: true });
    },
    openOptions: async () => {
      const { SR6ForgeOptions } = await import("./apps/options-app.mjs");
      return new SR6ForgeOptions().render({ force: true });
    },
    openAdvancement: async (actor) => {
      const { SR6AdvancementApp } = await import("./apps/advancement/advancement-app.mjs");
      return new SR6AdvancementApp({ actor }).render({ force: true });
    },
  };
});

/* Quench integration tests — only loaded when that module is active, so the
   test code never ships weight into a normal session. */
Hooks.on("quenchReady", async (quench) => {
  try {
    const { registerQuenchBatches } = await import("./tests/quench-batches.mjs");
    registerQuenchBatches(quench);
  } catch (err) {
    console.error(`${LOG_PREFIX} failed to register Quench batches`, err);
  }
});

/* Launcher: button in the Actors directory footer (v13 AppV2 directory). */
Hooks.on("renderActorDirectory", (app, html) => {
  const el = html instanceof HTMLElement ? html : html[0];
  if (!el || el.querySelector(".sr6-forge-launch")) return;
  const footer = el.querySelector(".directory-footer") ?? el;
  const btn = document.createElement("button");
  btn.className = "sr6-forge-launch";
  btn.innerHTML = `<i class="fas fa-user-plus"></i> ${game.i18n.localize("SR6FORGE.Launch")}`;
  btn.addEventListener("click", () => game.modules.get(MODULE_ID).api.open());
  footer.append(btn);
});

/* Advancement entry points. Eden's PC sheet is ApplicationV1 today and may
 * migrate to V2, and the two generations use different hooks — so register for
 * both, plus a directory context-menu entry that works regardless. */
const advancementLabel = () => game.i18n.localize("SR6FORGE.Advancement");
const openAdvancement = (actor) => game.modules.get(MODULE_ID).api.openAdvancement(actor);

/* ApplicationV1 sheets. */
Hooks.on("getActorSheetHeaderButtons", (sheet, buttons) => {
  if (sheet.actor?.type !== "Player") return;
  buttons.unshift({
    label: advancementLabel(),
    class: "sr6-forge-advancement",
    icon: "fas fa-arrow-trend-up",
    onclick: () => openAdvancement(sheet.actor),
  });
});

/* ApplicationV2 sheets — `getHeaderControls` fires with (app, controls). */
Hooks.on("getHeaderControls", (app, controls) => {
  const actor = app?.document ?? app?.actor;
  if (actor?.documentName !== "Actor" || actor.type !== "Player") return;
  if (controls.some((c) => c.action === "sr6ForgeAdvancement")) return;
  controls.unshift({
    action: "sr6ForgeAdvancement",
    icon: "fas fa-arrow-trend-up",
    label: advancementLabel(),
    onClick: () => openAdvancement(actor),
  });
});

/* Actors directory context menu — the fallback that needs no sheet at all. */
Hooks.on("getActorContextOptions", (_html, options) => {
  options.push({
    name: advancementLabel(),
    icon: '<i class="fas fa-arrow-trend-up"></i>',
    condition: (li) => {
      const actor = game.actors.get(li.dataset?.entryId ?? li.dataset?.documentId);
      return actor?.type === "Player" && actor.isOwner;
    },
    callback: (li) => {
      const actor = game.actors.get(li.dataset?.entryId ?? li.dataset?.documentId);
      if (actor) openAdvancement(actor);
    },
  });
});
