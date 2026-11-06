"use client";

import { AlertTriangle, CheckCircle2, CircleDashed, ClipboardCheck, Lock } from "lucide-react";
import { type ComponentType, useId } from "react";

import { SOURCE_TEXT, STAGE_TEXT, actionTone, type Tone } from "@/lib/customer";
import { cn } from "@/lib/utils";
import type { ProposedAction } from "@/lib/types";

const TONE: Record<Tone, { rail: string; pill: string; Icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }> }> = {
  draft: { rail: "bg-mk-line-strong", pill: "bg-mk-draft-soft text-mk-draft", Icon: CircleDashed },
  ready: { rail: "bg-mk-brand", pill: "bg-mk-brand-soft text-mk-brand", Icon: ClipboardCheck },
  sent: { rail: "bg-mk-sent", pill: "bg-mk-sent-soft text-mk-sent", Icon: CheckCircle2 },
  urgent: { rail: "bg-mk-danger", pill: "bg-mk-danger-soft text-mk-danger", Icon: AlertTriangle },
  blocked: { rail: "bg-mk-line-strong", pill: "bg-mk-draft-soft text-mk-draft", Icon: Lock },
};

export interface ActionCardProps {
  action: ProposedAction;
  /** Older cards in the transcript are read-only summaries. */
  interactive: boolean;
  busy?: boolean;
  confirmDisabledReason?: string | null;
  cancelAvailable?: boolean;
  onConfirm?: () => void;
  onCancel?: () => void;
}

export function ActionCard({
  action,
  interactive,
  busy = false,
  confirmDisabledReason = null,
  cancelAvailable = true,
  onConfirm,
  onCancel,
}: ActionCardProps) {
  const tone = actionTone(action);
  const { rail, pill, Icon } = TONE[tone];
  const stageText = action.stage === "submitted" && action.record ? action.record.status_label : STAGE_TEXT[action.stage];
  const headingId = useId();
  const shownFields = action.fields.filter((f) => f.value);

  return (
    <div
      role="group"
      aria-labelledby={headingId}
      className="relative mt-3 overflow-hidden rounded-lg border border-mk-line bg-mk-surface"
      data-testid="action-card"
      data-stage={action.stage}
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1.5", rail)} />
      <div className="py-3 pr-3 pl-5 sm:pr-4 sm:pl-6">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
          <h2 id={headingId} className="text-base font-semibold">
            {action.title}
          </h2>
          <p className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-medium", pill)}>
            <Icon aria-hidden className="size-4 shrink-0" />
            {stageText}
          </p>
        </div>

        {action.record && (
          <p className="mt-1 text-sm text-mk-muted">
            Reference <span className="font-semibold text-mk-ink">{action.record.id}</span>
          </p>
        )}

        {interactive && shownFields.length > 0 && action.stage !== "submitted" && <FieldList fields={shownFields} />}
        {interactive && shownFields.length > 0 && action.stage === "submitted" && (
          <details className="mt-2">
            <summary className="mk-focus inline-flex min-h-11 cursor-pointer items-center text-mk-brand underline underline-offset-2">
              What was sent
            </summary>
            <FieldList fields={shownFields} />
          </details>
        )}

        {interactive && action.missing.length > 0 && (
          <p className="mt-2 text-sm">
            <span className="font-semibold">Still needed:</span> {action.missing.join(", ")}
          </p>
        )}

        {interactive && <p className="mt-2 text-sm text-mk-muted">{action.note}</p>}

        {interactive && action.stage === "ready" && action.confirm_label && (
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy || !!confirmDisabledReason}
              aria-describedby={confirmDisabledReason ? `${headingId}-why` : undefined}
              className="mk-focus inline-flex min-h-11 items-center justify-center rounded-md bg-mk-brand px-4 text-base font-semibold text-white hover:bg-mk-brand-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Sending…" : action.confirm_label}
            </button>
            {cancelAvailable && (
              <button
                type="button"
                onClick={onCancel}
                disabled={busy}
                className="mk-focus inline-flex min-h-11 items-center justify-center rounded-md border border-mk-line-strong bg-mk-surface px-4 text-base font-medium hover:bg-mk-paper disabled:opacity-60"
              >
                Don&apos;t send
              </button>
            )}
            {confirmDisabledReason && (
              <p id={`${headingId}-why`} className="text-sm text-mk-muted">
                {confirmDisabledReason}
              </p>
            )}
          </div>
        )}
        {interactive && action.stage === "collecting" && (
          <p className="mt-2 text-sm text-mk-muted">Nothing is sent until you check the details and press send.</p>
        )}
      </div>
    </div>
  );
}

function FieldList({ fields }: { fields: ProposedAction["fields"] }) {
  return (
    <dl className="mt-3 divide-y divide-mk-line border-y border-mk-line">
      {fields.map((f) => (
        <div key={f.key} className="py-2 sm:grid sm:grid-cols-[9.5rem_1fr_auto] sm:items-baseline sm:gap-3">
          <dt className="flex items-baseline justify-between gap-3 text-sm text-mk-muted sm:block">
            <span>{f.label}</span>
            <span className="sm:hidden">{SOURCE_TEXT[f.source] ?? f.source}</span>
          </dt>
          <dd className="text-base break-words">{sentenceCase(f.value ?? "")}</dd>
          <dd className="hidden text-sm text-mk-muted sm:block sm:text-right">{SOURCE_TEXT[f.source] ?? f.source}</dd>
        </div>
      ))}
    </dl>
  );
}

function sentenceCase(v: string): string {
  return v ? v[0].toUpperCase() + v.slice(1) : v;
}
