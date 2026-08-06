/** Wizard draft persistence. No actor exists before commit, so an unfinished
 *  character has to live somewhere of its own.
 *
 *  Two backends, chosen by one setting:
 *
 *  **World setting** (the default, and what every existing world uses). Drafts
 *  sit in the world's settings database. Reliable and backed up with the
 *  world, but opaque — LevelDB, not readable or copyable — and locked to this
 *  world.
 *
 *  **A folder** under Foundry's data directory, once one is configured. Drafts
 *  become a plain JSON file you can read, back up, diff or carry into another
 *  world. Setting the folder MOVES the drafts: they are written to the file and
 *  then cleared from the world setting, so there is exactly one source of truth
 *  and no chance of two diverging copies.
 *
 *  One file rather than one per draft, because Foundry gives clients no way to
 *  delete a file — deleting a draft has to be a rewrite of the whole document.
 */
import { MODULE_ID, SETTINGS } from "../config.mjs";

/** Filename written inside the configured folder. */
export const DRAFT_FILE = "sr6-forge-drafts.json";

const FP = () => foundry.applications.apps.FilePicker.implementation;

function folder() {
  try {
    return (game.settings.get(MODULE_ID, SETTINGS.DRAFT_FOLDER) ?? "").trim();
  } catch {
    return "";                       // setting not registered yet
  }
}

/** Where drafts currently live: "file" once a folder is set, else "world". */
export function draftBackend() {
  return folder() ? "file" : "world";
}

function filePath(dir = folder()) {
  return `${dir.replace(/\/+$/, "")}/${DRAFT_FILE}`;
}

/* ---------- world-setting backend ---------- */

function readWorld() {
  try {
    return foundry.utils.deepClone(game.settings.get(MODULE_ID, SETTINGS.DRAFTS) ?? {});
  } catch {
    return {};
  }
}

const writeWorld = (all) => game.settings.set(MODULE_ID, SETTINGS.DRAFTS, all);

/* ---------- file backend ---------- */

async function readFile(dir = folder()) {
  try {
    // cache-bust: Foundry serves Data/ with normal HTTP caching, and a draft
    // saved seconds ago must not read back stale
    const res = await fetch(`${filePath(dir)}?t=${Date.now()}`);
    if (!res.ok) return {};
    return await res.json();
  } catch {
    return {};                       // no file yet, or unreadable
  }
}

async function writeFile(all, dir = folder()) {
  const clean = dir.replace(/\/+$/, "");
  try {
    await FP().createDirectory("data", clean);
  } catch {
    /* already exists — the only reliable way to find out is to try */
  }
  const blob = new Blob([JSON.stringify(all, null, 2)], { type: "application/json" });
  const file = new File([blob], DRAFT_FILE, { type: "application/json" });
  const res = await FP().upload("data", clean, file, {}, { notify: false });
  if (!res?.path) throw new Error(`could not write ${filePath(clean)}`);
}

/* ---------- public API ---------- */

export const DraftStore = {
  async _all() {
    return draftBackend() === "file" ? await readFile() : readWorld();
  },

  async _save(all) {
    if (draftBackend() === "file") await writeFile(all);
    else await writeWorld(all);
  },

  async list() {
    return Object.entries(await this._all())
      .map(([id, d]) => ({ id, ...d }))
      .sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  },

  async load(id) {
    return (await this._all())[id] ?? null;
  },

  async save(id, { name, step, engineState }) {
    const all = await this._all();
    all[id] = { name: name || "Unnamed runner", step, engineState, updatedAt: Date.now() };
    await this._save(all);
  },

  async delete(id) {
    const all = await this._all();
    delete all[id];
    await this._save(all);
  },

  /**
   * Move every draft into `dir`, or back into the world setting when `dir` is
   * empty. Called when the folder setting changes.
   *
   * Deliberately ordered: write the destination first and only clear the source
   * once that has succeeded, so a failed write leaves the drafts exactly where
   * they were rather than losing them between two stores. Drafts already at the
   * destination are kept — moving into a folder that another world has used
   * merges rather than overwrites.
   *
   * @returns {Promise<number>} how many drafts were moved
   */
  async relocate(dir) {
    const from = folder();
    const to = (dir ?? "").trim();
    if (from === to) return 0;

    const source = from ? await readFile(from) : readWorld();
    const moving = Object.keys(source).length;
    if (moving) {
      const target = to ? await readFile(to) : readWorld();
      const merged = { ...target, ...source };
      if (to) await writeFile(merged, to);
      else await writeWorld(merged);
    }

    // destination is safe; now point the setting at it and empty the old store
    await game.settings.set(MODULE_ID, SETTINGS.DRAFT_FOLDER, to);
    if (moving) {
      if (from) await writeFile({}, from);
      else await writeWorld({});
    }
    return moving;
  },
};
