"use client";

import { useEffect, useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api } from "@/lib/api";
import type { EvalCase, Health, ModelTarget, Persona } from "@/lib/types";

import { ChatWorkbench } from "./ChatWorkbench";
import { EvalDashboard } from "./EvalDashboard";
import { DemoBanner, StatusBar } from "./StatusBar";

interface Boot {
  health: Health;
  personas: Persona[];
  targets: ModelTarget[];
  cases: EvalCase[];
}

export function AppShell() {
  const [boot, setBoot] = useState<Boot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.health(), api.personas(), api.models(), api.evalCases()])
      .then(([health, personas, targets, cases]) => {
        if (!cancelled) {
          setBoot({ health, personas, targets, cases });
          setError(null);
        }
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof ApiError ? e.message : "Failed to load"));
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  return (
    <>
      <DemoBanner />
      <main className="mx-auto w-full max-w-7xl flex-1 space-y-4 p-4 md:p-6">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">McKinley AI — leasing & resident assistant prototype</h1>
          <p className="text-sm text-muted-foreground">
            Compare a generic baseline against the McKinley-aware assistant on the same message, model and settings.
          </p>
          <StatusBar health={boot?.health ?? null} error={error} />
          {error && (
            <button className="text-sm underline" onClick={() => setAttempt((a) => a + 1)}>
              Retry
            </button>
          )}
        </header>
        {boot && (
          <Tabs defaultValue="chat">
            <TabsList>
              <TabsTrigger value="chat">Chat comparison</TabsTrigger>
              <TabsTrigger value="evals">Five-case evaluation</TabsTrigger>
            </TabsList>
            <TabsContent value="chat">
              <ChatWorkbench personas={boot.personas} targets={boot.targets} cases={boot.cases} />
            </TabsContent>
            <TabsContent value="evals">
              <EvalDashboard targets={boot.targets} cases={boot.cases} />
            </TabsContent>
          </Tabs>
        )}
      </main>
    </>
  );
}
