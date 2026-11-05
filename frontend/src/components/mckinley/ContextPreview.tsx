"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { SafeContext } from "@/lib/types";

export function ContextPreview({
  ctx,
  loading,
  error,
  emptyHint,
}: {
  ctx: SafeContext | null;
  loading: boolean;
  error: string | null;
  emptyHint?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Context preview</CardTitle>
        <CardDescription>
          Exactly what mode C (McKinley + resident context) sends to the model. Modes A and B receive none of these
          fields.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm" aria-live="polite" aria-busy={loading}>
        {error && <p role="alert" className="text-destructive">{error}</p>}
        {!ctx && !error && <p className="text-muted-foreground">{loading ? "Loading…" : (emptyHint ?? "Select a persona.")}</p>}
        {ctx && (
          <>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">audience: {ctx.audience}</Badge>
              <Badge variant={ctx.record_found ? "secondary" : "destructive"}>
                {ctx.record_found ? "record matched" : "no matched record"}
              </Badge>
              {ctx.topics.map((t) => (
                <Badge key={t} variant="outline">topic: {t}</Badge>
              ))}
            </div>
            {ctx.fields.length > 0 ? (
              <dl className="space-y-1">
                {ctx.fields.map((f, i) => (
                  <div key={`${f.name}-${i}`} className="grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)] gap-2 break-words">
                    <dt className="font-medium">{f.name}</dt>
                    <dd>
                      {f.value}
                      <span className="block text-xs text-muted-foreground">source: {f.source}</span>
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-muted-foreground">No personal context fields will be sent.</p>
            )}
            {ctx.withheld_fields.length > 0 && (
              <p className="text-xs text-muted-foreground">
                <span className="font-medium">Withheld (never sent):</span> {ctx.withheld_fields.join(", ")}
              </p>
            )}
            {ctx.dropped_items.length > 0 && (
              <p className="text-xs text-amber-700 dark:text-amber-300">
                <span className="font-medium">Dropped by safety screen:</span> {ctx.dropped_items.join("; ")}
              </p>
            )}
            {ctx.notes.map((n) => (
              <p key={n} className="text-xs text-muted-foreground">{n}</p>
            ))}
          </>
        )}
      </CardContent>
    </Card>
  );
}
