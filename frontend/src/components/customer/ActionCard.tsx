"use client";

import { AlertTriangle, Ban, CheckCircle2, CircleDashed, ClipboardCheck, History, Lock } from "lucide-react";
import { type ComponentType, useId } from "react";

import { type UIStrings, actionTone, type Tone } from "@/lib/customer";
import { cn } from "@/lib/utils";
import type { ProposedAction } from "@/lib/types";

type Icon = ComponentType<{ className?: string; "aria-hidden"?: boolean }>;

/**
 * State vocabulary (shared with the staff console): draft = neutral, ready = blue "check and send",
 * sent = brand green, urgent = red, not sent / earlier version = muted. Text and icon always carry the meaning.
 */
const TONE: Record<Tone | "inactive", { rail: string; pill: string; Icon: Icon }> = {
  draft: { rail: "bg-mk-line-strong", pill: "bg-mk-draft-soft text-mk-draft", Icon: CircleDashed },
  ready: { rail: "bg-mk-sent", pill: "bg-mk-sent-soft text-mk-sent", Icon: ClipboardCheck },
  sent: { rail: "bg-mk-brand", pill: "bg-mk-brand-soft text-mk-brand", Icon: CheckCircle2 },
  urgent: { rail: "bg-mk-danger", pill: "bg-mk-danger-soft text-mk-danger", Icon: AlertTriangle },
  blocked: { rail: "bg-mk-line-strong", pill: "bg-mk-draft-soft text-mk-draft", Icon: Lock },
  inactive: { rail: "bg-mk-line", pill: "bg-mk-draft-soft text-mk-draft", Icon: History },
};

export type CardState = "current" | "superseded" | "declined";

export interface ActionCardProps {
  action: ProposedAction;
  state: CardState;
  t: UIStrings;
  busy?: boolean;
  /** False in preview mode when the recording doesn't continue with this button: then it is hidden, not disabled. */
  confirmAvailable?: boolean;
  cancelAvailable?: boolean;
  onConfirm?: () => void;
  onCancel?: () => void;
}

export function ActionCard({
  action,
  state,
  t,
  busy = false,
  confirmAvailable = true,
  cancelAvailable = true,
  onConfirm,
  onCancel,
}: ActionCardProps) {
  const headingId = useId();
  const submitted = action.stage === "submitted";
  const inactive = state !== "current" && !submitted;
  const tone: Tone | "inactive" = inactive ? "inactive" : actionTone(action);
  const { rail, pill, Icon } = TONE[tone];
  const PillIcon = state === "declined" && !submitted ? Ban : Icon;
  const stageText =
    state === "declined" && !submitted
      ? t.notSent
      : inactive
        ? t.replaced
        : submitted && action.record
          ? action.record.status_label
          : t.stage[action.stage];
  const shownFields = action.fields.filter((f) => f.value);
  const showDetails = state === "current" && !submitted;

  return (
    <div
      role="group"
      aria-labelledby={headingId}
      className={cn("relative mt-3 overflow-hidden rounded-lg border bg-mk-surface", inactive ? "border-mk-line" : "border-mk-line-strong/50")}
      data-testid="action-card"
      data-stage={action.stage}
      data-state={state}
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1.5", rail)} />
      <div className={cn("py-3 pr-3 pl-5 sm:pr-4 sm:pl-6", inactive && "py-2")}>
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
          <h2 id={headingId} className={cn("text-base font-semibold", inactive && "text-mk-muted")}>
            {action.title}
          </h2>
          <p className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-medium whitespace-nowrap", pill)}>
            <PillIcon aria-hidden className="size-4 shrink-0" />
            {stageText}
          </p>
        </div>

        {action.record && (
          <p className="mt-1 text-sm text-mk-muted">
            {t.reference} <span className="font-semibold text-mk-ink tabular-nums">{action.record.id}</span>
          </p>
        )}

        {showDetails && shownFields.length > 0 && <FieldList fields={shownFields} t={t} />}
        {submitted && shownFields.length > 0 && (
          <details className="mt-1">
            <summary className="mk-focus inline-flex min-h-11 cursor-pointer items-center text-mk-brand underline underline-offset-2">
              {t.whatWasSent}
            </summary>
            <FieldList fields={shownFields} t={t} />
          </details>
        )}

        {showDetails && action.missing.length > 0 && (
          <p className="mt-2 text-sm">
            <span className="font-semibold">{t.stillNeeded}</span> {action.missing.join(", ")}
          </p>
        )}

        {(showDetails || submitted) && <p className="mt-2 text-sm text-mk-muted">{action.note}</p>}

        {showDetails && action.stage === "ready" && action.confirm_label && (confirmAvailable || cancelAvailable) && (
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            {confirmAvailable && (
              <button
                type="button"
                onClick={onConfirm}
                disabled={busy}
                className="mk-focus inline-flex min-h-11 items-center justify-center rounded-md bg-mk-brand px-4 text-base font-semibold text-white hover:bg-mk-brand-hover disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy ? t.sending : action.confirm_label}
              </button>
            )}
            {cancelAvailable && (
              <button
                type="button"
                onClick={onCancel}
                disabled={busy}
                className="mk-focus inline-flex min-h-11 items-center justify-center rounded-md border border-mk-line-strong bg-mk-surface px-4 text-base font-medium hover:bg-mk-paper disabled:opacity-60"
              >
                {t.dontSend}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FieldList({ fields, t }: { fields: ProposedAction["fields"]; t: UIStrings }) {
  return (
    <dl className="mt-3 divide-y divide-mk-line border-y border-mk-line">
      {fields.map((f) => (
        // Phone: label + source on the first row, value below. Desktop: three columns. The dt is the label only.
        <div key={f.key} className="grid grid-cols-[1fr_auto] gap-x-3 py-2 sm:grid-cols-[9.5rem_1fr_auto] sm:items-baseline">
          <dt className="text-sm text-mk-muted">{f.label}</dt>
          <dd className="col-span-2 row-start-2 text-base break-words sm:col-span-1 sm:row-start-1">{sentenceCase(f.value ?? "")}</dd>
          <dd className="col-start-2 row-start-1 text-right text-xs text-mk-muted sm:col-start-3">
            {t.source[f.source as keyof UIStrings["source"]] ?? f.source}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function sentenceCase(v: string): string {
  return v ? v[0].toUpperCase() + v.slice(1) : v;
}
