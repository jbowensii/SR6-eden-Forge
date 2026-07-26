# Review Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local Node web app (`site/`) to browse, edit, QA, and validate the extracted data files, with a live preview of the exact Foundry/Eden document each item exports as.

**Architecture:** Express server exposing a small file-backed JSON API over `data/` (no database — every save is a `git diff`-able file write), plus a React (Vite) frontend. The canonical→Foundry transform lives in `site/shared/` so the browser preview and the future export pipeline share one implementation. Validation reuses the Python validator via subprocess with a new `--json` flag.

**Tech Stack:** Node 20+ (ESM), Express 4, Vite + React 18, Vitest + Supertest. No UI framework — plain CSS.

## Global Constraints

- All server file access is rooted at the repo's `data/` directory; API paths are validated against `^[a-z0-9_]+$` segments (no traversal).
- The canonical item shape is `{id, name, system{}, meta{}}` per `schemas/`; the Foundry document shape is `{name, type: "gear", img: "icons/svg/item-bag.svg", system: {...system fields...}, effects: [], flags: {}}` — `meta` is never exported; `system` passes through verbatim (Eden owns the field semantics).
- `qaStatus` transitions are unrestricted edits among `extracted|reviewed|approved` (workflow is advisory, not enforced).
- Item edits PUT the whole item; the server rewrites the category file with 2-space indent, `ensure_ascii`-equivalent OFF (UTF-8, no escaping), trailing newline — byte-compatible with the extractor's output format (`json.dumps(..., indent=2, ensure_ascii=False)` in Python ↔ `JSON.stringify(..., null, 2)` in Node; both write real UTF-8 characters).
- Tests use invented items only; server tests run against a temp data dir, never `data/corebook`.
- Python for the validate endpoint: `./.venv/Scripts/python` on Windows, `python3` fallback — resolve via `process.env.FORGE_PYTHON` first, then those candidates.
- Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Working directory: repo root; site commands run in `site/`.

## File Structure

```
validator/cli.py                  ← MODIFY: add --json flag
site/package.json                 ← ESM, scripts: dev/build/test/serve
site/vite.config.js               ← Vite + proxy /api → :8347
site/shared/edenTransform.mjs     ← toFoundryDoc(item) (shared browser/server)
site/server/store.mjs             ← tree(), readCategory(), writeItem()
site/server/pythonBridge.mjs      ← runValidator(dataRoot) -> issues[]
site/server/app.mjs               ← buildApp(dataRoot) Express app (no listen)
site/server/index.mjs             ← listen(8347), serves dist/ statically
site/tests/store.test.mjs
site/tests/transform.test.mjs
site/tests/api.test.mjs
site/src/main.jsx                 ← React root
site/src/App.jsx                  ← layout: sidebar + table + editor
site/src/api.js                   ← fetch helpers
site/src/components/Tree.jsx
site/src/components/CategoryTable.jsx
site/src/components/ItemEditor.jsx
site/src/components/Preview.jsx
site/src/styles.css
site/index.html
```

---

### Task 1: Validator `--json` output

**Files:**
- Modify: `validator/cli.py`
- Test: append to `tests/test_cli.py`

**Interfaces:**
- Produces: `python -m validator <path> --json` prints a single JSON object `{"ok": bool, "files": N, "items": N, "issues": [{"file","item_id","rule","message"}]}` to stdout (no other output) and keeps the same exit codes.

- [ ] **Step 1: Failing tests** — append to `tests/test_cli.py`:

```python
def test_json_output_clean(tmp_path, gear_file, capsys):
    import json as jsonlib

    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    assert main([str(tmp_path), "--json"]) == 0
    out = jsonlib.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["files"] == 1 and out["items"] == 1
    assert out["issues"] == []


def test_json_output_with_issues(tmp_path, gear_file, capsys):
    import json as jsonlib

    gear_file["items"][0]["system"]["dmgDef"] = "3X"
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    assert main([str(tmp_path), "--json"]) == 1
    out = jsonlib.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert out["issues"][0]["rule"] == "damage-format"
    assert out["issues"][0]["item_id"] == "example_autopistol"
```

- [ ] **Step 2: Run to verify FAIL** — `./.venv/Scripts/python -m pytest tests/test_cli.py -v` (unknown --json flag → SystemExit 2 → failures).

- [ ] **Step 3: Implement** — in `validator/cli.py`: add `parser.add_argument("--json", action="store_true")`; refactor `main` so issues/files/items are computed as today, then:

```python
    if args.json:
        import json as jsonlib
        from dataclasses import asdict

        print(jsonlib.dumps({
            "ok": not issues,
            "files": len(files),
            "items": item_count,
            "issues": [asdict(i) for i in issues],
        }))
        return 1 if issues else 0
```

(placed instead of `_report`/summary prints; the non-json path is unchanged). Keep exit code 2 path printing plain text.

- [ ] **Step 4: PASS** — full suite 81 passed.
- [ ] **Step 5: Commit** — `feat: validator --json output for tooling` (+ trailer).

---

### Task 2: Site scaffold + store module

**Files:**
- Create: `site/package.json`, `site/server/store.mjs`, `site/tests/store.test.mjs`, `site/.gitignore`

**Interfaces:**
- Produces (all paths are `{book, domain, category}` slugs, pre-validated by callers or rejected here):
  - `store.tree(dataRoot) -> [{book, domain, category, items: N, qa: {extracted: N, reviewed: N, approved: N}}]` — scans `dataRoot/<book>/<domain>/*.json`, skipping `_`-prefixed dirs (`_raw`, `_fixes`) and `README.md`.
  - `store.readCategory(dataRoot, book, domain, category) -> payload` (parsed envelope) — throws `StoreError('not-found')` / `StoreError('bad-segment')`.
  - `store.writeItem(dataRoot, book, domain, category, itemId, item) -> item` — replaces the item with matching `id` (404 if absent; the incoming `item.id` must equal `itemId`), writes the file (2-space indent, UTF-8, trailing `\n`), returns the stored item.
  - `SEGMENT = /^[a-z0-9_]+$/` exported for route validation.

- [ ] **Step 1: Scaffold**

`site/package.json`:

```json
{
  "name": "sr6-eden-forge-site",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "serve": "node server/index.mjs",
    "test": "vitest run"
  },
  "dependencies": {
    "express": "^4.19.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "supertest": "^7.0.0",
    "vite": "^5.4.0",
    "vitest": "^2.0.0"
  }
}
```

`site/.gitignore`:

```
node_modules/
dist/
```

Run `npm install` in `site/` (uses network; report failures rather than improvising).

- [ ] **Step 2: Failing tests** — `site/tests/store.test.mjs`:

```javascript
import { mkdtempSync, readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { SEGMENT, StoreError, readCategory, tree, writeItem } from "../server/store.mjs";

const ITEM = {
  id: "example_autopistol",
  name: "Example Autopistol",
  system: { type: "WEAPON_FIREARMS", price: 620 },
  meta: { book: "corebook", page: 1, extractedAt: "2026-07-25", extractorVersion: "0.1.0", qaStatus: "extracted" },
};

function seed() {
  const root = mkdtempSync(join(tmpdir(), "forge-"));
  const dir = join(root, "corebook", "gear");
  mkdirSync(dir, { recursive: true });
  mkdirSync(join(root, "_raw", "corebook"), { recursive: true });
  writeFileSync(
    join(dir, "weapons_firearms.json"),
    JSON.stringify({ book: "corebook", domain: "gear", category: "weapons_firearms", items: [ITEM] }, null, 2) + "\n",
  );
  return root;
}

describe("store", () => {
  it("tree lists categories with qa counts and skips _dirs", () => {
    const entries = tree(seed());
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ book: "corebook", domain: "gear", category: "weapons_firearms", items: 1 });
    expect(entries[0].qa).toEqual({ extracted: 1, reviewed: 0, approved: 0 });
  });

  it("readCategory returns the envelope", () => {
    const payload = readCategory(seed(), "corebook", "gear", "weapons_firearms");
    expect(payload.items[0].name).toBe("Example Autopistol");
  });

  it("rejects bad segments", () => {
    expect(() => readCategory(seed(), "..", "gear", "x")).toThrow(StoreError);
    expect(SEGMENT.test("weapons_firearms")).toBe(true);
    expect(SEGMENT.test("../evil")).toBe(false);
  });

  it("writeItem replaces and persists with trailing newline", () => {
    const root = seed();
    const updated = { ...ITEM, name: "Example Autopistol MkII", meta: { ...ITEM.meta, qaStatus: "reviewed" } };
    writeItem(root, "corebook", "gear", "weapons_firearms", "example_autopistol", updated);
    const raw = readFileSync(join(root, "corebook", "gear", "weapons_firearms.json"), "utf8");
    expect(raw.endsWith("\n")).toBe(true);
    const payload = JSON.parse(raw);
    expect(payload.items[0].name).toBe("Example Autopistol MkII");
    expect(payload.items[0].meta.qaStatus).toBe("reviewed");
  });

  it("writeItem 404s unknown ids and mismatched ids", () => {
    const root = seed();
    expect(() => writeItem(root, "corebook", "gear", "weapons_firearms", "nope", { ...ITEM, id: "nope2" })).toThrow(StoreError);
    expect(() => writeItem(root, "corebook", "gear", "weapons_firearms", "nope", { ...ITEM, id: "nope" })).toThrow(/not-found/);
  });
});
```

- [ ] **Step 3: FAIL** — `npm test` in `site/` → module not found.
- [ ] **Step 4: Implement** `site/server/store.mjs`:

```javascript
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export const SEGMENT = /^[a-z0-9_]+$/;

export class StoreError extends Error {
  constructor(code, detail = "") {
    super(detail ? `${code}: ${detail}` : code);
    this.code = code;
  }
}

function checkSegments(...segments) {
  for (const s of segments) {
    if (!SEGMENT.test(s)) throw new StoreError("bad-segment", s);
  }
}

function categoryPath(dataRoot, book, domain, category) {
  checkSegments(book, domain, category);
  return join(dataRoot, book, domain, `${category}.json`);
}

export function tree(dataRoot) {
  const out = [];
  for (const book of readdirSync(dataRoot)) {
    if (book.startsWith("_") || !SEGMENT.test(book)) continue;
    const bookDir = join(dataRoot, book);
    if (!statSync(bookDir).isDirectory()) continue;
    for (const domain of readdirSync(bookDir)) {
      if (domain.startsWith("_") || !SEGMENT.test(domain)) continue;
      const domainDir = join(bookDir, domain);
      if (!statSync(domainDir).isDirectory()) continue;
      for (const file of readdirSync(domainDir)) {
        if (!file.endsWith(".json")) continue;
        const payload = JSON.parse(readFileSync(join(domainDir, file), "utf8"));
        const qa = { extracted: 0, reviewed: 0, approved: 0 };
        for (const item of payload.items ?? []) {
          const s = item.meta?.qaStatus;
          if (s in qa) qa[s] += 1;
        }
        out.push({ book, domain, category: file.replace(/\.json$/, ""), items: (payload.items ?? []).length, qa });
      }
    }
  }
  return out.sort((a, b) => `${a.book}/${a.domain}/${a.category}`.localeCompare(`${b.book}/${b.domain}/${b.category}`));
}

export function readCategory(dataRoot, book, domain, category) {
  const path = categoryPath(dataRoot, book, domain, category);
  let raw;
  try {
    raw = readFileSync(path, "utf8");
  } catch {
    throw new StoreError("not-found", `${book}/${domain}/${category}`);
  }
  return JSON.parse(raw);
}

export function writeItem(dataRoot, book, domain, category, itemId, item) {
  if (item.id !== itemId) throw new StoreError("id-mismatch", `${item.id} != ${itemId}`);
  const payload = readCategory(dataRoot, book, domain, category);
  const index = payload.items.findIndex((i) => i.id === itemId);
  if (index === -1) throw new StoreError("not-found", itemId);
  payload.items[index] = item;
  const path = categoryPath(dataRoot, book, domain, category);
  writeFileSync(path, JSON.stringify(payload, null, 2) + "\n", "utf8");
  return item;
}
```

- [ ] **Step 5: PASS** — `npm test` → 5 tests. **Commit** `feat: site scaffold + file-backed store` (+ trailer; commit `site/package-lock.json` too).

---

### Task 3: Eden transform (shared)

**Files:**
- Create: `site/shared/edenTransform.mjs`
- Test: `site/tests/transform.test.mjs`

**Interfaces:**
- Produces: `toFoundryDoc(item) -> {name, type: "gear", img: "icons/svg/item-bag.svg", system, effects: [], flags: {}}` where `system` is a deep copy of `item.system` with `description` defaulted to `""` and `genesisID` defaulted to `item.id`. Throws `TypeError` if `item.system.type` is missing.

- [ ] **Step 1: Failing tests** — `site/tests/transform.test.mjs`:

```javascript
import { describe, expect, it } from "vitest";
import { toFoundryDoc } from "../shared/edenTransform.mjs";

const ITEM = {
  id: "example_autopistol",
  name: "Example Autopistol",
  system: { type: "WEAPON_FIREARMS", price: 620, dmgDef: "2P" },
  meta: { book: "corebook", page: 1, extractedAt: "2026-07-25", extractorVersion: "0.1.0", qaStatus: "approved" },
};

describe("toFoundryDoc", () => {
  it("wraps system, strips meta, defaults description and genesisID", () => {
    const doc = toFoundryDoc(ITEM);
    expect(doc).toMatchObject({ name: "Example Autopistol", type: "gear", img: "icons/svg/item-bag.svg" });
    expect(doc.system.price).toBe(620);
    expect(doc.system.description).toBe("");
    expect(doc.system.genesisID).toBe("example_autopistol");
    expect(doc.meta).toBeUndefined();
    expect(doc.effects).toEqual([]);
  });

  it("does not mutate the input", () => {
    const before = JSON.stringify(ITEM);
    toFoundryDoc(ITEM);
    expect(JSON.stringify(ITEM)).toBe(before);
  });

  it("throws without a system type", () => {
    expect(() => toFoundryDoc({ id: "x", name: "X", system: {} })).toThrow(TypeError);
  });
});
```

- [ ] **Step 2: FAIL.** **Step 3: Implement** `site/shared/edenTransform.mjs`:

```javascript
export function toFoundryDoc(item) {
  if (!item?.system?.type) throw new TypeError(`item ${item?.id ?? "?"} has no system.type`);
  const system = structuredClone(item.system);
  system.description ??= "";
  system.genesisID ??= item.id;
  return {
    name: item.name,
    type: "gear",
    img: "icons/svg/item-bag.svg",
    system,
    effects: [],
    flags: {},
  };
}
```

- [ ] **Step 4: PASS** (8 site tests). **Step 5: Commit** `feat: shared canonical->Foundry gear transform` (+ trailer).

---

### Task 4: API app + python bridge

**Files:**
- Create: `site/server/app.mjs`, `site/server/pythonBridge.mjs`, `site/server/index.mjs`
- Test: `site/tests/api.test.mjs`

**Interfaces:**
- `buildApp(dataRoot, {schemasDir, validate}) -> express app`; `index.mjs` calls it with repo paths and `runValidator`, serves `site/dist` statically, listens on 8347.
- Routes (all JSON):
  - `GET /api/tree` → store.tree
  - `GET /api/schema/:domain` → schemas/<domain>.schema.json (404 unknown)
  - `GET /api/category/:book/:domain/:category` → envelope
  - `PUT /api/item/:book/:domain/:category/:id` → body is the item; 400 on StoreError bad-segment/id-mismatch, 404 not-found; responds `{item, doc}` where doc = toFoundryDoc (doc may be null + `docError` string if transform throws)
  - `POST /api/validate` → `{ok, files, items, issues}` from injected `validate(dataRoot)`
- `pythonBridge.runValidator(dataRoot)` spawns the resolved python with `-m validator <dataRoot> --json` (cwd = repo root), parses stdout JSON; rejects with stderr text on spawn failure/unparseable output.

- [ ] **Step 1: Failing tests** — `site/tests/api.test.mjs` (uses supertest; validate is injected as a stub — no python in unit tests):

```javascript
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import request from "supertest";
import { describe, expect, it } from "vitest";
import { buildApp } from "../server/app.mjs";

const ITEM = {
  id: "example_autopistol",
  name: "Example Autopistol",
  system: { type: "WEAPON_FIREARMS", price: 620 },
  meta: { book: "corebook", page: 1, extractedAt: "2026-07-25", extractorVersion: "0.1.0", qaStatus: "extracted" },
};

function makeApp() {
  const root = mkdtempSync(join(tmpdir(), "forge-api-"));
  const dir = join(root, "corebook", "gear");
  mkdirSync(dir, { recursive: true });
  writeFileSync(
    join(dir, "weapons_firearms.json"),
    JSON.stringify({ book: "corebook", domain: "gear", category: "weapons_firearms", items: [ITEM] }, null, 2) + "\n",
  );
  const schemasDir = mkdtempSync(join(tmpdir(), "forge-schemas-"));
  writeFileSync(join(schemasDir, "gear.schema.json"), JSON.stringify({ title: "gear stub" }));
  const validate = async () => ({ ok: true, files: 1, items: 1, issues: [] });
  return buildApp(root, { schemasDir, validate });
}

describe("api", () => {
  it("GET /api/tree", async () => {
    const res = await request(makeApp()).get("/api/tree");
    expect(res.status).toBe(200);
    expect(res.body[0].category).toBe("weapons_firearms");
  });

  it("GET /api/schema/:domain and 404", async () => {
    const app = makeApp();
    expect((await request(app).get("/api/schema/gear")).status).toBe(200);
    expect((await request(app).get("/api/schema/nope")).status).toBe(404);
  });

  it("GET /api/category and 404", async () => {
    const app = makeApp();
    const res = await request(app).get("/api/category/corebook/gear/weapons_firearms");
    expect(res.body.items).toHaveLength(1);
    expect((await request(app).get("/api/category/corebook/gear/nope")).status).toBe(404);
  });

  it("PUT /api/item updates and returns preview doc", async () => {
    const app = makeApp();
    const updated = { ...ITEM, meta: { ...ITEM.meta, qaStatus: "approved" } };
    const res = await request(app).put("/api/item/corebook/gear/weapons_firearms/example_autopistol").send(updated);
    expect(res.status).toBe(200);
    expect(res.body.item.meta.qaStatus).toBe("approved");
    expect(res.body.doc.type).toBe("gear");
    const after = await request(app).get("/api/category/corebook/gear/weapons_firearms");
    expect(after.body.items[0].meta.qaStatus).toBe("approved");
  });

  it("PUT rejects id mismatch and traversal", async () => {
    const app = makeApp();
    expect((await request(app).put("/api/item/corebook/gear/weapons_firearms/example_autopistol").send({ ...ITEM, id: "other" })).status).toBe(400);
    expect((await request(app).put("/api/item/corebook/gear/weapons_firearms/%2e%2e").send(ITEM)).status).toBe(400);
  });

  it("POST /api/validate returns injected result", async () => {
    const res = await request(makeApp()).post("/api/validate");
    expect(res.body.ok).toBe(true);
  });
});
```

- [ ] **Step 2: FAIL.** **Step 3: Implement.**

`site/server/app.mjs`:

```javascript
import { readFileSync } from "node:fs";
import { join } from "node:path";
import express from "express";
import { toFoundryDoc } from "../shared/edenTransform.mjs";
import { SEGMENT, StoreError, readCategory, tree, writeItem } from "./store.mjs";

export function buildApp(dataRoot, { schemasDir, validate }) {
  const app = express();
  app.use(express.json({ limit: "2mb" }));

  app.get("/api/tree", (req, res) => res.json(tree(dataRoot)));

  app.get("/api/schema/:domain", (req, res) => {
    if (!SEGMENT.test(req.params.domain)) return res.status(400).json({ error: "bad-segment" });
    try {
      res.type("json").send(readFileSync(join(schemasDir, `${req.params.domain}.schema.json`), "utf8"));
    } catch {
      res.status(404).json({ error: "no-schema" });
    }
  });

  app.get("/api/category/:book/:domain/:category", (req, res) => {
    handle(res, () => readCategory(dataRoot, req.params.book, req.params.domain, req.params.category));
  });

  app.put("/api/item/:book/:domain/:category/:id", (req, res) => {
    handle(res, () => {
      const item = writeItem(dataRoot, req.params.book, req.params.domain, req.params.category, req.params.id, req.body);
      let doc = null;
      let docError = null;
      try {
        doc = toFoundryDoc(item);
      } catch (err) {
        docError = String(err.message ?? err);
      }
      return { item, doc, docError };
    });
  });

  app.post("/api/validate", async (req, res) => {
    try {
      res.json(await validate(dataRoot));
    } catch (err) {
      res.status(500).json({ error: String(err.message ?? err) });
    }
  });

  return app;
}

function handle(res, fn) {
  try {
    res.json(fn());
  } catch (err) {
    if (err instanceof StoreError) {
      const status = err.code === "not-found" ? 404 : 400;
      return res.status(status).json({ error: err.code, detail: err.message });
    }
    res.status(500).json({ error: String(err.message ?? err) });
  }
}
```

`site/server/pythonBridge.mjs`:

```javascript
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

export function resolvePython(repoRoot) {
  if (process.env.FORGE_PYTHON) return process.env.FORGE_PYTHON;
  const venv = join(repoRoot, ".venv", "Scripts", "python.exe");
  if (existsSync(venv)) return venv;
  const venvPosix = join(repoRoot, ".venv", "bin", "python");
  if (existsSync(venvPosix)) return venvPosix;
  return "python3";
}

export function runValidator(repoRoot, dataRoot) {
  const python = resolvePython(repoRoot);
  return new Promise((resolve, reject) => {
    execFile(python, ["-m", "validator", dataRoot, "--json"], { cwd: repoRoot }, (error, stdout, stderr) => {
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error(`validator failed: ${stderr || error?.message || "unparseable output"}`));
      }
    });
  });
}
```

`site/server/index.mjs`:

```javascript
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import express from "express";
import { buildApp } from "./app.mjs";
import { runValidator } from "./pythonBridge.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");
const dataRoot = join(repoRoot, "data");

const app = buildApp(dataRoot, {
  schemasDir: join(repoRoot, "schemas"),
  validate: (root) => runValidator(repoRoot, root),
});
app.use(express.static(join(here, "..", "dist")));

const port = process.env.PORT ?? 8347;
app.listen(port, () => console.log(`SR6-eden-Forge review app: http://localhost:${port}`));
```

- [ ] **Step 4: PASS** — `npm test` → 14 site tests. **Step 5: Commit** `feat: review API (tree/category/item/schema/validate)` (+ trailer).

---

### Task 5: React UI

**Files:**
- Create: `site/index.html`, `site/vite.config.js`, `site/src/main.jsx`, `site/src/api.js`, `site/src/App.jsx`, `site/src/components/Tree.jsx`, `site/src/components/CategoryTable.jsx`, `site/src/components/ItemEditor.jsx`, `site/src/components/Preview.jsx`, `site/src/styles.css`

**Interfaces:**
- Consumes the Task 4 API. `npm run build` must succeed; `npm run dev` proxies `/api` to :8347.
- Behavior: Tree lists book/domain/category with QA badge counts; clicking loads the category table (name, subtype, price, avail, qaStatus); clicking a row opens the editor: name field, qaStatus select, `system` fields rendered by value type (boolean→checkbox, number→number input, string→text input, `modes` object→4 checkboxes, `attackRating` array→5 number inputs, other objects→readonly JSON), notes textarea; Save PUTs and shows the returned Foundry doc in the Preview pane; a "Validate" button POSTs /api/validate and shows issue count + per-item issues inline in the table.

The complete file contents are specified in the plan appendix below — implement them verbatim.

- [ ] **Step 1:** create all files per Appendix A. **Step 2:** `npm run build` in `site/` → succeeds. **Step 3:** `npm test` still green. **Step 4: Commit** `feat: review UI (tree, table, editor, preview, validate)` (+ trailer).

---

### Task 6: Smoke test + docs (controller)

- [ ] Controller runs the server against real data (`npm run serve` after build; or dev mode), browses corebook categories, edits one item's qaStatus and reverts it, confirms validate button reports OK, screenshots for the session log.
- [ ] README: "Using the review app" section (install/build/serve commands, port, FORGE_PYTHON note); Status checklist tick.
- [ ] Commit `docs: review app usage` (+ trailer); push branch.

---

## Appendix A — UI file contents (Task 5, verbatim)

`site/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SR6-eden-Forge — Review</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

`site/vite.config.js`:

```javascript
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8347" } },
});
```

`site/src/main.jsx`:

```jsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(<App />);
```

`site/src/api.js`:

```javascript
async function json(res) {
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? `HTTP ${res.status}`);
  return res.json();
}

export const getTree = () => fetch("/api/tree").then(json);
export const getCategory = (b, d, c) => fetch(`/api/category/${b}/${d}/${c}`).then(json);
export const putItem = (b, d, c, item) =>
  fetch(`/api/item/${b}/${d}/${c}/${item.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  }).then(json);
export const validate = () => fetch("/api/validate", { method: "POST" }).then(json);
```

`site/src/App.jsx`:

```jsx
import React, { useEffect, useState } from "react";
import CategoryTable from "./components/CategoryTable.jsx";
import ItemEditor from "./components/ItemEditor.jsx";
import Preview from "./components/Preview.jsx";
import Tree from "./components/Tree.jsx";
import { getCategory, getTree, putItem, validate } from "./api.js";

export default function App() {
  const [tree, setTree] = useState([]);
  const [selected, setSelected] = useState(null); // {book, domain, category}
  const [payload, setPayload] = useState(null);
  const [editing, setEditing] = useState(null); // item
  const [doc, setDoc] = useState(null);
  const [issues, setIssues] = useState(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    getTree().then(setTree).catch((e) => setStatus(String(e)));
  }, []);

  async function openCategory(entry) {
    setSelected(entry);
    setEditing(null);
    setDoc(null);
    setPayload(await getCategory(entry.book, entry.domain, entry.category));
  }

  async function save(item) {
    const res = await putItem(selected.book, selected.domain, selected.category, item);
    setDoc(res.doc);
    setStatus(res.docError ? `saved; preview error: ${res.docError}` : `saved ${item.id}`);
    setPayload(await getCategory(selected.book, selected.domain, selected.category));
    setTree(await getTree());
    setEditing(res.item);
  }

  async function runValidate() {
    setStatus("validating…");
    const res = await validate();
    setIssues(res.issues);
    setStatus(res.ok ? `validator: OK (${res.items} items)` : `validator: ${res.issues.length} issue(s)`);
  }

  return (
    <div className="layout">
      <aside>
        <h1>SR6 Forge</h1>
        <button onClick={runValidate}>Validate all</button>
        <Tree entries={tree} selected={selected} onSelect={openCategory} />
      </aside>
      <main>
        <div className="status">{status}</div>
        {payload && (
          <CategoryTable
            payload={payload}
            issues={issues}
            onEdit={(item) => {
              setEditing(item);
              setDoc(null);
            }}
          />
        )}
      </main>
      <section className="right">
        {editing && <ItemEditor key={editing.id} item={editing} onSave={save} />}
        {doc && <Preview doc={doc} />}
      </section>
    </div>
  );
}
```

`site/src/components/Tree.jsx`:

```jsx
import React from "react";

export default function Tree({ entries, selected, onSelect }) {
  return (
    <nav>
      {entries.map((e) => {
        const key = `${e.book}/${e.domain}/${e.category}`;
        const active = selected && key === `${selected.book}/${selected.domain}/${selected.category}`;
        return (
          <div key={key} className={`tree-row ${active ? "active" : ""}`} onClick={() => onSelect(e)}>
            <span>{key}</span>
            <span className="badge">
              {e.items} · {e.qa.approved}✓
            </span>
          </div>
        );
      })}
    </nav>
  );
}
```

`site/src/components/CategoryTable.jsx`:

```jsx
import React from "react";

export default function CategoryTable({ payload, issues, onEdit }) {
  const issueMap = new Map();
  for (const issue of issues ?? []) {
    if (issue.item_id) issueMap.set(issue.item_id, [...(issueMap.get(issue.item_id) ?? []), issue]);
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Name</th><th>Subtype</th><th>Price</th><th>Avail</th><th>QA</th><th>Issues</th>
        </tr>
      </thead>
      <tbody>
        {payload.items.map((item) => (
          <tr key={item.id} onClick={() => onEdit(item)}>
            <td>{item.name}</td>
            <td>{item.system.subtype ?? ""}</td>
            <td>{item.system.priceDef ?? item.system.price}</td>
            <td>{item.system.availDef ?? item.system.avail}</td>
            <td className={`qa qa-${item.meta.qaStatus}`}>{item.meta.qaStatus}</td>
            <td>{(issueMap.get(item.id) ?? []).map((i) => i.rule).join(", ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

`site/src/components/ItemEditor.jsx`:

```jsx
import React, { useState } from "react";

const QA = ["extracted", "reviewed", "approved"];
const MODES = ["SS", "SA", "BF", "FA"];

export default function ItemEditor({ item, onSave }) {
  const [draft, setDraft] = useState(() => structuredClone(item));

  const setSystem = (field, value) => setDraft((d) => ({ ...d, system: { ...d.system, [field]: value } }));

  function renderField(field, value) {
    if (field === "modes" && value && typeof value === "object") {
      return (
        <span>
          {MODES.map((m) => (
            <label key={m} className="inline">
              <input type="checkbox" checked={!!value[m]} onChange={(e) => setSystem("modes", { ...value, [m]: e.target.checked })} />
              {m}
            </label>
          ))}
        </span>
      );
    }
    if (field === "attackRating" && Array.isArray(value)) {
      return (
        <span>
          {value.map((v, i) => (
            <input
              key={i}
              className="ar"
              type="number"
              value={v}
              onChange={(e) => {
                const next = [...value];
                next[i] = Number(e.target.value);
                setSystem("attackRating", next);
              }}
            />
          ))}
        </span>
      );
    }
    if (typeof value === "boolean") {
      return <input type="checkbox" checked={value} onChange={(e) => setSystem(field, e.target.checked)} />;
    }
    if (typeof value === "number") {
      return <input type="number" value={value} onChange={(e) => setSystem(field, Number(e.target.value))} />;
    }
    if (typeof value === "string") {
      return <input type="text" value={value} onChange={(e) => setSystem(field, e.target.value)} />;
    }
    return <code>{JSON.stringify(value)}</code>;
  }

  return (
    <div className="editor">
      <h2>{draft.id}</h2>
      <label>
        Name <input type="text" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </label>
      <label>
        QA status
        <select
          value={draft.meta.qaStatus}
          onChange={(e) => setDraft({ ...draft, meta: { ...draft.meta, qaStatus: e.target.value } })}
        >
          {QA.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      {Object.entries(draft.system).map(([field, value]) => (
        <label key={field}>
          {field} {renderField(field, value)}
        </label>
      ))}
      <button onClick={() => onSave(draft)}>Save</button>
    </div>
  );
}
```

`site/src/components/Preview.jsx`:

```jsx
import React from "react";

export default function Preview({ doc }) {
  return (
    <div className="preview">
      <h3>Foundry document</h3>
      <pre>{JSON.stringify(doc, null, 2)}</pre>
    </div>
  );
}
```

`site/src/styles.css`:

```css
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.4 system-ui, sans-serif; color: #1b1b1f; }
.layout { display: grid; grid-template-columns: 280px 1fr 380px; gap: 0; height: 100vh; }
aside { border-right: 1px solid #ddd; padding: 12px; overflow-y: auto; }
aside h1 { font-size: 16px; margin: 0 0 8px; }
main { padding: 12px; overflow-y: auto; }
.right { border-left: 1px solid #ddd; padding: 12px; overflow-y: auto; }
.tree-row { display: flex; justify-content: space-between; padding: 4px 6px; cursor: pointer; border-radius: 4px; }
.tree-row:hover { background: #f0f0f4; }
.tree-row.active { background: #e3e8ff; }
.badge { color: #666; font-size: 12px; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid #eee; }
tbody tr { cursor: pointer; }
tbody tr:hover { background: #f7f7fa; }
.qa-extracted { color: #a15c00; }
.qa-reviewed { color: #0b62a4; }
.qa-approved { color: #1a7f37; }
.status { min-height: 20px; color: #555; margin-bottom: 8px; }
.editor label { display: block; margin: 6px 0; }
.editor input[type="text"], .editor input[type="number"] { width: 220px; }
.editor input.ar { width: 48px; margin-right: 4px; }
.editor label.inline { display: inline-block; margin-right: 8px; }
.preview pre { background: #f6f8fa; padding: 8px; border-radius: 6px; overflow-x: auto; font-size: 12px; }
button { padding: 6px 12px; border-radius: 6px; border: 1px solid #bbb; background: #fff; cursor: pointer; }
button:hover { background: #f0f0f4; }
```

## Self-Review Notes

- Store rejects `_`-prefixed dirs so `_raw`/`_fixes` never surface in the app.
- The transform is deliberately in `site/shared/` — the export plan (next) imports it so preview === export.
- PUT round-trips the whole item; the UI never constructs partial writes, keeping file output byte-stable against the extractor format.
- Task 6 is controller-run: the smoke test needs the real local dataset and a browser.
