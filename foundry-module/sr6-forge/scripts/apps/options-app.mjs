/** Optional-rules configuration — the switches the upstream data exposes,
 *  plus this project's own (OWN_RULES), applied on top of the selected rule
 *  interpretation. Stored world-scoped so every new character inherits them. */
import { MODULE_ID, SETTINGS, OWN_RULES } from "../config.mjs";
import { chargenData } from "../main.mjs";

import { RememberPosition } from "./remember-position.mjs";

const { ApplicationV2, HandlebarsApplicationMixin } = foundry.applications.api;

/** Creation settings that take a number rather than a yes/no. */
const NUMERIC_SETTINGS = new Set([
  "maxAvailability", "maxInitiationGrade", "maxSubmersionGrade",
  "maxTranshumanGrade", "maxAnimalismGrade", "sumToTenTarget",
  "maxKarmaRemaining", "maxNuyenRemaining",
]);

const ownRuleLabels = () =>
  Object.fromEntries(Object.entries(OWN_RULES).map(([k, v]) => [k, v.label]));
const ownRuleDefaults = () =>
  Object.fromEntries(Object.entries(OWN_RULES).map(([k, v]) => [k, v.default]));

export class SR6ForgeOptions extends RememberPosition(
  HandlebarsApplicationMixin(ApplicationV2), "options") {
  static DEFAULT_OPTIONS = {
    id: "sr6-forge-options",
    classes: ["sr6-forge"],
    window: { title: "SR6 Forge — Optional Rules", resizable: true },
    position: { width: 620, height: 640 },
    actions: {
      resetRules: SR6ForgeOptions.#onReset,
      closeOptions: SR6ForgeOptions.#onClose,
    },
  };

  static PARTS = { body: { template: `modules/${MODULE_ID}/templates/options.hbs` } };

  /** Effective value: world override -> interpretation default -> undefined. */
  static effective(rulesetId) {
    const data = chargenData();
    const base = data.rules?.[rulesetId]?.settings ?? {};
    const over = game.settings.get(MODULE_ID, SETTINGS.OPTIONAL_RULES) ?? {};
    return { ...ownRuleDefaults(), ...base, ...over };
  }

  async _prepareContext() {
    // reachable from Foundry's settings pane, where a failed data load would
    // otherwise surface as a stack trace instead of an explanation
    let data;
    try {
      data = chargenData();
    } catch {
      return { rows: [], rulesets: [], rulesetId: null,
        unavailable: "chargen-data.json is not loaded — rebuild and redeploy the module." };
    }
    const rulesetId = game.settings.get(MODULE_ID, SETTINGS.RULESET);
    const base = { ...ownRuleDefaults(), ...(data.rules?.[rulesetId]?.settings ?? {}) };
    const over = game.settings.get(MODULE_ID, SETTINGS.OPTIONAL_RULES) ?? {};
    const labels = { ...(data.ruleLabels ?? {}), ...ownRuleLabels() };
    const rows = Object.entries(labels).sort((a, b) => a[1].localeCompare(b[1]))
      .map(([key, label]) => {
        const dflt = base[key];
        const cur = key in over ? over[key] : dflt;
        const numeric = NUMERIC_SETTINGS.has(key) || typeof dflt === "number";
        return {
          key, label, numeric,
          value: numeric ? (cur ?? "") : !!cur,
          overridden: key in over,
          defaultText: dflt === undefined ? "—" : String(dflt),
        };
      });
    return {
      rows, rulesetId,
      rulesets: Object.keys(data.rules ?? {}).filter((r) => !r.endsWith("_de"))
        .map((id) => ({ id, selected: id === rulesetId,
          name: { core: "Core Rulebook", core_seattle: "Standard (Seattle)",
            srm: "Shadowrun Missions", houserules: "House Rules" }[id] ?? id })),
    };
  }

  async _onRender() {
    const root = this.element;
    root.querySelector("[data-change=ruleset]")?.addEventListener("change", async (ev) => {
      await game.settings.set(MODULE_ID, SETTINGS.RULESET, ev.target.value);
      this.render();
    });
    for (const el of root.querySelectorAll("[data-rule]")) {
      el.addEventListener("change", async () => {
        const over = foundry.utils.deepClone(game.settings.get(MODULE_ID, SETTINGS.OPTIONAL_RULES) ?? {});
        const key = el.dataset.rule;
        if (el.type === "checkbox") over[key] = el.checked;
        else if (el.value === "") delete over[key];
        else over[key] = Number(el.value);
        await game.settings.set(MODULE_ID, SETTINGS.OPTIONAL_RULES, over);
        this.render();
      });
    }
  }

  static async #onReset() {
    await game.settings.set(MODULE_ID, SETTINGS.OPTIONAL_RULES, {});
    ui.notifications.info("SR6 Forge: optional rules reset to the interpretation defaults.");
    this.render();
  }

  static async #onClose() { await this.close(); }
}
