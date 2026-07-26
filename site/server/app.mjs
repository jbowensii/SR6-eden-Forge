import { readFileSync } from "node:fs";
import { join } from "node:path";
import express from "express";
import { toFoundryDoc } from "../shared/edenTransform.mjs";
import { SEGMENT, StoreError, readCategory, tree, writeItem } from "./store.mjs";

export function buildApp(dataRoot, { schemasDir, validate }) {
  const app = express();
  app.use(express.json({ limit: "2mb" }));

  app.get("/api/tree", (req, res) => handle(res, () => tree(dataRoot)));

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
