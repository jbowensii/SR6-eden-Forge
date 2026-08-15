import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { parseArgs } from "node:util";
import { exportAll, exportModule } from "../server/exportModule.mjs";
import { resolveDataRoot } from "../server/dataRoot.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");
// SR6_DATA wins, exactly as the review app resolves it — the repo
// carries a stale library of its own and exporting it succeeds silently.
const dataRoot = resolveDataRoot(repoRoot);
// Say it out loud. An export from the wrong library does not fail — it
// produces a complete, plausible compendium from a stale snapshot, and
// the only clue is a row count nobody checks.
console.log(`reading library from ${dataRoot}`);
const { values } = parseArgs({
  options: {
    book: { type: "string" },
    domain: { type: "string", default: "gear" },
    all: { type: "boolean", default: false },
    status: { type: "string", default: "approved" },
    version: { type: "string", default: "0.1.0" },
  },
});
if (!["approved", "reviewed", "all"].includes(values.status)) {
  console.error(`invalid --status "${values.status}" (approved|reviewed|all)`);
  process.exit(2);
}
if (!values.book) {
  console.error("usage: node site/scripts/export.mjs --book corebook [--domain gear] [--status approved|reviewed|all] [--version x.y.z]");
  process.exit(2);
}
try {
  if (values.all) {
    const res = await exportAll(dataRoot, join(repoRoot, "export"), values);
    const counts = Object.entries(res.perDomain)
      .filter(([, v]) => v.count).map(([d, v]) => `${d}:${v.count}`).join(" ");
    console.log(`exported ${res.packs} pack(s) -> ${res.moduleDir}\n  ${counts}`);
  } else {
    const res = await exportModule(dataRoot, join(repoRoot, "export"), values);
    console.log(`exported ${res.count} item(s) -> ${res.moduleDir}`);
  }
} catch (err) {
  console.error(String(err.message ?? err));
  process.exit(1);
}
