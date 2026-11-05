"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { ALL_MODES, MODE_META, newSessionId } from "@/lib/format";
import type { ChatResponse, DemoSnapshot, EvalCase, GateConfig, GateProvider, Mode, ModelTarget, Persona, SafeContext } from "@/lib/types";

import { ContextPreview } from "./ContextPreview";
import { ResponseView } from "./ResponseDetails";

interface ModeResult {
  response?: ChatResponse;
  error?: ApiError;
  pending?: boolean;
}

interface Turn {
  user: string;
  results: Partial<Record<Mode, ModeResult>>;
}

const GATE_PROVIDERS: { id: GateProvider; label: string }[] = [
  { id: "rules", label: "Rules (deterministic)" },
  { id: "llm", label: "LLM classifier" },
  { id: "jev", label: "Jev (experimental)" },
];

const DEFAULT_MODES: Mode[] = ["baseline", "aware"];

const selectClass =
  "h-9 w-full min-w-0 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";

function isAvailable(status: string | undefined): boolean {
  return !!status && !status.startsWith("unavailable");
}

export function ChatWorkbench({
  personas,
  targets,
  cases,
  gateConfig = null,
  demo = null,
}: {
  personas: Persona[];
  targets: ModelTarget[];
  cases: EvalCase[];
  gateConfig?: GateConfig | null;
  demo?: DemoSnapshot | null;
}) {
  const defaultTarget = targets.find((t) => t.is_default)?.key ?? targets[0]?.key ?? "";
  const [personaId, setPersonaId] = useState<string>(cases[0]?.persona_id ?? "P-RELOCATE-AA");
  const [target, setTarget] = useState<string>(defaultTarget);
  const [modes, setModes] = useState<Mode[]>(DEFAULT_MODES);
  const [gate, setGate] = useState<GateProvider | "">(
    (gateConfig?.configured_provider as GateProvider | undefined) ?? "",
  );
  const [message, setMessage] = useState("");
  const [sessionId, setSessionId] = useState<string>(() => newSessionId());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeCase, setActiveCase] = useState<string | null>(null);
  const [ctx, setCtx] = useState<SafeContext | null>(null);
  const [ctxLoading, setCtxLoading] = useState(false);
  const [ctxError, setCtxError] = useState<string | null>(null);

  const resetSession = useCallback(() => {
    setSessionId(newSessionId());
    setTurns([]);
  }, []);

  // Live mode: context preview follows persona + draft message (debounced). Demo mode uses snapshot contexts.
  useEffect(() => {
    if (demo) return;
    const handle = setTimeout(() => {
      setCtxLoading(true);
      api
        .contextPreview(personaId || null, message)
        .then((c) => {
          setCtx(c);
          setCtxError(null);
        })
        .catch((e: unknown) => setCtxError(e instanceof ApiError ? e.message : "Context preview failed"))
        .finally(() => setCtxLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [personaId, message, demo]);

  const selectedTarget = useMemo(() => targets.find((t) => t.key === target), [targets, target]);
  const busy = turns.some((t) => Object.values(t.results).some((r) => r?.pending));
  const orderedModes = ALL_MODES.filter((m) => modes.includes(m));
  const coreCases = cases.filter((c) => (c.suite ?? "core") === "core");
  const extendedCases = cases.filter((c) => c.suite === "extended");

  function toggleMode(m: Mode, on: boolean) {
    setModes((prev) => (on ? [...prev, m] : prev.length > 1 ? prev.filter((x) => x !== m) : prev));
  }

  async function send() {
    const text = message.trim();
    if (demo || !text || busy || !target) return;
    const sendModes = orderedModes;
    const idx = turns.length;
    setTurns((prev) => [
      ...prev,
      { user: text, results: Object.fromEntries(sendModes.map((m) => [m, { pending: true }])) },
    ]);
    await Promise.all(
      sendModes.map(async (mode) => {
        let update: ModeResult;
        try {
          const response = await api.chat({
            message: text,
            persona_id: personaId || null,
            mode,
            session_id: sessionId,
            target,
            ...(gate ? { gate_provider: gate } : {}),
          });
          update = { response };
        } catch (e) {
          update = { error: e instanceof ApiError ? e : new ApiError("UNKNOWN", "Unexpected error") };
        }
        setTurns((prev) => prev.map((t, i) => (i === idx ? { ...t, results: { ...t.results, [mode]: update } } : t)));
      }),
    );
  }

  function loadCase(c: EvalCase) {
    setActiveCase(c.id);
    if (demo) {
      // Pre-computed responses for every mode; the toggles only choose which columns are shown.
      const stored = demo.responses[c.id] ?? {};
      setPersonaId(c.persona_id);
      setMessage(c.message);
      setCtx(demo.contexts[c.id] ?? null);
      setTurns([
        {
          user: c.message,
          results: Object.fromEntries(
            ALL_MODES.map((m) => [
              m,
              stored[m]
                ? { response: stored[m] }
                : { error: new ApiError("NOT_IN_SNAPSHOT", "This mode was not pre-computed for this scenario.") },
            ]),
          ),
        },
      ]);
      return;
    }
    if (c.persona_id !== personaId) resetSession();
    setPersonaId(c.persona_id);
    setMessage(c.message);
  }

  const scenarioGroup = (title: string, list: EvalCase[], offset: number) =>
    list.length > 0 && (
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium">{title}</legend>
        <div className="flex flex-col gap-1">
          {list.map((c, i) => (
            <Button
              key={c.id}
              variant={activeCase === c.id ? "secondary" : "outline"}
              size="sm"
              aria-pressed={activeCase === c.id}
              className="h-auto min-h-7 justify-start whitespace-normal py-1 text-left"
              onClick={() => loadCase(c)}
            >
              {offset + i + 1}. {c.title}
            </Button>
          ))}
        </div>
      </fieldset>
    );

  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
      <div className="min-w-0 space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Scenario</CardTitle>
            <CardDescription>
              {demo ? "Pick a pre-computed scenario." : "Pick a synthetic persona, model, decision gate and message."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="persona">Persona</Label>
              <select
                id="persona"
                className={selectClass}
                value={personaId}
                disabled={!!demo}
                onChange={(e) => {
                  setPersonaId(e.target.value);
                  setActiveCase(null);
                  resetSession();
                }}
              >
                <option value="">No persona (unknown visitor)</option>
                {personas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            {demo ? (
              <p className="text-xs text-muted-foreground">
                Model: <strong>MOCK</strong> (deterministic template) · Decision gate: <strong>rules</strong> (pre-computed)
              </p>
            ) : (
              <>
                <div className="space-y-1">
                  <Label htmlFor="target">Model target</Label>
                  <select
                    id="target"
                    className={selectClass}
                    value={target}
                    onChange={(e) => {
                      setTarget(e.target.value);
                      resetSession();
                    }}
                  >
                    {targets.map((t) => (
                      <option key={t.key} value={t.key}>
                        {t.key}
                        {t.is_mock ? " (MOCK)" : ""}
                        {!t.ready ? ` — ${t.status}` : ""}
                      </option>
                    ))}
                  </select>
                  {selectedTarget && !selectedTarget.ready && (
                    <p className="text-xs text-destructive">This target is not ready: {selectedTarget.status}</p>
                  )}
                </div>
                {gateConfig && (
                  <div className="space-y-1">
                    <Label htmlFor="gate">Decision gate</Label>
                    <select id="gate" className={selectClass} value={gate} onChange={(e) => setGate(e.target.value as GateProvider)}>
                      {GATE_PROVIDERS.map((g) => (
                        <option key={g.id} value={g.id}>
                          {g.label}
                          {g.id === gateConfig.configured_provider ? " — server default" : ""}
                          {!isAvailable(gateConfig.availability[g.id]) ? " (unavailable, falls back to rules)" : ""}
                        </option>
                      ))}
                    </select>
                    {gate && gateConfig.availability[gate] && (
                      <p className="break-words text-xs text-muted-foreground">{gateConfig.availability[gate]}</p>
                    )}
                    <p className="text-xs text-muted-foreground">Applies to modes B and C. The rules gate always runs as a safety floor.</p>
                  </div>
                )}
              </>
            )}
            {scenarioGroup("Core five", coreCases, 0)}
            {scenarioGroup("Extended scenarios", extendedCases, coreCases.length)}
          </CardContent>
        </Card>
        <ContextPreview ctx={ctx} loading={ctxLoading} error={ctxError} emptyHint={demo ? "Pick a scenario to see its context." : undefined} />
      </div>

      <div className="min-w-0 space-y-4">
        <Card>
          <CardContent className="space-y-3 pt-4">
            <fieldset>
              <legend className="mb-1 text-sm font-medium">Compare modes</legend>
              <div className="grid gap-2 sm:grid-cols-3">
                {ALL_MODES.map((m) => {
                  const meta = MODE_META[m];
                  const checked = modes.includes(m);
                  return (
                    <label
                      key={m}
                      className={`flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm ${checked ? "border-primary bg-primary/5" : ""}`}
                    >
                      <input
                        type="checkbox"
                        className="mt-0.5 size-4 shrink-0"
                        checked={checked}
                        disabled={busy || (checked && modes.length === 1)}
                        onChange={(e) => toggleMode(m, e.target.checked)}
                      />
                      <span className="min-w-0">
                        <span className="font-medium">
                          {meta.letter} · {meta.title}
                        </span>
                        <span className="block text-xs text-muted-foreground">{meta.description}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
              {!demo && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Each selected mode is a separate model call ({orderedModes.length} per message). Free-tier rate limits apply.
                </p>
              )}
            </fieldset>

            <div className="space-y-1">
              <Label htmlFor="message">Message (sent identically to every selected mode)</Label>
              <Textarea
                id="message"
                value={message}
                maxLength={4000}
                rows={3}
                disabled={!!demo}
                aria-describedby={demo ? "demo-chat-note" : undefined}
                placeholder="e.g. My AC stopped cooling again…"
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void send();
                }}
              />
              {demo && (
                <p id="demo-chat-note" className="text-xs text-muted-foreground">
                  Typing your own message needs the live backend. In this static demo, pick a scenario to see its
                  pre-computed responses.
                </p>
              )}
            </div>
            {!demo && (
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => void send()} disabled={busy || !message.trim() || !target}>
                  {busy ? "Waiting for model…" : "Compare responses"}
                </Button>
                <Button variant="ghost" onClick={resetSession} disabled={busy}>
                  New session
                </Button>
                <span className="text-xs text-muted-foreground">Session {sessionId.slice(0, 8)} · Ctrl/⌘+Enter to send</span>
              </div>
            )}
          </CardContent>
        </Card>

        <div className={`grid gap-4 ${orderedModes.length > 1 ? "md:grid-cols-2" : ""} ${orderedModes.length > 2 ? "2xl:grid-cols-3" : ""}`}>
          {orderedModes.map((mode) => {
            const meta = MODE_META[mode];
            return (
              <Card key={mode} aria-label={`${meta.title} responses`} className="min-w-0">
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2">
                    <span>
                      {meta.letter} · {meta.title}
                    </span>
                    {(demo || selectedTarget?.is_mock) && <Badge variant="secondary">MOCK</Badge>}
                  </CardTitle>
                  <CardDescription>{meta.description}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4" aria-live="polite">
                  {turns.length === 0 && (
                    <p className="text-sm text-muted-foreground">{demo ? "Pick a scenario." : "No messages yet."}</p>
                  )}
                  {turns.map((t, i) => {
                    const res = t.results[mode];
                    return (
                      <div key={i} className="space-y-2 border-b pb-3 last:border-b-0">
                        <p className="rounded-md bg-muted p-2 text-sm break-words">
                          <span className="sr-only">Customer: </span>
                          {t.user}
                        </p>
                        {!res && <p className="text-xs text-muted-foreground">Not requested in this mode.</p>}
                        {res?.pending && <p className="text-sm text-muted-foreground">Generating…</p>}
                        {res?.error && (
                          <div role="alert" className="rounded-md border border-destructive/50 p-2 text-sm text-destructive">
                            <p className="font-semibold">{res.error.code}</p>
                            <p>{res.error.message}</p>
                          </div>
                        )}
                        {res?.response && <ResponseView r={res.response} />}
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}
