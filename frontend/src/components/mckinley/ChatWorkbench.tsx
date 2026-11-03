"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { newSessionId } from "@/lib/format";
import type { ChatResponse, EvalCase, Mode, ModelTarget, Persona, SafeContext } from "@/lib/types";

import { ContextPreview } from "./ContextPreview";
import { ResponseDetails } from "./ResponseDetails";

interface Turn {
  user: string;
  response?: ChatResponse;
  error?: ApiError;
  pending?: boolean;
}

const MODES: { mode: Mode; title: string; description: string }[] = [
  { mode: "baseline", title: "Generic baseline", description: "Generic assistant prompt, no McKinley rules or context." },
  { mode: "aware", title: "McKinley-aware", description: "McKinley system prompt + minimized safe context + policy gates." },
];

const selectClass =
  "h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function ChatWorkbench({ personas, targets, cases }: { personas: Persona[]; targets: ModelTarget[]; cases: EvalCase[] }) {
  const defaultTarget = targets.find((t) => t.is_default)?.key ?? targets[0]?.key ?? "";
  const [personaId, setPersonaId] = useState<string>("P-RELOCATE-AA");
  const [target, setTarget] = useState<string>(defaultTarget);
  const [message, setMessage] = useState("");
  const [sessionId, setSessionId] = useState<string>(() => newSessionId());
  const [turns, setTurns] = useState<Record<Mode, Turn[]>>({ baseline: [], aware: [] });
  const [ctx, setCtx] = useState<SafeContext | null>(null);
  const [ctxLoading, setCtxLoading] = useState(false);
  const [ctxError, setCtxError] = useState<string | null>(null);

  const resetSession = useCallback(() => {
    setSessionId(newSessionId());
    setTurns({ baseline: [], aware: [] });
  }, []);

  // Context preview follows persona + draft message (debounced).
  useEffect(() => {
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
  }, [personaId, message]);

  const selectedTarget = useMemo(() => targets.find((t) => t.key === target), [targets, target]);
  const busy = turns.baseline.some((t) => t.pending) || turns.aware.some((t) => t.pending);

  async function send() {
    const text = message.trim();
    if (!text || busy || !target) return;
    setTurns((prev) => ({
      baseline: [...prev.baseline, { user: text, pending: true }],
      aware: [...prev.aware, { user: text, pending: true }],
    }));
    await Promise.all(
      MODES.map(async ({ mode }) => {
        let update: Partial<Turn>;
        try {
          const response = await api.chat({ message: text, persona_id: personaId || null, mode, session_id: sessionId, target });
          update = { response };
        } catch (e) {
          update = { error: e instanceof ApiError ? e : new ApiError("UNKNOWN", "Unexpected error") };
        }
        setTurns((prev) => {
          const list = [...prev[mode]];
          list[list.length - 1] = { ...list[list.length - 1], ...update, pending: false };
          return { ...prev, [mode]: list };
        });
      }),
    );
  }

  function loadCase(c: EvalCase) {
    if (c.persona_id !== personaId) resetSession();
    setPersonaId(c.persona_id);
    setMessage(c.message);
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Scenario</CardTitle>
            <CardDescription>Pick a synthetic persona, model target and message.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="persona">Persona</Label>
              <select
                id="persona"
                className={selectClass}
                value={personaId}
                onChange={(e) => {
                  setPersonaId(e.target.value);
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
            <fieldset className="space-y-1">
              <legend className="text-sm font-medium">Five evaluation scenarios</legend>
              <div className="flex flex-col gap-1">
                {cases.map((c, i) => (
                  <Button key={c.id} variant="outline" size="sm" className="justify-start" onClick={() => loadCase(c)}>
                    {i + 1}. {c.title}
                  </Button>
                ))}
              </div>
            </fieldset>
          </CardContent>
        </Card>
        <ContextPreview ctx={ctx} loading={ctxLoading} error={ctxError} />
      </div>

      <div className="space-y-4">
        <Card>
          <CardContent className="space-y-2 pt-4">
            <Label htmlFor="message">Message (sent identically to both modes)</Label>
            <Textarea
              id="message"
              value={message}
              maxLength={4000}
              rows={3}
              placeholder="e.g. My AC stopped cooling again…"
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void send();
              }}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => void send()} disabled={busy || !message.trim() || !target}>
                {busy ? "Waiting for model…" : "Compare responses"}
              </Button>
              <Button variant="ghost" onClick={resetSession} disabled={busy}>
                New session
              </Button>
              <span className="text-xs text-muted-foreground">Session {sessionId.slice(0, 8)} · Ctrl/⌘+Enter to send</span>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4 md:grid-cols-2">
          {MODES.map(({ mode, title, description }) => (
            <Card key={mode} aria-label={`${title} responses`}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  {title}
                  {selectedTarget?.is_mock && <Badge variant="secondary">MOCK</Badge>}
                </CardTitle>
                <CardDescription>{description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4" aria-live="polite">
                {turns[mode].length === 0 && <p className="text-sm text-muted-foreground">No messages yet.</p>}
                {turns[mode].map((t, i) => (
                  <div key={i} className="space-y-2 border-b pb-3 last:border-b-0">
                    <p className="rounded-md bg-muted p-2 text-sm">
                      <span className="sr-only">User: </span>
                      {t.user}
                    </p>
                    {t.pending && <p className="text-sm text-muted-foreground">Generating…</p>}
                    {t.error && (
                      <div role="alert" className="rounded-md border border-destructive/50 p-2 text-sm text-destructive">
                        <p className="font-semibold">{t.error.code}</p>
                        <p>{t.error.message}</p>
                      </div>
                    )}
                    {t.response && (
                      <>
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">
                          <span className="sr-only">Assistant: </span>
                          {t.response.reply}
                        </p>
                        <ResponseDetails r={t.response} />
                      </>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
