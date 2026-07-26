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
