/** SR6 Forge — entry point. Registers settings, loads chargen-data.json,
 *  extends compendium index fields, exposes the module API, and adds the
 *  launcher button to the Actors directory. */
import { MODULE_ID, SETTINGS, EXTRA_INDEX_FIELDS } from "./config.mjs";
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
});

/**
 * The wizard's browse lists need price/avail/type indexed on top of eden's
 * `["name", "type", "system.genesisID"]`.
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
    console.log(`${MODULE_ID} | chargen-data loaded:`,
      Object.keys(state.chargenData.metatypes ?? {}).length, "metatypes,",
      Object.keys(state.chargenData.skills ?? {}).length, "skills");
  } catch (err) {
    console.error(`${MODULE_ID} | failed to load chargen-data.json`, err);
    ui.notifications?.error("SR6 Forge: chargen-data.json missing — rebuild the module.");
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
    console.error(`${MODULE_ID} | failed to register Quench batches`, err);
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
