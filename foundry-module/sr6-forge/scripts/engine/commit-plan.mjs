/** Build the commit plan: everything the actor-committer needs to create the
 *  eden Player actor. RAW INPUTS ONLY — eden derives pools/monitors/essence. */
import { attrRating, skillRank, CORE_ATTRS } from "./budgets.mjs";
// config.mjs is the one place that names eden's catalog field; importing it
// here keeps that boundary intact and costs nothing — it pulls in no Foundry
// globals, so this module still unit-tests in plain node.
import { setCatalogId } from "../config.mjs";

export function buildCommitPlan(state, data, rules, provider, budgets) {
  const mt = data.metatypes?.[state.metatypeId] ?? {};
  const system = {
    metatype: mt.name ?? state.metatypeId ?? "",
    mortype: state.morId,
    nuyen: Math.max(0, budgets.nuyen.left),
    karma: Math.max(0, budgets.karma.left),
    karma_total: rules.startingKarma.value,
    attributes: {},
    skills: {},
  };
  for (const k of CORE_ATTRS) {
    system.attributes[k] = { base: attrRating(state, k, provider) };
  }
  const edge = attrRating(state, "edg", provider);
  system.attributes.edg = { max: edge, current: edge };
  const mor = data.morTypes?.[state.morId] ?? {};
  if (mor.magic) system.attributes.mag = { base: attrRating(state, "mag", provider) };
  if (mor.resonance) system.attributes.res = { base: attrRating(state, "res", provider) };

  for (const [id, sk] of Object.entries(state.skills)) {
    // eden stores one rank per skill — free points and karma-bought ranks merge
    const rank = skillRank(sk);
    if (!(rank > 0)) continue;
    system.skills[id] = { points: rank };
    if (sk.spec) system.skills[id].specialization = sk.spec;
    if (sk.expertise) system.skills[id].expertise = sk.expertise;
  }

  /* ---- items from compendia (resolved to uuids by the committer/catalog) ---- */
  const embeddedFromPacks = [];
  for (const q of state.qualities) {
    embeddedFromPacks.push({
      catalogId: q.catalogId, itemType: "quality",
      overrides: {
        ...(q.rating > 1 ? { "system.level": q.rating } : {}),
        ...(q.note ? { "system.explain": q.note } : {}),
        ...(q.choiceText ? { choiceText: q.choiceText } : {}),
      },
    });
  }
  // declared up here because custom purchases in the loop below build straight
  // into it — they have no compendium document to reference
  const syntheticItems = [];
  for (const p of state.purchases) {
    // The PACK line is a receipt, not a thing: its contents are the items that
    // belong on the sheet, and they are already in this list.
    if (p.isPack) continue;
    // A homebrew item has no compendium document to copy, so it is built here
    // instead. Eden's `gear` template is permissive, so it lands on the sheet
    // as a normal piece of kit.
    if (p.custom) {
      syntheticItems.push({
        name: p.name || "Custom item", type: "gear",
        system: {
          type: p.gearType || "TOOLS", subtype: p.subtype || "",
          price: p.price ?? 0, avail: p.avail ?? 0,
          essence: p.essence ?? 0, count: p.qty ?? 1,
          ...(p.rating ? { rating: p.rating } : {}),
          description: p.note ?? "",
        },
      });
      continue;
    }
    embeddedFromPacks.push({ uuid: p.uuid, catalogId: p.catalogId, itemType: p.itemType,
      overrides: { ...(p.qty > 1 ? { "system.count": p.qty } : {}),
                   ...(p.rating ? { "system.rating": p.rating } : {}) } });
    // Accessories fitted into this item's mount slots are their own items on
    // the actor — a factory-fitted one came with the host and is not bought
    // again, but it still has to exist so the sheet shows it.
    for (const a of p.accessories ?? []) {
      if (!a.uuid) continue;                      // factory items have no pack uuid
      embeddedFromPacks.push({ uuid: a.uuid, itemType: "gear",
        overrides: { "system.description": `Fitted to ${p.name} (${a.slot}).` } });
    }
  }
  for (const sp of state.spells) embeddedFromPacks.push({ uuid: sp.uuid, itemType: "spell" });
  for (const pw of state.powers) {
    embeddedFromPacks.push({ uuid: pw.uuid, itemType: "adeptpower",
      overrides: pw.level > 1 ? { "system.level": pw.level } : {} });
  }
  for (const cf of state.complexForms) embeddedFromPacks.push({ uuid: cf.uuid, itemType: "complexform" });
  for (const r of state.rituals) embeddedFromPacks.push({ uuid: r.uuid, itemType: "ritual" });
  for (const f of state.foci) embeddedFromPacks.push({ uuid: f.uuid, itemType: "focus" });

  /* ---- synthetic items, continued ---- */
  for (const c of state.contacts) {
    syntheticItems.push({
      name: c.name || "Contact", type: "contact",
      system: { rating: c.connection, loyalty: c.loyalty,
                type: c.archetype ?? c.archetypeId ?? "", description: "" },
    });
  }
  for (const sin of state.sins) {
    const lic = (sin.licenses ?? []).map((l) =>
      (typeof l === "object" ? `${l.name} (R${l.rating ?? 1})` : String(l)));
    syntheticItems.push({
      name: sin.name || (sin.kind === "real" ? "Real SIN" : "Fake SIN"), type: "sin",
      system: {
        // eden stores the SIN's quality rating; a real SIN has no forged
        // rating, so it records as 6 — nothing verifies better than the truth
        quality: String(sin.kind === "real" ? 6 : (sin.rating ?? 1)),
        description: [
          sin.kind === "real" ? "Real SIN." : `Fake SIN, rating ${sin.rating ?? 1}.`,
          lic.length ? `Licences: ${lic.join(", ")}.` : "",
        ].filter(Boolean).join(" "),
      },
    });
  }
  if (state.lifestyleId) {
    const ls = data.lifestyles?.[state.lifestyleId] ?? {};
    syntheticItems.push({
      name: ls.name ?? state.lifestyleId, type: "lifestyle",
      system: { type: state.lifestyleId, cost: ls.cost ?? 0,
                paid: state.lifestyleMonths ?? 1 },
    });
  }
  for (const k of state.knowledge) {
    // Eden keys an item's localisation and icon off `<type>.<catalogId>` in
    // preCreateItem, so a knowledge skill written with a bare `catalogId`
    // arrives with eden's field empty and is looked up as "skill." — set it
    // through the boundary helper, which knows the real field name.
    syntheticItems.push({
      name: k.name, type: "skill",
      system: setCatalogId({ points: k.native ? 4 : (k.points ?? 1) }, k.type),
    });
  }

  return {
    actorData: {
      name: state.name || "New Runner",
      type: "Player",
      system,
      flags: {
        "sr6-forge": {
          metatypeId: state.metatypeId,
          method: state.method,
          rulesetId: state.rulesetId,
          chargen: structuredClone(state),
          ledger: [{
            ts: Date.now(), phase: "creation", op: "create",
            karma: rules.startingKarma.value - Math.max(0, budgets.karma.left),
            nuyen: budgets.nuyen.max - Math.max(0, budgets.nuyen.left),
            note: `Created via ${state.method} (${state.rulesetId})`,
          }],
        },
      },
    },
    embeddedFromPacks,
    syntheticItems,
    effects: [],
  };
}
