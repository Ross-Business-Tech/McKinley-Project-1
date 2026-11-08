import { AlertTriangle, Ban, CheckCircle2, CircleDashed, ClipboardCheck, Clock, Lock } from "lucide-react";
import type { ComponentType, ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * One status vocabulary for the chat cards, the customer status list and the staff work queue.
 * urgent = danger red + warning icon; owed = amber; ready = brand (check, then send); submitted = brand;
 * draft / not sent / blocked = neutral. Text and icon always carry the meaning; colour only reinforces it.
 */
export type StatusTone = "urgent" | "owed" | "ready" | "submitted" | "draft" | "declined" | "blocked";

type Icon = ComponentType<{ className?: string; "aria-hidden"?: boolean }>;

export const STATUS_STYLE: Record<StatusTone, { pill: string; Icon: Icon }> = {
  urgent: { pill: "bg-mk-danger-soft text-mk-danger", Icon: AlertTriangle },
  owed: { pill: "bg-mk-attention-soft text-mk-attention", Icon: Clock },
  ready: { pill: "bg-mk-brand-soft text-mk-brand", Icon: ClipboardCheck },
  submitted: { pill: "bg-mk-brand-soft text-mk-brand", Icon: CheckCircle2 },
  draft: { pill: "bg-mk-draft-soft text-mk-draft", Icon: CircleDashed },
  declined: { pill: "bg-mk-draft-soft text-mk-draft", Icon: Ban },
  blocked: { pill: "bg-mk-draft-soft text-mk-draft", Icon: Lock },
};

/** Tone for a saved record or a status-list line, from its status text and priority. */
export function statusTone(status: string, priority?: string | null): StatusTone {
  if (/urgent|urgente|emergenc/i.test(status) || priority === "urgent") return "urgent";
  if (/owed|pendiente|overdue/i.test(status)) return "owed";
  return "submitted";
}

export function StatusPill({ tone, children, className }: { tone: StatusTone; children: ReactNode; className?: string }) {
  const { pill, Icon } = STATUS_STYLE[tone];
  return (
    <span className={cn("inline-flex max-w-full items-start gap-1.5 rounded-lg px-2.5 py-0.5 text-sm font-medium break-words", pill, className)}>
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span className="min-w-0">{children}</span>
    </span>
  );
}
