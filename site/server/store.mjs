// The review app's disk layer: read a domain's items, write an edited one back,
// and catalogue the edit so a re-import cannot quietly undo it.
//
// Two things live here that the rest of the server relies on and neither is
// obvious from the function names:
//
//   * Every path segment that reaches the filesystem goes through SEGMENT and
//     checkSegments first. Domain, category and item id all arrive from the
//     browser, and none of them may become "..".
//
//   * Writing an item ALSO writes a correction record (recordCorrection). The
//     library is regenerated from the PDFs on every import; the correction file
//     is the only reason a manual edit is still there afterwards. Anything that
//     saves an item and skips the record has silently made that edit temporary.
//     tools/apply_corrections.py is the other half of that contract.
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, writeFileSync } from "node:fs";
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
          const visible = (payload.items ?? []).filter((i) => !i.meta?.hidden);
          for (const item of visible) {
            const s = item.meta?.qaStatus;
            if (s in qa) qa[s] += 1;
          }
          out.push({ book, domain, category, items: visible.length, qa });
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
  qualities: { groupBy: "category", subBy: "subtype" },
  lifestyles: { groupBy: "category", subBy: "subtype" },
  skills: { groupBy: "category", subBy: "attribute" },
  npcs: { groupBy: "category", subBy: "metatype" },
  critters: { groupBy: "category", subBy: "subtype" },
  spirits: { groupBy: "category", subBy: "subtype" },
  complexforms: { groupBy: "category", subBy: "duration" },
  echoes: { groupBy: "category", subBy: "subtype" },
  sprite_powers: { groupBy: "category", subBy: "subtype" },
  critter_powers: { groupBy: "category", subBy: "type" },
  metamagics: { groupBy: "category", subBy: "subtype" },
  martial_arts: { groupBy: "category", subBy: "subtype" },
  martial_techniques: { groupBy: "category", subBy: "style" },
  contacts: { groupBy: "category", subBy: "type" },
  sins: { groupBy: "category", subBy: "quality" },
  foci: { groupBy: "category", subBy: "subtype" },
  vehicles: { groupBy: "type", subBy: "subtype" },
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
    for (const item of (payload.items ?? []).filter((i) => !i.meta?.hidden)) {
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
    for (const item of (payload.items ?? []).filter((i) => !i.meta?.hidden)) {
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
    for (const item of (payload.items ?? []).filter((i) => !i.meta?.hidden)) {
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

// Persistent manual corrections: every save is catalogued under
// data/_corrections/<domain>/<id>.json. tools/apply_corrections.py re-applies
// them after any re-import, so a manual edit survives re-extraction until it is
// edited again. Deleting an item records a tombstone so it isn't re-added.
export function recordCorrection(dataRoot, domain, category, item, { deleted = false, before = null } = {}) {
  const dir = join(dataRoot, "_corrections", domain);
  if (!SEGMENT.test(domain) || !SEGMENT.test(item.id)) return;
  mkdirSync(dir, { recursive: true });

  let rec;
  if (deleted) {
    // A tombstone carries `ref` for the same reason an edit does, and more
    // urgently. It is matched on id, and the rows worth deleting have the
    // LEAST stable ids in the library: junk names slug straight into the id,
    // so "OFF ROAD) INTERVAL Dodge Scoot Harley-Davidson" becomes
    // off_road_interval_dodge_scoot_harley_davidson. Improve the reader that
    // produced that name and the id changes, the tombstone stops matching,
    // and a row deleted months ago quietly comes back.
    //
    // Seen for real on 2026-08-08: rejoining wrapped vehicle names turned
    // krupp_bentley into cl6_saeder_krupp_bentley_concordat and three
    // corrections lost their target.
    rec = { domain, category, id: item.id, deleted: true,
            ref: { name: item.name ?? null, book: item.meta?.book ?? null },
            correctedAt: new Date().toISOString() };
  } else {
    // Store only what CHANGED, plus enough to find the item again.
    //
    // A correction used to hold the whole item. That made every edit a
    // wholesale replacement: re-applying one overwrote every field, including
    // values from Commlink6 the user never touched. It also made corrections
    // brittle — when Commlink6 re-keyed rows to cl6_* ids, 55 corrections lost
    // their anchor and there was nothing in the file to re-find the item by.
    //
    // `ref` is that anchor. `changed` is the edit itself.
    const changed = {};
    const sysBefore = (before && before.system) || {};
    const sysNow = item.system || {};
    const sysDelta = {};
    for (const [k, v] of Object.entries(sysNow)) {
      if (JSON.stringify(v) !== JSON.stringify(sysBefore[k])) sysDelta[k] = v;
    }
    if (Object.keys(sysDelta).length) changed.system = sysDelta;
    if (!before || item.name !== before.name) changed.name = item.name;
    if (!before || item.img !== before.img) changed.img = item.img;
    const qa = item.meta?.qaStatus;
    if (!before || qa !== before.meta?.qaStatus) changed.qaStatus = qa;

    rec = {
      domain, category, id: item.id,
      correctedAt: new Date().toISOString(),
      ref: { name: item.name, book: item.meta?.book },
      changed,
    };
  }

  const path = join(dir, `${item.id}.json`);
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, JSON.stringify(rec, null, 2) + "\n", "utf8");
  renameSync(tmp, path);
}

export function writeItem(dataRoot, book, domain, category, itemId, item) {
  if (item.id !== itemId) throw new StoreError("id-mismatch", `${item.id} != ${itemId}`);
  const payload = readCategory(dataRoot, book, domain, category);
  const index = payload.items.findIndex((i) => i.id === itemId);
  if (index === -1) throw new StoreError("not-found", itemId);
  // the item as it WAS, so the correction can record only what changed
  const before = payload.items[index];
  payload.items[index] = item;
  const path = categoryPath(dataRoot, book, domain, category);
  const tmpPath = `${path}.tmp`;
  writeFileSync(tmpPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  renameSync(tmpPath, path);
  recordCorrection(dataRoot, domain, category, item, { before });
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
  // Artwork is a manual choice like any other, so it belongs in the corrections
  // layer. Without this the next import silently wiped every picture assigned
  // by hand: the category file is rewritten from the books, and nothing
  // remembered what had been chosen.
  recordCorrection(dataRoot, domain, category, item);
  return { img: rel };
}

export function deleteItem(dataRoot, book, domain, category, itemId) {
  const payload = readCategory(dataRoot, book, domain, category);
  // Captured BEFORE the filter: the tombstone records the item's name and book
  // so it can still be matched after a reader improvement changes its id, and
  // once the row is gone there is nothing left to read them from.
  const doomed = payload.items.find((i) => i.id === itemId);
  if (!doomed) throw new StoreError("not-found", itemId);
  payload.items = payload.items.filter((i) => i.id !== itemId);
  const path = categoryPath(dataRoot, book, domain, category);
  const tmpPath = `${path}.tmp`;
  writeFileSync(tmpPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  renameSync(tmpPath, path);
  recordCorrection(dataRoot, domain, category, doomed, { deleted: true });
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
