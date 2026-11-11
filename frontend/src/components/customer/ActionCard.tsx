"use client";

import { useId } from "react";

import { type UIStrings, actionTone } from "@/lib/customer";
import { cn } from "@/lib/utils";
import type { ProposedAction } from "@/lib/types";

import { ListChecks } from "lucide-react";

import { StatusPill, type StatusTone } from "./StatusPill";

/** current = the card to act on (or a saved record); declined = the person chose not to send it. */
export type CardState = "current" | "declined";

export interface ActionCardProps {
  action: ProposedAction;
  state: CardState;
  t: UIStrings;
  busy?: boolean;
  /** Prospects and guests have a profile, not an account: relabels "On your account". */
  onFileLabel?: string;
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
  onFileLabel,
  confirmAvailable = true,
  cancelAvailable = true,
  onConfirm,
  onCancel,
}: ActionCardProps) {
  const headingId = useId();
  const submitted = action.stage === "submitted";
  const declined = state === "declined" && !submitted;
  const base = actionTone(action);
  const tone: StatusTone = declined ? "declined" : base === "sent" ? "submitted" : base;
  const stageText = declined ? t.notSent : submitted && action.record ? t.statusText(action.record.status_label) : t.stage[action.stage];
  const shownFields = action.fields.filter((f) => f.value);
  const open = !declined && !submitted;
  const urgent = tone === "urgent";

  return (
    <div
      role="group"
      aria-labelledby={headingId}
      className={cn(
        "mt-3 rounded-xl border bg-mk-surface px-4 py-3.5 shadow-[0_1px_2px_rgb(28_37_48/0.06)] sm:px-5",
        urgent ? "border-mk-danger/60" : declined ? "border-mk-line shadow-none" : submitted ? "border-mk-done/40" : "border-mk-line-strong/60",
      )}
      data-testid="action-card"
      data-stage={action.stage}
      data-state={state}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
        <h3 id={headingId} className={cn("font-heading text-[1.05rem] font-semibold", declined && "text-mk-muted")}>
          {action.title}
        </h3>
        <StatusPill tone={tone}>{stageText}</StatusPill>
      </div>

      {action.record && (
        <p className="mt-1 text-sm text-mk-muted">
          {t.reference} <span className="font-semibold text-mk-ink tabular-nums">{action.record.id}</span>
        </p>
      )}

      {open && shownFields.length > 0 && <FieldList fields={shownFields} t={t} onFileLabel={onFileLabel} />}
      {(submitted || declined) && shownFields.length > 0 && (
        <details className="mt-1">
          {/* WebKit ignores display:flex on <summary>, so the 44px target height lives on an inner span. */}
          <summary className="mk-focus block w-fit min-h-11 cursor-pointer text-mk-brand-hover underline underline-offset-2">
            <span className="inline-flex min-h-11 items-center">{submitted ? t.whatWasSent : t.whatItSaid}</span>
          </summary>
          <FieldList fields={shownFields} t={t} onFileLabel={onFileLabel} />
        </details>
      )}

      {open && action.missing.length > 0 && (
        <p className="mt-2 text-sm">
          <span className="font-semibold">{t.stillNeeded}</span> {action.missing.join(", ")}
        </p>
      )}

      {/* A sent card gets one honest line instead of the backend's "Prototype…" note next to "waiting for review". */}
      {!declined && <p className="mt-2 text-sm text-mk-muted">{submitted ? t.sentDemoNote : action.note}</p>}

      {open && action.stage === "ready" && action.confirm_label && (confirmAvailable || cancelAvailable) && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
          {confirmAvailable && (
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy}
              className="mk-focus inline-flex min-h-12 items-center justify-center rounded-lg bg-mk-brand px-5 font-heading text-[1.05rem] font-semibold text-white hover:bg-mk-brand-hover active:bg-mk-brand-strong disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? t.sending : action.confirm_label}
            </button>
          )}
          {cancelAvailable && (
            <button
              type="button"
              onClick={onCancel}
              disabled={busy}
              className="mk-focus inline-flex min-h-12 items-center justify-center rounded-lg border border-mk-line-strong bg-mk-surface px-5 text-base font-medium hover:bg-mk-paper disabled:opacity-60"
            >
              {t.dontSend}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** Account values come from the (English) workbook; in a Spanish conversation they are tagged lang="en". */
const ENGLISH_VALUE =
  /\b(the|and|by|prefers?|afternoons?|mornings?|evenings?|weekdays?|weekends?|email|phone|text|chat|am|pm|kitchen|bathroom|bedroom|living room|hallway|heating|cooling|system)\b/i;

/** Rows that describe the demo system rather than the request: not shown to customers (staff console keeps them). */
const SYSTEM_ONLY = /^(not collected in this prototype|no se recoge en este prototipo|signed-in resident \(demo account\)|signed in(?: as [^()]+)? \(demo account\))$/i;

function FieldList({ fields, t, onFileLabel }: { fields: ProposedAction["fields"]; t: UIStrings; onFileLabel?: string }) {
  const spanish = t.lang === "es";
  return (
    <dl className="mt-3 divide-y divide-mk-line border-y border-mk-line">
      {fields.filter((f) => !SYSTEM_ONLY.test(f.value ?? "")).map((f) => (
        // Phone: label + source on the first row, value below. Desktop: three columns. The dt is the label only.
        <div key={f.key} className="grid grid-cols-[1fr_auto] gap-x-3 py-2 sm:grid-cols-[9.5rem_1fr_auto] sm:items-baseline">
          <dt className="col-start-1 row-start-1 text-sm text-mk-muted">{f.label}</dt>
          <dd
            className="col-span-2 col-start-1 row-start-2 text-base break-words sm:col-span-1 sm:col-start-2 sm:row-start-1"
            lang={spanish && f.source !== "you_said" && ENGLISH_VALUE.test(f.value ?? "") ? "en" : undefined}
          >
            {sentenceCase(f.value ?? "")}
          </dd>
          <dd className="col-start-2 row-start-1 text-right text-xs text-mk-muted sm:col-start-3">
            {f.source === "on_file" && onFileLabel ? onFileLabel : (t.source[f.source as keyof UIStrings["source"]] ?? f.source)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function sentenceCase(v: string): string {
  return v ? v[0].toUpperCase() + v.slice(1) : v;
}

/** One-line progress note shown instead of a full card while details are still being collected. */
export function ProgressHint({ action, t }: { action: ProposedAction; t: UIStrings }) {
  return (
    <p className="mt-2 flex max-w-full items-start gap-2 text-sm text-mk-muted" data-testid="progress-hint">
      <ListChecks aria-hidden className="mt-0.5 size-4 shrink-0 text-mk-brand" />
      <span>
        <span className="font-semibold text-mk-ink">{action.title}.</span>{" "}
        {action.missing.length ? `${t.stillNeeded} ${action.missing.join(", ")}` : t.stage.collecting}
      </span>
    </p>
  );
}
