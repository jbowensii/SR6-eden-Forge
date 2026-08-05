import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";

import { ChargenEngine, blankState } from "../sr6-forge/scripts/engine/chargen-engine.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(readFileSync(join(here, "..", "..", "export", "chargen-data.json"), "utf8"));
const rules = JSON.parse(readFileSync(join(here, "..", "sr6-forge", "data", "creation-rules.json"), "utf8"));

/** Standard street-sam-ish spread used across tests. */
function engineWith(priorities = { METATYPE: "C", ATTRIBUTE: "A", MAGIC: "E", SKILLS: "B", RESOURCES: "D" }) {
  const e = new ChargenEngine(data, rules);
  for (const [col, letter] of Object.entries(priorities)) e.setPriority(col, letter);
  return e;
}

describe("priority budgets", () => {
  it("grants table values per letter", () => {
    const e = engineWith();
    e.setMetatype("human");
    const b = e.budgets();
    expect(b.attributePoints.max).toBe(24);   // A
    expect(b.skillPoints.max).toBe(24);       // B
    expect(b.nuyen.max).toBe(50000);          // D
    expect(b.karma.max).toBe(50);
  });

  it("adjustment points depend on metatype at the letter", () => {
    const a = engineWith({ METATYPE: "A", ATTRIBUTE: "B", MAGIC: "E", SKILLS: "C", RESOURCES: "D" });
    a.setMetatype("dwarf");
    expect(a.budgets().adjustmentPoints.max).toBe(13);
    const c = engineWith({ METATYPE: "C", ATTRIBUTE: "A", MAGIC: "E", SKILLS: "B", RESOURCES: "D" });
    c.setMetatype("human");
    expect(c.budgets().adjustmentPoints.max).toBe(9);
  });

  it("metavariants inherit their parent's priority slot", () => {
    const e = engineWith({ METATYPE: "A", ATTRIBUTE: "B", MAGIC: "E", SKILLS: "C", RESOURCES: "D" });
    const legal = e.legalMetatypes().map((m) => m.id);
    expect(legal).toContain("gnome");         // dwarf variant
    e.setMetatype("gnome");
    expect(e.budgets().adjustmentPoints.max).toBe(13);
  });

  it("magic rating comes from the MAGIC letter", () => {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A", SKILLS: "C", RESOURCES: "E" });
    e.setMetatype("human");
    e.setMagicPath("magician");
    expect(e.attrRating("mag")).toBe(4);
  });
});

describe("legality", () => {
  it("duplicate letters fail validation", () => {
    const e = engineWith({ METATYPE: "A", ATTRIBUTE: "A", MAGIC: "E", SKILLS: "B", RESOURCES: "C" });
    e.setMetatype("human");
    expect(e.validate().some((i) => i.id === "prio.lettersUnique")).toBe(true);
  });

  it("the metatype allow-list follows the table (SR6: human absent at A, troll fine at E)", () => {
    const a = engineWith({ METATYPE: "A", ATTRIBUTE: "B", MAGIC: "E", SKILLS: "C", RESOURCES: "D" });
    expect(a.legalMetatypes().some((m) => m.id === "human")).toBe(false);
    const e = engineWith({ METATYPE: "E", ATTRIBUTE: "A", MAGIC: "D", SKILLS: "B", RESOURCES: "C" });
    expect(e.legalMetatypes().some((m) => m.id === "troll")).toBe(true);   // 1 adj pt
    expect(e.legalMetatypes().some((m) => m.id === "sasquatch")).toBe(false);
  });

  it("magician is not legal at magic priority E", () => {
    const e = engineWith();      // MAGIC: E
    expect(e.legalMagicPaths().some((m) => m.id === "magician")).toBe(false);
    expect(e.legalMagicPaths().some((m) => m.id === "mundane")).toBe(true);
  });
});

describe("attributes", () => {
  let e;
  beforeEach(() => {
    e = engineWith();
    e.setMetatype("troll");
  });

  it("creation maxima come from the metatype", () => {
    for (let i = 0; i < 9; i++) e.spend({ kind: "attribute", target: "bod" });
    // bod = 1 + 9 = 10 > troll max 9
    expect(e.validate().some((i) => i.id === "attr.creationMax")).toBe(true);
  });

  it("only one attribute may sit at its max", () => {
    for (let i = 0; i < 8; i++) e.spend({ kind: "attribute", target: "bod" });   // 9 = max
    for (let i = 0; i < 8; i++) e.spend({ kind: "attribute", target: "str" });   // 9 = max
    expect(e.validate().some((i) => i.id === "attr.oneAtMax")).toBe(true);
  });

  it("adjustment points on a non-adjusted attribute is illegal", () => {
    e.spend({ kind: "attribute", target: "log", pool: "adjust" });   // troll log max 6 => not adjusted
    expect(e.validate().some((i) => i.id === "attr.adjustTargets")).toBe(true);
  });

  it("adjustment on edge and raised attributes is legal", () => {
    e.spend({ kind: "attribute", target: "edg", pool: "adjust" });
    e.spend({ kind: "attribute", target: "bod", pool: "adjust" });   // troll bod max 9 => adjusted
    expect(e.validate().some((i) => i.id === "attr.adjustTargets")).toBe(false);
  });

  it("overspend is flagged", () => {
    for (let i = 0; i < 25; i++) e.spend({ kind: "attribute", target: "agi" });
    expect(e.validate().some((i) => i.id === "attr.overspent"
      || i.id === "attr.creationMax")).toBe(true);
  });
});

describe("skills", () => {
  it("specialization costs a skill point and requires training", () => {
    const e = engineWith();
    e.setMetatype("human");
    expect(e.spend({ kind: "spec", target: "firearms", spec: "pistols" }).ok).toBe(false);
    e.spend({ kind: "skill", target: "firearms", delta: 3 });
    expect(e.spend({ kind: "spec", target: "firearms", spec: "pistols" }).ok).toBe(true);
    expect(e.budgets().skillPoints.spent).toBe(4);   // 3 points + 1 spec
  });

  it("restricted skills need the right magic path", () => {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A", SKILLS: "C", RESOURCES: "E" });
    e.setMetatype("human");
    e.spend({ kind: "skill", target: "sorcery", delta: 2 });
    expect(e.validate().some((i) => i.id === "skill.restricted")).toBe(true);   // mundane
    e.setMagicPath("magician");
    expect(e.validate().some((i) => i.id === "skill.restricted")).toBe(false);
    e.setMagicPath("technomancer");
    expect(e.validate().some((i) => i.id === "skill.restricted")).toBe(true);   // sorcery not unlocked
  });

  it("cap 6 at creation", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "skill", target: "stealth", delta: 7 });
    expect(e.validate().some((i) => i.id === "skill.capSix")).toBe(true);
  });
});

describe("qualities & karma", () => {
  it("racial qualities are free and survive metatype swap", () => {
    const e = engineWith({ METATYPE: "A", ATTRIBUTE: "B", MAGIC: "E", SKILLS: "C", RESOURCES: "D" });
    e.setMetatype("troll");
    expect(e.state.qualities.some((q) => q.genesisID === "thermographic_vision" && q.free)).toBe(true);
    expect(e.budgets().karma.spent).toBe(0);
    e.setMetatype("elf");
    expect(e.state.qualities.some((q) => q.genesisID === "thermographic_vision")).toBe(false);
  });

  it("negative qualities add karma, positive spend it, caps enforced", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "quality", genesisID: "built_tough", rating: 4 });   // 4x4 = 16 karma
    const b = e.budgets();
    expect(b.karma.spent).toBe(16);
    e.spend({ kind: "quality", genesisID: "ambidextrous" });             // +4 => 20 (cap ok)
    expect(e.validate().some((i) => i.id === "quality.posCap")).toBe(false);
    e.spend({ kind: "quality", genesisID: "analytical_mind" });          // 3 more => over 20
    expect(e.validate().some((i) => i.id === "quality.posCap")).toBe(true);
  });

  it("negative qualities GRANT karma even when chargen-data has no metadata", () => {
    // qualityMeta covers only the books we parsed (273 of 686 pack qualities);
    // the pack row's category/value must win, or negatives get charged as positives.
    const e = engineWith();
    e.setMetatype("human");
    const before = e.budgets().karma;
    e.spend({ kind: "quality", genesisID: "not_in_chargen_data_xyz",
      name: "Made-up Flaw", positive: false, karma: 20 });
    const after = e.budgets().karma;
    expect(after.max).toBe(before.max + 20);      // budget grew
    expect(after.spent).toBe(before.spent);        // nothing was charged
    expect(after.left).toBe(before.left + 20);
  });

  it("positive qualities still cost karma when unknown to chargen-data", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "quality", genesisID: "unknown_boon", name: "Boon",
      positive: true, karma: 7 });
    expect(e.budgets().karma.spent).toBe(7);
  });

  it("karma-to-nuyen conversion is capped", () => {
    const e = engineWith();
    e.setMetatype("human");
    for (let i = 0; i < 10; i++) expect(e.spend({ kind: "karma2nuyen" }).ok).toBe(true);
    expect(e.spend({ kind: "karma2nuyen" }).ok).toBe(false);
    expect(e.budgets().nuyen.max).toBe(50000 + 10 * 2000);
  });
});

describe("purchases", () => {
  it("availability cap and essence floor", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "purchase", uuid: "x", name: "MilSpec Toy", price: 1000, avail: 8 });
    expect(e.validate().some((i) => i.id === "gear.availCap")).toBe(true);
    e.spend({ kind: "purchase", uuid: "x", remove: true });
    e.spend({ kind: "purchase", uuid: "w1", name: "Ware", price: 1000, essence: 6 });
    expect(e.validate().some((i) => i.id === "essence.positive")).toBe(true);
  });

  it("troll surcharge applies to nuyen spent", () => {
    const e = engineWith({ METATYPE: "A", ATTRIBUTE: "B", MAGIC: "E", SKILLS: "C", RESOURCES: "D" });
    e.setMetatype("troll");
    e.spend({ kind: "purchase", uuid: "g", name: "Gear", price: 1000 });
    expect(e.budgets().nuyen.spent).toBe(1100);   // EVERYTHING +10%
  });

  it("spells forbidden for mundane", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.state.spells.push({ uuid: "s1", name: "Zap" });
    expect(e.validate().some((i) => i.id === "magic.spellsAllowed")).toBe(true);
  });
});

describe("commitPlan", () => {
  it("emits raw-input eden paths only", () => {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A", SKILLS: "C", RESOURCES: "E" });
    e.setMetatype("human");
    e.setMagicPath("magician");
    e.state.name = "Testrunner";
    e.spend({ kind: "attribute", target: "bod", delta: 3 });
    e.spend({ kind: "skill", target: "sorcery", delta: 4 });
    e.spend({ kind: "spec", target: "sorcery", spec: "spellcasting" });
    e.spend({ kind: "contact", name: "Fixer Jane", connection: 2, loyalty: 1 });
    e.spend({ kind: "lifestyle", id: "low" });
    e.spend({ kind: "knowledge", name: "English", type: "language", native: true });

    const plan = e.commitPlan();
    const sys = plan.actorData.system;
    expect(plan.actorData.type).toBe("Player");
    expect(sys.attributes.bod.base).toBe(4);
    expect(sys.attributes.mag.base).toBe(4);          // MAGIC A magician
    expect(sys.attributes.res).toBeUndefined();
    expect(sys.skills.sorcery).toEqual({ points: 4, specialization: "spellcasting" });
    expect(sys.mortype).toBe("magician");
    expect(sys.metatype).toBe("Human");
    // derived values must NOT be written
    expect(sys.physical).toBeUndefined();
    expect(sys.attributes.bod.pool).toBeUndefined();
    expect(sys.essence).toBeUndefined();
    // synthetic items
    const types = plan.syntheticItems.map((i) => i.type);
    expect(types).toContain("contact");
    expect(types).toContain("lifestyle");
    expect(types).toContain("skill");                 // native language
    const lang = plan.syntheticItems.find((i) => i.type === "skill");
    expect(lang.system.points).toBe(4);
    // provenance
    expect(plan.actorData.flags["sr6-forge"].metatypeId).toBe("human");
    expect(plan.actorData.flags["sr6-forge"].ledger).toHaveLength(1);
  });

  it("draft roundtrip preserves state", () => {
    const e = engineWith();
    e.setMetatype("dwarf");
    e.spend({ kind: "skill", target: "firearms", delta: 5 });
    const draft = e.toDraft();
    const e2 = ChargenEngine.fromDraft(draft, data, rules);
    expect(e2.budgets().skillPoints.spent).toBe(5);
    expect(e2.state.metatypeId).toBe("dwarf");
  });
});
