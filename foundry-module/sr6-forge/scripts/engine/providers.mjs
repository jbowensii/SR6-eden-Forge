/** Generation-method providers. Each supplies the method-specific budget
 *  sources; the engine core (state, spends, validation, commit) is shared.
 *
 *  Provenance of the numbers:
 *    Priority   — core rulebook p58-65
 *    SumToTen   — Sixth World Companion p27 (same table, letters sum to ten)
 *    PointBuy   — Sixth World Companion p28-29
 *    Karma      — NOT in any English book we own. Sourced from the Commlink6
 *                 1.14.0 implementation (KarmaCharacterGenerator: startKarma
 *                 1000; attributes and skills at the core advancement price of
 *                 5 x new rank; metatype and Magic/Resonance at their data
 *                 karma costs). Flagged unverified in creation-rules.json and
 *                 overridable from the optional-rules screen.
 *    Lifepath   — Sixth World Companion p31-48 (life modules grant the budgets)
 */

export class PriorityProvider {
  static id = "priority";

  constructor(data) {
    this.data = data;                       // chargen-data.json
  }

  /** Letters must be a permutation of A-E (one each). */
  lettersValid(priorities) {
    const letters = Object.values(priorities).filter(Boolean);
    return letters.length === 5 && new Set(letters).size === 5;
  }

  row(letter, type) {
    return this.data.priorities?.[letter]?.[type];
  }

  attributePoints(state) {
    return this.row(state.priorities.ATTRIBUTE, "ATTRIBUTE")?.attributePoints ?? 0;
  }

  skillPoints(state) {
    return this.row(state.priorities.SKILLS, "SKILLS")?.skillPoints ?? 0;
  }

  nuyen(state) {
    return this.row(state.priorities.RESOURCES, "RESOURCES")?.nuyen ?? 0;
  }

  /** Adjustment points depend on BOTH the metatype letter and the chosen
   *  metatype (dwarf 13 at A, human 9 ...). Metavariants inherit their base
   *  metatype's row entry. */
  adjustmentPoints(state) {
    const row = this.row(state.priorities.METATYPE, "METATYPE");
    if (!row) return 0;
    const mid = state.metatypeId;
    if (!mid) return row.adjustmentDefault ?? 0;
    if (mid in row.metatypes) return row.metatypes[mid];
    const parent = this.data.metatypes?.[mid]?.variantOf;
    if (parent && parent in row.metatypes) return row.metatypes[parent];
    return 0;
  }

  /** Metatypes legal at the current METATYPE letter (variants ride on parent). */
  legalMetatypes(state) {
    const row = this.row(state.priorities.METATYPE, "METATYPE");
    if (!row) return [];
    const out = [];
    for (const [mid, mt] of Object.entries(this.data.metatypes ?? {})) {
      const key = mid in row.metatypes ? mid
        : (mt.variantOf && mt.variantOf in row.metatypes ? mt.variantOf : null);
      if (key) out.push({ id: mid, ...mt, adjustmentPoints: row.metatypes[key] });
    }
    return out.sort((a, b) => a.name.localeCompare(b.name));
  }

  /** MOR paths legal at the current MAGIC letter, with the granted rating. */
  legalMors(state) {
    const by = this.row(state.priorities.MAGIC, "MAGIC")?.byMor ?? {};
    return Object.entries(this.data.morTypes ?? {})
      .filter(([id]) => id in by || id === "mundane")
      .map(([id, m]) => ({ id, ...m, rating: by[id] ?? 0 }));
  }

  /** MAG/RES rating granted by the MAGIC priority for the chosen path. */
  magicRating(state) {
    const by = this.row(state.priorities.MAGIC, "MAGIC")?.byMor ?? {};
    return by[state.morId] ?? 0;
  }
}

export class SumToTenProvider extends PriorityProvider {
  static id = "sumtoten";

  /** Any letters allowed as long as their numeric values sum to <= 10
   *  (A=4 .. E=0); elite variant raises the target via rules const. */
  lettersValid(priorities, target = 10) {
    const val = { A: 4, B: 3, C: 2, D: 1, E: 0 };
    const letters = Object.values(priorities).filter(Boolean);
    if (letters.length !== 5) return false;
    return letters.reduce((n, l) => n + val[l], 0) <= target;
  }
}

/* ========================================================================== */
/* Point Buy — Sixth World Companion p28-29. 100 CP, all of which must be     */
/* spent; the 50 customization karma is unchanged.                            */
/* ========================================================================== */

/** Free allotments and CP prices, straight from the book. */
export const POINT_BUY = {
  total: 100,
  awakened: 10,                                  // mundane 0 CP, Awakened/Emerged 10
  free: { attribute: 4, skill: 12, adjustment: 1, nuyen: 10000 },
  max: { attribute: 20, skill: 20, adjustment: 12, nuyen: 440000 },
  cost: { attribute: 2, skill: 2, adjustment: 4, powerPoint: 4, mysticPowerPoint: 8, spell: 2, complexForm: 2 },
  nuyenPerCp: 20000,
  /** Starting MAG/RES once Awakened/Emerged is paid for. */
  startRating: { magician: 1, mysticadept: 1, adept: 1, technomancer: 1, aspectedmagician: 2 },
};

export class PointBuyProvider {
  static id = "pointbuy";

  constructor(data) { this.data = data; }

  /** No priority letters in this method. */
  lettersValid() { return true; }

  #cp(state) {
    return { attribute: 0, skill: 0, adjustment: 0, resources: 0,
      powerPoints: 0, spells: 0, complexForms: 0, ...(state.cp ?? {}) };
  }

  attributePoints(state) { return POINT_BUY.free.attribute + this.#cp(state).attribute; }
  skillPoints(state) { return POINT_BUY.free.skill + this.#cp(state).skill; }
  adjustmentPoints(state) { return POINT_BUY.free.adjustment + this.#cp(state).adjustment; }
  nuyen(state) { return POINT_BUY.free.nuyen + this.#cp(state).resources * POINT_BUY.nuyenPerCp; }

  /** "Your choice of metatype ... does not cost any CP" — everything is legal,
   *  the metatype's karma comes out of the 50 customization karma. */
  legalMetatypes() {
    return Object.entries(this.data.metatypes ?? {})
      .map(([id, mt]) => ({ id, ...mt, adjustmentPoints: POINT_BUY.free.adjustment }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  legalMors() {
    return Object.entries(this.data.morTypes ?? {}).map(([id, m]) => ({
      id, ...m, rating: POINT_BUY.startRating[id] ?? 0,
      cp: id === "mundane" ? 0 : POINT_BUY.awakened,
    }));
  }

  magicRating(state) { return POINT_BUY.startRating[state.morId] ?? 0; }

  /** CP ledger — the wizard renders this and the validator enforces it. */
  characterPoints(state) {
    const cp = this.#cp(state);
    const mor = state.morId && state.morId !== "mundane" ? POINT_BUY.awakened : 0;
    const c = POINT_BUY.cost;
    const ppPrice = state.morId === "mysticadept" ? c.mysticPowerPoint : c.powerPoint;
    const spent = mor
      + cp.attribute * c.attribute
      + cp.skill * c.skill
      + cp.adjustment * c.adjustment
      + cp.resources
      + cp.powerPoints * ppPrice
      + cp.spells * c.spell
      + cp.complexForms * c.complexForm;
    return { max: POINT_BUY.total, spent, left: POINT_BUY.total - spent };
  }
}

/* ========================================================================== */
/* Karma build — Commlink6-sourced, see the provenance note above.            */
/* ========================================================================== */

export class KarmaProvider {
  static id = "karma";

  constructor(data) { this.data = data; }

  lettersValid() { return true; }

  // Everything is bought with karma, so there are no separate point pools.
  attributePoints() { return 0; }
  skillPoints() { return 0; }
  adjustmentPoints() { return 0; }
  nuyen() { return 0; }                    // nuyen comes from karma conversion

  legalMetatypes() {
    return Object.entries(this.data.metatypes ?? {})
      .map(([id, mt]) => ({ id, ...mt, adjustmentPoints: 0 }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  legalMors() {
    return Object.entries(this.data.morTypes ?? {})
      .map(([id, m]) => ({ id, ...m, rating: m.magic || m.resonance ? 1 : 0 }));
  }

  magicRating(state) {
    const mor = this.data.morTypes?.[state.morId] ?? {};
    return mor.magic || mor.resonance ? 1 : 0;
  }

  /** Karma-build replaces the 50-karma allowance with its own pool, and the
   *  Magic/Resonance path is paid for out of it. */
  startingKarma(rules) { return rules.karmaBuild?.startingKarma ?? 1000; }

  morKarma(state) { return this.data.morTypes?.[state.morId]?.karmaCost ?? 0; }
}

/* ========================================================================== */
/* Life modules — Companion p31-48. Budgets are the sum of the chosen         */
/* modules' grants rather than a table lookup.                                */
/* ========================================================================== */

export class LifepathProvider {
  static id = "lifepath";

  constructor(data) { this.data = data; }

  lettersValid() { return true; }

  /** Total of a grant field across every module the character has taken. */
  #sum(state, field) {
    return (state.lifepath ?? []).reduce((n, pick) => {
      const mod = this.data.lifepathModules?.[pick.id];
      return n + (mod?.grants?.[field] ?? 0);
    }, 0);
  }

  attributePoints(state) { return this.#sum(state, "attributePoints"); }
  skillPoints(state) { return this.#sum(state, "skillPoints"); }
  adjustmentPoints(state) { return this.#sum(state, "adjustmentPoints"); }
  nuyen(state) { return this.#sum(state, "nuyen"); }
  contactPointsBonus(state) { return this.#sum(state, "contactPoints"); }

  legalMetatypes() {
    return Object.entries(this.data.metatypes ?? {})
      .map(([id, mt]) => ({ id, ...mt, adjustmentPoints: 0 }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  legalMors() {
    return Object.entries(this.data.morTypes ?? {})
      .map(([id, m]) => ({ id, ...m, rating: m.magic || m.resonance ? 1 : 0 }));
  }

  magicRating(state) {
    const mor = this.data.morTypes?.[state.morId] ?? {};
    return (mor.magic || mor.resonance ? 1 : 0) + this.#sum(state, "magic");
  }

  /** Modules are taken in stages; the Companion requires one of each of the
   *  three opening stages before any adult module. */
  stages() { return ["NATIONALITY", "FORMATIVE", "TEEN", "ADULT", "EVENT"]; }

  modulesForStage(stage) {
    return Object.entries(this.data.lifepathModules ?? {})
      .filter(([, m]) => (m.stage ?? "ADULT") === stage)
      .map(([id, m]) => ({ id, ...m }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }
}

export function makeProvider(method, data) {
  switch (method) {
    case "sumtoten": return new SumToTenProvider(data);
    case "pointbuy": return new PointBuyProvider(data);
    case "karma": return new KarmaProvider(data);
    case "lifepath": return new LifepathProvider(data);
    case "priority":
    default: return new PriorityProvider(data);
  }
}
