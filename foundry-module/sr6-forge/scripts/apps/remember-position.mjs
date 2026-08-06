/** Remember where the user put a window, and how big they made it.
 *
 *  ApplicationV2 fires `_onPosition` after every reposition — including each
 *  pixel of a drag or resize — so the write is debounced rather than hammering
 *  the settings store. The saved geometry is injected back in
 *  `_initializeApplicationOptions`, which runs while the constructor is still
 *  assembling `options`, so the window opens at the remembered size instead of
 *  opening at the default and jumping.
 *
 *  Stored client-scoped: window geometry is a personal preference, and two
 *  people sharing a world should not fight over it.
 */
import { MODULE_ID, SETTINGS, LOG_PREFIX } from "../config.mjs";

/** How long to wait after the last move/resize before writing. */
const SAVE_DELAY_MS = 400;

/** Geometry we persist. Anything else ApplicationV2 tracks is transient. */
const KEYS = ["width", "height", "left", "top"];

function readAll() {
  try {
    return game.settings.get(MODULE_ID, SETTINGS.WINDOW_STATE) ?? {};
  } catch {
    return {};                     // setting not registered yet (very early call)
  }
}

/**
 * Mix window-geometry persistence into an ApplicationV2 subclass.
 *
 * @param {typeof foundry.applications.api.ApplicationV2} Base
 * @param {string} key  storage key, e.g. "wizard" — distinct per window type
 */
export function RememberPosition(Base, key) {
  return class extends Base {
    /** @inheritDoc */
    _initializeApplicationOptions(options) {
      const merged = super._initializeApplicationOptions(options);
      const saved = readAll()[key];
      if (saved) {
        // an explicit position passed by the caller still wins
        merged.position = { ...merged.position, ...saved, ...(options.position ?? {}) };
      }
      return merged;
    }

    /** @inheritDoc */
    _onPosition(position) {
      super._onPosition?.(position);
      clearTimeout(this.#saveTimer);
      this.#saveTimer = setTimeout(() => this.#savePosition(position), SAVE_DELAY_MS);
    }

    /** @inheritDoc */
    async close(options) {
      // a close can beat the debounce; capture the final geometry first
      clearTimeout(this.#saveTimer);
      if (this.position) await this.#savePosition(this.position);
      return super.close(options);
    }

    #saveTimer = null;

    async #savePosition(position) {
      const geometry = {};
      for (const k of KEYS) {
        const v = position?.[k];
        // a maximised window reports "auto" for height; do not persist that
        if (typeof v === "number" && Number.isFinite(v)) geometry[k] = Math.round(v);
      }
      if (!Object.keys(geometry).length) return;
      const all = foundry.utils.deepClone(readAll());
      // foundry.utils.equals since v14; objectsEqual is deprecated
      const same = foundry.utils.equals ?? foundry.utils.objectsEqual;
      if (same(all[key] ?? {}, geometry)) return;                        // no-op write
      all[key] = geometry;
      try {
        await game.settings.set(MODULE_ID, SETTINGS.WINDOW_STATE, all);
      } catch (err) {
        console.warn(`${LOG_PREFIX} could not save window position`, err);
      }
    }
  };
}

/** Forget every remembered window, so they reopen at their default size. */
export async function resetWindowPositions() {
  await game.settings.set(MODULE_ID, SETTINGS.WINDOW_STATE, {});
}
