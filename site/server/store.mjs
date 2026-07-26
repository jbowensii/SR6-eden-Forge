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
