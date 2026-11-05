"use client";

import { Badge } from "@/components/ui/badge";
import type { Health } from "@/lib/types";

export function DemoBanner() {
  return (
    <div role="note" className="w-full bg-amber-100 px-4 py-2 text-center text-sm text-amber-950 dark:bg-amber-900/40 dark:text-amber-100">
      <strong>Synthetic-data prototype.</strong> All residents, prospects and history are fictional. No live Yardi,
      Databricks, phone, SMS, email or work-order systems are connected. Handoffs are recommendations only.
    </div>
  );
}

/** Persistent banner shown when the site runs from the pre-computed static snapshot. */
export function StaticDemoBanner({ notice, generatedAt }: { notice: string; generatedAt?: string }) {
  return (
    <div role="status" className="rounded-md border-2 border-sky-400 bg-sky-50 p-3 text-sm text-sky-950 dark:border-sky-700 dark:bg-sky-950/40 dark:text-sky-100">
      <p className="font-semibold">
        Static demo — responses were pre-computed with the MOCK provider and rules gate; no live AI is running.
      </p>
      <p className="mt-1 text-xs">
        {notice}
        {generatedAt && <> Snapshot generated {generatedAt.slice(0, 10)}.</>}
      </p>
    </div>
  );
}

export function StatusBar({ health, error }: { health: Health | null; error: string | null }) {
  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        Backend unavailable: {error}
      </p>
    );
  }
  if (!health) return <p className="text-sm text-muted-foreground" aria-live="polite">Checking backend…</p>;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" aria-label="Backend status">
      <Badge variant="outline">
        Default: {health.provider}:{health.model}
      </Badge>
      {health.provider === "mock" ? (
        <Badge variant="secondary">MOCK provider — not a language model</Badge>
      ) : health.provider_ready ? (
        <Badge variant="secondary">{health.provider_status}</Badge>
      ) : (
        <Badge variant="destructive">{health.provider_status}</Badge>
      )}
      <Badge variant="outline">Prompt {health.prompt_version}</Badge>
      {health.data_loaded ? (
        <Badge variant="outline">
          Synthetic workbook: {health.resident_count} residents / {health.interaction_count} interactions
        </Badge>
      ) : (
        <Badge variant="destructive">Workbook missing — resident personas unavailable</Badge>
      )}
    </div>
  );
}
