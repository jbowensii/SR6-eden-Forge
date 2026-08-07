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

// Where the library lives, strongest first:
//
//   1. SR6_DATA          — set by the Catalog Builder, which knows the
//                          workspace the user chose
//   2. settings.dataDir  — set in the Setup panel; applies on restart
//   3. <repo>/data       — what a developer standing in the repo expects
//
// SR6_DATA has to win. Installed, the app lives under Program Files and its
// own data/ does not exist, so without it the review app opened on an empty
// library AND recorded every edit into the installation directory instead of
// the user's workspace — where the import would never look for them.
const dataRoot = process.env.SR6_DATA
  ? resolve(process.env.SR6_DATA)
  : (loadSettings(defaultData).dataDir
      ? resolve(loadSettings(defaultData).dataDir)
      : defaultData);

const app = buildApp(dataRoot, {
  schemasDir: join(repoRoot, "schemas"),
  validate: (root) => runValidator(repoRoot, root),
  exporter: (opts) => exportModule(dataRoot, join(repoRoot, "export"), opts),
});
app.use(express.static(join(here, "..", "dist")));

const port = process.env.PORT ?? 8347;
app.listen(port, "127.0.0.1", () => console.log(`SR6-eden-Forge review app: http://localhost:${port}`));
