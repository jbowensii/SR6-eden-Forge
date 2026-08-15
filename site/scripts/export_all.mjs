// Export every domain of a book into one shadowrun6-eden module (Item + Actor
// packs), for the full Foundry format-compatibility test. Then read each
// compiled LevelDB pack back and sanity-check the docs.
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { parseArgs } from "node:util";
import { exportAll } from "../server/exportModule.mjs";
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
    book: { type: "string", default: "corebook" },
    status: { type: "string", default: "all" },
    version: { type: "string", default: "0.1.0" },
    data: { type: "string" },
  },
});
// Which library to export, same order the rest of the toolchain uses: --data,
// then SR6_DATA, then the repo's own copy. This was pinned to <repo>/data,
// which is a developer's scratch copy — once the installed builder is in use it
// is a different, older library, and the module would be built from it without
// a word. The path is printed so a wrong one is obvious immediately.
const dataRoot = values.data ?? process.env.SR6_DATA ?? dataRoot;
try {
  console.log(`library: ${dataRoot}`);
  const res = await exportAll(dataRoot, join(repoRoot, "export"), values);
  console.log(`\nmodule -> ${res.moduleDir}`);
  console.log(`${res.packs} pack(s):`);
  let items = 0, actors = 0;
  for (const [dom, info] of Object.entries(res.perDomain)) {
    if (info.error) console.log(`  ${dom.padEnd(18)} ERROR ${info.error}`);
    else {
      console.log(`  ${dom.padEnd(18)} ${String(info.count ?? 0).padStart(4)}  ${info.type ?? ""}`);
      if (info.type === "Actor") actors += info.count ?? 0; else items += info.count ?? 0;
    }
  }
  console.log(`TOTAL items=${items} actors=${actors}`);
  console.log("done");
} catch (err) {
  console.error("EXPORT FAILED:", String(err.message ?? err));
  process.exit(1);
}
