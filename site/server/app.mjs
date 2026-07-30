import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join, dirname, sep } from "node:path";

// Show/store paths in the host OS's separator (Windows "\", POSIX "/").
const osPath = (p) => (typeof p === "string" ? p.replace(/[\\/]+/g, sep) : p);
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

  // extracted art lives in <artDir> (default data/_assets); served read-only.
  // artDir is read at startup — editing it in Setup applies on restart.
  const artRoot = loadSettings(dataRoot).artDir || join(dataRoot, "_assets");
  app.use("/assets", express.static(artRoot));

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
    const s = loadSettings(dataRoot);
    const icon = Array.isArray(s.iconLibrary) ? s.iconLibrary[0] : s.iconLibrary;
    return {
      paths: {
        data: osPath(s.dataDir || dataRoot),
        art: osPath(s.artDir || join(dataRoot, "_assets")),
        iconLibrary: osPath(icon || ""),
      },
      books: Object.entries(books)
        .map(([slug, b]) => ({ slug, title: b.title ?? slug, pdf: osPath(b.pdf ?? ""), exists: Boolean(b.pdf && existsSync(b.pdf)) }))
        .sort((a, b) => a.slug.localeCompare(b.slug)),
    };
  }));

  // edit the DATA / ART / ICON LIBRARY paths. iconLibrary applies live; dataDir
  // and artDir take effect on server restart (read at startup).
  app.put("/api/config/paths", (req, res) => handle(res, () => {
    const cur = loadSettings(dataRoot);
    const b = req.body ?? {};
    if (typeof b.data === "string" && b.data.trim()) cur.dataDir = osPath(b.data.trim());
    if (typeof b.art === "string" && b.art.trim()) cur.artDir = osPath(b.art.trim());
    if (typeof b.iconLibrary === "string") cur.iconLibrary = b.iconLibrary.trim() ? osPath(b.iconLibrary.trim()) : undefined;
    writeFileSync(join(dataRoot, "settings.json"), JSON.stringify(cur, null, 2) + "\n", "utf8");
    return { saved: true, restartNeeded: Boolean(b.data || b.art) };
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

  // ── Artwork: internet image search config (engine + API key) ────────────
  app.get("/api/config/search", (_req, res) => handle(res, () => {
    const s = loadSettings(dataRoot).search ?? {};
    // never leak the full key to the browser — just whether one is set
    return { engine: s.engine ?? "scrape", hasKey: Boolean(s.apiKey), cseId: s.cseId ?? "",
             prefix: s.prefix ?? "shadowrun cyberpunk" };
  }));
  app.put("/api/config/search", (req, res) => handle(res, () => {
    const cur = loadSettings(dataRoot);
    const b = req.body ?? {};
    cur.search = {
      engine: ["scrape", "bing", "google"].includes(b.engine) ? b.engine : "scrape",
      apiKey: b.apiKey === "" ? "" : (b.apiKey ?? cur.search?.apiKey ?? ""),   // "" clears; undefined keeps
      cseId: b.cseId ?? cur.search?.cseId ?? "",
      prefix: b.prefix ?? cur.search?.prefix ?? "shadowrun cyberpunk",
    };
    writeFileSync(join(dataRoot, "settings.json"), JSON.stringify(cur, null, 2) + "\n", "utf8");
    return { saved: true };
  }));

  // test the search config (engine + key) with a sample query, before saving.
  // Uses the posted config, falling back to the saved key if none is entered.
  app.post("/api/config/search/test", async (req, res) => {
    const saved = loadSettings(dataRoot).search ?? {};
    const b = req.body ?? {};
    const cfg = { engine: b.engine ?? saved.engine ?? "scrape", apiKey: b.apiKey || saved.apiKey || "",
                  cseId: b.cseId ?? saved.cseId ?? "", prefix: b.prefix ?? saved.prefix };
    try {
      const out = await imageSearch("Ares Predator", cfg);
      const n = out.results?.length ?? 0;
      res.json({ ok: n > 0 && !out.error, count: n, error: out.error ?? null, engine: cfg.engine });
    } catch (err) {
      res.json({ ok: false, error: String(err.message ?? err), engine: cfg.engine });
    }
  });

  // internet image search — dispatches on the configured engine
  app.get("/api/artsearch", async (req, res) => {
    const q = String(req.query.q ?? "").trim();
    if (!q) return res.json({ results: [] });
    const cfg = loadSettings(dataRoot).search ?? {};
    try {
      const out = await imageSearch(q, cfg);
      res.json(out);
    } catch (err) {
      res.json({ results: [], error: String(err.message ?? err) });
    }
  });

  // download an image URL into the item's art (render) slot
  app.post("/api/art/download", async (req, res) => {
    const { book, domain, category, id, url } = req.body ?? {};
    if (![book, domain, category, id].every((s) => typeof s === "string" && SEGMENT.test(s))
        || !/^https?:\/\//.test(url ?? "")) {
      return res.status(400).json({ error: "bad-request" });
    }
    try {
      const payload = readCategory(dataRoot, book, domain, category);
      const item = payload.items.find((i) => i.id === id);
      if (!item) return res.status(404).json({ error: "not-found" });
      const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
      if (!r.ok) return res.status(502).json({ error: `fetch ${r.status}` });
      const ct = r.headers.get("content-type") || "";
      const ext = ct.includes("png") ? "png" : ct.includes("webp") ? "webp" : "jpg";
      const buf = Buffer.from(await r.arrayBuffer());
      if (buf.length > 8_000_000) return res.status(413).json({ error: "image too large" });
      const src = item.meta?.book ?? book;
      const rel = `${src}/${id}.${ext}`;
      const dest = join(dataRoot, "_assets", rel);
      const { mkdirSync } = await import("node:fs");
      mkdirSync(join(dataRoot, "_assets", src), { recursive: true });
      writeFileSync(dest, buf);
      item.img = rel;
      writeItem(dataRoot, book, domain, category, id, item);   // persists + records correction
      res.json({ img: rel });
    } catch (err) {
      res.status(500).json({ error: String(err.message ?? err) });
    }
  });

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

// Internet image search dispatched by configured engine. Returns {results:
// [{full, thumb}], searchUrl}. Google CSE and Bing API need a key; scrape is the
// keyless fallback (fragile). Query is prefixed (default "shadowrun cyberpunk").
export async function imageSearch(q, cfg = {}) {
  const prefix = cfg.prefix ?? "shadowrun cyberpunk";
  const query = `${prefix} ${q}`.trim();
  const engine = cfg.engine ?? "scrape";
  if (engine === "google" && cfg.apiKey && cfg.cseId) {
    const u = `https://www.googleapis.com/customsearch/v1?key=${encodeURIComponent(cfg.apiKey)}` +
      `&cx=${encodeURIComponent(cfg.cseId)}&searchType=image&num=10&q=${encodeURIComponent(query)}`;
    const r = await fetch(u);
    const j = await r.json();
    if (j.error) return { results: [], error: j.error.message };
    return { results: (j.items ?? []).map((it) => ({ full: it.link, thumb: it.image?.thumbnailLink ?? it.link })) };
  }
  if (engine === "bing" && cfg.apiKey) {
    const u = `https://api.bing.microsoft.com/v7.0/images/search?count=20&q=${encodeURIComponent(query)}`;
    const r = await fetch(u, { headers: { "Ocp-Apim-Subscription-Key": cfg.apiKey } });
    const j = await r.json();
    if (j.error) return { results: [], error: j.error.message ?? "bing error" };
    return { results: (j.value ?? []).map((v) => ({ full: v.contentUrl, thumb: v.thumbnailUrl })) };
  }
  // keyless scrape of Bing image results
  const url = `https://www.bing.com/images/search?q=${encodeURIComponent(query)}&form=HDRSC2`;
  const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" } });
  const html = await r.text();
  const seen = new Set(); const results = [];
  const re = /m="\{[^}]*&quot;murl&quot;:&quot;(.*?)&quot;[^}]*&quot;turl&quot;:&quot;(.*?)&quot;/g;
  let m;
  while ((m = re.exec(html)) && results.length < 24) {
    const full = m[1].replace(/&amp;/g, "&"); const thumb = m[2].replace(/&amp;/g, "&");
    if (!seen.has(full)) { seen.add(full); results.push({ full, thumb }); }
  }
  return { results, searchUrl: url };
}
