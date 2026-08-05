/** Turn a ChargenEngine commit plan into a live eden Player actor.
 *  Raw inputs only — eden's prepareData derives pools/monitors/essence.
 *  Items are embedded via createEmbeddedDocuments so eden's preCreateItem
 *  genesisID enrichment runs. Rollback deletes the actor on any failure. */
import { MODULE_ID, FLAGS } from "../config.mjs";
import { PackCatalog } from "./pack-catalog.mjs";

const QUALITY_DOMAINS = ["qualities"];

async function resolveGrantDocs(plan) {
  const itemData = [];
  for (const grant of plan.embeddedFromPacks) {
    let doc = null;
    if (grant.uuid) {
      doc = await fromUuid(grant.uuid);
    } else if (grant.genesisID) {
      const row = await PackCatalog.findByGenesisId(grant.genesisID, QUALITY_DOMAINS);
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
