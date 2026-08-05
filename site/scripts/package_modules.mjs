/** Zip the built modules for server deployment:
 *    export/sr6-forge/           -> export/dist/sr6-forge-v<ver>.zip
 *    export/sr6-forge-corebook/  -> export/dist/sr6-forge-corebook-v<ver>.zip
 *  Usage: node site/scripts/package_modules.mjs
 *  (Uses PowerShell Compress-Archive — no extra npm deps.) */
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const dist = join(root, "export", "dist");
mkdirSync(dist, { recursive: true });

for (const id of ["sr6-forge", "sr6-forge-corebook"]) {
  const dir = join(root, "export", id);
  if (!existsSync(dir)) { console.log(`skip ${id} (not built)`); continue; }
  const ver = JSON.parse(readFileSync(join(dir, "module.json"), "utf8")).version;
  const zip = join(dist, `${id}-v${ver}.zip`);
  execFileSync("powershell", ["-NoProfile", "-Command",
    `Compress-Archive -Path '${dir}' -DestinationPath '${zip}' -Force`]);
  console.log(`packaged ${zip}`);
}
