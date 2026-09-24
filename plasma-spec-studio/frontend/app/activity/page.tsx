"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Trash2, User, XCircle } from "lucide-react";

import { deleteSharedResult, listSharedResults } from "@/lib/api";
import { supabase } from "@/lib/supabase/client";
import { toast } from "@/components/Toast";
import type { SharedResult } from "@/lib/types";

export default function ActivityPage() {
  const [items, setItems] = useState<SharedResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);

  useEffect(() => {
    supabase?.auth.getSession().then(({ data }) => setCurrentUserId(data.session?.user.id ?? null));
    refresh();
  }, []);

  function refresh() {
    setLoading(true);
    listSharedResults()
      .then((data) => setItems(data.results))
      .catch((exc) => toast.error("Couldn't load activity", exc instanceof Error ? exc.message : "unknown error"))
      .finally(() => setLoading(false));
  }

  async function remove(id: string) {
    try {
      await deleteSharedResult(id);
      setItems((prev) => prev.filter((item) => item.id !== id));
    } catch (exc) {
      toast.error("Couldn't delete", exc instanceof Error ? exc.message : "unknown error");
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="text-xl font-semibold text-ink">Activity</h1>
      <p className="mt-1 text-sm text-slate-500">Results other members have shared, newest first.</p>

      {loading ? (
        <p className="mt-8 text-center text-sm text-slate-500">Loading…</p>
      ) : items.length === 0 ? (
        <p className="mt-8 text-center text-sm text-slate-500">
          Nothing shared yet. Run an analysis in Studio and hit Share on the result.
        </p>
      ) : (
        <ul className="mt-6 grid gap-3">
          {items.map((item) => (
            <li key={item.id} className="panel p-4">
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 flex-none items-center justify-center overflow-hidden border border-line bg-slate-50 text-slate-400" style={{ borderRadius: 999 }}>
                  {item.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={item.avatar_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <User className="h-4 w-4" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-sm font-semibold text-ink">{item.display_name || "Someone"}</span>
                    <span className="text-xs text-slate-500">{formatTimestamp(item.created_at)}</span>
                    {qualityChip(item.result_json?.fit_quality)}
                    {item.user_id === currentUserId ? (
                      <button
                        type="button"
                        className="icon-button ml-auto h-7 w-7"
                        title="Delete this share"
                        onClick={() => remove(item.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    ) : null}
                  </div>
                  <p className="mt-1 truncate text-xs text-slate-500">
                    {item.spectrum_filename ?? "(no filename)"} · {item.diagnostic}
                  </p>
                  {item.caption ? <p className="mt-2 text-sm text-ink">{item.caption}</p> : null}
                  {headlineMetrics(item.result_json).length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-600">
                      {headlineMetrics(item.result_json).map(([key, value]) => (
                        <span key={key}>
                          <span className="text-slate-400">{key}:</span> {value}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function qualityChip(quality?: string) {
  if (quality === "good") {
    return (
      <span className="inline-flex items-center gap-1 border border-teal-200 bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-900" style={{ borderRadius: 999 }}>
        <CheckCircle2 className="h-3 w-3" />good
      </span>
    );
  }
  if (quality === "bad") {
    return (
      <span className="inline-flex items-center gap-1 border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-900" style={{ borderRadius: 999 }}>
        <XCircle className="h-3 w-3" />bad
      </span>
    );
  }
  if (quality === "warning") {
    return (
      <span className="inline-flex items-center gap-1 border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-950" style={{ borderRadius: 999 }}>
        <AlertTriangle className="h-3 w-3" />warn
      </span>
    );
  }
  return null;
}

function headlineMetrics(result: SharedResult["result_json"] | undefined): Array<[string, string]> {
  if (!result?.metrics) return [];
  return Object.entries(result.metrics)
    .slice(0, 3)
    .map(([key, value]) => [key, formatNumber(value)]);
}

function formatNumber(value: unknown): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value ?? "—");
  if (Math.abs(number) >= 1e5 || (Math.abs(number) < 0.001 && number !== 0)) return number.toExponential(2);
  return number.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function formatTimestamp(value: string): string {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}
