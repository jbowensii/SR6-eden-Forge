/** Declarative creation-validation rules. Each returns null (pass) or a params
 *  object (fail) — message keys live in lang/en.json as SR6FORGE.Validate.<id>.
 *  ctx = { state, data, rules, provider, budgets } */
import { CORE_ATTRS, SPECIAL_ATTRS, attrRating, qualityKarma, creationSetting, skillRank, ratedValues } from "./budgets.mjs";
import { POINT_BUY, LIFEPATH_ADULT_COUNT } from "./providers.mjs";

/** Split of paid quality karma (free racial qualities excluded). */
const qualitySplit = (state, data) => qualityKarma(state, data);

/** Only Priority and Sum-to-Ten assign letters; the other methods have none. */
const usesPriorities = (provider) =>
  provider.constructor.id === "priority" || provider.constructor.id === "sumtoten";

export const VALIDATION_RULES = [
  {
    id: "prio.allAssigned", severity: "error", step: "priority",
    check: ({ state, provider }) =>
      !usesPriorities(provider) || Object.values(state.priorities).every(Boolean) ? null : {},
  },
  {
    id: "prio.lettersUnique", severity: "error", step: "priority",
    check: ({ state, provider }) =>
      provider.lettersValid(state.priorities) ? null : {},
  },
  {
    id: "prio.metatypeAllowed", severity: "error", step: "metatype",
    check: ({ state, provider }) => {
      if (!state.metatypeId) return { metatype: "(none)", letter: state.priorities.METATYPE };
      const ok = provider.legalMetatypes(state).some((m) => m.id === state.metatypeId);
      return ok ? null : { metatype: state.metatypeId, letter: state.priorities.METATYPE };
    },
  },
  {
    id: "prio.morAllowed", severity: "error", step: "magic",
    check: ({ state, provider }) => {
      const ok = provider.legalMors(state).some((m) => m.id === state.morId);
      return ok ? null : { mor: state.morId, letter: state.priorities.MAGIC };
    },
  },
  {
    id: "attr.overspent", severity: "error", step: "attributes",
    check: ({ budgets }) => (budgets.attributePoints.left >= 0 ? null : {}),
  },
  {
    id: "adjust.overspent", severity: "error", step: "attributes",
    check: ({ budgets }) => (budgets.adjustmentPoints.left >= 0 ? null : {}),
  },
  {
    id: "attr.creationMax", severity: "error", step: "attributes",
    check: ({ state, data, provider }) => {
      const maxima = data.metatypes?.[state.metatypeId]?.attributeMaxCreation ?? {};
      for (const k of [...CORE_ATTRS, "edg"]) {
        const max = maxima[k] ?? 6;
        if (attrRating(state, k, provider) > max) return { attr: k, max };
      }
      return null;
    },
  },
  {
    id: "attr.oneAtMax", severity: "error", step: "attributes",
    check: ({ state, data, rules, provider }) => {
      if (!rules.oneAttributeAtMax.value) return null;
      const maxima = data.metatypes?.[state.metatypeId]?.attributeMaxCreation ?? {};
      const keys = rules.oneAttributeAtMax.includesEdge ? [...CORE_ATTRS, "edg"] : CORE_ATTRS;
      const atMax = keys.filter((k) => attrRating(state, k, provider) >= (maxima[k] ?? 6));
      return atMax.length <= 1 ? null : { attrs: atMax.join(", ") };
    },
  },
  {
    id: "attr.adjustTargets", severity: "error", step: "attributes",
    check: ({ state, data, rules }) => {
      const maxima = data.metatypes?.[state.metatypeId]?.attributeMaxCreation ?? {};
      const onLowered = creationSetting("adjustmentOnLoweredMax",
        data, rules, state.rulesetId, state.optionalRules) ?? false;
      for (const k of CORE_ATTRS) {
        if (!(state.attributes[k]?.adjust > 0)) continue;
        const max = maxima[k] ?? 6;
        if (max > 6) continue;                       // raised max -> adjusted attr
        if (max < 6 && onLowered) continue;          // ruleset opt-in
        return { attr: k };
      }
      return null;    // edg/mag/res always legal adjustment targets
    },
  },
  {
    id: "skill.overspent", severity: "error", step: "skills",
    check: ({ budgets }) => (budgets.skillPoints.left >= 0 ? null : {}),
  },
  {
    id: "skill.capSix", severity: "error", step: "skills",
    check: ({ state, rules }) => {
      const hasAptitude = state.qualities.some(
        (q) => q.catalogId === rules.skillCreationCap.aptitudeQualityId);
      const cap = hasAptitude ? rules.skillCreationCap.aptitudeCap
        : rules.skillCreationCap.value;
      let overCap = 0;
      for (const [id, s] of Object.entries(state.skills)) {
        const rank = skillRank(s);        // skill points + karma-bought ranks
        if (rank > cap) return { skill: id, cap };
        if (hasAptitude && rank > rules.skillCreationCap.value) overCap += 1;
      }
      return overCap <= 1 ? null : { skill: "multiple", cap: rules.skillCreationCap.value };
    },
  },
  {
    id: "skill.restricted", severity: "error", step: "skills",
    check: ({ state, data }) => {
      const unlocks = new Set(data.morTypes?.[state.morId]?.skillUnlocks ?? []);
      const aspectedPick = state.aspectedSkill;
      for (const [id, s] of Object.entries(state.skills)) {
        if (!(skillRank(s) > 0)) continue;
        if (!data.skills?.[id]?.restricted) continue;
        if (unlocks.has(id)) {
          const mor = data.morTypes?.[state.morId];
          if (mor?.aspected && id !== aspectedPick && id !== "astral") return { skill: id };
          continue;
        }
        return { skill: id };
      }
      return null;
    },
  },
  {
    // Core p67: "You can't select more than six total qualities at character
    // creation, and the net bonus Karma cannot be more than 20." The cap is on
    // the NET (negatives minus positives), not on each side separately.
    id: "quality.netBonusCap", severity: "error", step: "qualities",
    check: ({ state, data, rules }) => {
      const { pos, neg } = qualitySplit(state, data);
      const net = neg - pos;
      const cap = rules.qualityNetBonusKarmaCap.value;
      return net <= cap ? null : { net, cap };
    },
  },
  {
    id: "quality.maxCount", severity: "error", step: "qualities",
    check: ({ state, rules }) => {
      const n = state.qualities.filter((q) => !q.free).length;   // racial are free
      const cap = rules.qualityMaxCount.value;
      return n <= cap ? null : { count: n, cap };
    },
  },
  {
    id: "karma.overspent", severity: "error", step: "review",
    check: ({ budgets }) => (budgets.karma.left >= 0 ? null : {}),
  },
  {
    id: "nuyen.overspent", severity: "error", step: "gear",
    check: ({ budgets, state, data, rules }) => {
      const allowNeg = creationSetting("allowNegativeNuyen", data, rules, state.rulesetId, state.optionalRules);
      return budgets.nuyen.left >= 0 || allowNeg ? null : {};
    },
  },
  {
    id: "gear.availCap", severity: "error", step: "gear",
    check: ({ state, data, rules }) => {
      const cap = creationSetting("maxAvailability", data, rules, state.rulesetId, state.optionalRules);
      for (const p of state.purchases) {
        // a rated item's availability rises with its rating
        if (ratedValues(p, data).avail > cap) return { item: p.name ?? p.uuid, cap };
        for (const a of p.accessories ?? []) {
          if ((a.avail ?? 0) > cap) return { item: a.name ?? a.catalogId, cap };
        }
      }
      return null;
    },
  },
  {
    id: "gear.ratingRange", severity: "error", step: "gear",
    check: ({ state, data }) => {
      for (const p of state.purchases) {
        const meta = data.gearRatings?.[p.catalogId];
        if (!meta?.ratings?.length) continue;
        const r = p.rating ?? meta.ratings[0];
        if (!meta.ratings.includes(r)) {
          return { item: p.name ?? p.uuid, max: meta.maxRating };
        }
      }
      return null;
    },
  },
  {
    id: "essence.positive", severity: "error", step: "augments",
    check: ({ budgets }) => (budgets.essence.left > 0 ? null : {}),
  },
  {
    id: "magic.spellsAllowed", severity: "error", step: "powers",
    check: ({ state, data }) => {
      if (!state.spells.length) return null;
      return data.morTypes?.[state.morId]?.spells ? null : {};
    },
  },
  {
    id: "adept.ppBudget", severity: "error", step: "powers",
    check: ({ budgets, state, data }) => {
      const mor = data.morTypes?.[state.morId];
      if (!mor?.powers) return state.powers.length ? {} : null;
      return budgets.powerPoints.left >= 0 ? null : {};
    },
  },
  {
    // Core p67: a mystic adept buys power points "up to a maximum of their
    // Magic attribute" from the priority table.
    id: "adept.ppCap", severity: "error", step: "powers",
    check: ({ budgets, state, data }) => {
      const mor = data.morTypes?.[state.morId];
      if (!mor?.paysPowers) return null;
      const cap = budgets.powerPoints.cap;
      const bought = state.powerPointsBought ?? 0;
      return bought <= cap ? null : { bought, cap };
    },
  },
  {
    id: "contact.budget", severity: "error", step: "contacts",
    check: ({ budgets }) => (budgets.contactPoints.left >= 0 ? null : {}),
  },
  {
    // Core p68: neither Connection nor Loyalty may exceed Charisma at creation.
    id: "contact.ratingCap", severity: "error", step: "contacts",
    check: ({ state, budgets }) => {
      const cap = budgets.contactPoints.ratingCap;
      for (const c of state.contacts) {
        if ((c.connection ?? 1) > cap || (c.loyalty ?? 1) > cap) {
          return { name: c.name || "(unnamed)", cap };
        }
      }
      return null;
    },
  },
  {
    // Companion p28: "All of your CP must be spent finishing your character;
    // none of it can carry over in any way."
    id: "pointbuy.overspent", severity: "error", step: "priority",
    check: ({ budgets }) => {
      const cp = budgets.characterPoints;
      if (!cp) return null;                       // not the point-buy method
      return cp.left >= 0 ? null : { over: -cp.left };
    },
  },
  {
    id: "pointbuy.unspent", severity: "error", step: "review",
    check: ({ budgets }) => {
      const cp = budgets.characterPoints;
      if (!cp) return null;
      return cp.left === 0 ? null : { left: cp.left };
    },
  },
  {
    // Companion p29 caps each pool independently of the 100 CP total.
    id: "pointbuy.poolCap", severity: "error", step: "priority",
    check: ({ state, provider }) => {
      if (provider.constructor.id !== "pointbuy") return null;
      const max = POINT_BUY.max;
      const cp = state.cp ?? {};
      for (const [pool, cap] of [["attribute", max.attribute], ["skill", max.skill],
        ["adjustment", max.adjustment], ["resources", max.nuyen / POINT_BUY.nuyenPerCp]]) {
        if ((cp[pool] ?? 0) > cap) return { pool, cap };
      }
      return null;
    },
  },
  {
    // Companion p29: "You may also have no more than one specialization at
    // character creation." (The priority system has no such limit.)
    id: "pointbuy.oneSpecialization", severity: "error", step: "skills",
    check: ({ state, provider }) => {
      if (provider.constructor.id !== "pointbuy") return null;
      const n = Object.values(state.skills).filter((s) => s.spec).length;
      return n <= 1 ? null : { count: n };
    },
  },
  {
    // Companion p33: "You must take exactly eight life modules." The three
    // opening modules are fixed and do not count toward that total.
    id: "lifepath.moduleCount", severity: "error", step: "priority",
    check: ({ state, provider }) => {
      if (provider.constructor.id !== "lifepath") return null;
      const n = (state.lifepath ?? []).length;
      return n === LIFEPATH_ADULT_COUNT ? null : { count: n, need: LIFEPATH_ADULT_COUNT };
    },
  },
  {
    // Companion p33: contact ratings cap at 8 on the life path, not Charisma.
    id: "lifepath.mixedChoices", severity: "error", step: "priority",
    check: ({ state, data, provider }) => {
      if (provider.constructor.id !== "lifepath") return null;
      for (const pick of state.lifepath ?? []) {
        const mod = data.lifepathModules?.[pick.id];
        for (const [i, choice] of (mod?.choices ?? []).entries()) {
          if (choice.kind === "mixed" && !pick.choices?.[i]) {
            return { module: mod?.name ?? pick.id, text: choice.text };
          }
        }
      }
      return null;
    },
  },
  {
    id: "leftover.karma", severity: "warning", step: "review",
    check: ({ budgets, state, data, rules }) => {
      const cap = creationSetting("maxKarmaRemaining", data, rules, state.rulesetId, state.optionalRules);
      return budgets.karma.left <= cap ? null : { cap };
    },
  },
  {
    id: "leftover.nuyen", severity: "warning", step: "review",
    check: ({ budgets, state, data, rules }) => {
      const cap = creationSetting("maxNuyenRemaining", data, rules, state.rulesetId, state.optionalRules);
      return budgets.nuyen.left <= cap ? null : { cap };
    },
  },
];

export function runValidation(ctx) {
  const issues = [];
  for (const rule of VALIDATION_RULES) {
    let params = null;
    try {
      params = rule.check(ctx);
    } catch (err) {
      params = { error: String(err) };
    }
    if (params) {
      issues.push({ id: rule.id, severity: rule.severity, step: rule.step, params });
    }
  }
  return issues;
}
