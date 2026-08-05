/** SR6 Forge — entry point. Registers settings, loads chargen-data.json,
 *  extends compendium index fields, exposes the module API, and adds the
 *  launcher button to the Actors directory. */
import { MODULE_ID, SETTINGS, EXTRA_INDEX_FIELDS } from "./config.mjs";

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
  game.settings.register(MODULE_ID, SETTINGS.RULESET, {
    name: "SR6FORGE.Settings.Ruleset",
    hint: "SR6FORGE.Settings.RulesetHint",
    scope: "world", config: true, type: String, default: "core",
    choices: { core: "Core Rulebook", core_seattle: "Standard (Seattle)", srm: "Shadowrun Missions", houserules: "House Rules" },
  });

  // browse lists need these on top of eden's ["name","type","system.genesisID"]
  for (const f of EXTRA_INDEX_FIELDS) {
    if (!CONFIG.Item.compendiumIndexFields.includes(f)) {
      CONFIG.Item.compendiumIndexFields.push(f);
    }
  }
});

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

/* Advancement header button — dual registration (eden PC sheet is AppV1 today,
 * may migrate to AppV2; context-menu fallback always works). */
Hooks.on("getActorSheetHeaderButtons", (sheet, buttons) => {
  if (sheet.actor?.type !== "Player") return;
  buttons.unshift({
    label: game.i18n.localize("SR6FORGE.Advancement"),
    class: "sr6-forge-advancement",
    icon: "fas fa-arrow-trend-up",
    onclick: () => game.modules.get(MODULE_ID).api.openAdvancement(sheet.actor),
  });
});
