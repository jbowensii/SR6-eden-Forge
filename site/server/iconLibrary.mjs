import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
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

/** Search roots: settings.iconLibrary (string or array) plus the repo-local
 * data/_assets/iconsets tree. Order is stable — assign() references roots by
 * index. */
export function libraryRoots(dataRoot) {
  const configured = loadSettings(dataRoot).iconLibrary;
  const roots = (Array.isArray(configured) ? configured : configured ? [configured] : []).filter((p) => existsSync(p));
  const iconsets = join(dataRoot, "_assets", "iconsets");
  if (existsSync(iconsets)) roots.push(iconsets);
  return roots;
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
          entries.push({ rel, tokens: rel.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean) });
        }
      }
    };
    walk(libraryRoot);
    indexCache.set(libraryRoot, entries);
  }
  return indexCache.get(libraryRoot);
}

export function searchIcons(roots, query, limit = 60) {
  const rootList = Array.isArray(roots) ? roots : [roots];
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  const out = [];
  for (let r = 0; r < rootList.length; r++) {
    for (const entry of libraryIndex(rootList[r])) {
      if (terms.every((t) => entry.tokens.some((tok) => tok.startsWith(t)))) {
        out.push({ r, p: entry.rel });
        if (out.length >= limit) return out;
      }
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

  let itemType = null;
  let subtype = null;
  rewriteDomain(dataRoot, book, domain, (item, cat) => {
    if (cat === category && item.id === itemId) {
      itemType = String(item.system?.type ?? "");
      subtype = String(item.system?.subtype ?? "");
    }
    return false;
  });
  if (itemType === null) throw new StoreError("not-found", itemId);

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

  // mode === "generic": install the icon as the shared image for every item
  // of this TYPE+SUBTYPE across the domain, and remember the choice in
  // data/_assets/generic/defaults.json so future imports reuse it
  const slug = `${itemType}_${subtype}`.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const genericDir = join(dataRoot, "_assets", "generic");
  mkdirSync(genericDir, { recursive: true });
  const img = `generic/${slug}${ext}`;
  copyFileSync(source, join(genericDir, `${slug}${ext}`));

  const defaultsPath = join(genericDir, "defaults.json");
  let defaults = {};
  try {
    defaults = JSON.parse(readFileSync(defaultsPath, "utf8"));
  } catch {}
  defaults[`${itemType}/${subtype}`] = img;
  writeFileSync(defaultsPath, JSON.stringify(defaults, null, 2) + "\n", "utf8");

  const updated = rewriteDomain(dataRoot, book, domain, (item) => {
    if (String(item.system?.type ?? "") !== itemType) return false;
    if (String(item.system?.subtype ?? "") !== subtype) return false;
    if (item.img === img) return false;
    item.img = img;
    return true;
  });
  return { img, updated, scope: `${itemType}/${subtype}` };
}
