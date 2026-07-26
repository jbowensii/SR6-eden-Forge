import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
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
});
