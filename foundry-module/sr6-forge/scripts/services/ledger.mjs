/** Append-only advancement ledger stored on the actor.
 *
 *  Every entry records the patch that was applied AND the values it replaced,
 *  so undo is a replay of `before` rather than an inverse computed after the
 *  fact. Undo is strictly last-in-first-out: reversing an older entry would
 *  leave the newer ones sitting on state that no longer exists.
 */
import { MODULE_ID, FLAGS } from "../config.mjs";

export const Ledger = {
  entries(actor) {
    return actor.getFlag(MODULE_ID, FLAGS.LEDGER) ?? [];
  },

  /** Karma spent through the ledger (not the actor's whole history). */
  spent(actor) {
    return this.entries(actor).reduce((n, e) => n + (e.karma ?? 0), 0);
  },

  async append(actor, entry) {
    const list = [...this.entries(actor), entry];
    await actor.setFlag(MODULE_ID, FLAGS.LEDGER, list);
    return entry;
  },

  async popLast(actor) {
    const list = [...this.entries(actor)];
    const last = list.pop();
    if (!last) return null;
    await actor.setFlag(MODULE_ID, FLAGS.LEDGER, list);
    return last;
  },

  /** Snapshot of the paths a patch is about to overwrite. */
  captureBefore(actor, patch) {
    const before = {};
    for (const path of Object.keys(patch ?? {})) {
      before[path] = foundry.utils.getProperty(actor, path) ?? 0;
    }
    return before;
  },
};
