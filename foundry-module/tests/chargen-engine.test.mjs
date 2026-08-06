import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";

import { ChargenEngine, blankState, migrateState } from "../sr6-forge/scripts/engine/chargen-engine.mjs";
import { LIFEPATH_OPENING } from "../sr6-forge/scripts/engine/providers.mjs";
import { augmentBonus, augmentedRating, ratedValues, qualityKarma } from "../sr6-forge/scripts/engine/budgets.mjs";

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
    expect(e.state.qualities.some((q) => q.catalogId === "thermographic_vision" && q.free)).toBe(true);
    expect(e.budgets().karma.spent).toBe(0);
    e.setMetatype("elf");
    expect(e.state.qualities.some((q) => q.catalogId === "thermographic_vision")).toBe(false);
  });

  it("negative qualities add karma and positive ones spend it", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "quality", catalogId: "built_tough", rating: 4 });   // 4x4 = 16 karma
    expect(e.budgets().karma.spent).toBe(16);
  });

  // Core p67: "You can't select more than six total qualities at character
  // creation, and the net bonus Karma cannot be more than 20."
  it("the quality cap is on NET bonus karma, not each side separately", () => {
    const e = engineWith();
    e.setMetatype("human");
    const neg = (id, k) => e.spend({ kind: "quality", catalogId: id, name: id, positive: false, karma: k });
    const pos = (id, k) => e.spend({ kind: "quality", catalogId: id, name: id, positive: true, karma: k });
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
      e.spend({ kind: "quality", catalogId: `q${i}`, name: `q${i}`, positive: false, karma: 1 });
    }
    expect(e.validate().some((i) => i.id === "quality.maxCount")).toBe(false);
    e.spend({ kind: "quality", catalogId: "q7", name: "q7", positive: false, karma: 1 });
    expect(e.validate().some((i) => i.id === "quality.maxCount")).toBe(true);
  });

  it("negative qualities GRANT karma even when chargen-data has no metadata", () => {
    // qualityMeta covers only the books we parsed (273 of 686 pack qualities);
    // the pack row's category/value must win, or negatives get charged as positives.
    const e = engineWith();
    e.setMetatype("human");
    const before = e.budgets().karma;
    e.spend({ kind: "quality", catalogId: "not_in_chargen_data_xyz",
      name: "Made-up Flaw", positive: false, karma: 20 });
    const after = e.budgets().karma;
    expect(after.max).toBe(before.max + 20);      // budget grew
    expect(after.spent).toBe(before.spent);        // nothing was charged
    expect(after.left).toBe(before.left + 20);
  });

  it("positive qualities still cost karma when unknown to chargen-data", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "quality", catalogId: "unknown_boon", name: "Boon",
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
    e.setOptionalRules({ maxAvailability: 12 });
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

describe("magic at creation (core p66-67)", () => {
  /** MAGIC priority A: full 4, aspected 5, mystic adept 4, adept 4, techno 4. */
  function mage(morId, magicLetter = "A") {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "B", MAGIC: magicLetter,
      SKILLS: "C", RESOURCES: "E" });
    e.setMetatype("human");
    e.setMagicPath(morId);
    return e;
  }

  it("gives a full magician priority Magic x 2 spells for free", () => {
    const e = mage("magician");
    const priority = e.provider.magicRating(e.state);
    expect(e.budgets().spellSlots.max).toBe(priority * 2);
    for (let i = 0; i < priority * 2; i++) {
      e.spend({ kind: "spell", uuid: `s${i}`, name: `Spell ${i}` });
    }
    expect(e.budgets().karma.spent).toBe(0);            // all free
    expect(e.budgets().spellSlots.left).toBe(0);
  });

  it("charges 5 karma per spell beyond the free allotment", () => {
    const e = mage("magician");
    const free = e.budgets().spellSlots.max;
    for (let i = 0; i <= free; i++) {
      e.spend({ kind: "spell", uuid: `s${i}`, name: `Spell ${i}` });
    }
    expect(e.budgets().karma.spent).toBe(rules.spellsAtCreation.karmaCost);
  });

  it("counts rituals against the same allotment as spells", () => {
    const e = mage("magician");
    const free = e.budgets().spellSlots.max;
    for (let i = 0; i < free; i++) e.spend({ kind: "spell", uuid: `s${i}`, name: `S${i}` });
    expect(e.budgets().karma.spent).toBe(0);
    e.spend({ kind: "ritual", uuid: "r1", name: "A ritual" });
    expect(e.budgets().karma.spent).toBe(rules.spellsAtCreation.karmaCost);
  });

  it("uses the PRIORITY Magic, not the adjusted rating", () => {
    const e = mage("magician");
    const priority = e.provider.magicRating(e.state);
    e.spend({ kind: "attribute", target: "mag", pool: "adjust", delta: 2 });
    expect(e.attrRating("mag")).toBe(priority + 2);      // the attribute rose
    expect(e.budgets().spellSlots.max).toBe(priority * 2); // the allotment did not
  });

  it("gives an adept power points equal to priority Magic, free", () => {
    const e = mage("adept");
    const priority = e.provider.magicRating(e.state);
    expect(e.budgets().powerPoints.max).toBe(priority);
    expect(e.budgets().karma.spent).toBe(0);
  });

  it("splits a mystic adept's Magic between power points and spells", () => {
    const e = mage("mysticadept");
    const priority = e.provider.magicRating(e.state);
    expect(e.budgets().spellSlots.max).toBe(priority * 2);
    e.spend({ kind: "powerpoints", delta: 1 });
    expect(e.budgets().powerPoints.max).toBe(1);
    expect(e.budgets().spellSlots.max).toBe((priority - 1) * 2);
    expect(e.budgets().karma.spent).toBe(0);            // a split, not a purchase
  });

  it("caps a mystic adept's power points at its priority Magic", () => {
    const e = mage("mysticadept");
    const priority = e.provider.magicRating(e.state);
    for (let i = 0; i < priority; i++) e.spend({ kind: "powerpoints", delta: 1 });
    expect(e.budgets().spellSlots.max).toBe(0);
    expect(e.validate().map((i) => i.id)).not.toContain("adept.ppCap");
    e.spend({ kind: "powerpoints", delta: 1 });
    expect(e.validate().map((i) => i.id)).toContain("adept.ppCap");
  });

  it("gives a technomancer Resonance x 2 complex forms for free", () => {
    const e = mage("technomancer");
    const priority = e.provider.magicRating(e.state);
    expect(e.budgets().spellSlots.max).toBe(priority * 2);
    for (let i = 0; i < priority * 2; i++) {
      e.spend({ kind: "complexform", uuid: `c${i}`, name: `Form ${i}` });
    }
    expect(e.budgets().karma.spent).toBe(0);
  });
});

describe("quality karma signs (core p67)", () => {
  // A positive quality COSTS karma; a negative quality GIVES karma. The wizard
  // therefore shows a positive quality as "−n" and a negative one as "+n".
  function withQualities(...list) {
    const e = engineWith();
    e.setMetatype("human");
    for (const [name, karma, positive] of list) {
      e.spend({ kind: "quality", catalogId: name, name, karma, positive });
    }
    return e;
  }

  it("charges for positive qualities and pays for negative ones", () => {
    const base = engineWith();
    base.setMetatype("human");
    const start = base.budgets().karma.max;

    const pos = withQualities(["catlike", 12, true]);
    expect(pos.budgets().karma.spent).toBe(12);       // costs
    expect(pos.budgets().karma.max).toBe(start);      // pool unchanged

    const neg = withQualities(["sinner", 8, false]);
    expect(neg.budgets().karma.spent).toBe(0);        // costs nothing
    expect(neg.budgets().karma.max).toBe(start + 8);  // enlarges the pool
  });

  it("reproduces John's example character exactly", () => {
    // mentor spirit −10 (positive), honorbound +10, SINner +8,
    // prejudice +8, dependants +4  ->  net bonus karma +20, which is legal
    const e = withQualities(
      ["mentor_spirit", 10, true],
      ["honorbound", 10, false],
      ["sinner", 8, false],
      ["prejudice", 8, false],
      ["dependents", 4, false],
    );
    const b = e.budgets();
    expect(b.karma.spent).toBe(10);                   // the one positive
    expect(b.karma.max).toBe(50 + 30);                // 30 karma of negatives
    const ids = e.validate().map((i) => i.id);
    expect(ids).not.toContain("quality.netBonusCap"); // net +20 is exactly the cap
    expect(ids).not.toContain("quality.maxCount");    // five qualities, cap is six
  });

  it("flags a net bonus above 20", () => {
    const e = withQualities(
      ["a", 10, false], ["b", 8, false], ["c", 8, false],
    );                                                // net +26, no positives
    expect(e.validate().map((i) => i.id)).toContain("quality.netBonusCap");
  });

  it("prices a mentor spirit as the positive quality it is", () => {
    // the packs categorise individual spirits as "negative" with no value;
    // chargen-data now supplies the parent quality's 10 karma / positive
    const meta = data.qualityMeta.bear;
    expect(meta.karma).toBe(10);
    expect(meta.positive).toBe(true);
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "quality", catalogId: "bear", name: "Bear" });
    expect(e.budgets().karma.spent).toBe(10);         // costs, never pays
  });
});

describe("accessory mounting", () => {
  // Commlink6's two-sided contract: the host declares HOOK slots, the
  // accessory declares the slots it fits plus which host subtypes accept it.
  function armed() {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "purchase", uuid: "Item.pred", name: "Ares Predator VI",
      catalogId: "ares_predator_vi", subtype: "PISTOLS_HEAVY", price: 750, avail: 2 });
    return e;
  }
  const fit = (e, over = {}) => e.spend({
    kind: "accessory", index: 0, uuid: "Item.sil", catalogId: "silencer",
    name: "Silencer", price: 500, avail: 4, ...over,
  });

  it("knows the Predator's mount slots", () => {
    expect(data.gearMounts.ares_predator_vi.hooks).toEqual(["BARREL", "TOP"]);
    expect(data.gearMounts.silencer.fits).toEqual(["BARREL"]);
  });

  it("fits a silencer to the barrel and charges for it", () => {
    const e = armed();
    const before = e.budgets().nuyen.spent;
    expect(fit(e).ok).toBe(true);
    const acc = e.state.purchases[0].accessories.find((a) => a.catalogId === "silencer");
    expect(acc.slot).toBe("BARREL");
    expect(e.budgets().nuyen.spent).toBe(before + 500);
  });

  it("refuses a second accessory in an occupied slot", () => {
    const e = armed();
    fit(e);
    const again = fit(e, { uuid: "Item.sil2" });
    expect(again.ok).toBe(false);
    expect(again.reason).toBe("slot-occupied");
  });

  it("refuses a host whose subtype the accessory does not allow", () => {
    const e = engineWith();
    e.setMetatype("human");
    // a sword has no business taking a silencer
    e.spend({ kind: "purchase", uuid: "Item.sword", name: "Katana",
      catalogId: "katana", subtype: "BLADES", price: 350, avail: 4 });
    const r = fit(e);
    expect(r.ok).toBe(false);
    expect(["no-compatible-slot", "host-lacks-slot", "subtype-not-allowed"])
      .toContain(r.reason);
  });

  it("carries factory-fitted accessories and will not let them be removed", () => {
    const e = armed();
    const fitted = e.state.purchases[0].accessories;
    // the Predator ships with a smartgun system and variable ammo
    expect(fitted.some((a) => a.catalogId === "smartgun_system")).toBe(true);
    expect(fitted.every((a) => a.price === 0)).toBe(true);
    const r = e.spend({ kind: "accessory", index: 0, remove: true,
      uuid: fitted[0].uuid });
    expect(r.ok).toBe(false);
  });

  it("counts an accessory against the availability cap", () => {
    const e = armed();
    fit(e, { avail: 12 });
    expect(e.validate().map((i) => i.id)).toContain("gear.availCap");
  });
});

describe("adept powers", () => {
  function adept() {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A",
      SKILLS: "C", RESOURCES: "E" });
    e.setMetatype("human");
    e.setMagicPath("adept");
    return e;
  }

  it("reads a real power-point cost from chargen-data", () => {
    // the packs carry no PP cost for adept powers; chargen-data does
    expect(data.adeptPowers.improved_reflexes.cost).toBeGreaterThan(0);
    expect(data.adeptPowers.improved_reflexes.hasLevel).toBe(true);
    expect(data.adeptPowers.astral_perception.hasLevel).toBe(false);
  });

  it("charges the power's cost, not zero", () => {
    const e = adept();
    e.spend({ kind: "power", uuid: "Item.ip", name: "Improved Reflexes",
      catalogId: "improved_reflexes" });
    const per = data.adeptPowers.improved_reflexes.cost;
    expect(e.budgets().powerPoints.spent).toBe(per);
  });

  it("multiplies the cost by the level", () => {
    const e = adept();
    e.spend({ kind: "power", uuid: "Item.ip", name: "Improved Reflexes",
      catalogId: "improved_reflexes" });
    const per = data.adeptPowers.improved_reflexes.cost;
    e.spend({ kind: "powerLevel", index: 0, delta: 2 });      // level 3
    expect(e.state.powers[0].level).toBe(3);
    expect(e.budgets().powerPoints.spent).toBe(per * 3);
  });

  it("refuses levels on a power that has none", () => {
    const e = adept();
    e.spend({ kind: "power", uuid: "Item.ap", name: "Astral Perception",
      catalogId: "astral_perception" });
    const r = e.spend({ kind: "powerLevel", index: 0, delta: 1 });
    expect(r.ok).toBe(false);
    expect(r.reason).toBe("power-has-no-levels");
  });

  it("lets a multi power be taken more than once, others not", () => {
    const e = adept();
    const take = (gid, uuid) => e.spend({ kind: "power", uuid, name: gid, catalogId: gid });
    expect(take("attribute_boost", "Item.ab1").ok).toBe(true);   // multi="yes"
    expect(take("attribute_boost", "Item.ab1").ok).toBe(true);
    expect(take("astral_perception", "Item.ap").ok).toBe(true);
    expect(take("astral_perception", "Item.ap").ok).toBe(false);
  });

  it("overspending power points is flagged", () => {
    const e = adept();
    const max = e.budgets().powerPoints.max;
    for (let i = 0; i < max + 2; i++) {
      e.spend({ kind: "power", uuid: `Item.x${i}`, name: "Killing Hands",
        catalogId: "improved_reflexes", cost: 1 });
    }
    expect(e.budgets().powerPoints.left).toBeLessThan(0);
    expect(e.validate().map((i) => i.id)).toContain("adept.ppBudget");
  });
});

describe("leveled powers are bought per level", () => {
  it("taking a leveled power again raises its level instead of erroring", () => {
    // reported: buying Improved Reflexes 3 times said "duplicate"
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A",
      SKILLS: "C", RESOURCES: "E" });
    e.setMetatype("human");
    e.setMagicPath("adept");
    const take = () => e.spend({ kind: "power", uuid: "Item.ir",
      name: "Improved Reflexes", catalogId: "improved_reflexes" });

    expect(take().ok).toBe(true);
    expect(e.state.powers[0].level).toBe(1);
    expect(take().ok).toBe(true);
    expect(take().ok).toBe(true);
    expect(e.state.powers).toHaveLength(1);          // one entry, level 3
    expect(e.state.powers[0].level).toBe(3);

    const per = data.adeptPowers.improved_reflexes.cost;
    expect(e.budgets().powerPoints.spent).toBe(per * 3);
  });

  it("a power without levels is still a duplicate the second time", () => {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A",
      SKILLS: "C", RESOURCES: "E" });
    e.setMetatype("human");
    e.setMagicPath("adept");
    const take = () => e.spend({ kind: "power", uuid: "Item.ap",
      name: "Astral Perception", catalogId: "astral_perception" });
    expect(take().ok).toBe(true);
    const again = take();
    expect(again.ok).toBe(false);
    expect(again.reason).toBe("duplicate");
  });

  it("Mystic Armor is available as a power, not only as a spell", () => {
    // it exists as both; a catalogId collision had dropped the power
    expect(data.adeptPowers.mystic_armor).toBeTruthy();
    expect(data.adeptPowers.mystic_armor.hasLevel).toBe(true);
  });
});

describe("knowledge skills bought with karma", () => {
  function withKnowledge() {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "knowledge", name: "Gang Politics", type: "knowledge" });
    return e;
  }

  it("starts at rank 1 on the free points", () => {
    const e = withKnowledge();
    expect(e.state.knowledge[0].points).toBe(1);
    expect(e.budgets().knowledgePoints.spent).toBe(1);
    expect(e.budgets().karma.spent).toBe(0);
  });

  it("charges the flat 3 karma the book gives, not 5 x rank", () => {
    const e = withKnowledge();
    const before = e.budgets().karma.spent;
    e.spend({ kind: "knowledgeRank", target: 0, pool: "karma", delta: 1 });
    expect(e.state.knowledge[0].karma).toBe(1);
    // core p69: "New Knowledge skills cost 3 Karma"
    expect(e.budgets().karma.spent).toBe(before + rules.karmaCosts.knowledgeSkill);
    // and it does not consume a free knowledge point
    expect(e.budgets().knowledgePoints.spent).toBe(1);
  });

  it("will not go below zero karma ranks", () => {
    const e = withKnowledge();
    const r = e.spend({ kind: "knowledgeRank", target: 0, pool: "karma", delta: -1 });
    expect(r.ok).toBe(false);
  });
});

describe("augmented ratings and power caps", () => {
  function adept() {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A",
      SKILLS: "C", RESOURCES: "E" });
    e.setMetatype("human");
    e.setMagicPath("adept");
    return e;
  }

  it("caps Improved Reflexes at 4 — the book states it", () => {
    // core p158: "The maximum level of this power is 4"
    expect(data.adeptPowers.improved_reflexes.maxLevel).toBe(4);
    const e = adept();
    const take = () => e.spend({ kind: "power", uuid: "Item.ir",
      name: "Improved Reflexes", catalogId: "improved_reflexes" });
    for (let i = 0; i < 4; i++) expect(take().ok).toBe(true);
    expect(e.state.powers[0].level).toBe(4);
    const fifth = take();
    expect(fifth.ok).toBe(false);
    expect(fifth.reason).toBe("at-max-level");
  });

  it("shows the adept power's bonus as an augmented rating", () => {
    const e = adept();
    const natural = e.attrRating("rea");
    e.spend({ kind: "power", uuid: "Item.ir", name: "Improved Reflexes",
      catalogId: "improved_reflexes" });
    expect(augmentBonus(e.state, "rea", data)).toBe(1);      // +1 per level
    e.spend({ kind: "powerLevel", index: 0, delta: 2 });      // level 3
    expect(augmentBonus(e.state, "rea", data)).toBe(3);
    expect(augmentedRating(e.state, "rea", e.provider, data)).toBe(natural + 3);
    expect(e.attrRating("rea")).toBe(natural);                // natural unchanged
  });

  it("scales rating-based ware by its rating", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "purchase", uuid: "Item.wr", name: "Wired Reflexes",
      catalogId: "wired_reflexes", price: 150000, avail: 3, rating: 2 });
    expect(data.gearMounts.wired_reflexes.bonuses.rea.perRating).toBe(1);
    expect(augmentBonus(e.state, "rea", data)).toBe(2);       // rating 2 -> +2
  });

  it("leaves attributes with no augmentation alone", () => {
    const e = adept();
    expect(augmentBonus(e.state, "cha", data)).toBe(0);
  });
});

describe("knowledge skills cost 3 karma, not 5 x rank", () => {
  it("charges the flat rate the book gives", () => {
    // core p69: "New Knowledge skills cost 3 Karma"
    expect(rules.karmaCosts.knowledgeSkill).toBe(3);
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "knowledge", name: "Gang Politics", type: "knowledge" });
    const before = e.budgets().karma.spent;
    e.spend({ kind: "knowledgeRank", target: 0, pool: "karma", delta: 1 });
    expect(e.budgets().karma.spent).toBe(before + 3);
  });

  it("is cheaper than an active skill rank", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "skill", target: "firearms", pool: "karma", delta: 1 });
    const activeCost = e.budgets().karma.spent;               // 5 x rank 1
    expect(activeCost).toBeGreaterThan(rules.karmaCosts.knowledgeSkill);
  });
});

describe("rated gear prices by rating", () => {
  // Rated items carry no flat price; the merge stored 0, so cyberware and
  // bioware were free and cost no Essence.
  function bought(catalogId, rating) {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "purchase", uuid: `Item.${catalogId}`, name: catalogId,
      catalogId, rating });
    return e;
  }

  it("reads Wired Reflexes' price table straight from the book values", () => {
    const meta = data.gearRatings.wired_reflexes;
    expect(meta.ratings).toEqual([1, 2, 3, 4]);
    expect(meta.maxRating).toBe(4);
    expect(ratedValues({ catalogId: "wired_reflexes" }, data, 1).price).toBe(40000);
    expect(ratedValues({ catalogId: "wired_reflexes" }, data, 4).price).toBe(450000);
  });

  it("charges the rating's price, not zero", () => {
    expect(bought("wired_reflexes", 1).budgets().nuyen.spent).toBe(40000);
    expect(bought("wired_reflexes", 3).budgets().nuyen.spent).toBe(250000);
  });

  it("costs Essence scaled by rating", () => {
    // wired reflexes: 1 Essence per rating
    expect(bought("wired_reflexes", 1).budgets().essence.spent).toBe(1);
    expect(bought("wired_reflexes", 3).budgets().essence.spent).toBe(3);
  });

  it("handles a formula as well as a table", () => {
    // synaptic booster: $RATING*95000, essence $RATING*0.5
    expect(ratedValues({ catalogId: "synaptic_booster" }, data, 2).price).toBe(190000);
    expect(ratedValues({ catalogId: "synaptic_booster" }, data, 2).essence).toBe(1);
  });

  it("raises availability with the rating, and flags going over the cap", () => {
    // wired reflexes availability table is 3L,3L,4L,6L against a cap of 6
    expect(ratedValues({ catalogId: "wired_reflexes" }, data, 1).avail).toBe(3);
    expect(ratedValues({ catalogId: "wired_reflexes" }, data, 4).avail).toBe(6);
    expect(bought("wired_reflexes", 4).validate().map((i) => i.id))
      .not.toContain("gear.availCap");
  });

  it("rejects a rating the item does not offer", () => {
    const e = bought("synaptic_booster", 5);        // it only goes to 3
    expect(e.validate().map((i) => i.id)).toContain("gear.ratingRange");
  });

  it("leaves unrated gear on its flat price", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "purchase", uuid: "Item.x", name: "Plain Thing",
      catalogId: "not_a_rated_item", price: 500, avail: 2, essence: 0 });
    expect(e.budgets().nuyen.spent).toBe(500);
  });

  it("essence drives the augmented Reaction too", () => {
    const e = bought("wired_reflexes", 3);
    expect(augmentBonus(e.state, "rea", data)).toBe(3);
  });
});

describe("pricing works from the item alone", () => {
  // The point of putting the tables on the item: a cost must be computable
  // WITHOUT chargen-data, so custom or homebrew gear prices correctly and the
  // two sources can never drift.
  const onItem = {
    catalogId: "some_homebrew_ware",
    sr6forge: {
      ratings: [1, 2, 3], maxRating: 3,
      priceByRating: [1000, 4000, 9000],
      availByRating: [2, 4, 8],
      essenceByRating: [0.5, 1, 1.5],
    },
  };

  it("prices from the item with NO chargen-data present", () => {
    const none = {};                                   // no gearRatings at all
    expect(ratedValues(onItem, none, 1).price).toBe(1000);
    expect(ratedValues(onItem, none, 3).price).toBe(9000);
    expect(ratedValues(onItem, none, 2).essence).toBe(1);
    expect(ratedValues(onItem, none, 3).avail).toBe(8);
  });

  it("prefers the item's own tables over the central ones", () => {
    // same id in both, different numbers: the item must win
    const conflicting = { gearRatings: { some_homebrew_ware: {
      ratings: [1], price: { flat: 999999 } } } };
    expect(ratedValues(onItem, conflicting, 2).price).toBe(4000);
  });

  it("still falls back to chargen-data for an item carrying nothing", () => {
    expect(ratedValues({ catalogId: "wired_reflexes" }, data, 3).price).toBe(250000);
  });

  it("falls back to the flat price for unrated gear either way", () => {
    expect(ratedValues({ catalogId: "nope", price: 250, avail: 1 }, {}, 1).price).toBe(250);
  });

  it("a purchase keeps its tables, so a reopened draft re-costs itself", () => {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "purchase", uuid: "Item.hb", name: "Homebrew Ware",
      catalogId: onItem.catalogId, sr6forge: onItem.sr6forge, rating: 3 });
    // round-trip through the draft, then cost it with NO chargen-data
    const draft = e.toDraft();
    const revived = ChargenEngine.fromDraft(draft, { gearRatings: {} }, rules);
    expect(revived.budgets().nuyen.spent).toBe(9000);
    expect(revived.budgets().essence.spent).toBe(1.5);
  });
});

describe("nuyen breakdown — gear is not the only drain", () => {
  /** Reproduces a real report: Priority E resources, no gear bought at all,
   *  yet the budget showed roughly -4,000¥ with nothing on screen to explain
   *  it. The money was a lifestyle and a fake SIN. */
  function priest() {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A", SKILLS: "C", RESOURCES: "E" });
    e.setMetatype("human");
    return e;
  }

  it("starts a Priority E character with the table's 8,000 nuyen", () => {
    expect(priest().budgets().nuyen.max).toBe(8000);
  });

  it("charges a lifestyle and a fake SIN, and says so", () => {
    const e = priest();
    e.spend({ kind: "lifestyle", id: "low", months: 1 });
    e.spend({ kind: "sin", name: "Fake SIN", rating: 4 });
    const n = e.budgets().nuyen;

    expect(e.state.purchases).toHaveLength(0);       // no gear at all
    expect(n.spent).toBe(12000);                     // 2,000 lifestyle + 10,000 SIN
    expect(n.left).toBe(-4000);

    // the whole point: the overdraft has to be explicable from the budget
    const labels = n.breakdown.map((b) => b.label).join(" | ");
    expect(n.breakdown).toHaveLength(2);
    expect(labels).toMatch(/Low lifestyle/i);
    expect(labels).toMatch(/rating 4/i);
    expect(n.breakdown.reduce((s, b) => s + b.amount, 0)).toBe(n.spent);
  });

  it("prices a fake SIN at rating x 2,500 (core p274)", () => {
    for (const rating of [1, 2, 3, 4]) {
      const e = priest();
      e.spend({ kind: "sin", name: "Fake SIN", rating });
      expect(e.budgets().nuyen.spent).toBe(rating * 2500);
    }
  });

  it("charges for fake licenses at rating x 200 (core p274)", () => {
    const e = priest();
    e.spend({ kind: "sin", name: "Fake SIN", rating: 1 });
    e.state.sins[0].licenses = [{ name: "driver's license", rating: 3 }, "concealed carry"];
    // 2,500 SIN + 600 rated license + 200 for the unrated one
    expect(e.budgets().nuyen.spent).toBe(3300);
  });

  it("reports an empty breakdown when nothing has been bought", () => {
    const n = priest().budgets().nuyen;
    expect(n.breakdown).toEqual([]);
    expect(n.left).toBe(n.max);
  });
});

describe("draft migration — drafts written before the catalog-id rename", () => {
  /** A draft as saved by the older build: entries keyed `genesisID`. */
  function oldDraft() {
    const st = blankState();
    st.method = "priority";
    st.metatypeId = "human";
    st.qualities = [
      { genesisID: "mentor_spirit", rating: 1, positive: true, free: false },
      { genesisID: "honorbound", rating: 1, positive: false, free: false },
      { genesisID: "sinner", rating: 1, positive: false, free: false },
      { genesisID: "prejudiced", rating: 1, positive: false, free: false },
      { genesisID: "dependents", rating: 1, positive: false, free: false },
    ];
    st.powers = [{ genesisID: "improved_reflexes", name: "Improved Reflexes", cost: 1, level: 3 }];
    return st;
  }

  it("renames the key so metadata resolves again", () => {
    const st = migrateState(oldDraft());
    expect(st.qualities.map((q) => q.catalogId)).toEqual(
      ["mentor_spirit", "honorbound", "sinner", "prejudiced", "dependents"]);
    expect(st.qualities.every((q) => q.genesisID === undefined)).toBe(true);
    expect(st.powers[0].catalogId).toBe("improved_reflexes");
  });

  it("credits the negative qualities that used to price at zero", () => {
    // the reported symptom: every quality resolved to 0 karma, so four
    // negative qualities earned nothing
    const before = qualityKarma(oldDraft(), data);
    expect(before).toEqual({ pos: 0, neg: 0 });

    const after = qualityKarma(migrateState(oldDraft()), data);
    expect(after.neg).toBe(30);                    // 10 + 8 + 8 + 4
    expect(after.pos).toBe(10);                    // mentor spirit
    expect(after.neg - after.pos).toBe(20);        // the missing 20 karma
  });

  it("migrates automatically when an engine is built from the draft", () => {
    const e = new ChargenEngine(data, rules, { state: oldDraft() });
    expect(e.state.qualities[0].catalogId).toBe("mentor_spirit");
  });

  it("leaves a current draft untouched", () => {
    const st = blankState();
    st.qualities = [{ catalogId: "honorbound", rating: 1, positive: false, free: false }];
    expect(migrateState(structuredClone(st))).toEqual(st);
  });
});

describe("removing a quality", () => {
  function withQualities() {
    const e = engineWith();
    e.setMetatype("human");
    e.spend({ kind: "quality", catalogId: "honorbound", positive: false, karma: 10 });
    return e;
  }

  it("removes by catalog id", () => {
    const e = withQualities();
    expect(e.spend({ kind: "quality", catalogId: "honorbound", remove: true }).ok).toBe(true);
    expect(e.state.qualities.filter((q) => !q.free)).toHaveLength(0);
  });

  it("removes by position when the id is missing", () => {
    // guards the reported "cannot remove it in the UI" case: the button sends
    // an empty id for a row whose catalogId never survived
    const e = withQualities();
    const i = e.state.qualities.findIndex((q) => !q.free);
    delete e.state.qualities[i].catalogId;
    expect(e.spend({ kind: "quality", catalogId: "", index: i, remove: true }).ok).toBe(true);
    expect(e.state.qualities.filter((q) => !q.free)).toHaveLength(0);
  });

  it("still refuses to remove a free racial quality", () => {
    const e = withQualities();
    const free = e.state.qualities.findIndex((q) => q.free);
    if (free >= 0) {
      expect(e.spend({ kind: "quality", catalogId: "", index: free, remove: true }).ok).toBe(false);
    }
  });
});

describe("Companion gear PACKs", () => {
  function rich() {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "C", MAGIC: "E", SKILLS: "D", RESOURCES: "A" });
    e.setMetatype("human");
    return e;
  }

  it("ships the English packs and skips the German ones", () => {
    expect(Object.keys(data.packs).length).toBe(177);          // 289 total, 112 lang="de"
    expect(data.packs.starterpack.price).toBe(25000);
  });

  it("charges the bundle price, not the sum of the parts", () => {
    const e = rich();
    e.spend({ kind: "pack", catalogId: "starterpack" });
    // one line for the pack itself...
    const packLine = e.state.purchases.filter((p) => p.isPack);
    expect(packLine).toHaveLength(1);
    expect(e.budgets().nuyen.spent).toBe(25000);
  });

  it("does not re-price contents that carry a real catalogId", () => {
    // the regression that matters: contents keep their catalogId, so a naive
    // implementation finds their real price in gearRatings and charges twice
    const e = rich();
    e.spend({ kind: "pack", catalogId: "starterpack" });
    const contents = e.state.purchases.filter((p) => p.fromPack);
    expect(contents.length).toBeGreaterThan(5);
    expect(contents.some((p) => p.catalogId && data.gearRatings[p.catalogId])).toBe(true);
    expect(e.budgets().nuyen.spent).toBe(25000);
  });

  it("counts an augmentation pack's essence once, from the pack", () => {
    const e = rich();
    e.spend({ kind: "pack", catalogId: "pack_hacker_a" });
    expect(e.budgets().essence.spent).toBeCloseTo(data.packs.pack_hacker_a.essence, 2);
  });

  it("grants the SIN, its licences and the lifestyle, not just gear", () => {
    const e = rich();
    e.spend({ kind: "pack", catalogId: "starterpack" });
    expect(e.state.sins).toHaveLength(1);
    expect(e.state.sins[0].rating).toBe(4);                    // SUPERFICIALLY_PLAUSIBLE
    expect(e.state.sins[0].licenses).toHaveLength(2);
    expect(e.state.lifestyleId).toBe("low");
  });

  it("will not overwrite a lifestyle the player already chose", () => {
    const e = rich();
    e.spend({ kind: "lifestyle", id: "high", months: 1 });
    e.spend({ kind: "pack", catalogId: "starterpack" });
    expect(e.state.lifestyleId).toBe("high");
  });

  it("removes cleanly, taking its contents with it", () => {
    const e = rich();
    e.spend({ kind: "purchase", uuid: "u1", name: "Own gear", price: 500 });
    e.spend({ kind: "pack", catalogId: "starterpack" });
    expect(e.spend({ kind: "pack", catalogId: "starterpack", remove: true }).ok).toBe(true);
    expect(e.state.purchases).toHaveLength(1);                 // the player's own item survives
    expect(e.state.purchases[0].uuid).toBe("u1");
    expect(e.state.sins).toHaveLength(0);
    expect(e.state.lifestyleId).toBe(null);
    expect(e.budgets().nuyen.spent).toBe(500);
  });

  it("flattens a pack that contains another pack", () => {
    // pack_hacker_a lists pack_cyberprograms among its contents
    const refs = data.packs.pack_hacker_a.contents.map((r) => r.ref);
    expect(refs).not.toContain("pack_cyberprograms");
    expect(refs).toContain("exploit");
  });

  it("refuses an unknown pack and a duplicate", () => {
    const e = rich();
    expect(e.spend({ kind: "pack", catalogId: "nope" }).ok).toBe(false);
    e.spend({ kind: "pack", catalogId: "starterpack" });
    expect(e.spend({ kind: "pack", catalogId: "starterpack" }).reason).toBe("already-owned");
  });
});

describe("committing a PACK", () => {
  it("plans the contents as items, not the pack receipt", () => {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "C", MAGIC: "E", SKILLS: "D", RESOURCES: "A" });
    e.setMetatype("human");
    e.spend({ kind: "pack", catalogId: "starterpack" });
    const plan = e.commitPlan();
    // the pack itself is a receipt; only real gear should reach the sheet
    expect(plan.embeddedFromPacks.some((g) => g.catalogId === "starterpack")).toBe(false);
    expect(plan.embeddedFromPacks.some((g) => g.catalogId === "respirator")).toBe(true);
    // contents carry no uuid, so the committer must have a catalogId to use
    const respirator = plan.embeddedFromPacks.find((g) => g.catalogId === "respirator");
    expect(respirator.uuid).toBeFalsy();
    expect(respirator.catalogId).toBe("respirator");
  });
});

describe("karma on special attributes", () => {
  function adept() {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A", SKILLS: "C", RESOURCES: "E" });
    e.setMetatype("human");
    e.setMagicPath("mysticadept");
    return e;
  }

  it("buys an Edge rank with karma at 5 x the new rating", () => {
    // Commlink6 does this (Knight: EDGE points3 = 1) and it was unreachable in
    // the UI, which only offered the adjustment pool for special attributes
    const e = adept();
    e.spend({ kind: "attribute", target: "edg", pool: "adjust", delta: 2 });
    const before = e.budgets().karma.spent;
    e.spend({ kind: "attribute", target: "edg", pool: "karma", delta: 1 });
    expect(e.attrRating("edg")).toBe(4);                 // 1 + 2 adjust + 1 karma
    expect(e.budgets().karma.spent - before).toBe(20);   // 4 x 5
  });

  it("names the Edge rank in the karma breakdown", () => {
    const e = adept();
    e.spend({ kind: "attribute", target: "edg", pool: "karma", delta: 1 });
    const line = e.budgets().karma.breakdown.find((x) => x.key === "attr:edg");
    expect(line).toBeTruthy();
    expect(line.label).toMatch(/EDG 1 → 2/);
  });

  it("caps Magic at 6 unless the world allows initiation past it", () => {
    const e = adept();
    // priority A Magic for a mystic adept is 4; push it well past 6
    e.spend({ kind: "attribute", target: "mag", pool: "karma", delta: 4 });
    expect(e.attrRating("mag")).toBeGreaterThan(6);
    expect(e.validate().some((i) => i.id === "attr.specialMax")).toBe(true);

    e.setOptionalRules({ raiseMagicAboveSix: true });
    expect(e.validate().some((i) => i.id === "attr.specialMax")).toBe(false);
  });

  it("still flags Edge past its metatype maximum", () => {
    const e = adept();
    e.spend({ kind: "attribute", target: "edg", pool: "karma", delta: 8 });
    expect(e.validate().some((i) => i.id === "attr.creationMax")).toBe(true);
  });
});

describe("stacking identical purchases", () => {
  function shop() {
    const e = engineWith({ METATYPE: "D", ATTRIBUTE: "C", MAGIC: "E", SKILLS: "D", RESOURCES: "A" });
    e.setMetatype("human");
    return e;
  }
  const buy = (e, over = {}) => e.spend({
    kind: "purchase", uuid: "u-pred", name: "Ares Predator VI", price: 725,
    catalogId: "ares_predator_vi", gearType: "WEAPON_FIREARMS",
    subtype: "PISTOLS_HEAVY", stack: true, ...over });

  it("gives each weapon its own line so they can differ", () => {
    // the reported bug: two Predators collapsed to one "x2" line, and since
    // accessories hang off the line you could not silence just one of them
    const e = shop();
    buy(e); buy(e);
    expect(e.state.purchases).toHaveLength(2);
    expect(e.state.purchases.every((p) => (p.qty ?? 1) === 1)).toBe(true);
  });

  it("fits an accessory to one copy only", () => {
    const e = shop();
    buy(e); buy(e);
    // the Predator carries a factory-fitted accessory of its own, so count
    // only what the player added
    const fitted = (p) => p.accessories.filter((a) => !a.included).length;
    expect(fitted(e.state.purchases[0])).toBe(0);
    e.spend({ kind: "accessory", index: 0, uuid: "u-silencer", name: "Silencer",
      catalogId: "silencer", slot: "BARREL", price: 500 });
    expect(fitted(e.state.purchases[0])).toBe(1);
    expect(fitted(e.state.purchases[1])).toBe(0);
  });

  it("still stacks ammo and consumables", () => {
    const e = shop();
    for (let i = 0; i < 3; i++) {
      e.spend({ kind: "purchase", uuid: "u-ammo", name: "Regular Ammo", price: 60,
        catalogId: "regular_ammo", gearType: "AMMUNITION", stack: true });
    }
    expect(e.state.purchases).toHaveLength(1);
    expect(e.state.purchases[0].qty).toBe(3);
  });

  it("charges the same either way", () => {
    const e = shop();
    buy(e); buy(e);
    expect(e.budgets().nuyen.spent).toBe(1450);          // 2 x 725
  });

  it("splits a stack saved by an older build", () => {
    const state = blankState();
    state.purchases = [{ uuid: "u-pred", name: "Ares Predator VI", price: 725,
      catalogId: "ares_predator_vi", gearType: "WEAPON_FIREARMS", qty: 2,
      accessories: [{ uuid: "u-s", name: "Silencer", slot: "TOP", price: 500 }] }];
    const migrated = migrateState(state, data);
    expect(migrated.purchases).toHaveLength(2);
    // the modification stays on one of them, which is what "I only did one" means
    expect(migrated.purchases[0].accessories).toHaveLength(1);
    expect(migrated.purchases[1].accessories).toHaveLength(0);
  });

  it("leaves a legitimate ammo stack alone when migrating", () => {
    const state = blankState();
    state.purchases = [{ uuid: "u-ammo", catalogId: "regular_ammo",
      gearType: "AMMUNITION", qty: 4, price: 60, accessories: [] }];
    expect(migrateState(state, data).purchases).toHaveLength(1);
  });
});
