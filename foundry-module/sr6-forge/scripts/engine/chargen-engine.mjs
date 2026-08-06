/** ChargenEngine — pure creation logic. No Foundry imports: chargen-data,
 *  creation-rules and (optionally) a pack catalog are injected, so the whole
 *  engine unit-tests in plain node. The wizard renders budgets()/validate()
 *  and calls the mutators; commitPlan() emits everything the committer needs. */
import { allBudgets, attrRating, skillRank, hookCapacity,
  CORE_ATTRS, SPECIAL_ATTRS } from "./budgets.mjs";
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
    optionalRules: {},              // world overrides of the creation settings
    name: "",
    priorities: { METATYPE: null, ATTRIBUTE: null, MAGIC: null, SKILLS: null, RESOURCES: null },
    // point-buy: character points allocated to each pool (Companion p28-29)
    cp: { attribute: 0, skill: 0, adjustment: 0, resources: 0,
          powerPoints: 0, spells: 0, complexForms: 0 },
    lifepath: [],                   // [{id, stage, choices:{uuid: pick}}]
    metatypeId: null,
    morId: "mundane",
    aspectedSkill: null,
    attributes: blankAttributes(),
    skills: {},                     // id -> {points, spec, expertise}
    knowledge: [],                  // {name, type:"knowledge"|"language", native}
    qualities: [],                  // {catalogId, rating, choiceText, subOptionKarma, free, positive}
    spells: [], powers: [], complexForms: [], rituals: [], foci: [],
    purchases: [],                  // {uuid, name, price, avail, essence, qty, rating,
                                    //  accessories:[{uuid,catalogId,name,price,avail,slot}]}
    contacts: [],                   // {name, archetype (free text), connection, loyalty}
    lifestyleId: null, lifestyleMonths: 1,
    lifestyleFromPack: null,        // set when a PACK supplied the lifestyle
    sins: [],                       // {name, rating(1-4? VERIFY), licenses[]}
    powerPointsBought: 0,
    conversions: { karmaToNuyen: 0 },
    log: [],
  };
}

/**
 * Item types that may share one line with a quantity.
 *
 * Consumables and supplies — rounds, chemicals, rope, tools. Everything else
 * is a discrete object: two Ares Predators are two guns, and collapsing them
 * into "x2" makes it impossible to silence one and leave the other alone,
 * because accessories hang off the line rather than the weapon.
 */
export const STACKABLE_TYPES = new Set([
  "AMMUNITION", "CHEMICALS", "SURVIVAL", "TOOLS",
]);

/** State collections whose entries are keyed by a catalog id. */
const CATALOG_KEYED = ["qualities", "spells", "powers", "complexForms", "rituals",
  "foci", "purchases", "knowledge", "contacts"];

/**
 * Bring a saved draft up to the current state shape.
 *
 * Drafts written before the catalog-id rename key their entries `genesisID`.
 * Nothing reads that name any more, so such a draft silently loses every
 * lookup that depends on it: qualities price at 0 Karma because their metadata
 * cannot be found, and they cannot be removed because the remove action
 * matches on an id that is now undefined. Renaming the key in place repairs
 * both and keeps whatever the player typed alongside it.
 *
 * @param {object} state  mutated in place and returned
 */
export function migrateState(state, data = null) {
  if (!state) return state;

  // Split lines that should never have been stacked. Drafts saved before
  // stacking was restricted collapsed two identical weapons into "x2", which
  // leaves them sharing one accessory list — you cannot silence one Predator
  // and not the other. Splitting is safe: the totals are unchanged, since
  // price is per unit and multiplied by qty either way.
  if (Array.isArray(state.purchases)) {
    const split = [];
    for (const p of state.purchases) {
      const gm = data?.gearMounts?.[p.catalogId] ?? {};
      const mountable = (gm.hooks ?? []).length
        || Object.keys(gm.hookCapacity ?? {}).length;
      const stackable = STACKABLE_TYPES.has(p.gearType) && !mountable;
      if (!stackable && (p.qty ?? 1) > 1) {
        const n = p.qty;
        for (let i = 0; i < n; i++) {
          // the accessories already fitted stay on the first copy; the rest
          // come out bare, which is what "I only modified one of them" means
          split.push({ ...structuredClone(p), qty: 1,
            accessories: i === 0 ? (p.accessories ?? []) : [] });
        }
      } else {
        split.push(p);
      }
    }
    state.purchases = split;
  }

  for (const key of CATALOG_KEYED) {
    for (const entry of state[key] ?? []) {
      if (entry?.genesisID !== undefined) {
        entry.catalogId ??= entry.genesisID;
        delete entry.genesisID;
      }
      // accessories carry their own catalog id
      for (const a of entry?.accessories ?? []) {
        if (a?.genesisID !== undefined) { a.catalogId ??= a.genesisID; delete a.genesisID; }
      }
    }
  }
  return state;
}

export class ChargenEngine {
  constructor(chargenData, creationRules, { state = null, catalog = null } = {}) {
    this.data = chargenData;
    this.rules = creationRules;
    this.catalog = catalog;
    this.state = migrateState(state ?? blankState(), chargenData);
    this.provider = makeProvider(this.state.method, chargenData);
    this.#syncQualityGrants();
  }

  /**
   * May this purchase share a line with an identical one?
   *
   * Only consumables, and only when the item takes no accessories — a hook
   * means the thing can be individually modified, which stacking would hide.
   */
  #stackable(op) {
    if (!STACKABLE_TYPES.has(op.gearType)) return false;
    const gm = this.data.gearMounts?.[op.catalogId] ?? {};
    return !((gm.hooks ?? []).length || Object.keys(gm.hookCapacity ?? {}).length);
  }

  /**
   * Keep quality-granted SINs in step with the qualities held.
   *
   * SINner declares `<itemmod type="SIN" ref="REAL_SIN"/>`, so the quality is
   * what makes a runner SINned (core p273). The SIN is created when the
   * quality is taken and withdrawn when it is dropped; anything the player
   * typed into it — the legal name — survives a round trip because the entry
   * is matched on the granting quality, not rebuilt blindly.
   */
  /**
   * Keep everything a quality HANDS OVER in step with the qualities held.
   *
   * Some qualities give you a thing rather than a modifier, and declare it in
   * their own data: SINner grants `<itemmod type="SIN" ref="REAL_SIN"/>`,
   * Shifter grants four further qualities, and the metagenetic ones grant
   * natural weapons as gear. All of it is reconciled here — created when the
   * parent is taken, withdrawn when it is dropped — so nothing has to name a
   * quality in code.
   *
   * Granted things are free: their cost sat in the parent's karma price.
   */
  #syncQualityGrants() {
    const s = this.state;
    s.sins ??= [];
    s.purchases ??= [];

    // parent quality -> what it hands over (only qualities actually held)
    const held = s.qualities.filter((q) => !q.fromQuality);
    const grants = held
      .map((q) => [q.catalogId, this.data.qualityMeta?.[q.catalogId]?.grants])
      .filter(([, g]) => g);
    const parents = new Set(grants.map(([cid]) => cid));

    // withdraw anything whose parent is gone
    s.sins = s.sins.filter((x) => !x.fromQuality || parents.has(x.fromQuality));
    s.purchases = s.purchases.filter((p) => !p.fromQuality || parents.has(p.fromQuality));
    s.qualities = s.qualities.filter((q) => !q.fromQuality || parents.has(q.fromQuality));

    for (const [cid, g] of grants) {
      for (const ref of g.sin ?? []) {
        if (s.sins.some((x) => x.fromQuality === cid)) continue;
        s.sins.push({
          id: `sin-${cid}`, kind: ref === "REAL_SIN" ? "real" : "fake",
          name: ref === "REAL_SIN" ? "Real SIN" : "Fake SIN",
          rating: ref === "REAL_SIN" ? null : 1, licenses: [], fromQuality: cid,
        });
      }
      for (const ref of g.quality ?? []) {
        if (s.qualities.some((q) => q.catalogId === ref && q.fromQuality === cid)) continue;
        const meta = this.data.qualityMeta?.[ref] ?? {};
        s.qualities.push({
          catalogId: ref, name: ref.replaceAll("_", " "), rating: 1,
          positive: meta.positive ?? false, karma: 0, free: true,
          fromQuality: cid, note: "",
        });
      }
      for (const ref of g.gear ?? []) {
        if (s.purchases.some((p) => p.catalogId === ref && p.fromQuality === cid)) continue;
        s.purchases.push({
          uuid: null, catalogId: ref, name: ref.replaceAll("_", " "),
          price: 0, avail: 0, essence: 0, qty: 1, rating: null,
          itemType: "gear", gearType: null, subtype: null,
          sr6forge: null, accessories: [], fromQuality: cid,
        });
      }
    }
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
        catalogId: gid, rating: mt.naturalRatings?.[gid] ?? 1, free: true,
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
          let i = op.catalogId
            ? s.qualities.findIndex((q) => q.catalogId === op.catalogId && !q.free)
            : -1;
          // fall back to position, so an entry with no usable id is still
          // removable rather than stuck on the sheet forever
          if (i < 0 && Number.isInteger(op.index)
              && s.qualities[op.index] && !s.qualities[op.index].free) {
            i = op.index;
          }
          if (i < 0) return { ok: false, reason: "not-taken" };
          s.qualities.splice(i, 1);
          this.#syncQualityGrants();
          return { ok: true };
        }
        const meta = this.data.qualityMeta?.[op.catalogId];
        const already = s.qualities.filter((q) => q.catalogId === op.catalogId);
        if (already.length && !meta?.multi) return { ok: false, reason: "already-taken" };
        s.qualities.push({
          catalogId: op.catalogId, name: op.name ?? op.catalogId, rating: op.rating ?? 1,
          choiceText: op.choiceText ?? null, subOptionKarma: op.subOptionKarma ?? null,
          // caller-supplied values (from the pack row) win: qualityMeta only
          // covers the books we parsed, so it is a fallback, not the authority.
          positive: op.positive ?? meta?.positive ?? true,
          karma: op.karma ?? meta?.karma ?? 0,
          note: "", free: false,
        });
        this.#syncQualityGrants();
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
        if (existing && op.stack && this.#stackable(op)) existing.qty = (existing.qty ?? 1) + 1;
        else s.purchases.push({ uuid: op.uuid, name: op.name, price: op.price ?? 0,
          avail: op.avail ?? 0, essence: op.essence ?? 0,
          qty: Math.max(1, op.qty ?? 1), rating: op.rating ?? null,
          // homebrew: no compendium document behind it, so the commit plan
          // builds the item rather than copying one
          custom: !!op.custom, note: op.note || null,
          itemType: op.itemType ?? "gear", gearType: op.gearType ?? null,
          catalogId: op.catalogId ?? null, subtype: op.subtype ?? null,
          // the item's own pricing tables travel with the purchase, so a draft
          // reopened later re-costs from the item rather than a lookup file
          sr6forge: op.sr6forge ?? null,
          // factory-fitted accessories occupy their slot and cost nothing extra
          accessories: (this.data.gearMounts?.[op.catalogId]?.embedded ?? [])
            .filter((e) => e.included)
            .map((e) => ({ catalogId: e.ref, name: e.ref.replaceAll("_", " "),
              slot: e.slot || "INTERNAL", price: 0, avail: 0, included: true })) });
        return { ok: true };
      }
      /* A Companion PACK (6WC p47+). The pack's own price replaces the sum of
       * its parts — that discount is the reason to buy one — so it enters as a
       * SINGLE purchase carrying the whole price and essence cost, and its
       * contents ride along as zero-priced lines. Commlink6 sells them the
       * same way, from its gear page.
       *
       * Contents are not all gear: a pack can hand over a fake SIN, licences
       * for it, and a month of lifestyle, so those land in the state fields
       * that already model them rather than becoming pretend gear. */
      case "pack": {
        const pack = this.data.packs?.[op.catalogId];
        if (!pack) return { ok: false, reason: "unknown-pack" };
        if (op.remove) {
          const i = s.purchases.findIndex(
            (p) => p.packId === op.catalogId && p.isPack);
          if (i < 0) return { ok: false, reason: "not-owned" };
          const [gone] = s.purchases.splice(i, 1);
          // take back exactly what this pack granted, and nothing else
          s.purchases = s.purchases.filter((p) => p.fromPack !== gone.packInstance);
          s.sins = s.sins.filter((x) => x.fromPack !== gone.packInstance);
          if (s.lifestyleFromPack === gone.packInstance) {
            s.lifestyleId = null;
            s.lifestyleFromPack = null;
          }
          return { ok: true };
        }
        if (s.purchases.some((p) => p.isPack && p.packId === op.catalogId)) {
          return { ok: false, reason: "already-owned" };
        }
        // distinguishes two copies of different packs when removing one
        const instance = `pack-${op.catalogId}-${s.purchases.length}`;
        s.purchases.push({
          uuid: op.uuid ?? null, name: op.name ?? pack.name ?? op.catalogId,
          price: pack.price ?? 0, avail: 0, essence: pack.essence ?? 0,
          qty: 1, rating: null, itemType: "pack", catalogId: op.catalogId,
          subtype: pack.subtype ?? null, sr6forge: null, accessories: [],
          isPack: true, packId: op.catalogId, packInstance: instance,
        });
        for (const row of pack.contents ?? []) {
          if (row.kind === "sin") {
            s.sins.push({ name: `Fake SIN (${row.level ?? "pack"})`,
              rating: row.rating ?? 1, licenses: [], fromPack: instance });
          } else if (row.kind === "license") {
            // attach to the SIN this pack just granted, else the newest one
            const sin = [...s.sins].reverse()
              .find((x) => x.fromPack === instance) ?? s.sins[s.sins.length - 1];
            for (let i = 0; i < (row.qty ?? 1); i++) {
              sin?.licenses.push({ name: "Fake licence", rating: row.rating ?? 1,
                fromPack: instance });
            }
          } else if (row.kind === "lifestyle") {
            // never silently replace a lifestyle the player chose themselves
            if (!s.lifestyleId) {
              s.lifestyleId = row.ref;
              s.lifestyleMonths = 1;
              s.lifestyleFromPack = instance;
            }
          } else {
            s.purchases.push({
              uuid: null, name: (row.ref ?? "?").replaceAll("_", " "),
              // the pack price already covers these
              price: 0, avail: 0, essence: 0,
              qty: row.qty ?? 1, rating: row.rating ?? null, itemType: "gear",
              catalogId: row.ref, subtype: null, sr6forge: null,
              grade: row.grade ?? null, variant: row.variant ?? null,
              note: row.text ?? null, fromPack: instance,
              accessories: (row.embeds ?? []).map((e) => ({
                catalogId: e.ref, name: (e.ref ?? "?").replaceAll("_", " "),
                slot: e.hook || "INTERNAL", price: 0, avail: 0, included: true })),
            });
          }
        }
        return { ok: true };
      }
      case "accessory": {
        const host = s.purchases[Number(op.index)];
        if (!host) return { ok: false, reason: "unknown-host" };
        host.accessories ??= [];
        if (op.remove) {
          const i = host.accessories.findIndex((x) => x.uuid === op.uuid);
          if (i < 0) return { ok: false, reason: "not-fitted" };
          if (host.accessories[i].included) return { ok: false, reason: "factory-fitted" };
          host.accessories.splice(i, 1);
          return { ok: true };
        }
        const mounts = this.data.gearMounts ?? {};
        const accMeta = mounts[op.catalogId] ?? {};
        // capacity, not a bare list: an item may offer several of one mount
        // (rating-3 glasses have three OPTICAL slots)
        const capacity = hookCapacity(host, this.data);
        // pick the slot: the caller's, else the first slot both sides share
        const slot = op.slot
          ?? (accMeta.fits ?? []).find((f) => capacity[f] > 0);
        if (!slot) return { ok: false, reason: "no-compatible-slot" };
        if (!capacity[slot]) return { ok: false, reason: "host-lacks-slot" };
        const usedHere = host.accessories.filter((x) => x.slot === slot).length;
        if (usedHere >= capacity[slot]) return { ok: false, reason: "slot-occupied" };
        const allowed = accMeta.hostSubtypes;
        if (allowed?.length && !allowed.includes(host.subtype)) {
          return { ok: false, reason: "subtype-not-allowed" };
        }
        host.accessories.push({
          uuid: op.uuid, catalogId: op.catalogId, name: op.name,
          price: op.price ?? 0, avail: op.avail ?? 0, slot, included: false,
        });
        return { ok: true };
      }
      case "powerLevel": {
        const pw = s.powers[Number(op.index)];
        if (!pw) return { ok: false, reason: "unknown-power" };
        const meta = this.data.adeptPowers?.[pw.catalogId] ?? {};
        if (!meta.hasLevel) return { ok: false, reason: "power-has-no-levels" };
        const next = (pw.level ?? 1) + (op.delta ?? 1);
        if (next < 1) return { ok: false, reason: "minimum-level-1" };
        if (meta.maxLevel && next > meta.maxLevel) {
          return { ok: false, reason: `max-level-${meta.maxLevel}` };
        }
        pw.level = next;
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
        const meta = op.kind === "power"
          ? (this.data.adeptPowers?.[op.catalogId] ?? {}) : {};
        const existing = list.find((x) => x.uuid === op.uuid);
        if (existing) {
          // A leveled power is bought per level — Improved Reflexes at 1 PP a
          // level is taken up to three times — so taking it again raises the
          // level rather than being rejected as a duplicate.
          if (meta.hasLevel) {
            // per-power cap where the book states one ("The maximum level of
            // this power is 4", core p158); otherwise the PP budget is the limit
            const cap = meta.maxLevel ?? 99;
            if ((existing.level ?? 1) >= cap) return { ok: false, reason: "at-max-level" };
            existing.level = (existing.level ?? 1) + 1;
            return { ok: true, level: existing.level };
          }
          // "multi" powers (Attribute Boost) are separate instances instead
          if (!meta.multi) return { ok: false, reason: "duplicate" };
        }
        list.push({
          uuid: op.uuid, name: op.name, catalogId: op.catalogId ?? null,
          cost: op.cost ?? meta.cost ?? 0,
          level: op.level ?? 1,
          hasLevel: meta.hasLevel ?? false,
        });
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
        const field = op.pool === "karma" ? "karma" : "points";
        const next = (k[field] ?? (field === "points" ? 1 : 0)) + (op.delta ?? 1);
        const floor = field === "points" ? 1 : 0;
        if (next < floor) return { ok: false, reason: `minimum-${floor}` };
        if ((k.points ?? 1) + (k.karma ?? 0) > 6) return { ok: false, reason: "maximum-6" };
        k[field] = next;
        return { ok: true };
      }
      case "cp": {
        // point-buy: move CP into one of the pools, respecting the book caps
        const pool = op.target;
        if (!(pool in s.cp)) return { ok: false, reason: "unknown-pool" };
        const next = (s.cp[pool] ?? 0) + (op.delta ?? 1);
        if (next < 0) return { ok: false, reason: "below-zero" };
        s.cp[pool] = next;
        return { ok: true };
      }
      case "lifemodule": {
        if (op.remove) {
          const i = s.lifepath.findIndex((m) => m.id === op.id);
          if (i < 0) return { ok: false, reason: "not-taken" };
          s.lifepath.splice(i, 1);
          return { ok: true };
        }
        if (s.lifepath.some((m) => m.id === op.id)) return { ok: false, reason: "already-taken" };
        s.lifepath.push({ id: op.id, stage: op.stage ?? "ADULT", choices: op.choices ?? {} });
        return { ok: true };
      }
      case "lifestyle": { s.lifestyleId = op.id; s.lifestyleMonths = op.months ?? 1; return { ok: true }; }
      /* SINs. A runner is SINless by default and holds a real SIN only via the
       * SINner quality (core p273); everything else is forged. Fake SINs and
       * fake licences both run rating 1-6, at 2,500¥ and 200¥ per rating, and
       * every licence is assigned to one SIN whose rating it may not exceed
       * (core p274). */
      case "sin": {
        if (op.remove) {
          const sin = s.sins[Number(op.index)];
          if (!sin) return { ok: false, reason: "unknown-sin" };
          // the real SIN belongs to the quality that granted it
          if (sin.fromQuality) return { ok: false, reason: "granted-by-quality" };
          s.sins.splice(Number(op.index), 1);
          return { ok: true };
        }
        if (op.rename !== undefined) {
          const sin = s.sins[Number(op.index)];
          if (!sin) return { ok: false, reason: "unknown-sin" };
          sin.name = op.rename;
          return { ok: true };
        }
        const kind = op.sinKind === "real" ? "real" : "fake";
        const rating = kind === "real" ? null
          : Math.min(6, Math.max(1, Number(op.rating) || 1));
        s.sins.push({
          id: `sin-${s.sins.length}-${(op.name ?? "").slice(0, 8)}`,
          kind, name: op.name || (kind === "real" ? "Real SIN" : "Fake SIN"),
          rating, licenses: [],
        });
        return { ok: true };
      }
      case "license": {
        const sin = s.sins[Number(op.index)];
        if (!sin) return { ok: false, reason: "unknown-sin" };
        sin.licenses ??= [];
        if (op.remove) {
          if (sin.licenses[Number(op.licenseIndex)] === undefined) {
            return { ok: false, reason: "no-such-licence" };
          }
          sin.licenses.splice(Number(op.licenseIndex), 1);
          return { ok: true };
        }
        let rating = Math.min(6, Math.max(1, Number(op.rating) || 1));
        // core p274: "License ratings cannot exceed the rating of the fake SIN
        // to which they are attached" — clamp rather than reject, so the player
        // gets the licence they asked for at the best rating it can legally be
        if (sin.kind !== "real" && rating > (sin.rating ?? 1)) rating = sin.rating ?? 1;
        sin.licenses.push({ name: op.name || "Fake licence", rating });
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
