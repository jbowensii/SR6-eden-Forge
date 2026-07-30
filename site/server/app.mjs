import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { spawn } from "node:child_process";
import express from "express";
import { toFoundryDoc } from "../shared/edenTransform.mjs";
import { EDEN } from "../shared/edenSpec.mjs";
import { loadBooks } from "./exportModule.mjs";
import { assignIcon, libraryRoots, loadSettings, resolveLibraryFile, searchIcons } from "./iconLibrary.mjs";
import { SEGMENT, StoreError, assignRender, deleteItem, domains, itemsByType, listBookImages, readCategory, searchItems, tree, typeTree, writeItem } from "./store.mjs";

const EXPORT_STATUSES = new Set(["approved", "reviewed", "all"]);

export function buildApp(dataRoot, { schemasDir, validate, exporter }) {
  const app = express();
  app.use(express.json({ limit: "2mb" }));

  app.get("/api/tree", (req, res) => handle(res, () => tree(dataRoot)));

  // item finder for the left-pane search box
  app.get("/api/search", (req, res) =>
    handle(res, () => searchItems(dataRoot, String(req.query.q ?? ""), Number(req.query.limit ?? 60))));

  // available domains, the per-domain grouping tree, and its items
  app.get("/api/domains", (req, res) => handle(res, () => ({ domains: domains(dataRoot) })));
  app.get("/api/typetree", (req, res) => handle(res, () => typeTree(dataRoot, String(req.query.domain ?? "gear"))));
  app.get("/api/items", (req, res) =>
    handle(res, () => itemsByType(dataRoot, String(req.query.type ?? ""),
      req.query.subtype === undefined ? undefined : String(req.query.subtype),
      String(req.query.domain ?? "gear"))));

  // book metadata (titles + whether a PDF is wired up) from data/books.json
  app.get("/api/books", (req, res) => {
    handle(res, () => {
      const books = loadBooks(dataRoot);
      return Object.fromEntries(
        Object.entries(books).map(([slug, b]) => [slug, { title: b.title ?? slug, pdf: Boolean(b.pdf && existsSync(b.pdf)) }]),
      );
    });
  });

  // stream the source PDF so the browser viewer can jump to #page=N
  app.get("/api/pdf/:book", (req, res) => {
    if (!SEGMENT.test(req.params.book)) return res.status(400).json({ error: "bad-segment" });
    const pdf = loadBooks(dataRoot)[req.params.book]?.pdf;
    if (!pdf || !existsSync(pdf)) return res.status(404).json({ error: "no-pdf", detail: "add it to data/books.json" });
    res.sendFile(pdf);
  });

  // item images live in data/_assets/<book>/...; served read-only for previews
  app.use("/assets", express.static(join(dataRoot, "_assets")));

  // graphics extracted from a book, and assigning one as an item's render
  app.get("/api/bookimages/:book", (req, res) => handle(res, () => ({ images: listBookImages(dataRoot, req.params.book) })));
  app.post("/api/assign-render", (req, res) => {
    const { book, domain, category, itemId, imagePath } = req.body ?? {};
    handle(res, () => assignRender(dataRoot, book, domain, category, itemId, imagePath));
  });

  // icon library roots (data/settings.json iconLibrary + data/_assets/iconsets)
  app.get("/api/icons", (req, res) => {
    const roots = libraryRoots(dataRoot);
    if (!roots.length) return res.status(404).json({ error: "no-library", detail: "set iconLibrary in data/settings.json" });
    handle(res, () => searchIcons(roots, String(req.query.q ?? ""), Number(req.query.limit ?? 60)));
  });

  app.get(/^\/icon-lib\/(\d+)\/(.+)$/, (req, res) => {
    const roots = libraryRoots(dataRoot);
    const root = roots[Number(req.params[0])];
    if (!root) return res.status(404).end();
    try {
      res.sendFile(resolveLibraryFile(root, req.params[1]));
    } catch {
      res.status(404).end();
    }
  });

  app.post("/api/icon/assign", (req, res) => {
    const roots = libraryRoots(dataRoot);
    if (!roots.length) return res.status(404).json({ error: "no-library" });
    const { book, domain, category, itemId, libraryPath, mode } = req.body ?? {};
    const root = roots[Number(req.body?.root ?? 0)];
    if (!root) return res.status(400).json({ error: "bad-root" });
    if (mode !== "item" && mode !== "generic") return res.status(400).json({ error: "bad-mode" });
    handle(res, () => assignIcon(dataRoot, root, { book, domain, category, itemId, libraryPath, mode }));
  });

  app.get("/api/edenspec", (_req, res) => handle(res, () => ({ eden: EDEN })));

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

  app.delete("/api/item/:book/:domain/:category/:id", (req, res) =>
    handle(res, () => deleteItem(dataRoot, req.params.book, req.params.domain, req.params.category, req.params.id)));

  app.put("/api/item/:book/:domain/:category/:id", (req, res) => {
    handle(res, () => {
      const item = writeItem(dataRoot, req.params.book, req.params.domain, req.params.category, req.params.id, req.body);
      let doc = null;
      let docError = null;
      try {
        doc = toFoundryDoc(item, { product: loadBooks(dataRoot)[req.params.book]?.title, domain: req.params.domain });
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

  app.post("/api/export", async (req, res) => {
    const { book, domain, version } = req.body ?? {};
    const status = req.body?.status ?? "approved";
    if (!SEGMENT.test(book ?? "") || !SEGMENT.test(domain ?? "")) {
      return res.status(400).json({ error: "bad-segment" });
    }
    if (!EXPORT_STATUSES.has(status)) {
      return res.status(400).json({ error: "bad-status" });
    }
    try {
      res.json(await exporter({ book, domain, status, version }));
    } catch (err) {
      const message = String(err.message ?? err);
      const statusCode = message.startsWith("no items match") ? 409 : 500;
      res.status(statusCode).json({ error: message });
    }
  });

  // ── Setup panel: configure book PDF paths + trigger the import pipeline ──
  const repoRoot = dirname(dataRoot);
  const booksPath = join(dataRoot, "books.json");
  const rebuild = { running: false, log: [], startedAt: null, code: null };

  app.get("/api/config/books", (_req, res) => handle(res, () => {
    const books = loadBooks(dataRoot);
    return {
      books: Object.entries(books)
        .map(([slug, b]) => ({ slug, title: b.title ?? slug, pdf: b.pdf ?? "", exists: Boolean(b.pdf && existsSync(b.pdf)) }))
        .sort((a, b) => a.slug.localeCompare(b.slug)),
    };
  }));

  // update one or more book PDF paths: body { updates: { slug: "C:/.../x.pdf" } }
  app.put("/api/config/books", (req, res) => handle(res, () => {
    const updates = req.body?.updates ?? {};
    const books = loadBooks(dataRoot);
    let changed = 0;
    for (const [slug, pdf] of Object.entries(updates)) {
      if (!SEGMENT.test(slug) || !(slug in books)) continue;
      books[slug].pdf = String(pdf); changed += 1;
    }
    writeFileSync(booksPath, JSON.stringify(books, null, 2) + "\n", "utf8");
    return { changed };
  }));

  app.get("/api/rebuild/status", (_req, res) =>
    res.json({ running: rebuild.running, startedAt: rebuild.startedAt, code: rebuild.code, log: rebuild.log.slice(-200) }));

  app.post("/api/rebuild", (_req, res) => {
    if (rebuild.running) return res.status(409).json({ error: "already-running" });
    rebuild.running = true; rebuild.log = []; rebuild.code = null; rebuild.startedAt = Date.now();
    const py = process.env.PYTHON || "python";
    const child = spawn(py, ["-u", join("tools", "rebuild_all.py")], { cwd: repoRoot });
    const push = (buf) => {
      for (const line of buf.toString().split(/\r?\n/)) if (line.trim()) rebuild.log.push(line);
      if (rebuild.log.length > 500) rebuild.log = rebuild.log.slice(-500);
    };
    child.stdout.on("data", push);
    child.stderr.on("data", (b) => { const s = b.toString(); if (!/FontBBox|CropBox/.test(s)) push(b); });
    child.on("close", (code) => { rebuild.running = false; rebuild.code = code; rebuild.log.push(`__exit ${code}`); });
    child.on("error", (e) => { rebuild.running = false; rebuild.code = -1; rebuild.log.push(`__error ${e.message}`); });
    res.json({ started: true });
  });

  // Dot-segment path components (e.g. "..") get collapsed by URL normalization
  // before routing sees them, so a malformed /api/item/... PUT request never
  // matches the PUT route above. Anything left unmatched under /api/item for
  // a PUT is a malformed request; any other method under /api/item is simply
  // an unrouted resource.
  //
  // Note: Express 4's `*name` named-wildcard syntax (Express 5 / path-to-regexp
  // v6+ feature) registers without error here but silently fails to match at
  // request time on this Express version, so the method check is done manually.
  app.use("/api/item", (req, res) => {
    if (req.method === "PUT") return res.status(400).json({ error: "bad-request" });
    res.status(404).json({ error: "no-route" });
  });

  // Malformed JSON bodies throw a SyntaxError from express.json() before any
  // route handler runs; without this handler Express's default error handler
  // returns an HTML stack trace instead of JSON.
  app.use((err, req, res, next) => {
    if (err?.type === "entity.parse.failed" || (err instanceof SyntaxError && (err.status ?? err.statusCode) === 400)) {
      return res.status(400).json({ error: "bad-json" });
    }
    next(err);
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
