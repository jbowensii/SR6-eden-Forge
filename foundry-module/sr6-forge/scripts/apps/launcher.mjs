/** Launcher: start a new character or resume a saved draft.
 *  (Save Draft in the wizard writes here; this is where drafts show up.) */
import { MODULE_ID } from "../config.mjs";
import { DraftStore } from "../services/draft-store.mjs";

import { RememberPosition } from "./remember-position.mjs";

const { ApplicationV2, HandlebarsApplicationMixin } = foundry.applications.api;

export class SR6ForgeLauncher extends RememberPosition(
  HandlebarsApplicationMixin(ApplicationV2), "launcher") {
  static DEFAULT_OPTIONS = {
    id: "sr6-forge-launcher",
    classes: ["sr6-forge", "sr6-forge-launcher"],
    window: { title: "SR6 Forge", resizable: false },
    position: { width: 480 },
    actions: {
      newChar: SR6ForgeLauncher.#onNew,
      resume: SR6ForgeLauncher.#onResume,
      deleteDraft: SR6ForgeLauncher.#onDelete,
      options: SR6ForgeLauncher.#onOptions,
    },
  };

  static PARTS = { body: { template: `modules/${MODULE_ID}/templates/launcher.hbs` } };

  async _prepareContext() {
    return {
      drafts: DraftStore.list().map((d) => ({
        id: d.id,
        name: d.name || "Unnamed runner",
        step: d.step ?? "method",
        when: new Date(d.updatedAt ?? Date.now()).toLocaleString(),
      })),
    };
  }

  static async #onNew() {
    const { SR6ForgeWizard } = await import("./wizard/wizard-app.mjs");
    await this.close();
    new SR6ForgeWizard().render({ force: true });
  }

  static async #onResume(_ev, target) {
    const { SR6ForgeWizard } = await import("./wizard/wizard-app.mjs");
    const draftId = target.dataset.draftId;
    await this.close();
    new SR6ForgeWizard({ draftId }).render({ force: true });
  }

  static async #onOptions() {
    const { SR6ForgeOptions } = await import("./options-app.mjs");
    new SR6ForgeOptions().render({ force: true });
  }

  static async #onDelete(_ev, target) {
    await DraftStore.delete(target.dataset.draftId);
    this.render();
  }
}
