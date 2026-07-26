import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
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
});
