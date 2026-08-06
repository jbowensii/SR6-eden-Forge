import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { preview, applyPatch, undoPatch, snapshot } from "../sr6-forge/scripts/engine/advancement-engine.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(readFileSync(join(here, "..", "..", "export", "chargen-data.json"), "utf8"));
const rules = JSON.parse(readFileSync(join(here, "..", "sr6-forge", "data", "creation-rules.json"), "utf8"));

/** Minimal stand-in for an eden Player actor. */
function actor({ karma = 100, mortype = "mundane", attrs = {}, skills = {} } = {}) {
  const attributes = {};
  for (const k of ["bod", "agi", "rea", "str", "wil", "log", "int", "cha"]) {
    attributes[k] = { base: attrs[k] ?? 3 };
  }
  attributes.edg = { max: attrs.edg ?? 3, current: attrs.edg ?? 3 };
  attributes.mag = { base: attrs.mag ?? 0, initiation: attrs.initiation ?? 0 };
  attributes.res = { base: attrs.res ?? 0, submersion: attrs.submersion ?? 0 };
  return { system: { karma, karma_total: karma, nuyen: 5000, mortype, attributes, skills } };
}

const snap = (a) => snapshot(a);

describe("advancement costs (core p68-70)", () => {
  it("prices an attribute raise at 5 x the new rating", () => {
    const s = snap(actor({ attrs: { bod: 4 } }));
    const pv = preview({ kind: "raiseAttribute", target: "bod" }, s, rules, { data });
    expect(pv.karma).toBe(25);                       // 4 -> 5
    expect(pv.patch["system.attributes.bod.base"]).toBe(5);
  });

  it("matches the book's worked example: 4 -> 6 costs 55 karma", () => {
    let s = snap(actor({ attrs: { bod: 4 } }));
    const first = preview({ kind: "raiseAttribute", target: "bod" }, s, rules, { data });
    s = { ...s, attributes: { ...s.attributes, bod: { base: 5 } } };
    const second = preview({ kind: "raiseAttribute", target: "bod" }, s, rules, { data });
    expect(first.karma + second.karma).toBe(55);     // 25 + 30
  });

  it("raises Edge through max/current, not base", () => {
    const s = snap(actor({ attrs: { edg: 2 } }));
    const pv = preview({ kind: "raiseAttribute", target: "edg" }, s, rules, { data });
    expect(pv.karma).toBe(15);
    expect(pv.patch["system.attributes.edg.max"]).toBe(3);
    expect(pv.patch["system.attributes.edg.current"]).toBe(3);
  });

  it("prices a skill raise at 5 x the new rank", () => {
    const s = snap(actor({ skills: { firearms: { points: 3 } } }));
    const pv = preview({ kind: "raiseSkill", target: "firearms" }, s, rules, { data });
    expect(pv.karma).toBe(20);
    expect(pv.patch["system.skills.firearms.points"]).toBe(4);
  });

  it("charges 5 for a specialization and requires one before an expertise", () => {
    let s = snap(actor({ skills: { firearms: { points: 3 } } }));
    const spec = preview({ kind: "addSpecialization", target: "firearms", value: "Pistols" }, s, rules, { data });
    expect(spec.karma).toBe(5);
    expect(preview({ kind: "addExpertise", target: "firearms", value: "Pistols" }, s, rules, { data }).ok).toBe(false);

    s = snap(actor({ skills: { firearms: { points: 3, specialization: "Pistols" } } }));
    expect(preview({ kind: "addExpertise", target: "firearms", value: "Pistols" }, s, rules, { data }).karma).toBe(5);
  });

  it("refuses a specialization on an untrained skill", () => {
    const s = snap(actor({ skills: { firearms: { points: 0 } } }));
    const pv = preview({ kind: "addSpecialization", target: "firearms", value: "Pistols" }, s, rules, { data });
    expect(pv.ok).toBe(false);
    expect(pv.reason).toBe("skill-untrained");
  });

  it("doubles quality karma in both directions", () => {
    const s = snap(actor());
    expect(preview({ kind: "buyQuality", name: "Catlike", karmaCost: 12, positive: true }, s, rules, { data }).karma).toBe(24);
    expect(preview({ kind: "removeQuality", name: "SINner", karmaCost: 8, positive: false }, s, rules, { data }).karma).toBe(16);
    // and refuses the nonsensical directions
    expect(preview({ kind: "buyQuality", name: "SINner", karmaCost: 8, positive: false }, s, rules, { data }).ok).toBe(false);
    expect(preview({ kind: "removeQuality", name: "Catlike", karmaCost: 12, positive: true }, s, rules, { data }).ok).toBe(false);
  });

  it("charges 10 + the new grade to initiate, and blocks the mundane", () => {
    const mage = snap(actor({ mortype: "magician", attrs: { mag: 4, initiation: 0 } }));
    expect(preview({ kind: "initiate" }, mage, rules, { data }).karma).toBe(11);
    const grade2 = snap(actor({ mortype: "magician", attrs: { mag: 4, initiation: 2 } }));
    const pv = preview({ kind: "initiate" }, grade2, rules, { data });
    expect(pv.karma).toBe(13);
    expect(pv.patch["system.attributes.mag.initiation"]).toBe(3);

    expect(preview({ kind: "initiate" }, snap(actor()), rules, { data }).ok).toBe(false);
  });

  it("submerges a technomancer through the resonance field", () => {
    const tm = snap(actor({ mortype: "technomancer", attrs: { res: 4, submersion: 1 } }));
    const pv = preview({ kind: "initiate" }, tm, rules, { data });
    expect(pv.patch["system.attributes.res.submersion"]).toBe(2);
  });

  it("only lets spellcasters learn spells", () => {
    const mage = snap(actor({ mortype: "magician" }));
    expect(preview({ kind: "learnSpell", name: "Fireball" }, mage, rules, { data }).karma).toBe(5);
    expect(preview({ kind: "learnSpell", name: "Fireball" }, snap(actor()), rules, { data }).ok).toBe(false);
    const tm = snap(actor({ mortype: "technomancer" }));
    expect(preview({ kind: "learnComplexForm", name: "Puppeteer" }, tm, rules, { data }).karma).toBe(5);
  });

  it("refuses anything the character cannot afford", () => {
    const broke = snap(actor({ karma: 3, attrs: { bod: 4 } }));
    const pv = preview({ kind: "raiseAttribute", target: "bod" }, broke, rules, { data });
    expect(pv.ok).toBe(false);
    expect(pv.reason).toBe("not-enough-karma");
  });
});

describe("apply and undo", () => {
  it("deducts karma on apply and restores everything on undo", () => {
    const a = actor({ karma: 50, attrs: { agi: 3 } });
    const s = snap(a);
    const pv = preview({ kind: "raiseAttribute", target: "agi" }, s, rules, { data });
    const update = applyPatch(pv, s);
    expect(update["system.attributes.agi.base"]).toBe(4);
    expect(update["system.karma"]).toBe(30);          // 50 - 20

    const entry = { karma: pv.karma, before: { "system.attributes.agi.base": 3 } };
    const after = snap(actor({ karma: 30, attrs: { agi: 4 } }));
    const back = undoPatch(entry, after);
    expect(back["system.attributes.agi.base"]).toBe(3);
    expect(back["system.karma"]).toBe(50);
  });
});

describe("nuyen to karma — 6WC p154 'Working for the People'", () => {
  const on = { ...rules, nuyenToKarma: { ...rules.nuyenToKarma, enabled: true } };

  it("is refused while the optional rule is off", () => {
    // the core book only ever moves karma TO nuyen (p67); the reverse is an
    // optional downtime rule, so it must not be available by default
    expect(rules.nuyenToKarma.enabled).toBe(false);
    const pv = preview({ kind: "nuyenToKarma", karma: 1 }, snap(actor()), rules, { data });
    expect(pv.ok).toBe(false);
    expect(pv.reason).toBe("optional-rule-off");
  });

  it("trades 2,000 nuyen for 1 karma once enabled", () => {
    const s = snap(actor({ karma: 10 }));            // the stand-in holds 5,000¥
    const pv = preview({ kind: "nuyenToKarma", karma: 1 }, s, on, { data });
    expect(pv.ok).toBe(true);
    expect(pv.patch["system.nuyen"]).toBe(3000);
    expect(applyPatch(pv, s)["system.karma"]).toBe(11);   // credited, not spent
  });

  it("will not spend nuyen the character does not have", () => {
    const pv = preview({ kind: "nuyenToKarma", karma: 4 }, snap(actor()), on, { data });
    expect(pv.ok).toBe(false);                       // 8,000¥ needed, 5,000¥ held
    expect(pv.reason).toBe("not-enough-nuyen");
  });

  it("reverses exactly, karma and nuyen both", () => {
    const s = snap(actor({ karma: 10 }));
    const pv = preview({ kind: "nuyenToKarma", karma: 2 }, s, on, { data });
    const after = { ...s, karma: applyPatch(pv, s)["system.karma"], nuyen: pv.patch["system.nuyen"] };
    expect(after.karma).toBe(12);
    expect(after.nuyen).toBe(1000);
    const back = undoPatch({ before: { "system.nuyen": s.nuyen }, karma: pv.karma }, after);
    expect(back["system.karma"]).toBe(10);
    expect(back["system.nuyen"]).toBe(5000);
  });
});
