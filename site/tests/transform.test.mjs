import { describe, expect, it } from "vitest";
import { toFoundryDoc } from "../shared/edenTransform.mjs";

const ITEM = {
  id: "example_autopistol",
  name: "Example Autopistol",
  system: { type: "WEAPON_FIREARMS", price: 620, dmgDef: "2P" },
  meta: { book: "corebook", page: 1, extractedAt: "2026-07-25", extractorVersion: "0.1.0", qaStatus: "approved" },
};

describe("toFoundryDoc", () => {
  it("wraps system, strips meta, defaults description and genesisID", () => {
    const doc = toFoundryDoc(ITEM);
    expect(doc).toMatchObject({ name: "Example Autopistol", type: "gear", img: "icons/svg/item-bag.svg" });
    expect(doc.system.price).toBe(620);
    expect(doc.system.description).toBe("");
    expect(doc.system.genesisID).toBe("example_autopistol");
    expect(doc.meta).toBeUndefined();
    expect(doc.effects).toEqual([]);
  });

  it("does not mutate the input", () => {
    const before = JSON.stringify(ITEM);
    toFoundryDoc(ITEM);
    expect(JSON.stringify(ITEM)).toBe(before);
  });

  it("throws without a system type", () => {
    expect(() => toFoundryDoc({ id: "x", name: "X", system: {} })).toThrow(TypeError);
  });
});

describe("toFoundryDoc references and images", () => {
  it("maps book/page into system.product/system.page", () => {
    const doc = toFoundryDoc(ITEM, { product: "Sixth World Core Rulebook" });
    expect(doc.system.product).toBe("Sixth World Core Rulebook");
    expect(doc.system.page).toBe(1);
  });

  it("falls back to the book slug without a product title", () => {
    const doc = toFoundryDoc(ITEM);
    expect(doc.system.product).toBe("corebook");
  });

  it("uses item.img when present", () => {
    const doc = toFoundryDoc({ ...ITEM, img: "corebook/pistol.webp" });
    expect(doc.img).toBe("corebook/pistol.webp");
    expect(toFoundryDoc(ITEM).img).toBe("icons/svg/item-bag.svg");
  });
});
