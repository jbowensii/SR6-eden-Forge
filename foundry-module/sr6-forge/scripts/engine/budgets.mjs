/** Budget computation for character creation. Pure functions over
 *  (state, chargenData, creationRules, provider) — no Foundry dependencies. */

export const CORE_ATTRS = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha"];
export const SPECIAL_ATTRS = ["edg", "mag", "res"];

/**
 * Effective value of a creation setting, most specific source first:
 * world override → rule interpretation → our own default.
 *
 * Setting names are this project's own (camelCase, Foundry/eden style); the
 * source data's SCREAMING_SNAKE rule ids are translated once at the import
 * boundary, in extractor/chargen_xml.py.
 *
 * @param {string} name        e.g. "maxAvailability"
 * @param {object} data        chargen-data.json
 * @param {object} rules       creation-rules.json
 * @param {string} rulesetId   selected rule interpretation
 * @param {object|null} overrides  world-level optional-rule overrides
 */
export function creationSetting(name, data, rules, rulesetId, overrides = null) {
  if (overrides && name in overrides) return overrides[name];
  const fromRuleset = data.rules?.[rulesetId]?.settings ?? {};
  if (name in fromRuleset) return fromRuleset[name];
  return rules.defaults?.[name];
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

/**
 * Total augmentation bonus to one attribute from adept powers and ware.
 *
 * Commlink6 shows these as "4 (6)" — the natural rating with the augmented one
 * beside it — and eden keeps them apart too (`base` vs `mod`). A leveled power
 * multiplies its bonus by the level; rating-based ware by its rating.
 */
export function augmentBonus(state, key, data) {
  let total = 0;
  for (const pw of state.powers ?? []) {
    const b = data.adeptPowers?.[pw.catalogId]?.bonuses?.[key];
    if (!b) continue;
    total += (b.flat ?? 0) + (b.perLevel ?? 0) * (pw.level ?? 1);
  }
  for (const p of state.purchases ?? []) {
    const b = data.gearMounts?.[p.catalogId]?.bonuses?.[key];
    if (!b) continue;
    const rating = p.rating ?? 1;
    total += ((b.flat ?? 0) + (b.perRating ?? 0) * rating) * (p.qty ?? 1);
    for (const a of p.accessories ?? []) {
      const ab = data.gearMounts?.[a.catalogId]?.bonuses?.[key];
      if (ab) total += (ab.flat ?? 0) + (ab.perRating ?? 0) * (a.rating ?? 1);
    }
  }
  return total;
}

/** Natural rating plus augmentations — what the character actually rolls. */
export function augmentedRating(state, key, provider, data) {
  return attrRating(state, key, provider) + augmentBonus(state, key, data);
}

/**
 * Resolve a rated item's price / availability / essence at a given rating.
 *
 * Rated gear carries no flat price — Wired Reflexes is 40,000 at rating 1 and
 * 450,000 at rating 4 — and eden's schema has room for exactly one `price`.
 * The per-rating tables therefore ride on the item itself, under our own
 * `system.sr6forge` namespace, which is what makes the cost computable from
 * the item alone.
 *
 * Sources, most authoritative first:
 *   1. `item.sr6forge` — carried by the item, so a custom or homebrew entry
 *      prices correctly with no central table to maintain
 *   2. `data.gearRatings` — the extracted fallback, keyed by catalogId
 *   3. the item's own flat price/avail/essence, for unrated gear
 *
 * @returns {{price:number, avail:number, essence:number, rating:number}}
 */
export function ratedValues(item, data, rating = null) {
  const onItem = item.sr6forge ?? null;
  const fromData = data?.gearRatings?.[item.catalogId] ?? null;
  const ratings = onItem?.ratings ?? fromData?.ratings ?? null;
  const r = rating ?? item.rating ?? ratings?.[0] ?? 1;

  // the item's arrays are already resolved per rating: index straight in
  const fromArray = (arr) => {
    if (!Array.isArray(arr) || !arr.length) return undefined;
    const v = arr[Math.min(Math.max(r, 1), arr.length) - 1];
    const n = parseFloat(String(v));
    return Number.isFinite(n) ? n : undefined;
  };
  // the extracted spec is a table or a multiplier
  const fromSpec = (spec) => {
    if (!spec) return undefined;
    if (spec.table) {
      const raw = spec.table[Math.min(Math.max(r, 1), spec.table.length) - 1];
      const n = parseFloat(String(raw));
      return Number.isFinite(n) ? n : undefined;
    }
    if (spec.perRating != null) return spec.perRating * r;
    if (spec.flat != null) return spec.flat;
    return undefined;
  };
  const pick = (arrKey, specKey, flat) =>
    fromArray(onItem?.[arrKey]) ?? fromSpec(fromData?.[specKey]) ?? flat ?? 0;

  return {
    rating: r,
    price: pick("priceByRating", "price", item.price),
    avail: pick("availByRating", "avail", item.avail),
    essence: pick("essenceByRating", "essence", item.essence),
  };
}

/**
 * How many of each mount an item offers, once its rating is known.
 *
 * Two kinds sit side by side. `hooks` are named mounts, one apiece — a pistol
 * has one BARREL. `hookCapacity` counts them instead, and the count is often
 * a formula: rating-3 glasses grant three OPTICAL slots, which is why rating
 * reads as "how much can I fit" on imaging gear and armour rather than as a
 * quality. Both are merged here so callers see one map.
 *
 * @returns {Record<string, number>} mount name -> how many are available
 */
export function hookCapacity(item, data) {
  const meta = data?.gearMounts?.[item?.catalogId] ?? {};
  const out = {};
  for (const h of meta.hooks ?? []) out[h] = (out[h] ?? 0) + 1;

  const rating = ratedValues(item, data).rating;
  for (const [ref, raw] of Object.entries(meta.hookCapacity ?? {})) {
    const n = resolveHookCount(raw, rating);
    if (n > 0) out[ref] = (out[ref] ?? 0) + n;
  }
  return out;
}

/**
 * Resolve a counted-hook value against a rating.
 *
 * Deliberately narrow: numbers, and the $RATING forms the data actually uses.
 * Anything else (notably $CONCURRENT_PROGRAMS, which depends on a device
 * rating we do not track here) yields 0 rather than a guess, so an unknown
 * formula shows no capacity instead of a wrong one.
 */
export function resolveHookCount(raw, rating = 1) {
  if (typeof raw === "number") return Math.floor(raw);
  if (typeof raw !== "string") return 0;
  const s = raw.replace(/\s+/g, "");
  if (/^-?\d+(\.\d+)?$/.test(s)) return Math.floor(Number(s));
  const m = s.match(/^\$RATING(?:([*/])(-?\d+(?:\.\d+)?))?$/);
  if (!m) return 0;
  if (!m[1]) return Math.floor(rating);
  const n = Number(m[2]);
  return Math.floor(m[1] === "*" ? rating * n : rating / n);
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
 *  rank, paid per rank, so the karma ranks are the TOP ranks of the skill.
 *  Knowledge and language skills are a flat rate instead — see below. */
export function skillKarmaSpent(state, rules) {
  const per = rules.karmaCosts?.skillPerRank ?? 5;
  let n = 0;
  for (const s of Object.values(state.skills)) {
    const top = skillRank(s);
    for (let i = 0; i < (s.karma ?? 0); i++) n += (top - i) * per;
  }
  // Core p69: "New Knowledge skills cost 3 Karma" — a flat rate, cheaper than
  // the 5 x new rank an active skill costs.
  const knowPer = rules.karmaCosts?.knowledgeSkill ?? 3;
  for (const k of state.knowledge ?? []) n += (k.karma ?? 0) * knowPer;
  return n;
}

/** Karma from qualities. The stored entry is authoritative (it carries the
 *  pack row's category/value); qualityMeta is only a fallback because it covers
 *  just the books we parsed. */
export function qualityKarma(state, data) {
  let pos = 0, neg = 0;
  for (const q of state.qualities) {
    if (q.free) continue;                          // racial qualities are free
    const meta = data.qualityMeta?.[q.catalogId];
    const per = q.subOptionKarma ?? q.karma ?? meta?.karma ?? 0;
    const total = Math.abs(per) * (q.rating ?? 1);
    const positive = q.positive ?? meta?.positive ?? true;
    if (positive) pos += total; else neg += total;
  }
  return { pos, neg };
}

/**
 * Spells, rituals and complex forms a character gets for free at creation.
 *
 * Core p66: a full magician gets Magic x 2, a technomancer Resonance x 2, and
 * both use the PRIORITY rating — "not as altered with any points, Karma, or
 * any other adjustments". Core p67: a mystic adept first spends priority Magic
 * on power points, then doubles what is left.
 */
export function freeSpellSlots(state, data, provider) {
  const mor = data.morTypes?.[state.morId] ?? {};
  const priorityRating = provider.magicRating(state);   // priority table only
  if (mor.resonance) return priorityRating * 2;
  if (!mor.spells) return 0;
  const spentOnPowers = mor.paysPowers ? (state.powerPointsBought ?? 0) : 0;
  return Math.max(0, priorityRating - spentOnPowers) * 2;
}

export function karmaBudget(state, data, rules, provider) {
  // Karma-build replaces the 50-karma allowance with its own pool
  const start = provider.startingKarma?.(rules) ?? rules.startingKarma.value;
  const q = qualityKarma(state, data);
  const free = freeSpellSlots(state, data, provider);
  const known = state.spells.length + state.rituals.length;
  const spellCost = Math.max(0, known - free) * rules.spellsAtCreation.karmaCost;
  const cfCost = Math.max(0, state.complexForms.length - free)
    * rules.complexFormsAtCreation.karmaCost;
  // Power points are a split of the priority Magic, not a karma purchase.
  const ppCost = 0;
  const perRank = rules.karmaCosts?.attributePerRank ?? 5;
  // per-attribute, so the review can say WHICH attribute ate the karma —
  // a raise near the top of the range costs several times one near the bottom
  const attrDetail = [];
  const attrKarma = [...CORE_ATTRS, ...SPECIAL_ATTRS]
    .reduce((n, k) => {
      const a = state.attributes[k] ?? {};
      let cost = 0;
      // karma raises during creation cost new-rating x5, applied per step
      const upto = attrRating(state, k, provider);
      for (let i = 0; i < (a.karma ?? 0); i++) cost += (upto - i) * perRank;
      if (cost) attrDetail.push({ key: k, ranks: a.karma, from: upto - a.karma, to: upto, cost });
      return n + cost;
    }, 0);
  const skillKarma = skillKarmaSpent(state, rules);
  const metaKarma = data.metatypes?.[state.metatypeId]?.karma ?? 0;
  // only karma-build charges for the Magic/Resonance path
  const morKarma = provider.morKarma?.(state) ?? 0;
  const spent = q.pos + spellCost + cfCost + ppCost + attrKarma + skillKarma
    + metaKarma + morKarma + (state.conversions.karmaToNuyen ?? 0);

  const breakdown = [];
  const add = (key, label, amount, sign = "spend") => {
    if (amount) breakdown.push({ key, label, amount, sign });
  };
  add("qualityNeg", "Negative qualities", q.neg, "gain");
  for (const d of attrDetail) {
    add(`attr:${d.key}`,
      `${d.key.toUpperCase()} ${d.from} → ${d.to} (${d.ranks} rank${d.ranks === 1 ? "" : "s"} by karma)`,
      d.cost);
  }
  add("skills", "Skills raised with karma", skillKarma);
  add("qualityPos", "Positive qualities", q.pos);
  add("spells", "Spells / rituals beyond the free ones", spellCost);
  add("complexForms", "Complex forms beyond the free ones", cfCost);
  add("metatype", "Metatype karma cost", metaKarma);
  add("mor", "Magic / Resonance path", morKarma);
  add("toNuyen", "Converted to nuyen", state.conversions.karmaToNuyen ?? 0);

  return { max: start + q.neg, spent, left: start + q.neg - spent,
    base: start, fromQualities: q.neg, breakdown };
}

/** Core p274: "Fake SIN 4(I) Rating x 2,500¥" / "Fake license 4(I) Rating x 200¥". */
export const FAKE_SIN_PER_RATING = 2500;
export const FAKE_LICENSE_PER_RATING = 200;

/**
 * Nuyen at creation.
 *
 * Returns a `breakdown` alongside the totals because gear is NOT the only
 * thing that costs money — a lifestyle and any fake SINs come out of the same
 * pool, and a character who has bought no gear at all can still be deep in the
 * red. Without an itemised list that reads as a bug in the budget.
 */
export function nuyenBudget(state, data, rules, provider) {
  const base = provider.nuyen(state);
  const conv = (state.conversions.karmaToNuyen ?? 0) * (rules.karmaToNuyen?.rate ?? 2000);
  const priceMods = data.metatypes?.[state.metatypeId]?.priceMods ?? {};
  const factor = 1 + (priceMods.EVERYTHING ?? 0);
  const breakdown = [];

  let gear = 0;
  for (const p of state.purchases) {
    // A PACK's own line carries the price of the whole bundle, so its contents
    // must not be priced again. They cannot simply be left at price 0 either:
    // they keep their catalogId, and ratedValues would happily find the real
    // price in gearRatings and charge it a second time.
    if (p.fromPack) continue;
    gear += ratedValues(p, data).price * (p.qty ?? 1);
    // fitted accessories are paid for too; factory-fitted ones are included in
    // the host's price and carry 0
    for (const a of p.accessories ?? []) gear += a.price ?? 0;
  }
  gear *= factor;
  let spent = gear;
  if (gear) {
    breakdown.push({ key: "gear", step: "purchases",
      label: `Gear (${state.purchases.length} item${state.purchases.length === 1 ? "" : "s"})`,
      amount: Math.round(gear) });
  }

  const ls = state.lifestyleFromPack ? null : data.lifestyles?.[state.lifestyleId];
  if (ls) {
    const months = state.lifestyleMonths ?? 1;
    const cost = ls.cost * months;
    spent += cost;
    if (cost) {
      breakdown.push({ key: "lifestyle", step: "purchases",
        label: `${ls.name} lifestyle x ${months} month${months === 1 ? "" : "s"}`,
        amount: cost });
    }
  }

  for (const s of state.sins) {
    if (s.fromPack) continue;          // covered by the pack's own price
    // a license may be a bare name or a rated object; an unrated one is Rating 1
    const licenses = (s.licenses ?? [])
      .reduce((n, l) => n + (typeof l === "object" ? (l.rating ?? 1) : 1)
        * FAKE_LICENSE_PER_RATING, 0);
    const cost = (s.rating ?? 1) * FAKE_SIN_PER_RATING + licenses;
    spent += cost;
    breakdown.push({ key: "sin", step: "purchases",
      label: `${s.name || "Fake SIN"} (rating ${s.rating ?? 1}${
        (s.licenses ?? []).length ? `, ${s.licenses.length} license${s.licenses.length === 1 ? "" : "s"}` : ""})`,
      amount: cost });
  }

  return { max: base + conv, spent: Math.round(spent),
    left: Math.round(base + conv - spent),
    base, converted: conv, breakdown };
}

export function essenceUsed(state, data) {
  // as with price: an augmentation PACK states one ESSENCECOST for the bundle,
  // so its contents' own essence must not be counted on top
  return state.purchases.reduce(
    (n, p) => (p.fromPack ? n : n + ratedValues(p, data).essence * (p.qty ?? 1)), 0);
}

/**
 * Adept power points. Core p67: an adept's pool equals "their Magic (as listed
 * in the Priority table, before any adjustments)"; a mystic adept instead buys
 * power points out of that same priority Magic, capped by it.
 */
export function powerPoints(state, data, rules, provider) {
  const mor = data.morTypes?.[state.morId] ?? {};
  let max = 0;
  if (mor.powers && !mor.paysPowers) max = provider.magicRating(state);       // adept
  else if (mor.powers && mor.paysPowers) max = state.powerPointsBought ?? 0;  // mystic adept
  // a leveled power costs `cost` power points PER LEVEL (Improved Reflexes at
  // 1 PP/level is 1 / 2 / 3 PP at levels 1 / 2 / 3)
  const spent = state.powers.reduce((n, p) => n + (p.cost ?? 0) * (p.level ?? 1), 0);
  return { max, spent: Math.round(spent * 100) / 100,
    left: Math.round((max - spent) * 100) / 100, cap: provider.magicRating(state) };
}

/** Core p68: Charisma x 6 points across Connection + Loyalty; neither rating
 *  may exceed Charisma at creation. */
export function contactPoints(state, rules, provider) {
  // the life path replaces this rule wholesale (Companion p33)
  if (provider.contactPoints) return provider.contactPoints(state);
  const cha = attrRating(state, "cha", provider);
  const mult = Number(String(rules.contactPointsFormula.value).split("*")[1] ?? 6);
  const max = cha * mult;
  const spent = state.contacts.reduce((n, c) => n + (c.connection ?? 1) + (c.loyalty ?? 1), 0);
  return { max, spent, left: max - spent, ratingCap: cha };
}

export function knowledgePoints(state, rules, provider) {
  if (provider.knowledgePoints) return provider.knowledgePoints(state);
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
    essence: (() => {
      const used = Math.round(essenceUsed(state, data) * 100) / 100;
      return { max: 6, spent: used, left: Math.round((6 - used) * 100) / 100 };
    })(),
    powerPoints: powerPoints(state, data, rules, provider),
    spellSlots: (() => {
      const max = freeSpellSlots(state, data, provider);
      const mor = data.morTypes?.[state.morId] ?? {};
      const used = mor.resonance ? state.complexForms.length
        : state.spells.length + state.rituals.length;
      return { max, spent: used, left: max - used };
    })(),
    contactPoints: contactPoints(state, rules, provider),
    knowledgePoints: knowledgePoints(state, rules, provider),
    // point-buy only; undefined for every other method
    characterPoints: provider.characterPoints?.(state),
  };
}
