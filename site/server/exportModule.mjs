import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { compilePack } from "@foundryvtt/foundryvtt-cli";
import { toFoundryDoc } from "../shared/edenTransform.mjs";


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

export function buildManifest({ book, version, packs }) {
  return {
    id: `sr6-forge-${book}`,
    title: `SR6 Forge — ${book} gear`,
    description: "Personal-use compendium built with SR6-eden-Forge. Not for distribution.",
    version,
    compatibility: { minimum: "13", verified: "13" },
    authors: [{ name: "SR6-eden-Forge" }],
    packs: packs.map((p) => ({ ...p, type: "Item", system: "shadowrun6-eden" })),
    relationships: { systems: [{ id: "shadowrun6-eden", type: "system", compatibility: {} }] },
  };
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
      if (!statusAllows(status, item.meta?.qaStatus)) continue;
      if (seen.has(item.id)) {
        throw new Error(`duplicate item id "${item.id}" in ${file} (also in ${seen.get(item.id)})`);
      }
      seen.set(item.id, file);
      const _id = docId(book, domain, item.id);
      const doc = {
        _id,
        _key: `!items!${_id}`,
        ...toFoundryDoc(item, { product }),
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
    rmSync(stagingDir, { recursive: true, force: true });
    throw err;
  }

  return { moduleDir, count: docs.length, packName };
}
