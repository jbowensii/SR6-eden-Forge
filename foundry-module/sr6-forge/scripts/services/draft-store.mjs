/** Wizard draft persistence in a world-scoped setting (no actor exists before
 *  commit). Shape: { [draftId]: {name, updatedAt, step, engineState} } */
import { MODULE_ID, SETTINGS } from "../config.mjs";

export const DraftStore = {
  _all() {
    return foundry.utils.deepClone(game.settings.get(MODULE_ID, SETTINGS.DRAFTS) ?? {});
  },

  list() {
    return Object.entries(this._all())
      .map(([id, d]) => ({ id, ...d }))
      .sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  },

  load(id) { return this._all()[id] ?? null; },

  async save(id, { name, step, engineState }) {
    const all = this._all();
    all[id] = { name: name || "Unnamed runner", step, engineState, updatedAt: Date.now() };
    await game.settings.set(MODULE_ID, SETTINGS.DRAFTS, all);
  },

  async delete(id) {
    const all = this._all();
    delete all[id];
    await game.settings.set(MODULE_ID, SETTINGS.DRAFTS, all);
  },
};
