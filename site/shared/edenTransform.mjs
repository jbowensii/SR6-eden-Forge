import { EDEN, NUMERIC, BOOLEAN, edenFor } from "./edenSpec.mjs";

// Turn a library item into a shadowrun6-eden Foundry document. The Foundry
// document `type` comes from the item's domain (gear→gear, spells→spell, …);
// gear additionally keeps its `system.type` discriminator. Eden's numeric /
// boolean fields are coerced from any strings we stored; every other field we
// carry (our "extra" data) rides along untouched — Eden ignores what it doesn't
// know, and we keep it for round-tripping.
function coerceNum(v) {
  if (typeof v === "number") return v;
  const m = String(v ?? "").match(/-?\d+(?:\.\d+)?/);
  return m ? Number(m[0]) : 0;
}

/** One of our effect records as a Foundry ActiveEffect.
 *
 * The library stores the shape the extractor produced; Foundry wants a few
 * fields it does not care about set explicitly, and a null priority omitted
 * rather than sent as null. `transfer: true` is what makes an effect apply to
 * the actor carrying the item rather than sitting inert on the item itself —
 * without it the whole feature looks fine on the sheet and changes nothing.
 */
export function toActiveEffect(effect) {
  return {
    name: effect.name ?? "",
    img: effect.img || "icons/svg/upgrade.svg",
    disabled: Boolean(effect.disabled),
    transfer: effect.transfer !== false,
    description: effect.description ?? "",
    duration: {},
    changes: (effect.changes ?? []).map((c) => ({
      key: c.key,
      mode: c.mode ?? 2,                 // ADD — modifiers stack, never replace
      value: String(c.value ?? ""),      // Foundry parses; a number here is fine but a string is what its own UI writes
      ...(c.priority == null ? {} : { priority: c.priority }),
    })),
  };
}

export function toFoundryDoc(item, { product, domain } = {}) {
  const dom = domain ?? item._domain;
  const spec = edenFor(dom);
  // Legacy gear path: no domain given but the item self-identifies via type.
  if (!spec && !dom && item?.system?.type) {
    return _wrap(item, "gear", structuredClone(item.system), product, dom);
  }
  if (!spec) throw new TypeError(`item ${item?.id ?? "?"} has unknown domain ${dom ?? "?"}`);
  // gear's Foundry type is a single "gear" with a system.type discriminator; a
  // gear item without it can't map to an Eden gear subtype.
  if (spec.discriminator && !item?.system?.[spec.discriminator]) {
    throw new TypeError(`item ${item?.id ?? "?"} has no system.${spec.discriminator}`);
  }

  const system = structuredClone(item.system ?? {});
  for (const f of [...spec.req, ...spec.opt]) {
    if (NUMERIC.has(f) && system[f] !== undefined && system[f] !== "") system[f] = coerceNum(system[f]);
    if (BOOLEAN.has(f) && typeof system[f] === "string") system[f] = /^(true|1|yes)$/i.test(system[f]);
  }
  return _wrap(item, spec.type, system, product, dom);
}

const _ATTR_KEYS = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha", "edg", "mag", "res", "essence"];

// SR6 active-skill name -> shadowrun6-eden skill code
const _SKILL_CODE = {
  astral: "astral", athletics: "athletics", biotech: "biotech", "close combat": "close_combat",
  con: "con", conjuring: "conjuring", cracking: "cracking", electronics: "electronics",
  enchanting: "enchanting", engineering: "engineering", "exotic weapons": "exotic_weapon",
  "exotic weapon": "exotic_weapon", firearms: "firearms", influence: "influence",
  outdoors: "outdoors", perception: "perception", piloting: "piloting", sorcery: "sorcery",
  stealth: "stealth", tasking: "tasking",
};
const _SKILL_RE = /([A-Za-z][A-Za-z ]+?)\s+(\d+)(?:\s*\(([^)]+)\))?/g;

function _mapSkills(str) {
  // "Athletics 5, Close Combat 9 (Intimidation +2), Con 6" -> nested by code
  const out = {};
  let m;
  while ((m = _SKILL_RE.exec(str)) !== null) {
    const name = m[1].trim().toLowerCase();
    const code = _SKILL_CODE[name];
    if (!code) continue;
    out[code] = { points: Number(m[2]) || 0, specialization: (m[3] || "").replace(/\s*[+\-]\d+/g, "").trim() };
  }
  return out;
}

function _mapMovement(str) {
  // "10/25/+3" (walk / run / sprint-per-hit) -> {walk, run, sprint}
  const m = String(str).match(/(\d+)\s*\/\s*(\d+)\s*\/\s*\+?(\d+)/);
  return m ? { walk: Number(m[1]), run: Number(m[2]), sprint: Number(m[3]) } : null;
}

function _actorSubstructures(system) {
  // Turn the extractor's flat strings into the nested objects Eden actor sheets
  // read, while keeping the originals as *_text so nothing is lost.
  const skillsStr = system.activeSkills || system.skills;
  if (typeof skillsStr === "string" && skillsStr) {
    const mapped = _mapSkills(skillsStr);
    if (Object.keys(mapped).length) {
      system.skills_text = skillsStr;
      system.skills = mapped;
    }
  }
  if (typeof system.movement === "string" && system.movement) {
    const mv = _mapMovement(system.movement);
    if (mv) { system.movement_text = system.movement; system.movement = mv; }
  }
  if (typeof system.defenseRating === "string" && system.defenseRating) {
    const dr = system.defenseRating.match(/\d+/);
    if (dr) system.defenserating = { physical: Number(dr[0]) };
  }
}

function _nestAttributes(system) {
  // Eden actor sheets read system.attributes.<code>.base (nested), but the
  // extractor stores flat integers (bod: 4). Convert so the stat block populates.
  const a = system.attributes;
  if (!a || typeof a !== "object") return;
  const nested = {};
  for (const [k, v] of Object.entries(a)) {
    if (v && typeof v === "object") { nested[k] = v; continue; }   // already nested
    const key = k === "ess" ? "essence" : (k === "magres" ? "mag" : k);
    nested[key] = { base: typeof v === "number" ? v : Number(v) || 0 };
  }
  system.attributes = nested;
}

function _wrap(item, type, system, product, domain) {
  system.description ??= "";
  system.genesisID ??= item.id;
  // reference location: book title + printed page travel with the document
  system.product ??= product ?? item.meta?.book ?? "";
  system.page ??= item.meta?.page ?? 0;
  const isActor = EDEN[domain]?.actor || ["npc", "critter", "spirit"].includes(type);
  if (isActor) { _nestAttributes(system); _actorSubstructures(system); }
  const doc = {
    name: item.name,
    type,
    img: item.img || "icons/svg/item-bag.svg",
    system,
    flags: {},
  };
  // actors carry an embedded-items array; items carry an effects array
  if (isActor) doc.items = [];
  else doc.effects = (item.effects ?? []).map(toActiveEffect);
  return doc;
}
