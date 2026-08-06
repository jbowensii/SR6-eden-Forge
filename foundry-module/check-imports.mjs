/** Catch identifiers used but never imported.
 *
 *  `node --check` validates syntax only, so a call to an un-imported helper
 *  passes it and fails at runtime — which is exactly how catalogIdOf() shipped
 *  broken into the Quench batches after a rename, and how four wrong import
 *  paths shipped before that. This walks every module, collects what each file
 *  imports plus what it declares locally, and reports any call to a name one of
 *  our own modules exports that was never brought in.
 *
 *      node foundry-module/check-imports.mjs
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, "sr6-forge", "scripts");

const files = [];
(function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) walk(p);
    else if (entry.endsWith(".mjs")) files.push(p);
  }
})(ROOT);

/** Every name our own modules export. */
const exported = new Set();
for (const f of files) {
  const src = readFileSync(f, "utf8");
  for (const m of src.matchAll(/^export\s+(?:async\s+)?(?:function|const|class)\s+(\w+)/gm)) {
    exported.add(m[1]);
  }
}

let missing = 0;
let unresolved = 0;

for (const f of files) {
  const src = readFileSync(f, "utf8");

  // relative imports must actually resolve on disk
  for (const m of src.matchAll(/from\s+"(\.[^"]+)"/g)) {
    const target = resolve(dirname(f), m[1]);
    try {
      statSync(target);
    } catch {
      console.log(`  ${f}\n      -> ${m[1]} does not resolve`);
      unresolved++;
    }
  }

  const imported = new Set();
  for (const m of src.matchAll(/import\s*\{([^}]+)\}/g)) {
    for (const part of m[1].split(",")) {
      imported.add(part.trim().split(/\s+as\s+/).pop().trim());
    }
  }
  const local = new Set();
  for (const m of src.matchAll(/(?:function|const|let|var|class)\s+(\w+)/g)) local.add(m[1]);
  // destructured, including `const { X } = await import(...)`
  for (const m of src.matchAll(/\{([^{}]*)\}\s*=/g)) {
    for (const part of m[1].split(",")) local.add(part.trim().split(":").pop().trim());
  }
  // class methods legitimately share names with exported helpers (contactPoints, ...)
  for (const m of src.matchAll(/^\s{2,}(?:async\s+|static\s+|#)*(\w+)\s*\(/gm)) local.add(m[1]);

  // strip comments, so prose like "see ratedValues()" is not read as a call
  const code = src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");

  for (const name of exported) {
    if (imported.has(name) || local.has(name)) continue;
    // a real call is not preceded by a dot — that would be a method on something else
    const called = new RegExp(String.raw`(^|[^.\w])${name}\s*\(`, "m");
    if (called.test(code)) {
      console.log(`  ${f}\n      -> calls ${name}() but never imports it`);
      missing++;
    }
  }
}

const bad = missing + unresolved;
console.log(bad
  ? `FAIL — ${missing} missing import(s), ${unresolved} unresolved path(s)`
  : `PASS — ${files.length} modules, every import resolves and every call is imported`);
process.exit(bad ? 1 : 0);
