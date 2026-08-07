/** Refuse to publish game content.
 *
 *    node site/scripts/verify_release.mjs
 *
 *  Opens the release artifact and inspects what is actually inside it, rather
 *  than trusting filenames. Two kinds of check:
 *
 *  **Structural** — files that are game data whatever they contain: compiled
 *  compendium packs, extracted artwork, PDFs.
 *
 *  **Textual** — every shipped JSON is scanned for prose. Rules and mechanics
 *  are systems and not copyrightable; written passages are. The packager
 *  strips the passages, and this proves it worked. A name-based rule cannot:
 *  the 0.5.0 build hid 188 prose strings, one of them 4,662 characters, under
 *  a `value` key inside `lifepathModules.*.bullets` that no filename check
 *  would ever have caught.
 *
 *  Item and module NAMES survive on purpose. They are identifiers the module
 *  needs to function, and names are not copyrightable — some life-event titles
 *  simply run long.
 *
 *  Exit code 1 means do not publish.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const dist = join(root, "export", "dist");

/** Paths that are game data regardless of content. */
const FORBIDDEN_PATHS = [
  /(^|[\\/])packs[\\/]/i, /\.ldb$/i, /CURRENT$/i, /MANIFEST-/i,
  /[\\/]_assets[\\/]/i, /\.pdf$/i,
];

/** Keys whose values are written passages, not mechanics. */
const PROSE_KEYS = new Set(["desc", "description", "flavor", "flavour", "bullets"]);

/** Twelve-plus consecutive ordinary words reads as prose, not a stat block. */
const PROSE_RE = /(?:\b[a-z]{2,}\b[ ,.;']+){12,}/i;

/** Keys holding identifiers, which are allowed to be long. Names and titles
 *  are not copyrightable, and the module cannot offer a blank option. */
const IDENTIFIER_KEYS = new Set(["name", "id", "label", "title"]);

/** Keys carrying OUR commentary inside a generated file — the explanatory
 *  notes the extractor writes and the citations it leaves behind, already
 *  reduced to a page reference by the packager. Ours to publish. */
const OUR_WORDS = new Set(["note", "_note", "verified", "_verified", "reason",
  "description", "hint", "_notice"]);

/** Files derived from the books. Only these can contain someone else's prose;
 *  module.json and lang/en.json are written by us end to end. */
const BOOK_DERIVED = /^sr6-forge[\\/]data[\\/]/i;

function scanJson(value, key, path, out) {
  if (Array.isArray(value)) {
    value.forEach((v) => scanJson(v, key, path, out));
    return;
  }
  if (value && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) scanJson(v, k, `${path}.${k}`, out);
    return;
  }
  if (typeof value !== "string") return;
  if (PROSE_KEYS.has(key)) {
    out.push({ path, why: `prose key "${key}"`, text: value.slice(0, 90) });
    return;
  }
  if (IDENTIFIER_KEYS.has(key)) return;          // names are not expression
  if (OUR_WORDS.has(key)) return;                // our own commentary
  const m = value.match(PROSE_RE);
  if (m && m[0].trim().length > 80) {
    out.push({ path, why: "reads as prose", text: value.slice(0, 90) });
  }
}

if (!existsSync(dist)) {
  console.log("nothing built — run package_modules.mjs --release first");
  process.exit(0);
}
const zips = readdirSync(dist).filter((f) => /^sr6-forge\.zip$/.test(f));
if (!zips.length) {
  console.log("no release artifact — run: node site/scripts/package_modules.mjs --release");
  process.exit(0);
}

let bad = 0;
for (const f of zips) {
  const zip = join(dist, f);
  const tmp = mkdtempSync(join(tmpdir(), "sr6-verify-"));
  try {
    execFileSync("powershell", ["-NoProfile", "-Command",
      `Expand-Archive -Path '${zip}' -DestinationPath '${tmp}' -Force`]);

    const files = [];
    (function walk(d) {
      for (const e of readdirSync(d, { withFileTypes: true })) {
        const p = join(d, e.name);
        if (e.isDirectory()) walk(p);
        else files.push(p);
      }
    })(tmp);

    const problems = [];
    for (const p of files) {
      const rel = p.slice(tmp.length + 1);
      if (FORBIDDEN_PATHS.some((re) => re.test(rel))) {
        problems.push({ path: rel, why: "game data file", text: "" });
        continue;
      }
      // only book-derived data can hold someone else's writing
      if (!rel.endsWith(".json") || !BOOK_DERIVED.test(rel)) continue;
      let doc;
      try { doc = JSON.parse(readFileSync(p, "utf8")); } catch { continue; }
      const found = [];
      scanJson(doc, "", rel, found);
      problems.push(...found);
    }

    if (problems.length) {
      console.log(`FAIL  ${f}  — ${problems.length} finding(s)`);
      for (const p of problems.slice(0, 12)) {
        console.log(`        ${p.path}  [${p.why}]`);
        if (p.text) console.log(`           ${JSON.stringify(p.text)}`);
      }
      if (problems.length > 12) console.log(`        ... and ${problems.length - 12} more`);
      bad++;
    } else {
      console.log(`ok    ${f}  — ${files.length} files, no game content`);
    }
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

if (bad) {
  console.log("\nDO NOT PUBLISH.");
  process.exit(1);
}
console.log("\nclean — safe to publish.");
