import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { parseArgs } from "node:util";
import { exportModule } from "../server/exportModule.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");
const { values } = parseArgs({
  options: {
    book: { type: "string" },
    domain: { type: "string", default: "gear" },
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
  const res = await exportModule(join(repoRoot, "data"), join(repoRoot, "export"), values);
  console.log(`exported ${res.count} item(s) -> ${res.moduleDir}`);
} catch (err) {
  console.error(String(err.message ?? err));
  process.exit(1);
}
