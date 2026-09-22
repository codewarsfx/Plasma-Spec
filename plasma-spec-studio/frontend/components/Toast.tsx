"use client";

/**
 * Lightweight toast system.
 *
 * - ``useToastStore`` is a tiny global subscribable store (no library dep).
 * - ``ToastHost`` renders the visible toasts in a fixed bottom-right column.
 * - ``toast.success / info / warning / error`` push toasts from anywhere.
 *
 * Toasts auto-dismiss after 4 s by default; pass ``durationMs: 0`` to make a
 * toast sticky and require manual dismissal.
 */

import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

type ToastKind = "success" | "info" | "warning" | "error";

type Toast = {
  id: string;
  kind: ToastKind;
  title: string;
  body?: string;
  durationMs: number;
};

type Subscriber = (toasts: Toast[]) => void;

let toasts: Toast[] = [];
const subscribers = new Set<Subscriber>();

function notify() {
  for (const sub of subscribers) sub([...toasts]);
}

function push(kind: ToastKind, title: string, body?: string, durationMs = 4000) {
  const id = Math.random().toString(36).slice(2, 9);
  const toast: Toast = { id, kind, title, body, durationMs };
  toasts = [...toasts, toast];
  notify();
  if (durationMs > 0) {
    setTimeout(() => dismiss(id), durationMs);
  }
  return id;
}

function dismiss(id: string) {
  toasts = toasts.filter((t) => t.id !== id);
  notify();
}

export const toast = {
  success: (title: string, body?: string, durationMs?: number) =>
    push("success", title, body, durationMs),
  info: (title: string, body?: string, durationMs?: number) =>
    push("info", title, body, durationMs),
  warning: (title: string, body?: string, durationMs?: number) =>
    push("warning", title, body, durationMs),
  error: (title: string, body?: string, durationMs?: number) =>
    push("error", title, body, durationMs ?? 6000),
  dismiss,
};

const KIND_STYLE: Record<ToastKind, { className: string; Icon: typeof CheckCircle2 }> = {
  success: {
    className: "border-teal-200 bg-teal-50 text-teal-900",
    Icon: CheckCircle2,
  },
  info: {
    className: "border-sky-200 bg-sky-50 text-sky-900",
    Icon: Info,
  },
  warning: {
    className: "border-amber-200 bg-amber-50 text-amber-950",
    Icon: AlertTriangle,
  },
  error: {
    className: "border-red-200 bg-red-50 text-red-900",
    Icon: XCircle,
  },
};

export function ToastHost() {
  const [current, setCurrent] = useState<Toast[]>(toasts);

  useEffect(() => {
    const sub: Subscriber = (next) => setCurrent(next);
    subscribers.add(sub);
    return () => {
      subscribers.delete(sub);
    };
  }, []);

  if (current.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex max-w-sm flex-col gap-2">
      {current.map((t) => {
        const style = KIND_STYLE[t.kind];
        const Icon = style.Icon;
        return (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-2 border px-3 py-2 shadow-md transition-all toast-enter ${style.className}`}
            style={{ borderRadius: 8 }}
            role="status"
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold leading-tight">{t.title}</div>
              {t.body ? (
                <div className="mt-0.5 text-xs leading-snug opacity-90">{t.body}</div>
              ) : null}
            </div>
            <button
              className="ml-1 rounded p-0.5 opacity-60 transition hover:bg-black/10 hover:opacity-100"
              onClick={() => dismiss(t.id)}
              title="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
