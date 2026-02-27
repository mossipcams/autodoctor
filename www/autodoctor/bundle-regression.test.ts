import { readFileSync } from "fs";
import path from "path";

describe("autodoctor-card bundle regression guards", () => {
  it("does not emit self-referential decorator helper aliases", () => {
    const bundlePath = path.resolve(__dirname, "autodoctor-card.js");
    const bundle = readFileSync(bundlePath, "utf-8");

    // Guard against transpiled helper output that regressed in prerelease bundles.
    expect(bundle).not.toContain("const t=t=>");
  });
});
