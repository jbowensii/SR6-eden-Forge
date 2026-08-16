import { describe, it, expect } from "vitest";

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

describe("a failed export reports failure", () => {
  it("exits non-zero when the book does not exist", async () => {
    const { execFileSync } = await import("node:child_process");
    const { fileURLToPath } = await import("node:url");
    const { dirname, join } = await import("node:path");
    const here = dirname(fileURLToPath(import.meta.url));
    let code = 0;
    try {
      execFileSync(process.execPath,
        [join(here, "..", "scripts", "export.mjs"), "--all",
         "--book", "no_such_book", "--status", "all"],
        { stdio: "ignore" });
    } catch (err) {
      code = err.status;
    }
    // The CLI is correct today; this pins it. Note for anyone WRAPPING it:
    // piping the output hands the exit status to the last command in the pipe,
    // which is how a failed export once read as a clean success — an error of
    // invocation, not of this script.
    expect(code).toBe(1);
  });
});
