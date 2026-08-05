/** Generation-method providers. Each supplies the method-specific budget
 *  sources; the engine core (state, spends, validation, commit) is shared.
 *  Priority (core book) ships first; SumToTen reuses the same table with a
 *  different letter constraint; PointBuy/Karma/Lifepath land in Phase 8. */

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

export function makeProvider(method, data) {
  switch (method) {
    case "sumtoten": return new SumToTenProvider(data);
    case "priority":
    default: return new PriorityProvider(data);
  }
}
