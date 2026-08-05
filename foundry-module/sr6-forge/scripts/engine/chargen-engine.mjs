/** ChargenEngine — pure creation logic. No Foundry imports: chargen-data,
 *  creation-rules and (optionally) a pack catalog are injected, so the whole
 *  engine unit-tests in plain node. The wizard renders budgets()/validate()
 *  and calls the mutators; commitPlan() emits everything the committer needs. */
import { allBudgets, attrRating, skillRank, CORE_ATTRS, SPECIAL_ATTRS } from "./budgets.mjs";
import { buildCommitPlan } from "./commit-plan.mjs";
import { makeProvider } from "./providers.mjs";
import { runValidation } from "./rules.mjs";

function blankAttributes() {
  const out = {};
  for (const k of CORE_ATTRS) out[k] = { points: 0, adjust: 0, karma: 0 };
  for (const k of SPECIAL_ATTRS) out[k] = { points: 0, adjust: 0, karma: 0 };
  return out;
}

export function blankState(method = "priority", rulesetId = "core") {
  return {
    method, rulesetId,
    optionalRules: {},              // world overrides of CHARGEN_* constants
    name: "",
    priorities: { METATYPE: null, ATTRIBUTE: null, MAGIC: null, SKILLS: null, RESOURCES: null },
    metatypeId: null,
    morId: "mundane",
    aspectedSkill: null,
    attributes: blankAttributes(),
    skills: {},                     // id -> {points, spec, expertise}
    knowledge: [],                  // {name, type:"knowledge"|"language", native}
    qualities: [],                  // {genesisID, rating, choiceText, subOptionKarma, free, positive}
    spells: [], powers: [], complexForms: [], rituals: [], foci: [],
    purchases: [],                  // {uuid, name, price, avail, essence, qty, rating}
    contacts: [],                   // {name, archetype (free text), connection, loyalty}
    lifestyleId: null, lifestyleMonths: 1,
    sins: [],                       // {name, rating(1-4? VERIFY), licenses[]}
    powerPointsBought: 0,
    conversions: { karmaToNuyen: 0 },
    log: [],
  };
}

export class ChargenEngine {
  constructor(chargenData, creationRules, { state = null, catalog = null } = {}) {
    this.data = chargenData;
    this.rules = creationRules;
    this.catalog = catalog;
    this.state = state ?? blankState();
    this.provider = makeProvider(this.state.method, chargenData);
  }

  /* ---------- persistence ---------- */
  toDraft() { return structuredClone(this.state); }

  static fromDraft(draft, chargenData, creationRules, opts = {}) {
    return new ChargenEngine(chargenData, creationRules,
      { ...opts, state: structuredClone(draft) });
  }

  /* ---------- step mutators ---------- */
  setMethod(method) {
    this.state.method = method;
    this.provider = makeProvider(method, this.data);
  }

  setRuleset(id) { this.state.rulesetId = id; }

  /** World-level optional-rule overrides (see apps/options-app.mjs). */
  setOptionalRules(overrides) { this.state.optionalRules = { ...(overrides ?? {}) }; }

  setPriority(column, letter) {
    this.state.priorities[column] = letter;
    // metatype/mor may no longer be legal — clear if so
    if (this.state.metatypeId
        && !this.provider.legalMetatypes(this.state).some((m) => m.id === this.state.metatypeId)) {
      this.state.metatypeId = null;
    }
    if (!this.provider.legalMors(this.state).some((m) => m.id === this.state.morId)) {
      this.state.morId = "mundane";
    }
  }

  legalMetatypes() { return this.provider.legalMetatypes(this.state); }

  setMetatype(id) {
    this.state.metatypeId = id;
    // racial qualities ride along for free
    this.state.qualities = this.state.qualities.filter((q) => !q.free);
    const mt = this.data.metatypes?.[id];
    for (const gid of mt?.racialQualityIds ?? []) {
      this.state.qualities.push({
        genesisID: gid, rating: mt.naturalRatings?.[gid] ?? 1, free: true,
      });
    }
  }

  legalMagicPaths() { return this.provider.legalMors(this.state); }

  setMagicPath(morId, { aspectedSkill = null } = {}) {
    this.state.morId = morId;
    this.state.aspectedSkill = aspectedSkill;
    const mor = this.data.morTypes?.[morId] ?? {};
    if (!mor.spells) this.state.spells = [];
    if (!mor.powers) { this.state.powers = []; this.state.powerPointsBought = 0; }
    if (!mor.resonance) this.state.complexForms = [];
  }

  /* ---------- uniform spend API ---------- */
  spend(op) {
    const s = this.state;
    switch (op.kind) {
      case "attribute": {
        const a = s.attributes[op.target];
        if (!a) return { ok: false, reason: "unknown-attribute" };
        const field = op.pool ?? "points";                    // points | adjust | karma
        const next = (a[field] ?? 0) + (op.delta ?? 1);
        if (next < 0) return { ok: false, reason: "below-zero" };
        a[field] = next;
        return { ok: true };
      }
      case "skill": {
        const sk = s.skills[op.target]
          ?? (s.skills[op.target] = { points: 0, karma: 0, spec: null, expertise: null });
        const field = op.pool === "karma" ? "karma" : "points";     // points | karma
        const next = (sk[field] ?? 0) + (op.delta ?? 1);
        if (next < 0) return { ok: false, reason: "below-zero" };
        sk[field] = next;
        if (!(sk.points > 0) && !(sk.karma > 0)) { sk.spec = null; sk.expertise = null; }
        return { ok: true };
      }
      case "spec": {
        const sk = s.skills[op.target];
        if (!sk || skillRank(sk) < 1) return { ok: false, reason: "skill-untrained" };
        sk.spec = op.spec ?? null;
        return { ok: true };
      }
      case "quality": {
        if (op.remove) {
          const i = s.qualities.findIndex((q) => q.genesisID === op.genesisID && !q.free);
          if (i < 0) return { ok: false, reason: "not-taken" };
          s.qualities.splice(i, 1);
          return { ok: true };
        }
        const meta = this.data.qualityMeta?.[op.genesisID];
        const already = s.qualities.filter((q) => q.genesisID === op.genesisID);
        if (already.length && !meta?.multi) return { ok: false, reason: "already-taken" };
        s.qualities.push({
          genesisID: op.genesisID, name: op.name ?? op.genesisID, rating: op.rating ?? 1,
          choiceText: op.choiceText ?? null, subOptionKarma: op.subOptionKarma ?? null,
          // caller-supplied values (from the pack row) win: qualityMeta only
          // covers the books we parsed, so it is a fallback, not the authority.
          positive: op.positive ?? meta?.positive ?? true,
          karma: op.karma ?? meta?.karma ?? 0,
          note: "", free: false,
        });
        return { ok: true };
      }
      case "purchase": {
        if (op.remove) {
          const i = s.purchases.findIndex((p) => p.uuid === op.uuid);
          if (i < 0) return { ok: false, reason: "not-owned" };
          if ((s.purchases[i].qty ?? 1) > 1 && !op.all) s.purchases[i].qty -= 1;
          else s.purchases.splice(i, 1);
          return { ok: true };
        }
        const existing = s.purchases.find((p) => p.uuid === op.uuid);
        if (existing && op.stack) existing.qty = (existing.qty ?? 1) + 1;
        else s.purchases.push({ uuid: op.uuid, name: op.name, price: op.price ?? 0,
          avail: op.avail ?? 0, essence: op.essence ?? 0, qty: 1, rating: op.rating ?? null,
          itemType: op.itemType ?? "gear" });
        return { ok: true };
      }
      case "spell": case "complexform": case "power": case "ritual": case "focus": {
        const list = { spell: s.spells, complexform: s.complexForms, power: s.powers,
          ritual: s.rituals, focus: s.foci }[op.kind];
        if (op.remove) {
          const i = list.findIndex((x) => x.uuid === op.uuid);
          if (i < 0) return { ok: false, reason: "not-known" };
          list.splice(i, 1);
          return { ok: true };
        }
        if (list.some((x) => x.uuid === op.uuid)) return { ok: false, reason: "duplicate" };
        list.push({ uuid: op.uuid, name: op.name, cost: op.cost ?? 0, level: op.level ?? 1 });
        return { ok: true };
      }
      case "powerpoints": {
        const next = (s.powerPointsBought ?? 0) + (op.delta ?? 1);
        if (next < 0) return { ok: false, reason: "below-zero" };
        s.powerPointsBought = next;
        return { ok: true };
      }
      case "contact": {
        if (op.remove) { s.contacts.splice(op.index, 1); return { ok: true }; }
        if (op.index != null) { Object.assign(s.contacts[op.index], op.patch); return { ok: true }; }
        s.contacts.push({ name: op.name ?? "", archetype: op.archetype ?? "",
          connection: op.connection ?? 1, loyalty: op.loyalty ?? 1 });
        return { ok: true };
      }
      case "knowledge": {
        if (op.remove) { s.knowledge.splice(op.index, 1); return { ok: true }; }
        s.knowledge.push({ name: op.name, type: op.type ?? "knowledge",
          native: op.native ?? false, points: op.native ? 4 : 1 });
        return { ok: true };
      }
      case "knowledgeRank": {
        const k = s.knowledge[Number(op.target)];
        if (!k) return { ok: false, reason: "unknown-entry" };
        if (k.native) return { ok: false, reason: "native-is-fixed" };
        const next = (k.points ?? 1) + (op.delta ?? 1);
        if (next < 1) return { ok: false, reason: "minimum-1" };
        if (next > 6) return { ok: false, reason: "maximum-6" };
        k.points = next;
        return { ok: true };
      }
      case "lifestyle": { s.lifestyleId = op.id; s.lifestyleMonths = op.months ?? 1; return { ok: true }; }
      case "sin": {
        if (op.remove) { s.sins.splice(op.index, 1); return { ok: true }; }
        s.sins.push({ name: op.name ?? "Fake SIN", rating: op.rating ?? 1, licenses: [] });
        return { ok: true };
      }
      case "karma2nuyen": {
        const next = (s.conversions.karmaToNuyen ?? 0) + (op.delta ?? 1);
        if (next < 0 || next > this.rules.karmaToNuyen.maxKarma) {
          return { ok: false, reason: "conversion-cap" };
        }
        s.conversions.karmaToNuyen = next;
        return { ok: true };
      }
      default:
        return { ok: false, reason: `unknown-op:${op.kind}` };
    }
  }

  /* ---------- reads ---------- */
  budgets() { return allBudgets(this.state, this.data, this.rules, this.provider); }

  attrRating(key) { return attrRating(this.state, key, this.provider); }

  skillRank(id) { return skillRank(this.state.skills[id]); }

  validate() {
    return runValidation({
      state: this.state, data: this.data, rules: this.rules,
      provider: this.provider, budgets: this.budgets(),
    });
  }

  commitPlan() {
    return buildCommitPlan(this.state, this.data, this.rules, this.provider, this.budgets());
  }
}
