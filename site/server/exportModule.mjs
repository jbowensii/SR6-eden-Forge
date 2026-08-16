import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { compilePack } from "@foundryvtt/foundryvtt-cli";
import { toFoundryDoc } from "../shared/edenTransform.mjs";
import { EDEN } from "../shared/edenSpec.mjs";


export function loadBooks(dataRoot) {
  try {
    return JSON.parse(readFileSync(join(dataRoot, "books.json"), "utf8"));
  } catch {
    return {};
  }
}

const ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

export function docId(book, domain, itemId) {
  const digest = createHash("sha1").update(`${book}/${domain}/${itemId}`).digest();
  let out = "";
  for (let i = 0; i < 16; i++) out += ALNUM[digest[i] % ALNUM.length];
  return out;
}

export function statusAllows(filter, qaStatus) {
  if (filter === "all") return true;
  if (filter === "reviewed") return qaStatus === "reviewed" || qaStatus === "approved";
  return qaStatus === "approved";
}

// domains that become Foundry Actors (compendium type "Actor", key prefix
// !actors!) rather than Items. Everything else is an Item.
export const ACTOR_DOMAINS = new Set(["npcs", "critters", "spirits", "vehicles"]);

// Domains that are CONFIGURATION, not content, and are never packaged.
//
// commlink6_extra holds 853 records that never fit an item domain: the
// character-creation machinery (priorities, metatypes, lifepaths, starting-gear
// packs) and the rules lookup tables the system reads. They are settings. The
// chargen module reads them in code from chargen-data.json; a player never drags
// one onto a sheet, and no Eden document type exists for them — which is exactly
// why the first real export died here with an empty database key.
export const CONFIG_DOMAINS = new Set(["commlink6_extra"]);

/** Display name of the generated compendium module. The generator that reads
 *  it is SR6 Forge; this is the library it reads FROM, and naming it after the
 *  setting rather than the tool says what it holds. */
export const CATALOG_NAME = "Shadowrun 6th World Catalog";

export function buildManifest({ book, version, packs, title }) {
  return {
    id: `sr6-forge-${book}`,
    title: title ?? `${CATALOG_NAME} — ${book}`,
    description: "Shadowrun 6th World game data, extracted from books you own. Personal use only — not for distribution.",
    version,
    compatibility: { minimum: "13", verified: "14" },
    authors: [{ name: "SR6-eden-Forge" }],
    // each pack carries its own type ("Item" default, "Actor" for actor domains)
    packs: packs.map((p) => ({ name: p.name, label: p.label, path: p.path,
      type: p.type ?? "Item", system: "shadowrun6-eden" })),
    relationships: { systems: [{ id: "shadowrun6-eden", type: "system", compatibility: {} }] },
  };
}

// Build the Foundry documents (+ referenced icon files) for one domain.
export function buildDocs(dataRoot, book, domain, status, { product } = {}) {
  const domainDir = join(dataRoot, book, domain);
  const files = readdirSync(domainDir).filter((f) => f.endsWith(".json")).sort();
  const isActor = ACTOR_DOMAINS.has(domain);
  const moduleId = `sr6-forge-${book}`;
  const docs = [];
  const icons = new Map();
  const seen = new Map();
  const skipped = [];
  for (const file of files) {
    const payload = JSON.parse(readFileSync(join(domainDir, file), "utf8"));
    for (const item of payload.items ?? []) {
      if (item.meta?.hidden) continue;
      if (!statusAllows(status, item.meta?.qaStatus)) continue;
      // A repeated id is not a defect. Commlink6 carries every book, books
      // reprint material, and two PDFs printing the same item legitimately
      // produce two rows sharing one id — 93 ids in the library do. That is
      // right for the library, which should keep every printing, and fatal for
      // a compendium, where the id IS the primary key and the second row
      // silently overwrites the first.
      //
      // So: keep one, skip the rest, and name every skip. A silent dedupe is
      // how you lose a row that was never really a duplicate.
      if (seen.has(item.id)) {
        skipped.push({ id: item.id, name: item.name, kept: seen.get(item.id), from: file });
        continue;
      }
      seen.set(item.id, file);
      const _id = docId(book, domain, item.id);
      const doc = {
        _id,
        _key: `${isActor ? "!actors!" : "!items!"}${_id}`,
        ...toFoundryDoc(item, { product, domain }),
        folder: null,
        sort: 0,
        ownership: { default: 0 },
        _stats: { coreVersion: "13" },
      };
      if (item.img && !/^(icons|systems|modules)\//.test(item.img)) {
        const source = join(dataRoot, "_assets", item.img);
        if (existsSync(source)) {
          const rel = `icons/${item.img.replace(/\\/g, "/")}`;
          icons.set(rel, source);
          doc.img = `modules/${moduleId}/${rel}`;
        } else {
          doc.img = isActor ? "icons/svg/mystery-man.svg" : "icons/svg/item-bag.svg";
        }
      }
            // Embedded documents need a key of their own.
      //
      // compilePack walks the hierarchy — applyHierarchy recurses into `effects`
      // — and reads doc._key on EVERY document it reaches, embedded ones
      // included. We stamped the item and stopped there, so all 356 ActiveEffects
      // imported from Commlink6 arrived with no key and compilePack rejected the
      // first one it met: "Key cannot be null or undefined". Every domain built
      // clean documents; the failure was one level down, which is why three
      // theories about handles, unknown domains and duplicate ids all missed it.
      //
      // Foundry's pack convention is !<parent>.<embedded>!<parentId>.<childId>.
      // The child id is derived from the parent and the effect's position, so it
      // is stable across exports rather than random each time.
      if (Array.isArray(doc.effects)) {
        doc.effects.forEach((fx, n) => {
          const fxId = docId(book, `${domain}.effect.${n}`, item.id);
          fx._id = fxId;
          fx._key = `${isActor ? "!actors" : "!items"}.effects!${_id}.${fxId}`;
        });
      }
      docs.push(doc);
    }
  }
  return { docs, icons, isActor, skipped };
}

export async function exportModule(dataRoot, exportRoot, { book, domain, status = "approved", version = "0.1.0" }) {
  const domainDir = join(dataRoot, book, domain);
  let files;
  try {
    files = readdirSync(domainDir).filter((f) => f.endsWith(".json")).sort();
  } catch {
    throw new Error(`no such domain ${book}/${domain} under ${dataRoot}`);
  }

  const product = loadBooks(dataRoot)[book]?.title;
  const moduleId = `sr6-forge-${book}`;
  const docs = [];
  const icons = new Map(); // module-relative icon path -> absolute source path
  const seen = new Map();
  for (const file of files) {
    const payload = JSON.parse(readFileSync(join(domainDir, file), "utf8"));
    for (const item of payload.items ?? []) {
      if (item.meta?.hidden) continue;
      if (!statusAllows(status, item.meta?.qaStatus)) continue;
      if (seen.has(item.id)) {
        throw new Error(`duplicate item id "${item.id}" in ${file} (also in ${seen.get(item.id)})`);
      }
      seen.set(item.id, file);
      const _id = docId(book, domain, item.id);
      const doc = {
        _id,
        _key: `!items!${_id}`,
        ...toFoundryDoc(item, { product, domain }),
        folder: null,
        sort: 0,
        ownership: { default: 0 },
        _stats: { coreVersion: "13" },
      };
      // item.img relative to data/_assets/ gets bundled into the module;
      // the full relative path is preserved so same-named files in different
      // subfolders cannot collide
      if (item.img && !/^(icons|systems|modules)\//.test(item.img)) {
        const source = join(dataRoot, "_assets", item.img);
        if (existsSync(source)) {
          const rel = `icons/${item.img.replace(/\\/g, "/")}`;
          icons.set(rel, source);
          doc.img = `modules/${moduleId}/${rel}`;
        } else {
          console.warn(`missing asset for ${item.id}: ${source} — using default icon`);
          doc.img = "icons/svg/item-bag.svg";
        }
      }
      docs.push(doc);
    }
  }
  if (!docs.length) throw new Error(`no items match status "${status}" in ${book}/${domain}`);

  const moduleDir = join(exportRoot, moduleId);
  const stagingDir = join(exportRoot, `.staging-${moduleId}`);
  rmSync(stagingDir, { recursive: true, force: true });

  const packName = `${book}-${domain}`;
  try {
    const packDir = join(stagingDir, "packs", domain);
    mkdirSync(packDir, { recursive: true });

    const srcDir = mkdtempSync(join(tmpdir(), "forge-packsrc-"));
    try {
      for (const doc of docs) writeFileSync(join(srcDir, `${doc._id}.json`), JSON.stringify(doc, null, 2));
      await compilePack(srcDir, packDir, { log: false });
    } finally {
      rmSync(srcDir, { recursive: true, force: true });
    }

    for (const [rel, source] of icons) {
      const dest = join(stagingDir, rel);
      mkdirSync(dirname(dest), { recursive: true });
      copyFileSync(source, dest);
    }

    const manifest = buildManifest({
      book,
      version,
      packs: [{ name: packName, label: `${product ?? book} ${domain}`, path: `packs/${domain}` }],
    });
    writeFileSync(join(stagingDir, "module.json"), JSON.stringify(manifest, null, 2) + "\n");

    rmSync(moduleDir, { recursive: true, force: true });
    renameSync(stagingDir, moduleDir);
  } catch (err) {
    // Tidying up must never outrank the reason we are here. This rmSync threw
    // EPERM on Windows — a handle still open under the staging directory — and
    // because it sat bare in the catch, it REPLACED the original error and
    // `throw err` never ran. Every run reported a permission problem on a temp
    // folder while the actual failure went unseen.
    try {
      rmSync(stagingDir, { recursive: true, force: true });
    } catch (cleanupErr) {
      console.error(`could not remove ${stagingDir}: ${cleanupErr.message}`);
    }
    throw err;
  }

  return { moduleDir, count: docs.length, packName };
}


// Export EVERY domain of a book into a single module: one compendium pack per
// domain, Item or Actor typed. Used for the full Foundry compatibility test.
export async function exportAll(dataRoot, exportRoot, { book, status = "all", version = "0.1.0" } = {}) {
  const bookDir = join(dataRoot, book);
  const domains = readdirSync(bookDir)
    .filter((d) => !d.startsWith("_") && /^[a-z0-9_]+$/.test(d))
    .filter((d) => { try { return statSync(join(bookDir, d)).isDirectory(); } catch { return false; } })
    .sort();
  const product = loadBooks(dataRoot)[book]?.title;
  const moduleId = `sr6-forge-${book}`;
  const moduleDir = join(exportRoot, moduleId);
  const stagingDir = join(exportRoot, `.staging-${moduleId}`);
  rmSync(stagingDir, { recursive: true, force: true });

  const packs = [];
  const allIcons = new Map();
  const perDomain = {};
  try {
    for (const domain of domains) {
      if (CONFIG_DOMAINS.has(domain)) {
        console.log(`  skipping ${domain} — configuration, not compendium content`);
        continue;
      }
      if (!EDEN[domain]) { perDomain[domain] = { skipped: "no Eden mapping (site-only)" }; continue; }
      let built;
      try {
        built = buildDocs(dataRoot, book, domain, status, { product });
      } catch (err) {
        perDomain[domain] = { error: String(err.message ?? err) };
        continue;
      }
      if (!built.docs.length) { perDomain[domain] = { count: 0 }; continue; }
      const packDir = join(stagingDir, "packs", domain);
      mkdirSync(packDir, { recursive: true });
      const srcDir = mkdtempSync(join(tmpdir(), "forge-packsrc-"));
      try {
        for (const doc of built.docs) writeFileSync(join(srcDir, `${doc._id}.json`), JSON.stringify(doc, null, 2));
        await compilePack(srcDir, packDir, { log: false });
      } finally {
        rmSync(srcDir, { recursive: true, force: true });
      }
      for (const [rel, source] of built.icons) allIcons.set(rel, source);
      if (built.skipped?.length) {
        console.log(`  ${domain}: kept 1 of each repeated id, skipped ${built.skipped.length}`);
        for (const s of built.skipped.slice(0, 5)) {
          console.log(`      ${s.id}  "${s.name}"  (kept the copy in ${s.kept})`);
        }
        if (built.skipped.length > 5) console.log(`      ... and ${built.skipped.length - 5} more`);
      }
      packs.push({ name: `${book}-${domain}`, label: `${product ?? book} — ${domain}`,
        path: `packs/${domain}`, type: built.isActor ? "Actor" : "Item" });
      perDomain[domain] = { count: built.docs.length, type: built.isActor ? "Actor" : "Item" };
    }
    if (!packs.length) throw new Error(`no exportable documents in ${book} (status "${status}")`);

    for (const [rel, source] of allIcons) {
      const dest = join(stagingDir, rel);
      mkdirSync(dirname(dest), { recursive: true });
      copyFileSync(source, dest);
    }
    const manifest = buildManifest({ book, version, packs,
      title: `${CATALOG_NAME} — ${product ?? book}` });
    writeFileSync(join(stagingDir, "module.json"), JSON.stringify(manifest, null, 2) + "\n");
    rmSync(moduleDir, { recursive: true, force: true });
    renameSync(stagingDir, moduleDir);
  } catch (err) {
    // Tidying up must never outrank the reason we are here. This rmSync threw
    // EPERM on Windows — a handle still open under the staging directory — and
    // because it sat bare in the catch, it REPLACED the original error and
    // `throw err` never ran. Every run reported a permission problem on a temp
    // folder while the actual failure went unseen.
    try {
      rmSync(stagingDir, { recursive: true, force: true });
    } catch (cleanupErr) {
      console.error(`could not remove ${stagingDir}: ${cleanupErr.message}`);
    }
    throw err;
  }
  return { moduleDir, packs: packs.length, perDomain };
}
