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

/** Companion p32-33: the three opening modules are fixed, not chosen, and
 *  they grant a flat opening budget before any adult module is picked. */
export const LIFEPATH_OPENING = [
  { id: "born_this_way", name: "Born This Way",
    text: "Metatype, metavariant and metagenetic qualities; mundane, Awakened "
      + "or Emerged; a nationality; one language at rank 4 (Native); and one or "
      + "two qualities (if two, one positive and one negative).",
    grants: {} },
  { id: "growing_up", name: "Growing Up: Early Childhood and Adolescence",
    text: "Four of Athletics, Close Combat, Con, Electronics, Influence, "
      + "Outdoors, Perception and Stealth, each at rank 2; one or two "
      + "qualities; the [Area] Knowledge skill for where you grew up.",
    grants: { skillPoints: 8 } },                 // four skills at rank 2
  { id: "coming_of_age", name: "Coming of Age: Early Adult",
    text: "One skill at rank 4 (rank 6 if already chosen); your best attribute "
      + "+5; one or two qualities; and one contact with four points split "
      + "between Connection and Loyalty.",
    grants: { skillPoints: 4, attributePoints: 5, nuyen: 25000, contactPoints: 4 } },
];

/** Companion p33: "You must take exactly eight life modules." */
export const LIFEPATH_ADULT_COUNT = 8;

export class LifepathProvider {
  static id = "lifepath";

  constructor(data) { this.data = data; }

  lettersValid() { return true; }

  /** Total of a grant field: the three fixed opening modules plus the picks. */
  #sum(state, field) {
    const opening = LIFEPATH_OPENING.reduce((n, m) => n + (m.grants[field] ?? 0), 0);
    return (state.lifepath ?? []).reduce((n, pick) => {
      const mod = this.data.lifepathModules?.[pick.id];
      let v = mod?.grants?.[field] ?? 0;
      // a "mixed" choice ("+1 to Edge, Sorcery, or Enchanting") is only worth a
      // point once the player has said which pool it lands in
      for (const [i, choice] of (mod?.choices ?? []).entries()) {
        if (choice.kind !== "mixed") continue;
        const picked = pick.choices?.[i];
        if (!picked) continue;
        if (picked.startsWith("nuyen:")) {          // "or +25,000 nuyen"
          if (field === "nuyen") v += Number(picked.slice(6)) || 0;
        } else if (ATTR_IDS.has(picked)) {
          if (field === "attributePoints") v += choice.points ?? 1;
        } else if (field === "skillPoints") {
          v += choice.points ?? 1;
        }
      }
      return n + v;
    }, opening);
  }

  attributePoints(state) { return this.#sum(state, "attributePoints"); }
  skillPoints(state) { return this.#sum(state, "skillPoints"); }
  adjustmentPoints(state) { return this.#sum(state, "adjustmentPoints"); }
  nuyen(state) { return this.#sum(state, "nuyen"); }

  /** Companion p33: "your Charisma does not provide you with contact points,
   *  and your contacts' ratings are not limited by your Charisma attribute."
   *  Points come from the modules alone and no rating may exceed 8. */
  contactPoints(state) {
    const max = this.#sum(state, "contactPoints");
    const spent = state.contacts.reduce((n, c) => n + (c.connection ?? 1) + (c.loyalty ?? 1), 0);
    return { max, spent, left: max - spent, ratingCap: 8 };
  }

  /** Companion p33: knowledge and language skills come from the modules, so
   *  "you do not gain additional ones based on your Logic attribute". */
  knowledgePoints(state) {
    const max = (state.lifepath ?? []).reduce((n, pick) =>
      n + (this.data.lifepathModules?.[pick.id]?.knowledgeSkills ?? 0), 0);
    const spent = state.knowledge.filter((k) => !k.native)
      .reduce((n, k) => n + (k.points ?? 1), 0);
    return { max, spent, left: max - spent };
  }

  legalMetatypes() {
    return Object.entries(this.data.metatypes ?? {})
      .map(([id, mt]) => ({ id, ...mt, adjustmentPoints: 0 }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  legalMors() {
    return Object.entries(this.data.morTypes ?? {})
      .map(([id, m]) => ({ id, ...m, rating: m.magic || m.resonance ? 1 : 0 }));
  }

  /** Born This Way: Emerged start at Resonance 1, full magicians / adepts /
   *  mystic adepts at Magic 1, aspected magicians at Magic 2. */
  magicRating(state) {
    const mor = this.data.morTypes?.[state.morId] ?? {};
    if (!mor.magic && !mor.resonance) return 0;
    return state.morId === "aspectedmagician" ? 2 : 1;
  }

  /** Modules a character of this path may still take. */
  available(state) {
    const taken = new Set((state.lifepath ?? []).map((m) => m.id));
    const mor = this.data.morTypes?.[state.morId] ?? {};
    return Object.entries(this.data.lifepathModules ?? {})
      .map(([id, m]) => ({ id, ...m }))
      .filter((m) => {
        if (!m.requires) return true;
        if (m.requires === "emerged") return !!mor.resonance;
        if (m.requires === "awakened") return !!mor.magic;
        if (m.requires === "adept") return !!mor.powers;
        if (m.requires === "magician") return !!mor.spells;
        return true;
      })
      .map((m) => ({ ...m, taken: taken.has(m.id) }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  opening() { return LIFEPATH_OPENING; }
}

const ATTR_IDS = new Set([...CORE_ATTR_IDS(), "edg", "mag", "res"]);
function CORE_ATTR_IDS() {
  return ["bod", "agi", "rea", "str", "wil", "log", "int", "cha"];
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
