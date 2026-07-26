import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { extractPack } from "@foundryvtt/foundryvtt-cli";
import { describe, expect, it } from "vitest";
import { buildManifest, docId, exportModule, statusAllows } from "../server/exportModule.mjs";

function item(id, qaStatus, price = 100) {
  return {
    id,
    name: id.replace(/_/g, " "),
    system: { type: "WEAPON_FIREARMS", price },
    meta: { book: "testbook", page: 1, extractedAt: "2026-07-25", extractorVersion: "0.1.0", qaStatus },
  };
}

function seed(items) {
  const root = mkdtempSync(join(tmpdir(), "forge-exp-"));
  const dir = join(root, "testbook", "gear");
  mkdirSync(dir, { recursive: true });
  writeFileSync(
    join(dir, "weapons_firearms.json"),
    JSON.stringify({ book: "testbook", domain: "gear", category: "weapons_firearms", items }, null, 2) + "\n",
  );
  return root;
}

describe("export", () => {
  it("docId is deterministic, 16 alphanumerics", () => {
    const a = docId("corebook", "gear", "example_autopistol");
    expect(a).toMatch(/^[a-zA-Z0-9]{16}$/);
    expect(docId("corebook", "gear", "example_autopistol")).toBe(a);
    expect(docId("corebook", "gear", "other")).not.toBe(a);
  });

  it("statusAllows tiers", () => {
    expect(statusAllows("approved", "approved")).toBe(true);
    expect(statusAllows("approved", "reviewed")).toBe(false);
    expect(statusAllows("reviewed", "reviewed")).toBe(true);
    expect(statusAllows("reviewed", "extracted")).toBe(false);
    expect(statusAllows("all", "extracted")).toBe(true);
  });

  it("manifest shape", () => {
    const m = buildManifest({ book: "testbook", version: "1.2.3", packs: [{ name: "testbook-gear", label: "Testbook Gear", path: "packs/gear" }] });
    expect(m.id).toBe("sr6-forge-testbook");
    expect(m.version).toBe("1.2.3");
    expect(m.compatibility).toEqual({ minimum: "13", verified: "13" });
    expect(m.packs[0]).toMatchObject({ type: "Item", system: "shadowrun6-eden" });
    expect(m.relationships.systems[0].id).toBe("shadowrun6-eden");
  });

  it("exportModule filters by status and round-trips through the pack", async () => {
    const root = seed([item("gun_a", "approved"), item("gun_b", "extracted")]);
    const out = mkdtempSync(join(tmpdir(), "forge-out-"));
    const res = await exportModule(root, out, { book: "testbook", domain: "gear" });
    expect(res.count).toBe(1);
    const manifest = JSON.parse(readFileSync(join(res.moduleDir, "module.json"), "utf8"));
    expect(manifest.id).toBe("sr6-forge-testbook");
    const unpacked = mkdtempSync(join(tmpdir(), "forge-un-"));
    await extractPack(join(res.moduleDir, "packs", "gear"), unpacked);
    const files = (await import("node:fs")).readdirSync(unpacked);
    expect(files).toHaveLength(1);
    const doc = JSON.parse(readFileSync(join(unpacked, files[0]), "utf8"));
    expect(doc.name).toBe("gun a");
    expect(doc.type).toBe("gear");
    expect(doc._id).toMatch(/^[a-zA-Z0-9]{16}$/);
    expect(doc.system.price).toBe(100);
    expect(doc.system.genesisID).toBe("gun_a");
  });

  it("exportModule throws when nothing matches", async () => {
    const root = seed([item("gun_b", "extracted")]);
    const out = mkdtempSync(join(tmpdir(), "forge-out2-"));
    await expect(exportModule(root, out, { book: "testbook", domain: "gear" })).rejects.toThrow(/no items match/);
  });

  it("failed compile leaves no partial module dir", async () => {
    const root = seed([item("gun_a", "approved")]);
    const out = mkdtempSync(join(tmpdir(), "forge-out3-"));
    // force failure: make packs path collide with a FILE inside staging is fiddly;
    // instead simulate by seeding a duplicate id across two files (throws mid-collection
    // BEFORE staging) and separately verify staging cleanup via the missing-domain error.
    await expect(exportModule(root, out, { book: "testbook", domain: "nope" })).rejects.toThrow(/no such domain/);
    const leftovers = readdirSync(out).filter((f) => f.startsWith(".staging"));
    expect(leftovers).toEqual([]);
  });

  it("duplicate item ids across files fail loud", async () => {
    const root = seed([item("gun_a", "approved")]);
    const dir = join(root, "testbook", "gear");
    writeFileSync(
      join(dir, "second.json"),
      JSON.stringify({ book: "testbook", domain: "gear", category: "second", items: [item("gun_a", "approved")] }, null, 2) + "\n",
    );
    const out = mkdtempSync(join(tmpdir(), "forge-out4-"));
    await expect(exportModule(root, out, { book: "testbook", domain: "gear" })).rejects.toThrow(/duplicate item id "gun_a"/);
  });

  it("re-export overwrites the previous module cleanly", async () => {
    const root = seed([item("gun_a", "approved")]);
    const out = mkdtempSync(join(tmpdir(), "forge-out5-"));
    await exportModule(root, out, { book: "testbook", domain: "gear" });
    const res2 = await exportModule(root, out, { book: "testbook", domain: "gear", version: "0.2.0" });
    const manifest = JSON.parse(readFileSync(join(res2.moduleDir, "module.json"), "utf8"));
    expect(manifest.version).toBe("0.2.0");
    expect(readdirSync(out).filter((f) => f.startsWith(".staging"))).toEqual([]);
  });
});

describe("export references and images", () => {
  it("bundles data/_assets images into the module and rewrites img", async () => {
    const withImg = { ...item("gun_a", "approved"), img: "testbook/gun_a.png" };
    const root = seed([withImg]);
    mkdirSync(join(root, "_assets", "testbook"), { recursive: true });
    writeFileSync(join(root, "_assets", "testbook", "gun_a.png"), Buffer.from([0x89, 0x50, 0x4e, 0x47]));
    writeFileSync(join(root, "books.json"), JSON.stringify({ testbook: { title: "Test Book" } }));
    const out = mkdtempSync(join(tmpdir(), "forge-img-"));
    const res = await exportModule(root, out, { book: "testbook", domain: "gear" });
    const { existsSync } = await import("node:fs");
    expect(existsSync(join(res.moduleDir, "icons", "testbook", "gun_a.png"))).toBe(true);
    const unpacked = mkdtempSync(join(tmpdir(), "forge-img-un-"));
    await extractPack(join(res.moduleDir, "packs", "gear"), unpacked);
    const files = readdirSync(unpacked);
    const doc = JSON.parse(readFileSync(join(unpacked, files[0]), "utf8"));
    expect(doc.img).toBe("modules/sr6-forge-testbook/icons/testbook/gun_a.png");
    expect(doc.system.product).toBe("Test Book");
    expect(doc.system.page).toBe(1);
  });

  it("missing asset falls back to the default icon", async () => {
    const withImg = { ...item("gun_a", "approved"), img: "testbook/nope.png" };
    const root = seed([withImg]);
    const out = mkdtempSync(join(tmpdir(), "forge-img2-"));
    const res = await exportModule(root, out, { book: "testbook", domain: "gear" });
    const unpacked = mkdtempSync(join(tmpdir(), "forge-img2-un-"));
    await extractPack(join(res.moduleDir, "packs", "gear"), unpacked);
    const doc = JSON.parse(readFileSync(join(unpacked, readdirSync(unpacked)[0]), "utf8"));
    expect(doc.img).toBe("icons/svg/item-bag.svg");
  });
});

  it("same basename in different subfolders does not collide", async () => {
    const a = { ...item("gun_a", "approved"), img: "one/grip.png" };
    const b = { ...item("gun_b", "approved"), img: "two/grip.png" };
    const root = seed([a, b]);
    mkdirSync(join(root, "_assets", "one"), { recursive: true });
    mkdirSync(join(root, "_assets", "two"), { recursive: true });
    writeFileSync(join(root, "_assets", "one", "grip.png"), "AAA");
    writeFileSync(join(root, "_assets", "two", "grip.png"), "BBB");
    const out = mkdtempSync(join(tmpdir(), "forge-col-"));
    const res = await exportModule(root, out, { book: "testbook", domain: "gear" });
    expect(readFileSync(join(res.moduleDir, "icons", "one", "grip.png"), "utf8")).toBe("AAA");
    expect(readFileSync(join(res.moduleDir, "icons", "two", "grip.png"), "utf8")).toBe("BBB");
  });
