/** Golden test: rebuild a real Commlink6 character through our engine.
 *
 *  Knight is a mystic adept exported from Commlink6 1.14.0. Its saved
 *  chargenSettings blob records exactly which priorities and per-attribute /
 *  per-skill spends produced it, so replaying those through ChargenEngine and
 *  diffing commitPlan() against the exported actor checks the priority tables,
 *  the spend model and the commit paths end to end against something a human
 *  actually built.
 *
 *  Both files live outside the repo (they are John's own character data, which
 *  is never committed), so the whole suite skips when they are absent.
 */
import { existsSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { ChargenEngine, blankState } from "../sr6-forge/scripts/engine/chargen-engine.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(readFileSync(join(here, "..", "..", "export", "chargen-data.json"), "utf8"));
const rules = JSON.parse(readFileSync(join(here, "..", "sr6-forge", "data", "creation-rules.json"), "utf8"));

const CL6 = "C:/Users/johnb/CommLink6";
const EXPORT = `${CL6}/pdfs/Knight.json`;
const SOURCE = `${CL6}/player/myself/shadowrun6/4c0fc46b-9ca1-4e74-861a-20b912715278/Knight.xml`;
const available = existsSync(EXPORT) && existsSync(SOURCE);

/** Commlink6 attribute names -> eden ids. */
const ATTR = {
  BODY: "bod", AGILITY: "agi", REACTION: "rea", STRENGTH: "str",
  WILLPOWER: "wil", LOGIC: "log", INTUITION: "int", CHARISMA: "cha",
  EDGE: "edg", MAGIC: "mag", RESONANCE: "res",
};

function loadSettings() {
  const xml = readFileSync(SOURCE, "utf8");
  const raw = /<chargenSettings>([\s\S]*?)<\/chargenSettings>/.exec(xml)[1];
  const json = raw
    .replaceAll("&#x0022;", '"').replaceAll("&quot;", '"')
    .replaceAll("&amp;", "&").replaceAll("&lt;", "<").replaceAll("&gt;", ">");
  return JSON.parse(json);
}

/** Replay a chargenSettings blob through our engine. */
function rebuild(cfg) {
  const e = new ChargenEngine(data, rules, { state: blankState("priority") });
  for (const [col, letter] of Object.entries(cfg.priorities)) e.setPriority(col, letter);
  e.setMetatype("human");
  e.setMagicPath("mysticadept");

  // points1 = adjustment points, points2 = attribute points, points3 = karma
  for (const [name, p] of Object.entries(cfg.perAttrib)) {
    const target = ATTR[name];
    if (!target) continue;
    for (const [pool, field] of [["points1", "adjust"], ["points2", "points"], ["points3", "karma"]]) {
      const n = p[pool] ?? 0;
      if (n) e.spend({ kind: "attribute", target, pool: field, delta: n });
    }
  }

  for (const [id, s] of Object.entries(cfg.perSkill)) {
    if (id.includes("/")) continue;                 // knowledge/language entries
    if (s.points1) e.spend({ kind: "skill", target: id, delta: s.points1 });
    if (s.points3) e.spend({ kind: "skill", target: id, pool: "karma", delta: s.points3 });
    if (s.pointSpec) e.spend({ kind: "spec", target: id, spec: "(specialized)" });
  }

  for (let i = 0; i < (cfg.mysticAdeptPowerPoints ?? 0); i++) {
    e.spend({ kind: "powerpoints", delta: 1 });
  }
  if (cfg.toNuyen) e.spend({ kind: "karma2nuyen", delta: cfg.toNuyen });
  return e;
}

describe.skipIf(!available)("golden character: Knight (Commlink6 1.14.0)", () => {
  const cfg = available ? loadSettings() : null;
  const gold = available ? JSON.parse(readFileSync(EXPORT, "utf8")) : null;

  it("reads the priorities the character was built with", () => {
    expect(cfg.priorities).toEqual({
      METATYPE: "D", ATTRIBUTE: "B", MAGIC: "A", SKILLS: "C", RESOURCES: "E",
    });
  });

  it("reproduces every attribute", () => {
    const plan = rebuild(cfg).commitPlan();
    const got = plan.actorData.system.attributes;
    for (const [k, want] of Object.entries(gold.system.attributes)) {
      const base = want.base ?? want.max;
      if (base == null) continue;
      if (k === "res") continue;                    // mundane resonance, not written
      expect(got[k]?.base ?? got[k]?.max, `attribute ${k}`).toBe(base);
    }
  });

  it("reproduces Magic 6 for the mystic adept at priority A", () => {
    const e = rebuild(cfg);
    expect(e.attrRating("mag")).toBe(gold.system.attributes.mag.base);
  });

  it("reproduces every trained skill and its rank", () => {
    const plan = rebuild(cfg).commitPlan();
    const got = plan.actorData.system.skills;
    const want = Object.fromEntries(
      Object.entries(gold.system.skills).filter(([, s]) => s.points > 0)
        .map(([k, s]) => [k, s.points]));
    expect(Object.fromEntries(
      Object.entries(got).map(([k, s]) => [k, s.points]))).toEqual(want);
  });

  it("carries the specialization Commlink6 recorded", () => {
    const plan = rebuild(cfg).commitPlan();
    expect(plan.actorData.system.skills.firearms.specialization).toBeTruthy();
    expect(gold.system.skills.firearms.specialization).toBeTruthy();
  });

  it("writes the metatype and mortype eden expects", () => {
    const plan = rebuild(cfg).commitPlan();
    expect(plan.actorData.system.mortype).toBe(gold.system.mortype);
    expect(plan.actorData.system.metatype.toLowerCase())
      .toBe(gold.system.metatype.toLowerCase());
  });

  it("stays within its budgets", () => {
    const b = rebuild(cfg).budgets();
    expect(b.attributePoints.left, "attribute points").toBeGreaterThanOrEqual(0);
    expect(b.adjustmentPoints.left, "adjustment points").toBeGreaterThanOrEqual(0);
    expect(b.skillPoints.left, "skill points").toBeGreaterThanOrEqual(0);
  });

  it("emits raw inputs only — eden derives the rest", () => {
    const sys = rebuild(cfg).commitPlan().actorData.system;
    for (const a of Object.values(sys.attributes)) {
      expect(a).not.toHaveProperty("pool");
      expect(a).not.toHaveProperty("mod");
    }
    expect(sys).not.toHaveProperty("derived");
    expect(sys).not.toHaveProperty("physical");
    expect(sys).not.toHaveProperty("initiative");
  });
});
