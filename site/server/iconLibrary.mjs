import { copyFileSync, existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, relative, resolve, sep } from "node:path";
import { SEGMENT, StoreError, rewriteDomain } from "./store.mjs";

const EXTS = new Set([".png", ".webp", ".svg", ".jpg", ".jpeg"]);

export function loadSettings(dataRoot) {
  try {
    return JSON.parse(readFileSync(join(dataRoot, "settings.json"), "utf8"));
  } catch {
    return {};
  }
}

const indexCache = new Map(); // libraryRoot -> [{rel, tokens}]

export function libraryIndex(libraryRoot) {
  if (!indexCache.has(libraryRoot)) {
    const entries = [];
    const walk = (dir) => {
      for (const name of readdirSync(dir)) {
        const full = join(dir, name);
        const stat = statSync(full);
        if (stat.isDirectory()) walk(full);
        else if (EXTS.has(extname(name).toLowerCase())) {
          const rel = relative(libraryRoot, full).split(sep).join("/");
          entries.push({ rel, haystack: rel.toLowerCase() });
        }
      }
    };
    walk(libraryRoot);
    indexCache.set(libraryRoot, entries);
  }
  return indexCache.get(libraryRoot);
}

export function searchIcons(libraryRoot, query, limit = 60) {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  const out = [];
  for (const entry of libraryIndex(libraryRoot)) {
    if (terms.every((t) => entry.haystack.includes(t))) {
      out.push(entry.rel);
      if (out.length >= limit) break;
    }
  }
  return out;
}

export function resolveLibraryFile(libraryRoot, rel) {
  const full = resolve(libraryRoot, rel);
  if (!full.startsWith(resolve(libraryRoot) + sep)) throw new StoreError("bad-segment", rel);
  if (!existsSync(full)) throw new StoreError("not-found", rel);
  return full;
}

/** Copy a library icon in and assign it to one item, or install it as the
 * shared generic for the item's subtype (re-pointing every subtype item that
 * has no specific art). Returns {img, updated}. */
export function assignIcon(dataRoot, libraryRoot, { book, domain, category, itemId, libraryPath, mode }) {
  for (const seg of [book, domain, category]) {
    if (!SEGMENT.test(seg ?? "")) throw new StoreError("bad-segment", String(seg));
  }
  if (!SEGMENT.test(itemId ?? "")) throw new StoreError("bad-segment", String(itemId));
  const source = resolveLibraryFile(libraryRoot, libraryPath);
  const ext = extname(source).toLowerCase();
  const destDir = join(dataRoot, "_assets", book, "lib");

  let subtype = null;
  rewriteDomain(dataRoot, book, domain, (item, cat) => {
    if (cat === category && item.id === itemId) {
      subtype = String(item.system?.subtype || item.system?.type || "");
    }
    return false;
  });
  if (subtype === null) throw new StoreError("not-found", itemId);

  if (mode === "item") {
    const img = `${book}/lib/${itemId}${ext}`;
    copyFileSync(source, join(destDir, `${itemId}${ext}`));
    const updated = rewriteDomain(dataRoot, book, domain, (item, cat) => {
      if (cat === category && item.id === itemId) {
        item.img = img;
        return true;
      }
      return false;
    });
    return { img, updated };
  }

  // mode === "generic": replace the subtype's shared icon and re-point every
  // subtype item that has no specific art (missing img or a _generic_ path)
  const img = `${book}/lib/_generic_${subtype.toLowerCase()}${ext}`;
  copyFileSync(source, join(destDir, `_generic_${subtype.toLowerCase()}${ext}`));
  const genericPrefix = `${book}/lib/_generic_${subtype.toLowerCase()}`;
  const updated = rewriteDomain(dataRoot, book, domain, (item) => {
    const itemSubtype = String(item.system?.subtype || item.system?.type || "");
    if (itemSubtype !== subtype) return false;
    if (item.img && !item.img.startsWith(genericPrefix)) return false;
    if (item.img === img) return false;
    item.img = img;
    return true;
  });
  return { img, updated };
}
