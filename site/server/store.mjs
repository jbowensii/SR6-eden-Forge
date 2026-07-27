import { readFileSync, readdirSync, renameSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

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

export function typeTree(dataRoot) {
  /** Nested TYPE -> SUBTYPE grouping of every item, with counts + qa rollups.
   * Items with no subtype fall under the "" (no subtype) bucket. */
  const types = new Map();
  for (const entry of tree(dataRoot)) {
    if (entry.error) continue;
    let payload;
    try {
      payload = readCategory(dataRoot, entry.book, entry.domain, entry.category);
    } catch {
      continue;
    }
    for (const item of payload.items ?? []) {
      const type = item.system?.type || "UNTYPED";
      const subtype = item.system?.subtype || "";
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

export function itemsByType(dataRoot, type, subtype) {
  /** Every item of a type (optionally narrowed to a subtype), each annotated
   * with its source `category` so edits still route to the right file. */
  const wantSub = subtype === undefined ? null : subtype;
  const out = [];
  for (const entry of tree(dataRoot)) {
    if (entry.error) continue;
    let payload;
    try {
      payload = readCategory(dataRoot, entry.book, entry.domain, entry.category);
    } catch {
      continue;
    }
    for (const item of payload.items ?? []) {
      if ((item.system?.type || "UNTYPED") !== type) continue;
      if (wantSub !== null && (item.system?.subtype || "") !== wantSub) continue;
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
