// Display aliases for Eden gear `type` codes. These are SYNONYMS: the exported
// Foundry `system.type` always stays the underlying code — only the UI label
// changes. Keep this list as the single source of truth for the renames.
//
//   ACCESSORY           -> "Weapon Accessory"
//   ARMOR_ADDITION      -> "Armor Accessory"
//   WEAPON_CLOSE_COMBAT -> "Weapon Melee"
export const TYPE_LABELS = {
  ACCESSORY: "Weapon Accessory",
  ARMOR_ADDITION: "Armor Accessory",
  WEAPON_CLOSE_COMBAT: "Weapon Melee",
};

const titleCase = (s) =>
  s.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

export const prettyType = (t) => TYPE_LABELS[t] ?? titleCase(t ?? "");
export const prettySubtype = (s) => (s ? titleCase(s) : "");
