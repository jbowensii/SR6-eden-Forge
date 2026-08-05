/** Budget computation for character creation. Pure functions over
 *  (state, chargenData, creationRules, provider) — no Foundry dependencies. */

export const CORE_ATTRS = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha"];
export const SPECIAL_ATTRS = ["edg", "mag", "res"];

/** Effective creation rule value: ruleset interpretation overrides defaults. */
export function ruleConst(name, data, rules, rulesetId, overrides = null) {
  // world-level optional-rule overrides beat the interpretation defaults
  if (overrides && name in overrides) return overrides[name];
  const set = data.rules?.[rulesetId]?.set ?? {};
  if (name in set) return set[name];
  const d = rules.defaults;
  switch (name) {
    case "CHARGEN_MAX_AVAILABILITY": return d.maxAvailability;
    case "CHARGEN_MAX_KARMA_REMAIN": return d.maxKarmaRemain;
    case "CHARGEN_MAX_NUYEN_REMAIN": return d.maxNuyenRemain;
    case "CHARGEN_NEGATIVE_NUYEN": return d.allowNegativeNuyen;
    default: return undefined;
  }
}

/** Natural rating of an attribute from raw spends (all start at 1; mag/res
 *  start at the MAGIC-priority rating, edge at 1). */
export function attrRating(state, key, provider) {
  const a = state.attributes[key] ?? {};
  const base = key === "mag" || key === "res"
    ? provider.magicRating(state)
    : 1;
  return base + (a.points ?? 0) + (a.adjust ?? 0) + (a.karma ?? 0);
}

export function attributePointsSpent(state) {
  return CORE_ATTRS.reduce((n, k) => n + (state.attributes[k]?.points ?? 0), 0);
}

export function adjustmentPointsSpent(state) {
  return [...CORE_ATTRS, ...SPECIAL_ATTRS]
    .reduce((n, k) => n + (state.attributes[k]?.adjust ?? 0), 0);
}

/** Effective rank of a skill entry: free skill points plus karma-bought ranks. */
export function skillRank(entry) {
  return (entry?.points ?? 0) + (entry?.karma ?? 0);
}

export function skillPointsSpent(state) {
  let n = 0;
  for (const s of Object.values(state.skills)) {
    n += (s.points ?? 0) + (s.spec ? 1 : 0);      // specialization costs 1 skill point at creation
  }
  return n;
}

/** Karma for ranks bought with karma instead of skill points. Core p68: 5 x new
 *  rank, paid per rank, so the karma ranks are the TOP ranks of the skill. */
export function skillKarmaSpent(state, rules) {
  const per = rules.karmaCosts?.skillPerRank ?? 5;
  let n = 0;
  for (const s of Object.values(state.skills)) {
    const top = skillRank(s);
    for (let i = 0; i < (s.karma ?? 0); i++) n += (top - i) * per;
  }
  return n;
}

/** Karma from qualities. The stored entry is authoritative (it carries the
 *  pack row's category/value); qualityMeta is only a fallback because it covers
 *  just the books we parsed. */
export function qualityKarma(state, data) {
  let pos = 0, neg = 0;
  for (const q of state.qualities) {
    if (q.free) continue;                          // racial qualities are free
    const meta = data.qualityMeta?.[q.genesisID];
    const per = q.subOptionKarma ?? q.karma ?? meta?.karma ?? 0;
    const total = Math.abs(per) * (q.rating ?? 1);
    const positive = q.positive ?? meta?.positive ?? true;
    if (positive) pos += total; else neg += total;
  }
  return { pos, neg };
}

export function karmaBudget(state, data, rules, provider) {
  // Karma-build replaces the 50-karma allowance with its own pool
  const start = provider.startingKarma?.(rules) ?? rules.startingKarma.value;
  const q = qualityKarma(state, data);
  const spellCost = Math.max(0, state.spells.length - rules.spellsAtCreation.freeSpells)
    * rules.spellsAtCreation.karmaCost;
  const cfCost = Math.max(0, state.complexForms.length - rules.complexFormsAtCreation.freeForms)
    * rules.complexFormsAtCreation.karmaCost;
  const ppCost = (state.powerPointsBought ?? 0) * rules.mysticAdeptPowerPoints.karmaPerPoint;
  const perRank = rules.karmaCosts?.attributePerRank ?? 5;
  const attrKarma = [...CORE_ATTRS, ...SPECIAL_ATTRS]
    .reduce((n, k) => {
      const a = state.attributes[k] ?? {};
      let cost = 0;
      // karma raises during creation cost new-rating x5, applied per step
      const upto = attrRating(state, k, provider);
      for (let i = 0; i < (a.karma ?? 0); i++) cost += (upto - i) * perRank;
      return n + cost;
    }, 0);
  const skillKarma = skillKarmaSpent(state, rules);
  const metaKarma = data.metatypes?.[state.metatypeId]?.karma ?? 0;
  // only karma-build charges for the Magic/Resonance path
  const morKarma = provider.morKarma?.(state) ?? 0;
  const spent = q.pos + spellCost + cfCost + ppCost + attrKarma + skillKarma
    + metaKarma + morKarma + (state.conversions.karmaToNuyen ?? 0);
  return { max: start + q.neg, spent, left: start + q.neg - spent };
}

export function nuyenBudget(state, data, rules, provider) {
  const base = provider.nuyen(state);
  const conv = (state.conversions.karmaToNuyen ?? 0) * rules.karmaToNuyen.rate;
  const priceMods = data.metatypes?.[state.metatypeId]?.priceMods ?? {};
  const factor = 1 + (priceMods.EVERYTHING ?? 0);
  let spent = 0;
  for (const p of state.purchases) spent += (p.price ?? 0) * (p.qty ?? 1);
  spent *= factor;
  const ls = data.lifestyles?.[state.lifestyleId];
  if (ls) spent += ls.cost * (state.lifestyleMonths ?? 1);
  for (const s of state.sins) spent += (s.rating ?? 1) * 2500;   // fake SIN pricing (VERIFY V-C12b)
  return { max: base + conv, spent: Math.round(spent), left: Math.round(base + conv - spent) };
}

export function essenceUsed(state) {
  return state.purchases.reduce((n, p) => n + (p.essence ?? 0) * (p.qty ?? 1), 0);
}

export function powerPoints(state, data, rules, provider) {
  const mor = data.morTypes?.[state.morId] ?? {};
  let max = 0;
  if (mor.powers && !mor.paysPowers) max = attrRating(state, "mag", provider);       // adept
  else if (mor.powers && mor.paysPowers) max = state.powerPointsBought ?? 0;         // mystic adept
  const spent = state.powers.reduce((n, p) => n + (p.cost ?? 0) * (p.level ?? 1), 0);
  return { max, spent, left: max - spent };
}

/** Core p68: Charisma x 6 points across Connection + Loyalty; neither rating
 *  may exceed Charisma at creation. */
export function contactPoints(state, rules, provider) {
  const cha = attrRating(state, "cha", provider);
  const mult = Number(String(rules.contactPointsFormula.value).split("*")[1] ?? 6);
  // life modules grant extra contact points on top of the Charisma allowance
  const max = cha * mult + (provider.contactPointsBonus?.(state) ?? 0);
  const spent = state.contacts.reduce((n, c) => n + (c.connection ?? 1) + (c.loyalty ?? 1), 0);
  return { max, spent, left: max - spent, ratingCap: cha };
}

export function knowledgePoints(state, rules, provider) {
  const max = attrRating(state, "log", provider);
  // each rank of a non-native knowledge/language costs one point
  const spent = state.knowledge
    .filter((k) => !k.native)
    .reduce((n, k) => n + (k.points ?? 1), 0);
  return { max, spent, left: max - spent };
}

/** All budgets in one bag — the wizard's budget bar renders this directly. */
export function allBudgets(state, data, rules, provider) {
  const ap = provider.attributePoints(state);
  const adj = provider.adjustmentPoints(state);
  const sp = provider.skillPoints(state);
  return {
    attributePoints: { max: ap, spent: attributePointsSpent(state), left: ap - attributePointsSpent(state) },
    adjustmentPoints: { max: adj, spent: adjustmentPointsSpent(state), left: adj - adjustmentPointsSpent(state) },
    skillPoints: { max: sp, spent: skillPointsSpent(state), left: sp - skillPointsSpent(state) },
    karma: karmaBudget(state, data, rules, provider),
    nuyen: nuyenBudget(state, data, rules, provider),
    essence: { max: 6, spent: essenceUsed(state), left: 6 - essenceUsed(state) },
    powerPoints: powerPoints(state, data, rules, provider),
    contactPoints: contactPoints(state, rules, provider),
    knowledgePoints: knowledgePoints(state, rules, provider),
    // point-buy only; undefined for every other method
    characterPoints: provider.characterPoints?.(state),
  };
}
