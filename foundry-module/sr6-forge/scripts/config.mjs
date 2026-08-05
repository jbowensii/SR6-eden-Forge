/** Shared constants for the SR6 Forge module. */
export const MODULE_ID = "sr6-forge";
export const FLAG_SCOPE = MODULE_ID;

/** Flag keys on the created actor. */
export const FLAGS = {
  METATYPE_ID: "metatypeId",       // stable cl6 metatype id ("dwarf")
  CHARGEN: "chargen",              // frozen engine-state snapshot at commit
  LEDGER: "ledger",                // advancement ledger (append-only array)
};

/** World-scoped settings keys. */
export const SETTINGS = {
  DRAFTS: "drafts",                // { [draftId]: {name, updatedAt, step, engineState} }
  RULESET: "ruleset",              // rule interpretation id (core | srm | ...)
};

/** Compendium index fields the wizard browse lists need (pushed, not replaced —
 *  eden already indexes name/type/system.genesisID). */
export const EXTRA_INDEX_FIELDS = [
  "system.type", "system.subtype", "system.price", "system.avail",
  "system.value", "system.category", "system.essence", "system.rating",
];

/** Data-module package prefix — every pack whose package id starts with this
 *  joins the catalog (corebook now, more books later). */
export const DATA_PACKAGE_PREFIX = "sr6-forge-";

/** The 19 eden actor skills (system.skills.<id>) — kept in one place. */
export const ACTOR_SKILLS = [
  "astral", "athletics", "biotech", "close_combat", "con", "conjuring",
  "cracking", "electronics", "enchanting", "engineering", "exotic_weapons",
  "firearms", "influence", "outdoors", "perception", "piloting", "sorcery",
  "stealth", "tasking",
];
