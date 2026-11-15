import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DemoSnapshot, Persona, PrototypeRecord } from "@/lib/types";
import { StaffConsole } from "@/components/staff/StaffConsole";
import { setStaffToken } from "@/lib/api";

afterEach(() => {
  cleanup();
  setStaffToken(null);
  vi.unstubAllGlobals();
});

const personas: Persona[] = [
  { id: "R001", label: "R001 · Marisol (synthetic resident)", kind: "resident", description: "", synthetic: true },
];

const record: PrototypeRecord = {
  id: "DEMO-MAINT-1001", kind: "maintenance_request", status: "queued", status_label: "Saved in demo",
  persona_id: "R001", session_hash: "abc123", created_at: "2026-11-05T07:57:22Z",
  summary: "Resident · maintenance · urgency high.", team: "maintenance", priority: "high", system: "prototype",
  fields: [{ key: "issue", label: "What's wrong", value: "The AC stopped cooling", source: "you_said" }],
};

const snapshot: DemoSnapshot = {
  kind: "static_demo_snapshot",
  generated_at: "2026-11-05T07:57:22Z",
  notice: "Static demonstration: pre-computed with the deterministic MOCK provider.",
  workbook_loaded: true,
  personas,
  journeys: [],
  prototype_records: [record],
};

describe("Staff console", () => {
  it("shows only the staff queue: saved requests and live conversations", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/demo/snapshot.json") return new Response(JSON.stringify(snapshot));
      throw new TypeError("fetch failed");
    }));
    render(<StaffConsole />);
    await waitFor(() => expect(screen.getByText(/Recorded demo: no backend runs behind this link/)).toBeInTheDocument());
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Saved requests", "Live conversations"]);
    expect(screen.queryByRole("button", { name: "Demo and evaluation" })).not.toBeInTheDocument();
    expect((await screen.findAllByText(/The AC stopped cooling/)).length).toBeGreaterThan(0);
  });

  it("on a hosted backend says staff tools are locked and never calls staff routes", async () => {
    const health = { status: "ok", provider: "gemini", model: "gemini-3.6-flash", provider_ready: true,
      provider_status: "API key configured", prompt_version: "v", data_loaded: true, data_error: null,
      resident_count: 20, interaction_count: 101, app_env: "hosted", database: "postgres",
      resident_source: "database (synthetic)", is_mock: false };
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/demo/snapshot.json") return new Response(JSON.stringify(snapshot));
      if (url.endsWith("/api/health")) return new Response(JSON.stringify(health));
      return new Response(JSON.stringify({ error: { code: "STAFF_ONLY", message: "locked", retryable: false } }),
        { status: 403 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<StaffConsole />);
    expect(await screen.findByTestId("staff-locked")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/api/prototype/records"))).toBe(false);
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/api/staff/conversations"))).toBe(false);
  });

  it("on a hosted backend a wrong staff token shows an error; the right one loads this backend's data", async () => {
    const health = { status: "ok", provider: "openrouter", model: "m", provider_ready: true, provider_status: "ok",
      prompt_version: "v", data_loaded: true, data_error: null, resident_count: 20, interaction_count: 101,
      app_env: "hosted", database: "postgres", resident_source: "database (synthetic)", is_mock: false };
    const live: PrototypeRecord = { ...record, id: "DEMO-WO-2001", fields: [{ key: "issue", label: "What's wrong",
      value: "Hosted backend record", source: "you_said" }] };
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/demo/snapshot.json") return new Response(JSON.stringify(snapshot));
      if (url.endsWith("/api/health")) return new Response(JSON.stringify(health));
      const token = new Headers(init?.headers).get("X-Staff-Token");
      if (token !== "right-token-0123456789abcdef")
        return new Response(JSON.stringify({ detail: { code: "STAFF_ONLY", message: "locked", retryable: false } }),
          { status: 403 });
      if (url.includes("/api/prototype/records")) return new Response(JSON.stringify([live]));
      if (url.includes("/api/staff/conversations")) return new Response(JSON.stringify([]));
      return new Response("{}", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    render(<StaffConsole />);
    const input = await screen.findByLabelText("Staff token");
    expect(input).toHaveAttribute("type", "password");

    fireEvent.change(input, { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Unlock staff tools" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That staff token isn't valid");
    expect(screen.getByTestId("staff-locked")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "right-token-0123456789abcdef" } });
    fireEvent.click(screen.getByRole("button", { name: "Unlock staff tools" }));
    expect((await screen.findAllByText("Hosted backend record")).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("staff-locked")).not.toBeInTheDocument();
    const liveTab = screen.getByRole("tab", { name: "Live conversations" });
    fireEvent.pointerDown(liveTab);
    fireEvent.mouseDown(liveTab);
    fireEvent.click(liveTab);
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => String(u).includes("/api/staff/conversations")
      && new Headers((i as RequestInit | undefined)?.headers).get("X-Staff-Token") === "right-token-0123456789abcdef")).toBe(true));
    // the token never goes into a URL, storage or a non-staff request
    expect(fetchMock.mock.calls.every(([u]) => !String(u).includes("right-token"))).toBe(true);
    expect(setItem.mock.calls.some((args) => args.join(" ").includes("right-token"))).toBe(false);
    expect(fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/api/health"))
      .every(([, i]) => !new Headers((i as RequestInit | undefined)?.headers).get("X-Staff-Token"))).toBe(true);
    setItem.mockRestore();
  });

  it("shows the backend error when the snapshot also fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/demo/snapshot.json") return new Response("not found", { status: 404 });
      throw new TypeError("fetch failed");
    }));
    render(<StaffConsole />);
    await waitFor(() => expect(screen.getByText(/Backend unavailable: Cannot reach the backend/)).toBeInTheDocument());
    expect(screen.queryByText(/Recorded demo/)).not.toBeInTheDocument();
  });
});
