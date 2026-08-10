import { describe, it, expect } from "vitest";
import { EDEN } from "../shared/edenSpec.mjs";
import { toFoundryDoc } from "../shared/edenTransform.mjs";

// Eden's Actor subtypes, copied from its template.json. A document whose type
// is not one of these is one Foundry cannot place — and nothing in the export
// pipeline notices, so it is pinned here.
const EDEN_ACTOR_TYPES = new Set(["Player", "NPC", "Critter", "Spirit", "Vehicle"]);
const EDEN_ITEM_TYPES = new Set([
  "complexform", "contact", "critterpower", "spritepower", "echo", "gear", "lifestyle",
  "martialartstyle", "martialarttech", "metamagic", "quality", "sin", "skill",
  "adeptpower", "spell", "ritual", "focus",
]);

describe("every domain maps onto a type Eden actually defines", () => {
  for (const [domain, spec] of Object.entries(EDEN)) {
    it(`${domain} -> ${spec.type}`, () => {
      const allowed = spec.actor ? EDEN_ACTOR_TYPES : EDEN_ITEM_TYPES;
      expect(allowed.has(spec.type)).toBe(true);
    });
  }
});

describe("vehicles export as Eden Vehicle actors", () => {
  const vehicle = (system = {}) => ({
    id: "v1", name: "Test Rig", meta: { book: "corebook", page: 296 },
    system: { subtype: "CARS", handlOn: "4", accOn: "2", bod: "12", arm: "6", ...system },
  });

  it("is an actor, not an item", () => {
    const doc = toFoundryDoc(vehicle(), { domain: "vehicles" });
    expect(doc.type).toBe("Vehicle");
    expect(doc.items).toEqual([]);      // actors carry embedded items
    expect(doc.effects).toBeUndefined();
  });

  it("coerces the stat strings Eden expects as numbers", () => {
    const { system } = toFoundryDoc(vehicle(), { domain: "vehicles" });
    expect(system.handlOn).toBe(4);
    expect(system.bod).toBe(12);
    expect(system.arm).toBe(6);
  });

  it("maps our extracted stat names onto Eden's", () => {
    // the books' names are not Eden's; without this the stat block is empty
    // while the numbers sit in the library one key away
    const { system } = toFoundryDoc({
      id: "v2", name: "Sedan", meta: {},
      system: { subtype: "CARS", handling: "5", accel: "3", speedInterval: "10",
                topSpeed: "80", body: "11", armor: "4", pilot: "1", sensor: "2", seats: "4" },
    }, { domain: "vehicles" });
    expect(system.handlOn).toBe(5);
    expect(system.tspd).toBe(80);
    expect(system.bod).toBe(11);
    expect(system.arm).toBe(4);
    expect(system.pil).toBe(1);
    expect(system.sen).toBe(2);
    expect(system.sea).toBe(4);
  });

  it("splits an on-road/off-road pair into Eden's two fields", () => {
    const { system } = toFoundryDoc({
      id: "v3", name: "Dirt Bike", meta: {},
      system: { subtype: "BIKES", handling: "5/7", accel: "4" },
    }, { domain: "vehicles" });
    expect(system.handlOn).toBe(5);
    expect(system.handlOff).toBe(7);
    // a single figure applies to both, rather than leaving off-road empty
    expect(system.accOn).toBe(4);
    expect(system.accOff).toBe(4);
  });

  it("survives a stat the books print as a dash", () => {
    const { system } = toFoundryDoc({
      id: "v4", name: "Drone", meta: { }, system: { subtype: "AIR", seats: "—", body: "2" },
    }, { domain: "vehicles" });
    expect(system.sea).toBe(0);
    expect(system.bod).toBe(2);
  });

  it("picks a vtype from the subtype so the right sheet renders", () => {
    const vt = (subtype) => toFoundryDoc(vehicle({ subtype }), { domain: "vehicles" }).system.vtype;
    expect(vt("BOATS")).toBe("watercraft");
    expect(vt("SUBMARINES")).toBe("watercraft");
    expect(vt("ROTORCRAFT")).toBe("aircraft");
    expect(vt("FIXED_WING")).toBe("aircraft");
    expect(vt("CARS")).toBe("ground_craft");
    expect(vt("BIKES")).toBe("ground_craft");     // the default, and the commonest
  });

  it("does not overwrite a vtype that is already set", () => {
    const { system } = toFoundryDoc(vehicle({ vtype: "aircraft", subtype: "CARS" }),
                                    { domain: "vehicles" });
    expect(system.vtype).toBe("aircraft");
  });

  it("seeds the vehicle sub-object Eden's sheet reads", () => {
    const { system } = toFoundryDoc(vehicle(), { domain: "vehicles" });
    expect(system.vehicle).toEqual({ belongs: "", opMode: "manual", offRoad: false, speed: 0 });
  });

  it("does not try to nest attributes the way a critter does", () => {
    // a vehicle has flat stats; running the critter path over it would invent
    // an attributes object Eden's vehicle sheet never reads
    const { system } = toFoundryDoc(vehicle(), { domain: "vehicles" });
    expect(system.attributes).toBeUndefined();
  });
});
