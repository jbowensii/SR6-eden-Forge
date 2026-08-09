// Single source of truth mapping each library domain to its shadowrun6-eden
// Foundry document type and the Eden `system` fields that type expects (from the
// system's template.json). `req` fields are the ones Eden really wants filled;
// `opt` are recognized-but-optional. Everything else we store is "extra" — kept
// on export but not part of the Eden contract. Both the exporter (edenTransform)
// and the review UI (field badges + readiness) consume this, so they never drift.
//
// Every Eden item also carries the genesis-template fields, which we always fill.
export const GENESIS = ["description", "genesisID", "product", "page"];

// Eden fields that must be numbers / booleans on export (we may store strings).
export const NUMERIC = new Set([
  "drain", "threshold", "cost", "value", "level", "modifier", "rating",
  "connection", "loyalty", "favors", "dmg", "points", "fading",
]);
export const BOOLEAN = new Set([
  "isSustained", "alchemic", "multiSense", "isOpposed", "withEssence", "wildDie",
  "adepts", "mages", "hasLevel", "bonded", "anchored",
]);

// domain -> { type: FoundryType, actor?: true, req: [...], opt: [...] }
export const EDEN = {
  gear:          { type: "gear", discriminator: "type", req: [], opt: [] },
  spells:        { type: "spell", req: ["category", "type", "duration", "range", "drain"],
                   opt: ["damage", "combatSpellType", "isSustained", "alchemic", "multiSense", "isOpposed", "withEssence", "wildDie"] },
  rituals:       { type: "ritual", req: ["threshold"], opt: ["features"] },
  adept_powers:  { type: "adeptpower", req: ["cost"], opt: ["activation", "hasLevel", "level", "choice"] },
  qualities:     { type: "quality", req: ["category", "value"], opt: ["explain", "level", "modifier"] },
  lifestyles:    { type: "lifestyle", req: ["type", "cost"], opt: ["paid", "sin"] },
  skills:        { type: "skill", req: [], opt: ["attribute", "points", "modifier"] },
  complexforms:  { type: "complexform", req: ["duration", "fading"], opt: ["skill", "skillSpec", "attrib", "threshold", "oppAttr1", "oppAttr2"] },
  echoes:        { type: "echo", req: [], opt: [] },
  sprite_powers: { type: "spritepower", req: [], opt: ["duration", "isSustained", "skill", "skillSpec", "oppAttr1", "oppAttr2", "dmg"] },
  critter_powers:{ type: "critterpower", req: ["type", "action", "range", "duration"], opt: [] },
  metamagics:    { type: "metamagic", req: [], opt: ["level", "adepts", "mages"] },
  foci:          { type: "focus", req: ["rating"], opt: ["force", "availability", "price"] },
  contacts:      { type: "contact", req: ["connection", "loyalty"], opt: ["favors", "type", "pronouns"] },
  sins:          { type: "sin", req: ["rating", "quality"], opt: [] },
  martial_arts:  { type: "martialartstyle", req: [], opt: ["techniques", "styleCategory"] },
  martial_techniques: { type: "martialarttech", req: [], opt: ["style", "choice"] },
  // actors — exported as Foundry Actors, not Items (separate pack type)
  npcs:          { type: "npc", actor: true, req: ["attributes"], opt: ["metatype", "activeSkills", "qualities", "gear", "weapons"] },
  critters:      { type: "critter", actor: true, req: ["attributes"], opt: ["skills", "powers", "movement"] },
  spirits:       { type: "spirit", actor: true, req: ["attributes"], opt: ["powers", "optionalPowers", "attacks"] },
};

export function edenFor(domain) {
  return EDEN[domain] ?? null;
}

// The set of Eden-recognized field names for a domain (req + opt + genesis, plus
// the gear discriminator). Used by the UI to badge which fields are "Eden".
export function edenFields(domain) {
  const spec = EDEN[domain];
  if (!spec) return new Set(GENESIS);
  return new Set([...spec.req, ...spec.opt, ...GENESIS, ...(spec.discriminator ? [spec.discriminator] : [])]);
}

// "empty" = the value Eden would treat as unset. Blank string, null/undefined.
export function isBlank(v) {
  return v === "" || v === null || v === undefined;
}

// Required Eden fields that are missing or blank on this item's system block.
export function missingRequired(domain, system = {}) {
  const spec = EDEN[domain];
  if (!spec) return [];
  return spec.req.filter((f) => isBlank(system[f]));
}

/** Does this item still want a human's attention?
 *
 * True when a required Eden field is blank, or validation reported an issue
 * against it. Deliberately NOT qaStatus: almost the whole library is
 * `extracted`, so counting that would flag nearly every row and the filter
 * would tell you nothing.
 *
 * Shared so the table's filter and the editor's readiness panel cannot drift
 * apart and disagree about what "needs attention" means.
 */
export function needsAttention(item, domain, issueCount = 0) {
  if (issueCount > 0) return true;
  return missingRequired(domain, item?.system ?? {}).length > 0;
}
