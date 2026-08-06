/** Turn a ChargenEngine commit plan into a live eden Player actor.
 *
 *  Raw inputs only. Eden derives everything else in Shadowrun6Actor.prepareData:
 *  attribute pools as `max(0, base + min(4, mod))`, the condition monitors, and
 *  essence from gear. We must never write those.
 *
 *  Items go through createEmbeddedDocuments rather than being stuffed into the
 *  actor's creation data, so eden's `preCreateItem` hook runs on each one — it
 *  swaps in the system icon for the item's type and, when a translation exists
 *  for `<type>.<catalogId>`, replaces the name and description with eden's
 *  localized text.
 *
 *  Rollback deletes the actor on any failure. */
import { MODULE_ID, FLAGS } from "../config.mjs";
import { PackCatalog } from "./pack-catalog.mjs";

const QUALITY_DOMAINS = ["qualities"];

/** Where to look for a grant that names a catalog id but carries no uuid —
 *  PACK contents are recipes referencing gear by id, so they resolve here. */
const GRANT_DOMAINS = ["qualities", "gear", "vehicles", "foci", "spells", "adept_powers"];

async function resolveGrantDocs(plan) {
  const itemData = [];
  for (const grant of plan.embeddedFromPacks) {
    let doc = null;
    if (grant.uuid) {
      doc = await fromUuid(grant.uuid);
    } else if (grant.catalogId) {
      // a quality grant knows its domain; a PACK's contents do not, so widen
      const domains = grant.itemType === "quality" ? QUALITY_DOMAINS : GRANT_DOMAINS;
      const row = await PackCatalog.findByCatalogId(grant.catalogId, domains);
      if (row) doc = await fromUuid(row.uuid);
    }
    if (!doc) {
      console.warn(`sr6-forge | grant not found`, grant);
      continue;
    }
    const obj = doc.toObject();
    delete obj._id;
    const { choiceText, ...overrides } = grant.overrides ?? {};
    if (choiceText) obj.name = `${obj.name} (${choiceText})`;
    for (const [path, value] of Object.entries(overrides)) {
      if (value === null) continue;
      foundry.utils.setProperty(obj, path, value);
    }
    itemData.push(obj);
  }
  return itemData;
}

/**
 * @param {object} plan                 ChargenEngine#commitPlan() output
 * @param {object} [opts]
 * @param {object} [opts.engineState]   frozen chargen state, kept on the actor
 *   so a finished character can still say how it was built (and so advancement
 *   can tell creation spends apart from later ones)
 * @returns {Promise<Actor>}
 */
export async function commitCharacter(plan, { engineState = null } = {}) {
  const actorData = foundry.utils.deepClone(plan.actorData);
  if (engineState) {
    foundry.utils.setProperty(actorData, `flags.${MODULE_ID}.${FLAGS.CHARGEN}`, engineState);
    foundry.utils.setProperty(actorData, `flags.${MODULE_ID}.${FLAGS.METATYPE_ID}`,
      engineState.metatypeId ?? null);
  }
  const actor = await Actor.create(actorData);
  try {
    const fromPacks = await resolveGrantDocs(plan);
    const itemData = [...fromPacks, ...plan.syntheticItems];
    if (itemData.length) await actor.createEmbeddedDocuments("Item", itemData);
    if (plan.effects?.length) await actor.createEmbeddedDocuments("ActiveEffect", plan.effects);
    return actor;
  } catch (err) {
    console.error("sr6-forge | commit failed, rolling back", err);
    await actor.delete();
    throw err;
  }
}
