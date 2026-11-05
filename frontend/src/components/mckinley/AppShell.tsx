"use client";

import { useEffect, useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api, loadDemoSnapshot } from "@/lib/api";
import type { DemoSnapshot, EvalCase, GateConfig, Health, ModelTarget, Persona } from "@/lib/types";

import { ChatWorkbench } from "./ChatWorkbench";
import { EvalDashboard } from "./EvalDashboard";
import { DemoBanner, StaticDemoBanner, StatusBar } from "./StatusBar";

interface Boot {
  health: Health | null;
  personas: Persona[];
  targets: ModelTarget[];
  cases: EvalCase[];
  gateConfig: GateConfig | null;
  demo: DemoSnapshot | null;
}

async function boot(): Promise<Boot> {
  try {
    const [health, personas, targets, cases] = await Promise.all([
      api.health(),
      api.personas(),
      api.models(),
      api.evalCases(),
    ]);
    // Gate config is optional: older backends or errors simply hide the selector.
    const gateConfig = await api.gatesConfig().catch(() => null);
    return { health, personas, targets, cases, gateConfig, demo: null };
  } catch (e) {
    if (!(e instanceof ApiError) || e.code !== "BACKEND_UNREACHABLE") throw e;
    try {
      const demo = await loadDemoSnapshot();
      return { health: null, personas: demo.personas, targets: [], cases: demo.cases, gateConfig: null, demo };
    } catch {
      throw e; // snapshot also failed: show the original backend error
    }
  }
}

export function AppShell() {
  const [state, setState] = useState<Boot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    boot()
      .then((b) => {
        if (!cancelled) {
          setState(b);
          setError(null);
        }
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof ApiError ? e.message : "Failed to load"));
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const demo = state?.demo ?? null;

  return (
    <>
      <DemoBanner />
      <main className="mx-auto w-full max-w-7xl min-w-0 flex-1 space-y-4 px-4 py-4 md:p-6">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">McKinley AI — leasing & resident assistant prototype</h1>
          <p className="text-sm text-muted-foreground">
            Compare a generic baseline, the McKinley prompt alone, and the McKinley prompt with resident context on the
            same message, model and settings.
          </p>
          {demo ? (
            <StaticDemoBanner notice={demo.notice} generatedAt={demo.generated_at} />
          ) : (
            <StatusBar health={state?.health ?? null} error={error} />
          )}
          {error && (
            <button className="text-sm underline" onClick={() => setAttempt((a) => a + 1)}>
              Retry
            </button>
          )}
        </header>
        {state && (
          <Tabs defaultValue="chat">
            <TabsList>
              <TabsTrigger value="chat">Chat comparison</TabsTrigger>
              <TabsTrigger value="evals">Evaluation</TabsTrigger>
            </TabsList>
            <TabsContent value="chat">
              <ChatWorkbench
                personas={state.personas}
                targets={state.targets}
                cases={state.cases}
                gateConfig={state.gateConfig}
                demo={demo}
              />
            </TabsContent>
            <TabsContent value="evals">
              <EvalDashboard targets={state.targets} cases={state.cases} gateConfig={state.gateConfig} demo={demo} />
            </TabsContent>
          </Tabs>
        )}
      </main>
    </>
  );
}
