import { describe, expect, it } from "vitest";

import { GUEST, UI, greeting } from "./customer";

describe("Sprint 10 review remediation", () => {
  it("keeps the greeting to one short line with the AI disclosure", () => {
    const g = greeting(GUEST);
    expect(g.split(/\s+/).length).toBeLessThanOrEqual(25);
    expect(g).toMatch(/automated assistant, not a person/);
  });

  it("labels the build in both languages", () => {
    expect(UI.en.buildLabel).toBe("Version");
    expect(UI.es.buildLabel).toBe("Versión");
  });
});
