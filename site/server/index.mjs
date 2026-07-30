import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import express from "express";
import { buildApp } from "./app.mjs";
import { exportModule } from "./exportModule.mjs";
import { runValidator } from "./pythonBridge.mjs";
import { loadSettings } from "./iconLibrary.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");
const defaultData = join(repoRoot, "data");
// data location is configurable in Setup (settings.dataDir); applies on restart
const dataRoot = loadSettings(defaultData).dataDir ? resolve(loadSettings(defaultData).dataDir) : defaultData;

const app = buildApp(dataRoot, {
  schemasDir: join(repoRoot, "schemas"),
  validate: (root) => runValidator(repoRoot, root),
  exporter: (opts) => exportModule(dataRoot, join(repoRoot, "export"), opts),
});
app.use(express.static(join(here, "..", "dist")));

const port = process.env.PORT ?? 8347;
app.listen(port, "127.0.0.1", () => console.log(`SR6-eden-Forge review app: http://localhost:${port}`));
