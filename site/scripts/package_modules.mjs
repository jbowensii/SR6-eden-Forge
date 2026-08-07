/** Zip the built modules.
 *
 *    node site/scripts/package_modules.mjs             # local/server use
 *    node site/scripts/package_modules.mjs --release   # for a public release
 *
 *  Two different jobs, and the difference matters.
 *
 *  A **local** package is for your own server: everything the module needs,
 *  including the generated `data/chargen-data.json`.
 *
 *  A **release** package is published to the world, and the line it draws is
 *  the one US law draws: rules and mechanics are systems, not expression, and
 *  are not copyrightable. Prose is. So a release ships the mechanical tables —
 *  priority columns, karma costs, mount capacities, rating ranges — and strips
 *  the written passages: the life-module write-ups, the PACK blurbs, the
 *  descriptions lifted off the page.
 *
 *  That keeps the released module genuinely useful. Every rule works out of
 *  the box; what a fresh install lacks is the flavour text, which the user's
 *  own catalog build restores from books they own.
 *
 *  The compendium module is never published in any form — it is game content
 *  end to end.
 */
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const dist = join(root, "export", "dist");
const RELEASE = process.argv.includes("--release");
mkdirSync(dist, { recursive: true });

/** Files that must never appear in a public artifact, in any form. */
const GAME_CONTENT = [];

/** Files published only after the written passages are removed from them. */
const SANITIZE = ["data/chargen-data.json", "data/creation-rules.json"];

/** Fields holding prose rather than mechanics. */
const PROSE_KEYS = new Set(["desc", "description", "flavor", "flavour",
  // Life-module benefit text, printed almost verbatim from the Companion. The
  // engine never reads it: `grants`, `choices`, `knowledgeSkills` and
  // `contactTypes` carry every mechanical effect separately, so removing the
  // bullets costs the wizard its blurb and nothing else. Found by scanning the
  // packaged file's CONTENT rather than trusting the key list — 188 strings,
  // one of them 4,662 characters, all under a `value` key the earlier rule
  // did not cover.
  "bullets"]);

/** `text` is mostly single-word mechanical tags ("stealth", "strength") inside
 *  the raw trees; only the long ones are written passages. */
const PROSE_TEXT_MIN = 40;

/** A citation keeps its page reference and loses the sentence it quotes.
 *
 *  The reference proves the same thing and is not someone else's writing.
 *  Splitting on the em dash alone was not enough — several notes quote without
 *  one, or carry a second quote further along — so every quoted span is
 *  removed outright, then what remains is trimmed back to the reference.
 */
function citationOnly(v) {
  return v
    .replace(/[‘’'"][^‘’'"]{20,}[‘’'"]/g, "")
    .split(/\s[—-]\s/)[0]
    .replace(/\s*[(;,]\s*$/, "")
    .trim();
}

function stripProse(obj) {
  if (Array.isArray(obj)) return obj.map(stripProse);
  if (obj && typeof obj === "object") {
    const out = {};
    for (const [k, v] of Object.entries(obj)) {
      // key check first, and regardless of type — `bullets` is an ARRAY of
      // {label, value} pairs, so testing only strings let it straight through
      if (PROSE_KEYS.has(k)) continue;
      if (typeof v === "string") {
        if (k === "text" && v.length >= PROSE_TEXT_MIN) continue;
        // matches verified / _verified / note / _note — the underscore prefix
        // is used inconsistently and an exact-name check missed `_verified`
        out[k] = /^_?(verified|note)$/.test(k) ? citationOnly(v) : v;
        continue;
      }
      out[k] = stripProse(v);
    }
    return out;
  }
  return obj;
}

/** Modules that are game data end to end and are never published. */
const NEVER_RELEASED = new Set(["sr6-forge-corebook"]);

for (const id of ["sr6-forge", "sr6-forge-corebook"]) {
  const dir = join(root, "export", id);
  if (!existsSync(dir)) { console.log(`skip ${id} (not built)`); continue; }
  if (RELEASE && NEVER_RELEASED.has(id)) {
    console.log(`skip ${id} — compendium, never distributed`);
    continue;
  }

  const ver = JSON.parse(readFileSync(join(dir, "module.json"), "utf8")).version;
  const suffix = RELEASE ? "" : `-v${ver}`;
  const zip = join(dist, `${id}${suffix}.zip`);

  let src = dir;
  let staging = null;
  if (RELEASE) {
    // Strip game content from a copy, so the built module stays usable locally.
    // Stage inside a wrapper so the folder INSIDE the zip is named `sr6-forge`.
    // Compress-Archive uses the source folder's own name, so staging directly
    // into `.staging-sr6-forge` would install the module under that name and
    // break every path in it.
    const wrap = join(dist, `.stage-${id}`);
    rmSync(wrap, { recursive: true, force: true });
    staging = join(wrap, id);
    cpSync(dir, staging, { recursive: true });
    for (const rel of GAME_CONTENT) {
      const p = join(staging, ...rel.split("/"));
      if (existsSync(p)) {
        rmSync(p, { force: true });
        console.log(`  removed ${rel} (game content)`);
      }
    }
    for (const rel of SANITIZE) {
      const p = join(staging, ...rel.split("/"));
      if (!existsSync(p)) continue;
      const before = readFileSync(p, "utf8");
      const after = stripProse(JSON.parse(before));
      const text = JSON.stringify(after, null, 1);
      writeFileSync(p, text + "\n");
      console.log(`  sanitized ${rel} — removed ${(before.length - text.length).toLocaleString()} chars of prose`);
    }
    src = staging;
  }

  rmSync(zip, { force: true });
  execFileSync("powershell", ["-NoProfile", "-Command",
    `Compress-Archive -Path '${src}' -DestinationPath '${zip}' -Force`]);
  if (staging) rmSync(join(dist, `.stage-${id}`), { recursive: true, force: true });
  console.log(`packaged ${zip}`);
}

if (RELEASE) {
  console.log("\nrelease artifacts carry no game data — verify before publishing:");
  console.log("  node site/scripts/verify_release.mjs");
}
