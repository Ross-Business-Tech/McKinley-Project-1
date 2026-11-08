import { describe, expect, it } from "vitest";

import { sortStatusItems } from "@/components/customer/CustomerApp";
import type { PrototypeRecord, StatusItem } from "@/lib/types";

import { ageLabel, sortQueue } from "./StaffConsole";

const rec = (id: string, status: PrototypeRecord["status"], priority: string | null, created: string) =>
  ({ id, status, priority, created_at: created }) as unknown as PrototypeRecord;

describe("staff and status helpers", () => {
  it("ageLabel gives short relative ages and tolerates bad input", () => {
    const now = Date.parse("2026-11-08T12:00:00Z");
    expect(ageLabel("2026-11-08T11:59:50Z", now)).toBe("just now");
    expect(ageLabel("2026-11-08T11:30:00Z", now)).toBe("30 min ago");
    expect(ageLabel("2026-11-08T09:00:00Z", now)).toBe("3 h ago");
    expect(ageLabel("2026-11-05T12:00:00Z", now)).toBe("3 d ago");
    expect(ageLabel("not a date", now)).toBe("");
  });

  it("sortQueue puts urgent first, then high, then newest", () => {
    const rows = [
      rec("a", "submitted_for_review", "normal", "2026-11-08T10:00:00Z"),
      rec("b", "urgent_queued", null, "2026-11-01T10:00:00Z"),
      rec("c", "submitted_for_review", "high", "2026-11-02T10:00:00Z"),
      rec("d", "submitted_for_review", "normal", "2026-11-08T11:00:00Z"),
    ];
    expect(sortQueue(rows).map((r) => r.id)).toEqual(["b", "c", "d", "a"]);
  });

  it("sortStatusItems keeps urgent and follow-up-owed items above the rest", () => {
    const item = (reference: string, status: string, opened: string) =>
      ({ reference, title: reference, status, opened, source: "prototype_store", note: null }) as StatusItem;
    const sorted = sortStatusItems([
      item("new", "Submitted, waiting for staff review", "2026-11-08"),
      item("urgent", "Urgent: saved for staff", "2026-11-01"),
      item("owed", "Open, follow-up owed", "2026-10-01"),
    ]);
    expect(sorted[sorted.length - 1].reference).toBe("new");
  });
});
