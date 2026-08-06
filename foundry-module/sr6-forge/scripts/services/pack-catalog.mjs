/** Compendium catalog: cached indices over every sr6-forge-* data-module pack,
 *  keyed by domain (pack name suffix). Browse lists render from index rows;
 *  full documents are fetched only on add. */
import { DATA_PACKAGE_PREFIX, EXTRA_INDEX_FIELDS, catalogIdOf } from "../config.mjs";

const cache = new Map();          // packCollection -> index (Array of rows)

function forgePacks() {
  return game.packs.filter((p) =>
    p.metadata.packageName?.startsWith(DATA_PACKAGE_PREFIX)
    && p.metadata.type === "Item");
}

/** domain = trailing segment of the pack name ("corebook-gear" -> "gear"). */
function domainOf(pack) {
  const name = pack.metadata.name ?? "";
  return name.split("-").slice(1).join("-") || name;
}

export const PackCatalog = {
  /** [{pack, domain}] for all connected forge data packs. */
  list() {
    return forgePacks().map((pack) => ({ pack, domain: domainOf(pack) }));
  },

  /** Merged, cached index rows for one domain across all forge packs.
   *  Rows carry {_id, uuid, name, type, system.{...index fields}}. */
  async index(domain) {
    const rows = [];
    for (const { pack, domain: d } of this.list()) {
      if (d !== domain) continue;
      if (!cache.has(pack.collection)) {
        // explicit dotted paths only — getIndex merges these with the pack's
        // configured indexFields (which already include eden's catalog field)
        const idx = await pack.getIndex({ fields: EXTRA_INDEX_FIELDS });
        cache.set(pack.collection, idx.contents.map((r) => ({
          ...r, uuid: `Compendium.${pack.collection}.Item.${r._id}`,
        })));
      }
      rows.push(...cache.get(pack.collection));
    }
    return rows;
  },

  /** Find one index row by catalogId across the given domain(s). */
  async findByCatalogId(catalogId, domains = ["qualities"]) {
    for (const d of domains) {
      const rows = await this.index(d);
      const hit = rows.find((r) => catalogIdOf(r) === catalogId);
      if (hit) return hit;
    }
    return null;
  },

  invalidate() { cache.clear(); },
};
