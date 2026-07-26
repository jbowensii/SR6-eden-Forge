import { mkdtempSync, readFileSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { SEGMENT, StoreError, readCategory, tree, writeItem } from "../server/store.mjs";

const ITEM = {
  id: "example_autopistol",
  name: "Example Autopistol",
  system: { type: "WEAPON_FIREARMS", price: 620 },
  meta: { book: "corebook", page: 1, extractedAt: "2026-07-25", extractorVersion: "0.1.0", qaStatus: "extracted" },
};

function seed() {
  const root = mkdtempSync(join(tmpdir(), "forge-"));
  const dir = join(root, "corebook", "gear");
  mkdirSync(dir, { recursive: true });
  mkdirSync(join(root, "_raw", "corebook"), { recursive: true });
  writeFileSync(
    join(dir, "weapons_firearms.json"),
    JSON.stringify({ book: "corebook", domain: "gear", category: "weapons_firearms", items: [ITEM] }, null, 2) + "\n",
  );
  return root;
}

describe("store", () => {
  it("tree lists categories with qa counts and skips _dirs", () => {
    const entries = tree(seed());
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ book: "corebook", domain: "gear", category: "weapons_firearms", items: 1 });
    expect(entries[0].qa).toEqual({ extracted: 1, reviewed: 0, approved: 0 });
  });

  it("readCategory returns the envelope", () => {
    const payload = readCategory(seed(), "corebook", "gear", "weapons_firearms");
    expect(payload.items[0].name).toBe("Example Autopistol");
  });

  it("rejects bad segments", () => {
    expect(() => readCategory(seed(), "..", "gear", "x")).toThrow(StoreError);
    expect(SEGMENT.test("weapons_firearms")).toBe(true);
    expect(SEGMENT.test("../evil")).toBe(false);
  });

  it("writeItem replaces and persists with trailing newline", () => {
    const root = seed();
    const updated = { ...ITEM, name: "Example Autopistol MkII", meta: { ...ITEM.meta, qaStatus: "reviewed" } };
    writeItem(root, "corebook", "gear", "weapons_firearms", "example_autopistol", updated);
    const raw = readFileSync(join(root, "corebook", "gear", "weapons_firearms.json"), "utf8");
    expect(raw.endsWith("\n")).toBe(true);
    const payload = JSON.parse(raw);
    expect(payload.items[0].name).toBe("Example Autopistol MkII");
    expect(payload.items[0].meta.qaStatus).toBe("reviewed");
  });

  it("writeItem 404s unknown ids and mismatched ids", () => {
    const root = seed();
    expect(() => writeItem(root, "corebook", "gear", "weapons_firearms", "nope", { ...ITEM, id: "nope2" })).toThrow(StoreError);
    expect(() => writeItem(root, "corebook", "gear", "weapons_firearms", "nope", { ...ITEM, id: "nope" })).toThrow(/not-found/);
  });

  it("writeItem writes atomically, leaving no .tmp file behind", () => {
    const root = seed();
    const updated = { ...ITEM, name: "Example Autopistol MkII", meta: { ...ITEM.meta, qaStatus: "reviewed" } };
    writeItem(root, "corebook", "gear", "weapons_firearms", "example_autopistol", updated);
    const dir = join(root, "corebook", "gear");
    const files = readdirSync(dir);
    expect(files).not.toContain("weapons_firearms.json.tmp");
    expect(files.some((f) => f.endsWith(".tmp"))).toBe(false);
    const payload = JSON.parse(readFileSync(join(dir, "weapons_firearms.json"), "utf8"));
    expect(payload.items[0].name).toBe("Example Autopistol MkII");
    expect(payload.items[0].meta.qaStatus).toBe("reviewed");
  });

  it("tree marks unreadable files as errors but still lists good categories", () => {
    const root = seed();
    writeFileSync(join(root, "corebook", "gear", "broken.json"), "{bad");
    const entries = tree(root);
    expect(entries).toHaveLength(2);
    const broken = entries.find((e) => e.category === "broken");
    expect(broken).toMatchObject({
      book: "corebook",
      domain: "gear",
      category: "broken",
      items: 0,
      qa: { extracted: 0, reviewed: 0, approved: 0 },
      error: "unreadable",
    });
    const good = entries.find((e) => e.category === "weapons_firearms");
    expect(good).toMatchObject({ book: "corebook", domain: "gear", category: "weapons_firearms", items: 1 });
  });
});
