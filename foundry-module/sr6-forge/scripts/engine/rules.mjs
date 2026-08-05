/** Declarative creation-validation rules. Each returns null (pass) or a params
 *  object (fail) — message keys live in lang/en.json as SR6FORGE.Validate.<id>.
 *  ctx = { state, data, rules, provider, budgets } */
import { CORE_ATTRS, SPECIAL_ATTRS, attrRating, qualityKarma, ruleConst } from "./budgets.mjs";

/** Split of paid quality karma (free racial qualities excluded). */
const qualitySplit = (state, data) => qualityKarma(state, data);

export const VALIDATION_RULES = [
  {
    id: "prio.allAssigned", severity: "error", step: "priority",
    check: ({ state }) =>
      Object.values(state.priorities).every(Boolean) ? null : {},
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
      const onLowered = ruleConst("CHARGEN_ADJUSTMENT_ON_LOWERED_MAX",
        data, rules, state.rulesetId) ?? false;
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
        (q) => q.genesisID === rules.skillCreationCap.aptitudeQualityId);
      const cap = hasAptitude ? rules.skillCreationCap.aptitudeCap
        : rules.skillCreationCap.value;
      let overCap = 0;
      for (const [id, s] of Object.entries(state.skills)) {
        if ((s.points ?? 0) > cap) return { skill: id, cap };
        if (hasAptitude && (s.points ?? 0) > rules.skillCreationCap.value) overCap += 1;
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
        if (!(s.points > 0)) continue;
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
    id: "nuyen.overspent", severity: "error", step: "purchases",
    check: ({ budgets, state, data, rules }) => {
      const allowNeg = ruleConst("CHARGEN_NEGATIVE_NUYEN", data, rules, state.rulesetId);
      return budgets.nuyen.left >= 0 || allowNeg ? null : {};
    },
  },
  {
    id: "gear.availCap", severity: "error", step: "purchases",
    check: ({ state, data, rules }) => {
      const cap = ruleConst("CHARGEN_MAX_AVAILABILITY", data, rules, state.rulesetId);
      for (const p of state.purchases) {
        if ((p.avail ?? 0) > cap) return { item: p.name ?? p.uuid, cap };
      }
      return null;
    },
  },
  {
    id: "essence.positive", severity: "error", step: "purchases",
    check: ({ budgets }) => (budgets.essence.left > 0 ? null : {}),
  },
  {
    id: "magic.spellsAllowed", severity: "error", step: "purchases",
    check: ({ state, data }) => {
      if (!state.spells.length) return null;
      return data.morTypes?.[state.morId]?.spells ? null : {};
    },
  },
  {
    id: "adept.ppBudget", severity: "error", step: "purchases",
    check: ({ budgets, state, data }) => {
      const mor = data.morTypes?.[state.morId];
      if (!mor?.powers) return state.powers.length ? {} : null;
      return budgets.powerPoints.left >= 0 ? null : {};
    },
  },
  {
    id: "contact.budget", severity: "error", step: "contacts",
    check: ({ budgets }) => (budgets.contactPoints.left >= 0 ? null : {}),
  },
  {
    id: "leftover.karma", severity: "warning", step: "review",
    check: ({ budgets, state, data, rules }) => {
      const cap = ruleConst("CHARGEN_MAX_KARMA_REMAIN", data, rules, state.rulesetId);
      return budgets.karma.left <= cap ? null : { cap };
    },
  },
  {
    id: "leftover.nuyen", severity: "warning", step: "review",
    check: ({ budgets, state, data, rules }) => {
      const cap = ruleConst("CHARGEN_MAX_NUYEN_REMAIN", data, rules, state.rulesetId);
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
