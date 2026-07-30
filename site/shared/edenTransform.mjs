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
  if (isActor) _nestAttributes(system);
  const doc = {
    name: item.name,
    type,
    img: item.img || "icons/svg/item-bag.svg",
    system,
    flags: {},
  };
  // actors carry an embedded-items array; items carry an effects array
  if (isActor) doc.items = [];
  else doc.effects = [];
  return doc;
}
