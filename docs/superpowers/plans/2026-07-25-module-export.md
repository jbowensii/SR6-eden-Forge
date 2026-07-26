# Module Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn reviewed data into an installable Foundry VTT module: canonical items → Foundry Item documents → LevelDB compendium pack via `@foundryvtt/foundryvtt-cli` → `export/sr6-forge-<book>/` with `module.json`, runnable as a CLI script and from a button in the review app.

**Architecture:** `site/server/exportModule.mjs` owns the whole pipeline (filter by qaStatus → `toFoundryDoc` from `site/shared/` → deterministic 16-char `_id`s → pack source JSON → `compilePack`). A thin CLI (`site/scripts/export.mjs`) and a `POST /api/export` route both call it. Round-trip integrity is tested with `extractPack`.

**Tech Stack:** Node 20+, `@foundryvtt/foundryvtt-cli` (adds `classic-level` transitively), existing vitest setup.

## Global Constraints

- Module id: `sr6-forge-<book>`; title `SR6 Forge — <book> gear`; version from `--version` (default `0.1.0`); `compatibility: {minimum: "13", verified: "13"}`; one pack per domain: `{name: "<book>-<domain>", label: "<Book> <Domain>", path: "packs/<domain>", type: "Item", system: "shadowrun6-eden"}`; `relationships.systems = [{id: "shadowrun6-eden", type: "system", compatibility: {}}]`.
- Document `_id`: deterministic 16 chars `[a-zA-Z0-9]` derived from `sha1(book + "/" + domain + "/" + item.id)` (hex digest → take chars, map to alphanumerics by re-hashing if needed — implementation below uses hex digest transformed: first 16 of base36 of the digest int — must match `/^[a-zA-Z0-9]{16}$/`).
- Foundry doc envelope adds to `toFoundryDoc` output: `_id`, `folder: null`, `sort: 0`, `ownership: {default: 0}`, `_stats: {coreVersion: "13"}`, `_key: "!items!<_id>"` (the `_key` field is required by foundryvtt-cli pack sources).
- Status filter: `approved` (default) | `reviewed` (means reviewed+approved) | `all`. Exporting zero items is an error (exit/throw) naming the filter.
- Export output is gitignored (`export/` already is). **Never distributed** — reinforce in README.
- Tests: invented items only; pack round-trip via `extractPack` into a temp dir.
- Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File Structure

```
site/server/exportModule.mjs   ← docId(), buildManifest(), exportModule()
site/scripts/export.mjs        ← CLI wrapper
site/tests/export.test.mjs
site/server/app.mjs            ← MODIFY: POST /api/export (injected exporter)
site/tests/api.test.mjs        ← MODIFY: export route tests
site/src/App.jsx               ← MODIFY: Export button + status line
README.md                      ← MODIFY: export usage + status
```

---

### Task 1: Export core

**Files:**
- Create: `site/server/exportModule.mjs`, `site/tests/export.test.mjs`
- Modify: `site/package.json` (dependency `@foundryvtt/foundryvtt-cli@^3`)

**Interfaces:**
- `docId(book, domain, itemId) -> string` — 16 chars, `/^[a-zA-Z0-9]{16}$/`, deterministic.
- `statusAllows(filter, qaStatus) -> bool` — `approved`→only approved; `reviewed`→reviewed|approved; `all`→everything.
- `buildManifest({book, version, packs}) -> object` per Global Constraints.
- `async exportModule(dataRoot, exportRoot, {book, domain, status = "approved", version = "0.1.0"}) -> {moduleDir, count, packName}` — reads every category in `dataRoot/<book>/<domain>/`, filters, maps to docs (with `_id`/`_key`/envelope), throws `Error("no items match status ...")` on empty, writes pack sources to a temp dir, `compilePack(srcDir, join(moduleDir, "packs", domain))`, writes `module.json`.

- [ ] **Step 1:** `cd site && npm install @foundryvtt/foundryvtt-cli` (network; BLOCKED on failure).
- [ ] **Step 2: Failing tests** — `site/tests/export.test.mjs`:

```javascript
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { extractPack } from "@foundryvtt/foundryvtt-cli";
import { describe, expect, it } from "vitest";
import { buildManifest, docId, exportModule, statusAllows } from "../server/exportModule.mjs";

function item(id, qaStatus, price = 100) {
  return {
    id,
    name: id.replace(/_/g, " "),
    system: { type: "WEAPON_FIREARMS", price },
    meta: { book: "testbook", page: 1, extractedAt: "2026-07-25", extractorVersion: "0.1.0", qaStatus },
  };
}

function seed(items) {
  const root = mkdtempSync(join(tmpdir(), "forge-exp-"));
  const dir = join(root, "testbook", "gear");
  mkdirSync(dir, { recursive: true });
  writeFileSync(
    join(dir, "weapons_firearms.json"),
    JSON.stringify({ book: "testbook", domain: "gear", category: "weapons_firearms", items }, null, 2) + "\n",
  );
  return root;
}

describe("export", () => {
  it("docId is deterministic, 16 alphanumerics", () => {
    const a = docId("corebook", "gear", "example_autopistol");
    expect(a).toMatch(/^[a-zA-Z0-9]{16}$/);
    expect(docId("corebook", "gear", "example_autopistol")).toBe(a);
    expect(docId("corebook", "gear", "other")).not.toBe(a);
  });

  it("statusAllows tiers", () => {
    expect(statusAllows("approved", "approved")).toBe(true);
    expect(statusAllows("approved", "reviewed")).toBe(false);
    expect(statusAllows("reviewed", "reviewed")).toBe(true);
    expect(statusAllows("reviewed", "extracted")).toBe(false);
    expect(statusAllows("all", "extracted")).toBe(true);
  });

  it("manifest shape", () => {
    const m = buildManifest({ book: "testbook", version: "1.2.3", packs: [{ name: "testbook-gear", label: "Testbook Gear", path: "packs/gear" }] });
    expect(m.id).toBe("sr6-forge-testbook");
    expect(m.version).toBe("1.2.3");
    expect(m.compatibility).toEqual({ minimum: "13", verified: "13" });
    expect(m.packs[0]).toMatchObject({ type: "Item", system: "shadowrun6-eden" });
    expect(m.relationships.systems[0].id).toBe("shadowrun6-eden");
  });

  it("exportModule filters by status and round-trips through the pack", async () => {
    const root = seed([item("gun_a", "approved"), item("gun_b", "extracted")]);
    const out = mkdtempSync(join(tmpdir(), "forge-out-"));
    const res = await exportModule(root, out, { book: "testbook", domain: "gear" });
    expect(res.count).toBe(1);
    const manifest = JSON.parse(readFileSync(join(res.moduleDir, "module.json"), "utf8"));
    expect(manifest.id).toBe("sr6-forge-testbook");
    const unpacked = mkdtempSync(join(tmpdir(), "forge-un-"));
    await extractPack(join(res.moduleDir, "packs", "gear"), unpacked);
    const files = (await import("node:fs")).readdirSync(unpacked);
    expect(files).toHaveLength(1);
    const doc = JSON.parse(readFileSync(join(unpacked, files[0]), "utf8"));
    expect(doc.name).toBe("gun a");
    expect(doc.type).toBe("gear");
    expect(doc._id).toMatch(/^[a-zA-Z0-9]{16}$/);
    expect(doc.system.price).toBe(100);
    expect(doc.system.genesisID).toBe("gun_a");
  });

  it("exportModule throws when nothing matches", async () => {
    const root = seed([item("gun_b", "extracted")]);
    const out = mkdtempSync(join(tmpdir(), "forge-out2-"));
    await expect(exportModule(root, out, { book: "testbook", domain: "gear" })).rejects.toThrow(/no items match/);
  });
});
```

- [ ] **Step 3: FAIL.** **Step 4: Implement** `site/server/exportModule.mjs`:

```javascript
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
```

- [ ] **Step 5: PASS** — `npm test` → 24 site tests. Commit `feat: module export core (docs, manifest, LevelDB pack)` (+ trailer, incl. package-lock).

---

### Task 2: CLI + API route + UI button

**Files:**
- Create: `site/scripts/export.mjs`
- Modify: `site/server/app.mjs` (inject `exporter` option; `POST /api/export` body `{book, domain, status, version}` → 200 `{moduleDir, count, packName}`, 400 on missing/invalid segments or unknown status, 409 with the error message on "no items match", 500 otherwise), `site/server/index.mjs` (pass real exporter bound to repo `data/`+`export/`), `site/src/App.jsx` + `site/src/api.js` (Export button beside Validate: exports the SELECTED book/domain with status `all` for now via prompt-free default; show result in status line), `site/tests/api.test.mjs` (+3 tests with injected fake exporter: success, 409 empty, 400 bad status).

`site/scripts/export.mjs`:

```javascript
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { parseArgs } from "node:util";
import { exportModule } from "../server/exportModule.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");
const { values } = parseArgs({
  options: {
    book: { type: "string" },
    domain: { type: "string", default: "gear" },
    status: { type: "string", default: "approved" },
    version: { type: "string", default: "0.1.0" },
  },
});
if (!values.book) {
  console.error("usage: node site/scripts/export.mjs --book corebook [--domain gear] [--status approved|reviewed|all] [--version x.y.z]");
  process.exit(2);
}
try {
  const res = await exportModule(join(repoRoot, "data"), join(repoRoot, "export"), values);
  console.log(`exported ${res.count} item(s) -> ${res.moduleDir}`);
} catch (err) {
  console.error(String(err.message ?? err));
  process.exit(1);
}
```

API tests to append (fake exporter):

```javascript
  it("POST /api/export happy path", async () => {
    const app = makeAppWithExporter(async () => ({ moduleDir: "X", count: 3, packName: "corebook-gear" }));
    const res = await request(app).post("/api/export").send({ book: "corebook", domain: "gear", status: "all" });
    expect(res.status).toBe(200);
    expect(res.body.count).toBe(3);
  });

  it("POST /api/export empty -> 409", async () => {
    const app = makeAppWithExporter(async () => {
      throw new Error("no items match status \"approved\" in corebook/gear");
    });
    const res = await request(app).post("/api/export").send({ book: "corebook", domain: "gear" });
    expect(res.status).toBe(409);
  });

  it("POST /api/export bad status -> 400", async () => {
    const app = makeAppWithExporter(async () => ({}));
    const res = await request(app).post("/api/export").send({ book: "corebook", domain: "gear", status: "everything" });
    expect(res.status).toBe(400);
  });
```

(`makeAppWithExporter` mirrors `makeApp` but passes `{schemasDir, validate, exporter}`.) Route logic: validate SEGMENT on book/domain, status ∈ {approved, reviewed, all} (default approved), version optional string; call `exporter({book, domain, status, version})`; catch: message starts with "no items match" → 409, else 500.

App.jsx: add beside Validate: `<button onClick={runExport} disabled={!selected}>Export…</button>`; `runExport` calls `api.exportModule(selected.book, selected.domain, "all")` and sets status to `exported N item(s) -> <dir>` or `error: ...` (try/catch). `api.js`: `export const exportModule = (book, domain, status) => fetch("/api/export", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({book, domain, status})}).then(json);`

- [ ] Tests RED → implement → `npm test` 27 passed → `npm run build` green → Commit `feat: export CLI, API route, UI button` (+ trailer).

---

### Task 3: Real export + docs (controller)

- [ ] Controller runs `node site/scripts/export.mjs --book corebook --status all` (nothing is approved yet — `all` proves the pipeline; the QA pass will re-export with `approved` later), inspects `export/sr6-forge-corebook/` (module.json + packs/gear LevelDB files), spot-verifies contents via `extractPack` (463 docs, sample doc field check).
- [ ] README: "Exporting a module" section — CLI + button, install instructions (copy `export/sr6-forge-corebook` into the Foundry server's `Data/modules/`, enable in world, items appear in the compendium tab), never-distribute reminder; Status checklist complete.
- [ ] Commit `docs: module export usage` (+ trailer); push.

## Self-Review Notes

- `_key` is required by foundryvtt-cli source JSON; missing it makes compilePack skip docs silently — the round-trip test guards this.
- docId collisions: sha1 of distinct keys mapping to same 16 alnum chars is negligible; determinism means re-exports overwrite the same documents (stable UUIDs for links).
- Export root is `export/` (gitignored); repeated exports overwrite in place.
