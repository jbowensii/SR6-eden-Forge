import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { compilePack } from "@foundryvtt/foundryvtt-cli";
import { toFoundryDoc } from "../shared/edenTransform.mjs";

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
  const docs = [];
  for (const file of readdirSync(domainDir).filter((f) => f.endsWith(".json")).sort()) {
    const payload = JSON.parse(readFileSync(join(domainDir, file), "utf8"));
    for (const item of payload.items ?? []) {
      if (!statusAllows(status, item.meta?.qaStatus)) continue;
      const _id = docId(book, domain, item.id);
      docs.push({
        _id,
        _key: `!items!${_id}`,
        ...toFoundryDoc(item),
        folder: null,
        sort: 0,
        ownership: { default: 0 },
        _stats: { coreVersion: "13" },
      });
    }
  }
  if (!docs.length) throw new Error(`no items match status "${status}" in ${book}/${domain}`);

  const moduleDir = join(exportRoot, `sr6-forge-${book}`);
  const packDir = join(moduleDir, "packs", domain);
  mkdirSync(packDir, { recursive: true });

  const srcDir = mkdtempSync(join(tmpdir(), "forge-packsrc-"));
  try {
    for (const doc of docs) writeFileSync(join(srcDir, `${doc._id}.json`), JSON.stringify(doc, null, 2));
    await compilePack(srcDir, packDir, { log: false });
  } finally {
    rmSync(srcDir, { recursive: true, force: true });
  }

  const packName = `${book}-${domain}`;
  const manifest = buildManifest({
    book,
    version,
    packs: [{ name: packName, label: `${book} ${domain}`, path: `packs/${domain}` }],
  });
  writeFileSync(join(moduleDir, "module.json"), JSON.stringify(manifest, null, 2) + "\n");
  return { moduleDir, count: docs.length, packName };
}
