import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";

import { ChargenEngine, blankState } from "../sr6-forge/scripts/engine/chargen-engine.mjs";
import { LIFEPATH_OPENING } from "../sr6-forge/scripts/engine/providers.mjs";

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

  it("negative qualities add karma and positive ones spend it", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "quality", genesisID: "built_tough", rating: 4 });   // 4x4 = 16 karma
    expect(e.budgets().karma.spent).toBe(16);
  });

  // Core p67: "You can't select more than six total qualities at character
  // creation, and the net bonus Karma cannot be more than 20."
  it("the quality cap is on NET bonus karma, not each side separately", () => {
    const e = engineWith();
    e.setMetatype("human");
    const neg = (id, k) => e.spend({ kind: "quality", genesisID: id, name: id, positive: false, karma: k });
    const pos = (id, k) => e.spend({ kind: "quality", genesisID: id, name: id, positive: true, karma: k });
    // John's example: 30 gained, 10 spent -> net +20 = legal
    pos("mentor_spirit", 10);
    neg("honorbound", 10); neg("sinner", 8); neg("prejudiced", 8); neg("dependents", 4);
    const b = e.budgets();
    expect(b.karma.max).toBe(50 + 30);
    expect(b.karma.spent).toBe(10);
    expect(e.validate().some((i) => i.id === "quality.netBonusCap")).toBe(false);
    // one more point of net bonus breaks it
    neg("extra_flaw", 1);
    expect(e.validate().some((i) => i.id === "quality.netBonusCap")).toBe(true);
  });

  it("no more than six selected qualities (racial ones are free)", () => {
    const e = engineWith({ METATYPE: "A", ATTRIBUTE: "B", MAGIC: "E", SKILLS: "C", RESOURCES: "D" });
    e.setMetatype("troll");                       // brings free racial qualities
    for (let i = 0; i < 6; i++) {
      e.spend({ kind: "quality", genesisID: `q${i}`, name: `q${i}`, positive: false, karma: 1 });
    }
    expect(e.validate().some((i) => i.id === "quality.maxCount")).toBe(false);
    e.spend({ kind: "quality", genesisID: "q7", name: "q7", positive: false, karma: 1 });
    expect(e.validate().some((i) => i.id === "quality.maxCount")).toBe(true);
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

describe("contact points (core p68: Charisma x 6, neither rating over Charisma)", () => {
  /** John's test character: CHA 2 -> 12 points, three contacts at 2/2 = 12. */
  function chaTwo() {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "attribute", target: "cha", delta: 1 });   // 1 base + 1 = 2
    return e;
  }

  it("grants Charisma x 6 points", () => {
    const e = chaTwo();
    expect(e.attrRating("cha")).toBe(2);
    expect(e.budgets().contactPoints.max).toBe(12);
    expect(e.budgets().contactPoints.ratingCap).toBe(2);
  });

  it("three 2/2 contacts spend the budget exactly and validate", () => {
    const e = chaTwo();
    for (const name of ["Fixer", "Doc", "Decker"]) {
      e.spend({ kind: "contact", name, connection: 2, loyalty: 2 });
    }
    const b = e.budgets().contactPoints;
    expect(b.spent).toBe(12);
    expect(b.left).toBe(0);
    const ids = e.validate().map((i) => i.id);
    expect(ids).not.toContain("contact.budget");
    expect(ids).not.toContain("contact.ratingCap");
  });

  it("flags a rating above Charisma", () => {
    const e = chaTwo();
    e.spend({ kind: "contact", name: "Mr. Johnson", connection: 3, loyalty: 1 });
    expect(e.validate().map((i) => i.id)).toContain("contact.ratingCap");
  });
});

describe("karma-bought ranks", () => {
  it("charges 5 x new rating for attributes and 5 x new rank for skills", () => {
    const e = engineWith();
    e.setMetatype("human");
    const before = e.budgets().karma.spent;
    e.spend({ kind: "attribute", target: "log", pool: "karma", delta: 1 });   // 1 -> 2
    expect(e.budgets().karma.spent - before).toBe(10);
    e.spend({ kind: "skill", target: "firearms", pool: "karma", delta: 1 });  // 0 -> 1
    expect(e.budgets().karma.spent - before).toBe(15);
  });

  it("karma ranks count toward the rank-6 creation cap and reach the actor", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "skill", target: "firearms", delta: 4 });
    e.spend({ kind: "skill", target: "firearms", pool: "karma", delta: 2 });
    expect(e.skillRank("firearms")).toBe(6);
    expect(e.validate().map((i) => i.id)).not.toContain("skill.capSix");
    expect(e.commitPlan().actorData.system.skills.firearms.points).toBe(6);
    e.spend({ kind: "skill", target: "firearms", pool: "karma", delta: 1 });
    expect(e.validate().map((i) => i.id)).toContain("skill.capSix");
  });

  it("karma ranks alone still allow a specialization", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "skill", target: "firearms", pool: "karma", delta: 1 });
    expect(e.spend({ kind: "spec", target: "firearms", spec: "pistols" }).ok).toBe(true);
  });
});

describe("optional-rule overrides", () => {
  it("world overrides beat the ruleset interpretation", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.state.purchases.push({ uuid: "x", name: "Ares Alpha", price: 0, avail: 12, qty: 1 });
    expect(e.validate().map((i) => i.id)).toContain("gear.availCap");
    e.setOptionalRules({ CHARGEN_MAX_AVAILABILITY: 12 });
    expect(e.validate().map((i) => i.id)).not.toContain("gear.availCap");
  });
});

describe("Point Buy (Companion p28-29)", () => {
  function pb(morId = "mundane") {
    const e = new ChargenEngine(data, rules, { state: blankState("pointbuy") });
    e.setMethod("pointbuy");
    e.setMetatype("human");
    e.setMagicPath(morId);
    return e;
  }

  it("starts with the free allotments and 100 CP", () => {
    const e = pb();
    const b = e.budgets();
    expect(b.characterPoints.max).toBe(100);
    expect(b.characterPoints.spent).toBe(0);
    expect(b.attributePoints.max).toBe(4);
    expect(b.skillPoints.max).toBe(12);
    expect(b.adjustmentPoints.max).toBe(1);
    expect(b.nuyen.max).toBe(10000);
  });

  it("prices each pool as the book does", () => {
    const e = pb();
    e.spend({ kind: "cp", target: "attribute", delta: 20 });   // 20 x 2 = 40 CP
    e.spend({ kind: "cp", target: "skill", delta: 20 });       // 20 x 2 = 40 CP
    e.spend({ kind: "cp", target: "adjustment", delta: 5 });   //  5 x 4 = 20 CP
    const b = e.budgets();
    expect(b.characterPoints.spent).toBe(100);
    expect(b.characterPoints.left).toBe(0);
    expect(b.attributePoints.max).toBe(24);                    // 4 free + 20
    expect(b.skillPoints.max).toBe(32);                        // 12 free + 20
    expect(b.adjustmentPoints.max).toBe(6);                    // 1 free + 5
    expect(e.validate().map((i) => i.id)).not.toContain("pointbuy.unspent");
  });

  it("charges 10 CP for Awakened and starts an aspected magician at Magic 2", () => {
    const e = pb("aspectedmagician");
    expect(e.budgets().characterPoints.spent).toBe(10);
    expect(e.attrRating("mag")).toBe(2);
    const t = pb("technomancer");
    expect(t.attrRating("res")).toBe(1);
  });

  it("converts resource CP at 20,000 nuyen each", () => {
    const e = pb();
    e.spend({ kind: "cp", target: "resources", delta: 22 });    // the 440,000 cap
    expect(e.budgets().nuyen.max).toBe(450000);
    expect(e.budgets().characterPoints.spent).toBe(22);
    e.spend({ kind: "cp", target: "resources", delta: 1 });
    expect(e.validate().map((i) => i.id)).toContain("pointbuy.poolCap");
  });

  it("requires every CP to be spent and flags overspending", () => {
    const e = pb();
    expect(e.validate().map((i) => i.id)).toContain("pointbuy.unspent");
    e.spend({ kind: "cp", target: "attribute", delta: 20 });
    e.spend({ kind: "cp", target: "skill", delta: 20 });
    e.spend({ kind: "cp", target: "adjustment", delta: 12 });   // 40+40+48 = 128
    expect(e.validate().map((i) => i.id)).toContain("pointbuy.overspent");
  });

  it("allows only one specialization", () => {
    const e = pb();
    e.spend({ kind: "skill", target: "firearms", delta: 2 });
    e.spend({ kind: "skill", target: "stealth", delta: 2 });
    e.spend({ kind: "spec", target: "firearms", spec: "pistols" });
    expect(e.validate().map((i) => i.id)).not.toContain("pointbuy.oneSpecialization");
    e.spend({ kind: "spec", target: "stealth", spec: "sneaking" });
    expect(e.validate().map((i) => i.id)).toContain("pointbuy.oneSpecialization");
  });
});

describe("Karma build (Commlink6-sourced)", () => {
  function kb() {
    const e = new ChargenEngine(data, rules, { state: blankState("karma") });
    e.setMethod("karma");
    return e;
  }

  it("opens a 1000-karma pool and no point pools", () => {
    const e = kb();
    const b = e.budgets();
    expect(b.karma.max).toBe(1000);
    expect(b.attributePoints.max).toBe(0);
    expect(b.skillPoints.max).toBe(0);
    expect(b.nuyen.max).toBe(0);
  });

  it("charges the metatype and the Magic/Resonance path out of the pool", () => {
    const e = kb();
    e.setMetatype("troll");
    e.setMagicPath("magician");
    const meta = data.metatypes.troll.karma ?? 0;
    const mor = data.morTypes.magician.karmaCost ?? 0;
    expect(mor).toBe(60);
    expect(e.budgets().karma.spent).toBe(meta + mor);
  });
});

describe("Life path (Companion p31-48)", () => {
  function lp() {
    const e = new ChargenEngine(data, rules, { state: blankState("lifepath") });
    e.setMethod("lifepath");
    e.setMetatype("human");
    return e;
  }
  // opening totals, before any adult module is taken
  const OPEN = LIFEPATH_OPENING.reduce((acc, m) => {
    for (const [k, v] of Object.entries(m.grants)) acc[k] = (acc[k] ?? 0) + v;
    return acc;
  }, {});

  it("starts from the three fixed opening modules", () => {
    const b = lp().budgets();
    expect(b.skillPoints.max).toBe(OPEN.skillPoints);       // 8 + 4
    expect(b.attributePoints.max).toBe(OPEN.attributePoints);
    expect(b.nuyen.max).toBe(OPEN.nuyen);
    expect(b.contactPoints.max).toBe(OPEN.contactPoints);
  });

  it("adds each module's grants on top", () => {
    const e = lp();
    e.spend({ kind: "lifemodule", id: "artifact_hunter" });
    const g = data.lifepathModules.artifact_hunter.grants;
    const b = e.budgets();
    expect(b.attributePoints.max).toBe(OPEN.attributePoints + g.attributePoints);
    expect(b.nuyen.max).toBe(OPEN.nuyen + g.nuyen);
  });

  it("takes contact points from modules only, capped at 8, not Charisma", () => {
    const e = lp();
    e.spend({ kind: "attribute", target: "cha", delta: 4 });   // Charisma 5
    const b = e.budgets();
    expect(b.contactPoints.max).toBe(OPEN.contactPoints);      // NOT cha x 6
    expect(b.contactPoints.ratingCap).toBe(8);
  });

  it("takes knowledge skills from modules, not Logic", () => {
    const e = lp();
    e.spend({ kind: "attribute", target: "log", delta: 4 });
    expect(e.budgets().knowledgePoints.max).toBe(0);
    e.spend({ kind: "lifemodule", id: "artifact_hunter" });
    expect(e.budgets().knowledgePoints.max)
      .toBe(data.lifepathModules.artifact_hunter.knowledgeSkills);
  });

  it("requires exactly eight adult modules", () => {
    const e = lp();
    const ids = Object.keys(data.lifepathModules)
      .filter((id) => !data.lifepathModules[id].requires).slice(0, 8);
    expect(e.validate().map((i) => i.id)).toContain("lifepath.moduleCount");
    for (const id of ids) e.spend({ kind: "lifemodule", id });
    expect(e.state.lifepath).toHaveLength(8);
    expect(e.validate().map((i) => i.id)).not.toContain("lifepath.moduleCount");
  });

  it("refuses to take the same module twice", () => {
    const e = lp();
    e.spend({ kind: "lifemodule", id: "artifact_hunter" });
    expect(e.spend({ kind: "lifemodule", id: "artifact_hunter" }).ok).toBe(false);
  });

  it("hides Awakened-only modules from a mundane character", () => {
    const e = lp();
    const ids = e.provider.available(e.state).map((m) => m.id);
    expect(ids).not.toContain("alchemist");
    e.setMagicPath("magician");
    expect(e.provider.available(e.state).map((m) => m.id)).toContain("alchemist");
  });

  it("holds a mixed choice's point back until the player assigns it", () => {
    const e = lp();
    const id = Object.keys(data.lifepathModules)
      .find((k) => (data.lifepathModules[k].choices ?? []).some((c) => c.kind === "mixed")
        && !data.lifepathModules[k].requires);
    expect(id).toBeTruthy();
    const mod = data.lifepathModules[id];
    const idx = mod.choices.findIndex((c) => c.kind === "mixed");
    const attrOption = mod.choices[idx].options.find((o) =>
      ["bod", "agi", "rea", "str", "wil", "log", "int", "cha", "edg", "mag", "res"].includes(o));

    e.spend({ kind: "lifemodule", id });
    const before = e.budgets();
    expect(e.validate().map((i) => i.id)).toContain("lifepath.mixedChoices");

    if (attrOption) {
      e.state.lifepath[0].choices = { [idx]: attrOption };
      expect(e.budgets().attributePoints.max)
        .toBe(before.attributePoints.max + (mod.choices[idx].points ?? 1));
    }
  });
});
