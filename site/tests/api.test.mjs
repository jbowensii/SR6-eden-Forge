import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import request from "supertest";
import { describe, expect, it } from "vitest";
import { buildApp } from "../server/app.mjs";

const ITEM = {
  id: "example_autopistol",
  name: "Example Autopistol",
  system: { type: "WEAPON_FIREARMS", price: 620 },
  meta: { book: "corebook", page: 1, extractedAt: "2026-07-25", extractorVersion: "0.1.0", qaStatus: "extracted" },
};

function makeApp() {
  const root = mkdtempSync(join(tmpdir(), "forge-api-"));
  const dir = join(root, "corebook", "gear");
  mkdirSync(dir, { recursive: true });
  writeFileSync(
    join(dir, "weapons_firearms.json"),
    JSON.stringify({ book: "corebook", domain: "gear", category: "weapons_firearms", items: [ITEM] }, null, 2) + "\n",
  );
  const schemasDir = mkdtempSync(join(tmpdir(), "forge-schemas-"));
  writeFileSync(join(schemasDir, "gear.schema.json"), JSON.stringify({ title: "gear stub" }));
  const validate = async () => ({ ok: true, files: 1, items: 1, issues: [] });
  return buildApp(root, { schemasDir, validate });
}

function makeAppWithExporter(exporter) {
  const root = mkdtempSync(join(tmpdir(), "forge-api-"));
  const dir = join(root, "corebook", "gear");
  mkdirSync(dir, { recursive: true });
  writeFileSync(
    join(dir, "weapons_firearms.json"),
    JSON.stringify({ book: "corebook", domain: "gear", category: "weapons_firearms", items: [ITEM] }, null, 2) + "\n",
  );
  const schemasDir = mkdtempSync(join(tmpdir(), "forge-schemas-"));
  writeFileSync(join(schemasDir, "gear.schema.json"), JSON.stringify({ title: "gear stub" }));
  const validate = async () => ({ ok: true, files: 1, items: 1, issues: [] });
  return buildApp(root, { schemasDir, validate, exporter });
}

describe("api", () => {
  it("GET /api/tree", async () => {
    const res = await request(makeApp()).get("/api/tree");
    expect(res.status).toBe(200);
    expect(res.body[0].category).toBe("weapons_firearms");
  });

  it("GET /api/schema/:domain and 404", async () => {
    const app = makeApp();
    expect((await request(app).get("/api/schema/gear")).status).toBe(200);
    expect((await request(app).get("/api/schema/nope")).status).toBe(404);
  });

  it("GET /api/category and 404", async () => {
    const app = makeApp();
    const res = await request(app).get("/api/category/corebook/gear/weapons_firearms");
    expect(res.body.items).toHaveLength(1);
    expect((await request(app).get("/api/category/corebook/gear/nope")).status).toBe(404);
  });

  it("PUT /api/item updates and returns preview doc", async () => {
    const app = makeApp();
    const updated = { ...ITEM, meta: { ...ITEM.meta, qaStatus: "approved" } };
    const res = await request(app).put("/api/item/corebook/gear/weapons_firearms/example_autopistol").send(updated);
    expect(res.status).toBe(200);
    expect(res.body.item.meta.qaStatus).toBe("approved");
    expect(res.body.doc.type).toBe("gear");
    const after = await request(app).get("/api/category/corebook/gear/weapons_firearms");
    expect(after.body.items[0].meta.qaStatus).toBe("approved");
  });

  it("PUT rejects id mismatch and malformed path segments", async () => {
    const app = makeApp();
    expect((await request(app).put("/api/item/corebook/gear/weapons_firearms/example_autopistol").send({ ...ITEM, id: "other" })).status).toBe(400);
    expect((await request(app).put("/api/item/corebook/gear/weapons_firearms/%2e%2e").send(ITEM)).status).toBe(400);
  });

  it("POST /api/validate returns injected result", async () => {
    const res = await request(makeApp()).post("/api/validate");
    expect(res.body.ok).toBe(true);
  });

  it("PUT returns docError when transform fails", async () => {
    const app = makeApp();
    const broken = { ...ITEM, system: {} };
    const res = await request(app).put("/api/item/corebook/gear/weapons_firearms/example_autopistol").send(broken);
    expect(res.status).toBe(200);
    expect(res.body.doc).toBeNull();
    expect(res.body.docError).toMatch(/system.type/);
  });

  it("malformed JSON body gets a JSON 400, not HTML", async () => {
    const res = await request(makeApp())
      .put("/api/item/corebook/gear/weapons_firearms/example_autopistol")
      .set("Content-Type", "application/json")
      .send("{bad json");
    expect(res.status).toBe(400);
    expect(res.headers["content-type"]).toMatch(/json/);
    expect(res.body.error).toBe("bad-json");
  });

  it("GET on /api/item is 404 json, not 400", async () => {
    const res = await request(makeApp()).get("/api/item/corebook/gear/weapons_firearms/example_autopistol");
    expect(res.status).toBe(404);
    expect(res.body.error).toBe("no-route");
  });

  it("POST /api/export happy path", async () => {
    const app = makeAppWithExporter(async () => ({ moduleDir: "X", count: 3, packName: "corebook-gear" }));
    const res = await request(app).post("/api/export").send({ book: "corebook", domain: "gear", status: "all" });
    expect(res.status).toBe(200);
    expect(res.body.count).toBe(3);
  });

  it("POST /api/export empty -> 409", async () => {
    const app = makeAppWithExporter(async () => {
      throw new Error("no items match status \"approved\" in corebook/gear");
    });
    const res = await request(app).post("/api/export").send({ book: "corebook", domain: "gear" });
    expect(res.status).toBe(409);
  });

  it("POST /api/export bad status -> 400", async () => {
    const app = makeAppWithExporter(async () => ({}));
    const res = await request(app).post("/api/export").send({ book: "corebook", domain: "gear", status: "everything" });
    expect(res.status).toBe(400);
  });
});

describe("books and pdf", () => {
  function makeAppWithBooks(books) {
    const root = mkdtempSync(join(tmpdir(), "forge-books-"));
    mkdirSync(join(root, "corebook", "gear"), { recursive: true });
    writeFileSync(
      join(root, "corebook", "gear", "weapons_firearms.json"),
      JSON.stringify({ book: "corebook", domain: "gear", category: "weapons_firearms", items: [ITEM] }, null, 2) + "\n",
    );
    if (books) writeFileSync(join(root, "books.json"), JSON.stringify(books));
    const schemasDir = mkdtempSync(join(tmpdir(), "forge-sch2-"));
    writeFileSync(join(schemasDir, "gear.schema.json"), "{}");
    return { root, app: buildApp(root, { schemasDir, validate: async () => ({}) }) };
  }

  it("GET /api/books reports titles and pdf availability", async () => {
    const pdf = join(mkdtempSync(join(tmpdir(), "forge-pdf-")), "book.pdf");
    writeFileSync(pdf, "%PDF-1.4 fake");
    const { app } = makeAppWithBooks({ corebook: { title: "Core", pdf } });
    const res = await request(app).get("/api/books");
    expect(res.body.corebook).toEqual({ title: "Core", pdf: true, pageOffset: 0 });
  });

  it("GET /api/pdf/:book streams when configured, 404 otherwise", async () => {
    const pdf = join(mkdtempSync(join(tmpdir(), "forge-pdf2-")), "book.pdf");
    writeFileSync(pdf, "%PDF-1.4 fake");
    const { app } = makeAppWithBooks({ corebook: { title: "Core", pdf } });
    const ok = await request(app).get("/api/pdf/corebook");
    expect(ok.status).toBe(200);
    expect(ok.headers["content-type"]).toMatch(/pdf/);
    const missing = await request(app).get("/api/pdf/nosuch");
    expect(missing.status).toBe(404);
  });

  it("PUT preview carries product from books.json", async () => {
    const { app } = makeAppWithBooks({ corebook: { title: "Core Book Title" } });
    const res = await request(app).put("/api/item/corebook/gear/weapons_firearms/example_autopistol").send(ITEM);
    expect(res.body.doc.system.product).toBe("Core Book Title");
    expect(res.body.doc.system.page).toBe(1);
  });
});

describe("icon library", () => {
  function makeIconApp() {
    const root = mkdtempSync(join(tmpdir(), "forge-iconlib-"));
    mkdirSync(join(root, "corebook", "gear"), { recursive: true });
    mkdirSync(join(root, "_assets", "corebook", "lib"), { recursive: true });
    const items = [
      { ...ITEM },
      {
        ...ITEM,
        id: "example_smg",
        name: "Example SMG",
        system: { type: "WEAPON_FIREARMS", subtype: "SUBMACHINE_GUNS", price: 900 },
        meta: { ...ITEM.meta },
      },
      {
        ...ITEM,
        id: "example_smg2",
        name: "Example SMG2",
        img: "corebook/lib/_generic_submachine_guns.svg",
        system: { type: "WEAPON_FIREARMS", subtype: "SUBMACHINE_GUNS", price: 950 },
        meta: { ...ITEM.meta },
      },
    ];
    writeFileSync(
      join(root, "corebook", "gear", "weapons_firearms.json"),
      JSON.stringify({ book: "corebook", domain: "gear", category: "weapons_firearms", items }, null, 2) + "\n",
    );
    const lib = mkdtempSync(join(tmpdir(), "forge-lib-"));
    mkdirSync(join(lib, "cyberpunk"), { recursive: true });
    writeFileSync(join(lib, "cyberpunk", "smg_worn.png"), "PNGDATA");
    writeFileSync(join(root, "settings.json"), JSON.stringify({ iconLibrary: lib }));
    const schemasDir = mkdtempSync(join(tmpdir(), "forge-sch3-"));
    writeFileSync(join(schemasDir, "gear.schema.json"), "{}");
    return { root, app: buildApp(root, { schemasDir, validate: async () => ({}) }) };
  }

  it("GET /api/icons searches the configured library", async () => {
    const { app } = makeIconApp();
    const res = await request(app).get("/api/icons?q=smg");
    expect(res.status).toBe(200);
    expect(res.body).toEqual([{ r: 0, p: "cyberpunk/smg_worn.png" }]);
    expect((await request(app).get("/api/icons?q=nothingmatches")).body).toEqual([]);
  });

  it("POST /api/icon/assign mode item sets one item's img", async () => {
    const { root, app } = makeIconApp();
    const res = await request(app).post("/api/icon/assign").send({
      book: "corebook", domain: "gear", category: "weapons_firearms",
      itemId: "example_smg", libraryPath: "cyberpunk/smg_worn.png", mode: "item",
    });
    expect(res.status).toBe(200);
    expect(res.body.img).toBe("corebook/lib/example_smg.png");
    const payload = JSON.parse(readFileSync(join(root, "corebook", "gear", "weapons_firearms.json"), "utf8"));
    expect(payload.items[1].img).toBe("corebook/lib/example_smg.png");
    expect(payload.items[2].img).toBe("corebook/lib/_generic_submachine_guns.svg");
  });

  it("POST /api/icon/assign mode generic scopes to TYPE+SUBTYPE and records a default", async () => {
    const { root, app } = makeIconApp();
    const res = await request(app).post("/api/icon/assign").send({
      book: "corebook", domain: "gear", category: "weapons_firearms",
      itemId: "example_smg", libraryPath: "cyberpunk/smg_worn.png", mode: "generic",
    });
    expect(res.status).toBe(200);
    expect(res.body.img).toBe("generic/weapon_firearms_submachine_guns.png");
    expect(res.body.updated).toBe(2); // both SMGs; the heavy pistol untouched
    const payload = JSON.parse(readFileSync(join(root, "corebook", "gear", "weapons_firearms.json"), "utf8"));
    expect(payload.items[0].img).toBeUndefined(); // PISTOLS_HEAVY-typed item... (no subtype match)
    expect(payload.items[1].img).toBe("generic/weapon_firearms_submachine_guns.png");
    expect(payload.items[2].img).toBe("generic/weapon_firearms_submachine_guns.png");
    const defaults = JSON.parse(readFileSync(join(root, "_assets", "generic", "defaults.json"), "utf8"));
    expect(defaults["WEAPON_FIREARMS/SUBMACHINE_GUNS"]).toBe("generic/weapon_firearms_submachine_guns.png");
  });

  it("assign rejects traversal and bad mode", async () => {
    const { app } = makeIconApp();
    const bad = await request(app).post("/api/icon/assign").send({
      book: "corebook", domain: "gear", category: "weapons_firearms",
      itemId: "example_smg", libraryPath: "../outside.png", mode: "item",
    });
    expect(bad.status).toBe(400);
    const badMode = await request(app).post("/api/icon/assign").send({
      book: "corebook", domain: "gear", category: "weapons_firearms",
      itemId: "example_smg", libraryPath: "cyberpunk/smg_worn.png", mode: "both",
    });
    expect(badMode.status).toBe(400);
  });
});

// ── bulk operations ────────────────────────────────────────────────────────

function makeBulkApp() {
  const root = mkdtempSync(join(tmpdir(), "forge-bulk-"));
  const gear = join(root, "corebook", "gear");
  const vehicles = join(root, "corebook", "vehicles");
  mkdirSync(gear, { recursive: true });
  mkdirSync(vehicles, { recursive: true });
  const mk = (id, name, system = {}) => ({
    id, name, system: { type: "WEAPON_FIREARMS", ...system },
    meta: { book: "corebook", page: 1, extractedAt: "2026-08-09",
            extractorVersion: "0.1.0", qaStatus: "extracted" },
  });
  writeFileSync(join(gear, "weapons_firearms.json"), JSON.stringify(
    { book: "corebook", domain: "gear", category: "weapons_firearms",
      items: [mk("a_one", "A One"), mk("b_two", "B Two", { subtype: "PISTOLS_HEAVY" })] }, null, 2) + "\n");
  writeFileSync(join(vehicles, "vehicles.json"), JSON.stringify(
    { book: "corebook", domain: "vehicles", category: "vehicles",
      items: [mk("c_three", "C Three", { type: "VEHICLE" })] }, null, 2) + "\n");
  const schemasDir = mkdtempSync(join(tmpdir(), "forge-schemas-"));
  writeFileSync(join(schemasDir, "gear.schema.json"), JSON.stringify({ title: "gear stub" }));
  return { app: buildApp(root, { schemasDir, validate: async () => ({ ok: true, issues: [] }) }), root };
}

const T = (id, domain = "gear", category = "weapons_firearms") =>
  ({ book: "corebook", domain, category, id });

describe("PATCH /api/items", () => {
  it("writes only the fields present in changes", async () => {
    const { app, root } = makeBulkApp();
    const res = await request(app).patch("/api/items").send({
      targets: [T("a_one"), T("b_two")],
      changes: { system: { subtype: "PISTOLS_LIGHT" } },
    });
    expect(res.status).toBe(200);
    expect(res.body.updated).toBe(2);
    const items = JSON.parse(readFileSync(
      join(root, "corebook", "gear", "weapons_firearms.json"), "utf8")).items;
    // subtype set on both...
    expect(items.map((i) => i.system.subtype)).toEqual(["PISTOLS_LIGHT", "PISTOLS_LIGHT"]);
    // ...and nothing else touched
    expect(items.map((i) => i.name)).toEqual(["A One", "B Two"]);
    expect(items.every((i) => i.system.type === "WEAPON_FIREARMS")).toBe(true);
  });

  it("spans books and domains in one call", async () => {
    const { app, root } = makeBulkApp();
    const res = await request(app).patch("/api/items").send({
      targets: [T("a_one"), T("c_three", "vehicles", "vehicles")],
      changes: { qaStatus: "reviewed" },
    });
    expect(res.body.updated).toBe(2);
    const veh = JSON.parse(readFileSync(
      join(root, "corebook", "vehicles", "vehicles.json"), "utf8")).items[0];
    expect(veh.meta.qaStatus).toBe("reviewed");
  });

  it("records one correction per item, as a delta", async () => {
    const { app, root } = makeBulkApp();
    await request(app).patch("/api/items").send({
      targets: [T("a_one"), T("b_two")],
      changes: { system: { subtype: "PISTOLS_LIGHT" } },
    });
    const rec = JSON.parse(readFileSync(
      join(root, "_corrections", "gear", "a_one.json"), "utf8"));
    expect(rec.changed.system.subtype).toBe("PISTOLS_LIGHT");
    expect(rec.changed.system.type).toBeUndefined();   // untouched, so not recorded
    expect(rec.ref.name).toBe("A One");
  });

  it("one bad target does not lose the rest of the batch", async () => {
    const { app } = makeBulkApp();
    const res = await request(app).patch("/api/items").send({
      targets: [T("a_one"), T("ghost"), T("b_two")],
      changes: { system: { subtype: "PISTOLS_LIGHT" } },
    });
    expect(res.body.updated).toBe(2);
    expect(res.body.failed).toHaveLength(1);
    expect(res.body.failed[0].id).toBe("ghost");
  });

  it("refuses an empty batch rather than silently doing nothing", async () => {
    const { app } = makeBulkApp();
    expect((await request(app).patch("/api/items").send({ targets: [], changes: {} })).status).toBe(400);
  });
});

describe("DELETE /api/items", () => {
  it("removes every target and reports the count", async () => {
    const { app, root } = makeBulkApp();
    const res = await request(app).delete("/api/items").send({ targets: [T("a_one"), T("b_two")] });
    expect(res.body.deleted).toBe(2);
    const items = JSON.parse(readFileSync(
      join(root, "corebook", "gear", "weapons_firearms.json"), "utf8")).items;
    expect(items).toHaveLength(0);
  });

  it("leaves a tombstone carrying name and book, not just an id", async () => {
    // The rows worth deleting have the least stable ids in the library — junk
    // names slug straight into the id. Without ref, improving the reader that
    // produced the name changes the id and the deletion silently undoes itself.
    const { app, root } = makeBulkApp();
    await request(app).delete("/api/items").send({ targets: [T("a_one")] });
    const rec = JSON.parse(readFileSync(
      join(root, "_corrections", "gear", "a_one.json"), "utf8"));
    expect(rec.deleted).toBe(true);
    // page too: 36 of the 43 id-collisions are separated only by book,
    // and the rest need the page to pin down which row was meant.
    expect(rec.ref).toEqual({ name: "A One", book: "corebook", page: 1 });
  });

  it("one missing target does not stop the others", async () => {
    const { app } = makeBulkApp();
    const res = await request(app).delete("/api/items").send({
      targets: [T("a_one"), T("ghost")],
    });
    expect(res.body.deleted).toBe(1);
    expect(res.body.failed).toHaveLength(1);
  });
});

// ── duplicates, and deleting ONE of a pair ────────────────────────────────

function makeTwinApp() {
  const root = mkdtempSync(join(tmpdir(), "forge-twin-"));
  const gear = join(root, "corebook", "gear");
  mkdirSync(gear, { recursive: true });
  const row = (id, name, book, page, system = {}, source = "commlink6") => ({
    id, name, system: { type: "WEAPON_ACCESSORY", ...system },
    meta: { book, page, source, qaStatus: "extracted",
            extractedAt: "2026-08-09", extractorVersion: "0.1.0" },
  });
  writeFileSync(join(gear, "weapon_accessories.json"), JSON.stringify({
    book: "corebook", domain: "gear", category: "weapon_accessories",
    items: [
      // the Folding Stock case: ONE id, two books, one fuller
      row("cl6_folding_stock", "Folding Stock", "corebook", 1, { price: 30 }),
      row("cl6_folding_stock", "Folding Stock", "firing_squad", 2,
          { price: 30, description: "Folding stock." }),
      // the other common shape: same name, different ids, mixed sources
      row("cl6_power_clip", "Power Clip", "deadly_arts", 3, { price: 500 }),
      row("power_clip", "Power Clip", "deadly_arts", 3, { price: 500 }, "pdf"),
    ],
  }, null, 2) + "\n");
  const schemasDir = mkdtempSync(join(tmpdir(), "forge-schemas-"));
  writeFileSync(join(schemasDir, "gear.schema.json"), JSON.stringify({ title: "stub" }));
  return { app: buildApp(root, { schemasDir, validate: async () => ({ ok: true, issues: [] }) }), root };
}

const rowsOf = (root) => JSON.parse(readFileSync(
  join(root, "corebook", "gear", "weapon_accessories.json"), "utf8")).items;

describe("deleting one of two rows sharing an id", () => {
  it("removes ONE row, not every row with that id", async () => {
    // Deleting by id took both copies of Folding Stock: two on screen, none
    // after. Commlink6 reuses ids across books, so this is not an edge case.
    const { app, root } = makeTwinApp();
    const res = await request(app).delete("/api/items").send({
      targets: [{ book: "corebook", domain: "gear", category: "weapon_accessories",
                  id: "cl6_folding_stock", srcBook: "corebook", srcPage: 1 }],
    });
    expect(res.body.deleted).toBe(1);
    const left = rowsOf(root).filter((i) => i.id === "cl6_folding_stock");
    expect(left).toHaveLength(1);
    expect(left[0].meta.book).toBe("firing_squad");     // the one we kept
  });

  it("the tombstone records which twin went", async () => {
    const { app, root } = makeTwinApp();
    await request(app).delete("/api/items").send({
      targets: [{ book: "corebook", domain: "gear", category: "weapon_accessories",
                  id: "cl6_folding_stock", srcBook: "corebook", srcPage: 1 }],
    });
    const rec = JSON.parse(readFileSync(
      join(root, "_corrections", "gear", "cl6_folding_stock.json"), "utf8"));
    expect(rec.ref).toEqual({ name: "Folding Stock", book: "corebook", page: 1 });
  });
});

describe("GET /api/duplicates", () => {
  it("finds name-collisions and picks a survivor", async () => {
    const { app } = makeTwinApp();
    const res = await request(app).get("/api/duplicates");
    expect(res.status).toBe(200);
    expect(res.body.names).toBe(2);
    expect(res.body.redundant).toBe(2);
  });

  it("keeps the Commlink6 row over a page-extracted twin", async () => {
    const { app } = makeTwinApp();
    const g = (await request(app).get("/api/duplicates")).body.groups
      .find((x) => x.name === "Power Clip");
    expect(g.keep.source).toBe("commlink6");
    expect(g.drop[0].source).toBe("pdf");
  });

  it("keeps the fuller row when both come from Commlink6", async () => {
    const { app } = makeTwinApp();
    const g = (await request(app).get("/api/duplicates")).body.groups
      .find((x) => x.name === "Folding Stock");
    expect(g.keep.book).toBe("firing_squad");     // it has the description
    expect(g.drop[0].book).toBe("corebook");
  });

  it("changes nothing on its own", async () => {
    const { app, root } = makeTwinApp();
    await request(app).get("/api/duplicates");
    expect(rowsOf(root)).toHaveLength(4);
  });
});
