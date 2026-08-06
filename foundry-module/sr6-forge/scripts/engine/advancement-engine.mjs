/** Post-creation karma advancement. Pure functions over a plain snapshot of
 *  the actor plus creation-rules.json, so the whole thing unit-tests in node —
 *  the app supplies the snapshot and applies the returned patch.
 *
 *  Every price is from the core rulebook p68-70:
 *    attributes and active skills   5 x new rank, paid per rank
 *    specialization / expertise     5
 *    new spell / ritual / complex form  5
 *    positive quality               twice its creation cost
 *    remove a negative quality      twice its creation bonus
 *    initiation / submersion        10 + the new level
 */

export const OPS = [
  "raiseAttribute", "raiseSkill", "addSpecialization", "addExpertise",
  "buyQuality", "removeQuality", "learnSpell", "learnRitual",
  "learnComplexForm", "initiate", "karmaToNuyen",
];

const CORE_ATTRS = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha"];

/** Read-only view of the bits of an eden actor advancement touches. */
export function snapshot(actor) {
  const sys = actor.system ?? {};
  const attributes = {};
  for (const k of [...CORE_ATTRS, "edg", "mag", "res"]) {
    const a = sys.attributes?.[k];
    if (!a) continue;
    attributes[k] = {
      base: k === "edg" ? (a.max ?? 0) : (a.base ?? 0),
      initiation: a.initiation ?? a.submersion ?? 0,
    };
  }
  const skills = {};
  for (const [id, s] of Object.entries(sys.skills ?? {})) {
    skills[id] = { points: s.points ?? 0, specialization: s.specialization ?? "",
      expertise: s.expertise ?? "" };
  }
  return {
    karma: sys.karma ?? 0,
    karmaTotal: sys.karma_total ?? 0,
    nuyen: sys.nuyen ?? 0,
    mortype: sys.mortype ?? "mundane",
    attributes, skills,
  };
}

/** Cost of moving a rank-based value from `from` to `from + 1`. */
function stepCost(from, perRank) { return (from + 1) * perRank; }

/**
 * Price and describe an operation without applying it.
 * @returns {{op, label, karma, nuyen, from, to, ok, reason, patch}}
 */
export function preview(op, snap, rules, { data = null } = {}) {
  const kc = rules.karmaCosts ?? {};
  const deny = (reason) => ({ ...op, ok: false, reason, karma: 0, nuyen: 0 });

  switch (op.kind) {
    case "raiseAttribute": {
      const cur = snap.attributes[op.target]?.base;
      if (cur == null) return deny("unknown-attribute");
      const max = op.max ?? 10;
      if (cur >= max) return deny("at-maximum");
      const karma = stepCost(cur, kc.attributePerRank ?? 5);
      const path = op.target === "edg"
        ? `system.attributes.edg.max` : `system.attributes.${op.target}.base`;
      const patch = { [path]: cur + 1 };
      if (op.target === "edg") patch["system.attributes.edg.current"] = cur + 1;
      return { ...op, ok: karma <= snap.karma, reason: karma > snap.karma ? "not-enough-karma" : null,
        label: `${op.target.toUpperCase()} ${cur} → ${cur + 1}`,
        karma, nuyen: 0, from: cur, to: cur + 1, patch };
    }

    case "raiseSkill": {
      const cur = snap.skills[op.target]?.points ?? 0;
      const max = op.max ?? 9;
      if (cur >= max) return deny("at-maximum");
      const karma = stepCost(cur, kc.skillPerRank ?? 5);
      return { ...op, ok: karma <= snap.karma, reason: karma > snap.karma ? "not-enough-karma" : null,
        label: `${op.name ?? op.target} ${cur} → ${cur + 1}`,
        karma, nuyen: 0, from: cur, to: cur + 1,
        patch: { [`system.skills.${op.target}.points`]: cur + 1 } };
    }

    case "addSpecialization":
    case "addExpertise": {
      const sk = snap.skills[op.target];
      if (!sk) return deny("unknown-skill");
      if (!(sk.points > 0)) return deny("skill-untrained");
      const field = op.kind === "addExpertise" ? "expertise" : "specialization";
      // core p70: an expertise requires the specialization it deepens
      if (field === "expertise" && !sk.specialization) return deny("needs-specialization");
      if (sk[field]) return deny("already-known");
      const karma = (field === "expertise" ? kc.expertise : kc.specialization) ?? 5;
      return { ...op, ok: karma <= snap.karma, reason: karma > snap.karma ? "not-enough-karma" : null,
        label: `${op.name ?? op.target}: ${field} "${op.value}"`,
        karma, nuyen: 0, from: "", to: op.value,
        patch: { [`system.skills.${op.target}.${field}`]: op.value } };
    }

    case "buyQuality": {
      // core p70: "Purchasing a positive quality requires spending twice the
      // normal Karma cost."
      const base = Math.abs(op.karmaCost ?? 0);
      const karma = base * (kc.positiveQualityMultiplier ?? 2);
      if (!op.positive) return deny("negative-qualities-cannot-be-bought");
      return { ...op, ok: karma <= snap.karma, reason: karma > snap.karma ? "not-enough-karma" : null,
        label: `Buy quality: ${op.name}`, karma, nuyen: 0, from: null, to: op.name,
        embed: op.uuid };
    }

    case "removeQuality": {
      // core p70: negative qualities "can be eliminated by paying twice the
      // base Karma bonus."
      const base = Math.abs(op.karmaCost ?? 0);
      const karma = base * (kc.removeNegativeQualityMultiplier ?? 2);
      if (op.positive) return deny("only-negative-qualities-can-be-bought-off");
      return { ...op, ok: karma <= snap.karma, reason: karma > snap.karma ? "not-enough-karma" : null,
        label: `Buy off quality: ${op.name}`, karma, nuyen: 0, from: op.name, to: null,
        removeItemId: op.itemId };
    }

    case "learnSpell":
    case "learnRitual":
    case "learnComplexForm": {
      const key = { learnSpell: "spell", learnRitual: "ritual", learnComplexForm: "complexForm" }[op.kind];
      const karma = kc[key] ?? 5;
      const needs = op.kind === "learnComplexForm" ? "resonance" : "magic";
      const mor = data?.morTypes?.[snap.mortype] ?? {};
      const allowed = needs === "resonance" ? mor.resonance : mor.spells;
      if (data && !allowed) return deny(`mortype-cannot-learn-${key}`);
      return { ...op, ok: karma <= snap.karma, reason: karma > snap.karma ? "not-enough-karma" : null,
        label: `Learn ${op.name}`, karma, nuyen: 0, from: null, to: op.name,
        embed: op.uuid };
    }

    case "initiate": {
      // core p70: "characters start at Level 0 and grow from there. Initiation
      // costs 10 Karma + the initiation/submersion level."
      const mor = data?.morTypes?.[snap.mortype] ?? {};
      const emerged = mor.resonance;
      const attr = emerged ? "res" : "mag";
      if (data && !mor.magic && !mor.resonance) return deny("mundane-cannot-initiate");
      const cur = snap.attributes[attr]?.initiation ?? 0;
      const next = cur + 1;
      const karma = (kc.initiationBase ?? 10) + next * (kc.initiationPerLevel ?? 1);
      const field = emerged ? "submersion" : "initiation";
      return { ...op, ok: karma <= snap.karma, reason: karma > snap.karma ? "not-enough-karma" : null,
        label: `${emerged ? "Submersion" : "Initiation"} grade ${cur} → ${next}`,
        karma, nuyen: 0, from: cur, to: next,
        patch: { [`system.attributes.${attr}.${field}`]: next } };
    }

    case "karmaToNuyen": {
      const karma = op.karma ?? 1;
      const nuyen = karma * (rules.karmaToNuyen?.rate ?? 2000);
      return { ...op, ok: karma <= snap.karma, reason: karma > snap.karma ? "not-enough-karma" : null,
        label: `Convert ${karma} karma to ${nuyen.toLocaleString()}¥`,
        karma, nuyen, from: snap.nuyen, to: snap.nuyen + nuyen,
        patch: { "system.nuyen": snap.nuyen + nuyen } };
    }

    /* Companion p154, "Working for the People" — the reverse trade. This is an
     * OPTIONAL downtime rule, not a creation one: the core book only ever lets
     * karma flow to nuyen (p67). Each karma costs a week of downtime, which the
     * table cannot track, so the note records the time owed for the GM. */
    case "nuyenToKarma": {
      const rule = rules.nuyenToKarma ?? {};
      if (!rule.enabled) return deny("optional-rule-off");
      const karma = op.karma ?? 1;
      const rate = rule.rate ?? 2000;
      const nuyen = karma * rate;
      if (nuyen > snap.nuyen) return { ...deny("not-enough-nuyen"),
        label: `Convert ${nuyen.toLocaleString()}¥ to ${karma} karma` };
      return { ...op, ok: true, reason: null,
        label: `Convert ${nuyen.toLocaleString()}¥ to ${karma} karma`,
        // negative spend: applyPatch subtracts, so this credits karma
        karma: -karma, nuyen: -nuyen,
        from: snap.karma, to: snap.karma + karma,
        note: `${karma} week${karma === 1 ? "" : "s"} of downtime`,
        patch: { "system.nuyen": snap.nuyen - nuyen } };
    }

    default:
      return deny(`unknown-op:${op.kind}`);
  }
}

/** Actor update for an approved preview: its patch plus the karma/nuyen spend. */
export function applyPatch(pv, snap) {
  const update = { ...(pv.patch ?? {}) };
  update["system.karma"] = snap.karma - pv.karma;
  return update;
}

/** Reverse of applyPatch, for undoing the most recent ledger entry. */
export function undoPatch(entry, snap) {
  const update = {};
  for (const [path, before] of Object.entries(entry.before ?? {})) update[path] = before;
  update["system.karma"] = snap.karma + entry.karma;
  return update;
}
