
describe("which library the export reads", () => {
  it("prefers SR6_DATA over the repo's own copy", async () => {
    const { resolveDataRoot } = await import("../server/dataRoot.mjs");
    const prev = process.env.SR6_DATA;
    process.env.SR6_DATA = "C:/somewhere/else/data";
    try {
      expect(resolveDataRoot("C:/repo")).toContain("somewhere");
    } finally {
      if (prev === undefined) delete process.env.SR6_DATA;
      else process.env.SR6_DATA = prev;
    }
  });

  it("falls back to the repo when nothing else is configured", async () => {
    const { resolveDataRoot } = await import("../server/dataRoot.mjs");
    const prev = process.env.SR6_DATA;
    delete process.env.SR6_DATA;
    try {
      expect(resolveDataRoot("C:/repo")).toContain("repo");
    } finally {
      if (prev !== undefined) process.env.SR6_DATA = prev;
    }
  });
});
