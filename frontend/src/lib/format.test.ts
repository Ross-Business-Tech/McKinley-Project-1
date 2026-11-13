import { describe, expect, it } from "vitest";

import { newSessionId } from "./format";

describe("session ids", () => {
  it("creates backend-compatible session ids", () => {
    const id = newSessionId();
    expect(id).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
    expect(newSessionId()).not.toBe(id);
  });
});
