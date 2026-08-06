/** Shared constants for the SR6 Forge module. */
export const MODULE_ID = "sr6-forge";
export const FLAG_SCOPE = MODULE_ID;

/**
 * The one place the upstream field name appears.
 *
 * shadowrun6-eden stores a stable cross-compendium identifier on every item at
 * `system.genesisID` — its own schema (template.json declares an Item template
 * called "genesis"), its own compendium index field, and the key its item
 * localization and importer match on. We cannot rename it without breaking
 * eden, and eden is never modified by this project.
 *
 * So it is quarantined here. Everywhere else in this codebase the concept is
 * called `catalogId`, and code reads it through `catalogIdOf()` rather than
 * naming the field.
 */
export const EDEN_CATALOG_FIELD = "system.genesisID";

/** The stable catalog id of a compendium row or item document. */
export function catalogIdOf(docOrRow) {
  return docOrRow?.system?.genesisID ?? null;
}

/** Set the catalog id on an item's system data, in eden's expected field. */
export function setCatalogId(systemData, id) {
  systemData.genesisID = id;
  return systemData;
}

/** Flag keys on the created actor. */
export const FLAGS = {
  METATYPE_ID: "metatypeId",       // stable metatype id ("dwarf")
  CHARGEN: "chargen",              // frozen engine-state snapshot at commit
  LEDGER: "ledger",                // advancement ledger (append-only array)
};

/** World-scoped settings keys. */
export const SETTINGS = {
  DRAFTS: "drafts",                // { [draftId]: {name, updatedAt, step, engineState} }
  RULESET: "ruleset",              // rule interpretation id (core | srm | ...)
  OPTIONAL_RULES: "optionalRules", // { settingName: boolean|number } overrides
  WINDOW_STATE: "windowState",
  DRAFT_FOLDER: "draftFolder",     // client-scoped {key: {width,height,left,top}}
};

/**
 * Optional rules this project adds on top of the ones the upstream data
 * defines. They are keyed and stored exactly like the imported ones, so the
 * options screen and the override store treat both alike; only the label and
 * default live here, because no upstream ruleset declares them.
 */
export const OWN_RULES = {
  allowNuyenToKarma: {
    label: "Allow nuyen → karma in downtime (6WC p154)",
    default: false,
  },
};

/** Compendium index fields the wizard browse lists need (pushed, not replaced —
 *  eden already indexes name/type and its own catalog field). */
export const EXTRA_INDEX_FIELDS = [
  "system.type", "system.subtype", "system.price", "system.avail",
  "system.value", "system.category", "system.essence", "system.rating",
  // Rated gear prices per rating, and eden has one `price` field. The tables
  // ride on the item under our own namespace so the cost can be computed from
  // the item alone — see ratedValues(). Indexed because the shop list works
  // from the compendium index, not from loaded documents.
  "system.sr6forge.ratings", "system.sr6forge.maxRating",
  "system.sr6forge.priceByRating", "system.sr6forge.availByRating",
  "system.sr6forge.essenceByRating",
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
