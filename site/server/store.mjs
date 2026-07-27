import { copyFileSync, existsSync, readFileSync, readdirSync, renameSync, statSync, writeFileSync } from "node:fs";
import { extname, join } from "node:path";

export const SEGMENT = /^[a-z0-9_]+$/;

export class StoreError extends Error {
  constructor(code, detail = "") {
    super(detail ? `${code}: ${detail}` : code);
    this.code = code;
  }
}

function checkSegments(...segments) {
  for (const s of segments) {
    if (!SEGMENT.test(s)) throw new StoreError("bad-segment", s);
  }
}

function categoryPath(dataRoot, book, domain, category) {
  checkSegments(book, domain, category);
  return join(dataRoot, book, domain, `${category}.json`);
}

export function tree(dataRoot) {
  const out = [];
  for (const book of readdirSync(dataRoot)) {
    if (book.startsWith("_") || !SEGMENT.test(book)) continue;
    const bookDir = join(dataRoot, book);
    if (!statSync(bookDir).isDirectory()) continue;
    for (const domain of readdirSync(bookDir)) {
      if (domain.startsWith("_") || !SEGMENT.test(domain)) continue;
      const domainDir = join(bookDir, domain);
      if (!statSync(domainDir).isDirectory()) continue;
      for (const file of readdirSync(domainDir)) {
        if (!file.endsWith(".json")) continue;
        const category = file.replace(/\.json$/, "");
        try {
          const payload = JSON.parse(readFileSync(join(domainDir, file), "utf8"));
          const qa = { extracted: 0, reviewed: 0, approved: 0 };
          for (const item of payload.items ?? []) {
            const s = item.meta?.qaStatus;
            if (s in qa) qa[s] += 1;
          }
          out.push({ book, domain, category, items: (payload.items ?? []).length, qa });
        } catch {
          out.push({
            book,
            domain,
            category,
            items: 0,
            qa: { extracted: 0, reviewed: 0, approved: 0 },
            error: "unreadable",
          });
        }
      }
    }
  }
  return out.sort((a, b) => `${a.book}/${a.domain}/${a.category}`.localeCompare(`${b.book}/${b.domain}/${b.category}`));
}

function _blankQa() {
  return { extracted: 0, reviewed: 0, approved: 0 };
}

function _addQa(qa, item) {
  const s = item.meta?.qaStatus;
  if (s in qa) qa[s] += 1;
}

// how each domain groups in the left pane: primary field -> secondary field.
export const DOMAIN_GROUPING = {
  gear: { groupBy: "type", subBy: "subtype" },
  spells: { groupBy: "category", subBy: "subtype" },
  rituals: { groupBy: "category", subBy: "subtype" },
  adept_powers: { groupBy: "category", subBy: "subtype" },
  toxins: { groupBy: "category", subBy: "subtype" },
  drugs: { groupBy: "category", subBy: "subtype" },
  qualities: { groupBy: "category", subBy: "subtype" },
  lifestyles: { groupBy: "category", subBy: "subtype" },
  skills: { groupBy: "category", subBy: "attribute" },
  npcs: { groupBy: "category", subBy: "metatype" },
};

export function domains(dataRoot) {
  /** Domains present in the library that have a schema-backed grouping. */
  const found = new Set(tree(dataRoot).map((e) => e.domain));
  return Object.keys(DOMAIN_GROUPING).filter((d) => found.has(d));
}

export function typeTree(dataRoot, domain = "gear") {
  /** Nested primary -> secondary grouping of a domain's items (gear: type ->
   * subtype; spells: category -> subtype), with counts + qa rollups. Items with
   * no secondary value fall under the "" bucket. */
  const { groupBy, subBy } = DOMAIN_GROUPING[domain] ?? DOMAIN_GROUPING.gear;
  const types = new Map();
  for (const entry of tree(dataRoot)) {
    if (entry.error || entry.domain !== domain) continue;
    let payload;
    try {
      payload = readCategory(dataRoot, entry.book, entry.domain, entry.category);
    } catch {
      continue;
    }
    for (const item of payload.items ?? []) {
      const type = item.system?.[groupBy] || "UNTYPED";
      const subtype = (subBy && item.system?.[subBy]) || "";
      if (!types.has(type)) types.set(type, { type, items: 0, qa: _blankQa(), subs: new Map() });
      const t = types.get(type);
      t.items += 1;
      _addQa(t.qa, item);
      if (!t.subs.has(subtype)) t.subs.set(subtype, { subtype, items: 0, qa: _blankQa() });
      const s = t.subs.get(subtype);
      s.items += 1;
      _addQa(s.qa, item);
    }
  }
  return [...types.values()]
    .map((t) => ({
      type: t.type,
      items: t.items,
      qa: t.qa,
      subtypes: [...t.subs.values()].sort((a, b) => a.subtype.localeCompare(b.subtype)),
    }))
    .sort((a, b) => a.type.localeCompare(b.type));
}

export function itemsByType(dataRoot, type, subtype, domain = "gear") {
  /** Every item of a primary group (optionally narrowed to a secondary value),
   * each annotated with its source category so edits route to the right file. */
  const { groupBy, subBy } = DOMAIN_GROUPING[domain] ?? DOMAIN_GROUPING.gear;
  const wantSub = subtype === undefined ? null : subtype;
  const out = [];
  for (const entry of tree(dataRoot)) {
    if (entry.error || entry.domain !== domain) continue;
    let payload;
    try {
      payload = readCategory(dataRoot, entry.book, entry.domain, entry.category);
    } catch {
      continue;
    }
    for (const item of payload.items ?? []) {
      if ((item.system?.[groupBy] || "UNTYPED") !== type) continue;
      if (wantSub !== null && ((subBy && item.system?.[subBy]) || "") !== wantSub) continue;
      out.push({ ...item, _category: entry.category, _book: entry.book, _domain: entry.domain });
    }
  }
  return { type, subtype: wantSub, items: out };
}

export function searchItems(dataRoot, query, limit = 60) {
  /** Scan every category file and return items whose name contains `query`
   * (case-insensitive). Powers the left-pane item finder. */
  const q = String(query || "").trim().toLowerCase();
  if (!q) return [];
  const hits = [];
  for (const entry of tree(dataRoot)) {
    if (entry.error) continue;
    let payload;
    try {
      payload = readCategory(dataRoot, entry.book, entry.domain, entry.category);
    } catch {
      continue;
    }
    for (const item of payload.items ?? []) {
      if (String(item.name || "").toLowerCase().includes(q)) {
        hits.push({
          book: entry.book, domain: entry.domain, category: entry.category,
          id: item.id, name: item.name,
          type: item.system?.type ?? "", sourceBook: item.meta?.book ?? entry.book,
        });
        if (hits.length >= limit) return hits;
      }
    }
  }
  return hits;
}

export function readCategory(dataRoot, book, domain, category) {
  const path = categoryPath(dataRoot, book, domain, category);
  let raw;
  try {
    raw = readFileSync(path, "utf8");
  } catch {
    throw new StoreError("not-found", `${book}/${domain}/${category}`);
  }
  return JSON.parse(raw);
}

export function writeItem(dataRoot, book, domain, category, itemId, item) {
  if (item.id !== itemId) throw new StoreError("id-mismatch", `${item.id} != ${itemId}`);
  const payload = readCategory(dataRoot, book, domain, category);
  const index = payload.items.findIndex((i) => i.id === itemId);
  if (index === -1) throw new StoreError("not-found", itemId);
  payload.items[index] = item;
  const path = categoryPath(dataRoot, book, domain, category);
  const tmpPath = `${path}.tmp`;
  writeFileSync(tmpPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  renameSync(tmpPath, path);
  return item;
}

const _IMG = /\.(png|jpe?g|webp)$/i;

export function listBookImages(dataRoot, book) {
  /** Every graphic extracted from a book — top-level renders and the unpaired
   * _inbox pile — as paths relative to _assets (served at /assets/<path>). */
  if (!SEGMENT.test(book)) throw new StoreError("bad-segment", book);
  const base = join(dataRoot, "_assets", book);
  const out = [];
  const scan = (dir, prefix) => {
    let names = [];
    try { names = readdirSync(dir); } catch { return; }
    for (const n of names.sort()) {
      if (_IMG.test(n)) out.push(`${prefix}${n}`);
    }
  };
  scan(base, `${book}/`);
  scan(join(base, "_inbox"), `${book}/_inbox/`);
  return out;
}

export function assignRender(dataRoot, book, domain, category, itemId, imagePath) {
  /** Copy an extracted book image to <sourceBook>/<itemId>.<ext> (the render
   * slot) and point the item's img at it. */
  const payload = readCategory(dataRoot, book, domain, category);
  const item = payload.items.find((i) => i.id === itemId);
  if (!item) throw new StoreError("not-found", itemId);
  // imagePath must be a safe "<book>/<...>/<file>" under _assets
  if (!/^[a-z0-9_]+\/(_inbox\/)?[A-Za-z0-9._-]+$/.test(imagePath || "")) {
    throw new StoreError("bad-segment", String(imagePath));
  }
  const source = join(dataRoot, "_assets", imagePath);
  if (!existsSync(source)) throw new StoreError("not-found", imagePath);
  const src = item.meta?.book ?? book;
  const rel = `${src}/${itemId}${extname(imagePath) || ".png"}`;
  copyFileSync(source, join(dataRoot, "_assets", rel));
  item.img = rel;
  const path = categoryPath(dataRoot, book, domain, category);
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, JSON.stringify(payload, null, 2) + "\n", "utf8");
  renameSync(tmp, path);
  return { img: rel };
}

export function deleteItem(dataRoot, book, domain, category, itemId) {
  const payload = readCategory(dataRoot, book, domain, category);
  const before = payload.items.length;
  payload.items = payload.items.filter((i) => i.id !== itemId);
  if (payload.items.length === before) throw new StoreError("not-found", itemId);
  const path = categoryPath(dataRoot, book, domain, category);
  const tmpPath = `${path}.tmp`;
  writeFileSync(tmpPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  renameSync(tmpPath, path);
  return { deleted: itemId };
}

export function rewriteDomain(dataRoot, book, domain, mutate) {
  /** Apply mutate(item, category) across every category file of a domain;
   * files with changes are rewritten atomically. Returns changed-item count. */
  checkSegments(book, domain);
  const domainDir = join(dataRoot, book, domain);
  let updated = 0;
  for (const file of readdirSync(domainDir).filter((f) => f.endsWith(".json")).sort()) {
    const path = join(domainDir, file);
    const payload = JSON.parse(readFileSync(path, "utf8"));
    let changed = false;
    for (const item of payload.items ?? []) {
      if (mutate(item, file.replace(/\.json$/, ""))) {
        changed = true;
        updated += 1;
      }
    }
    if (changed) {
      const tmpPath = `${path}.tmp`;
      writeFileSync(tmpPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
      renameSync(tmpPath, path);
    }
  }
  return updated;
}
