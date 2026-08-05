/** Assemble the installable sr6-forge app module:
 *    foundry-module/sr6-forge/  +  export/chargen-data.json  ->  export/sr6-forge/
 *  Usage: node site/scripts/build_module.mjs [--version 0.3.0] [--deploy]
 *  --deploy copies export/sr6-forge (and export/sr6-forge-corebook if present)
 *  into the local Foundry Data/modules dir (data/settings.json: foundryDataPath). */
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const args = process.argv.slice(2);
const argVal = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
};

const src = join(root, "foundry-module", "sr6-forge");
const out = join(root, "export", "sr6-forge");
const chargenData = join(root, "export", "chargen-data.json");

if (!existsSync(src)) throw new Error(`missing ${src}`);
if (!existsSync(chargenData)) {
  throw new Error("export/chargen-data.json missing — run: python tools/build_chargen_data.py");
}

rmSync(out, { recursive: true, force: true });
cpSync(src, out, { recursive: true });
mkdirSync(join(out, "data"), { recursive: true });
cpSync(chargenData, join(out, "data", "chargen-data.json"));

const manifestPath = join(out, "module.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const version = argVal("--version");
if (version) manifest.version = version;
writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
console.log(`built export/sr6-forge (v${manifest.version})`);

if (args.includes("--deploy")) {
  let settings = {};
  try { settings = JSON.parse(readFileSync(join(root, "data", "settings.json"), "utf8")); } catch {}
  const dataPath = settings.foundryDataPath;
  if (!dataPath || !existsSync(dataPath)) {
    throw new Error("data/settings.json foundryDataPath not set or missing " +
      "(point it at your local FoundryVTT Data folder)");
  }
  const modules = join(dataPath, "modules");
  // --app-only skips the data module (its LevelDB packs are locked while
  // Foundry is running; they rarely change anyway).
  const ids = args.includes("--app-only") ? ["sr6-forge"] : ["sr6-forge", "sr6-forge-corebook"];
  for (const id of ids) {
    const from = join(root, "export", id);
    if (!existsSync(from)) { console.log(`skip ${id} (not built)`); continue; }
    const to = join(modules, id);
    try {
      rmSync(to, { recursive: true, force: true });
      cpSync(from, to, { recursive: true });
      console.log(`deployed ${id} -> ${to}`);
    } catch (err) {
      if (err.code === "EPERM" || err.code === "EBUSY") {
        console.warn(`SKIPPED ${id}: files locked (close Foundry to redeploy packs)`);
      } else throw err;
    }
  }
}
