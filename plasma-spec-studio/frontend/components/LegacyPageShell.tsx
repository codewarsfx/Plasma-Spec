"use client";

import Link from "next/link";
import { Microscope } from "lucide-react";
import type { ReactNode } from "react";

/**
 * Shared shell for the legacy focused-workflow pages
 * (/spectra, /batch, /dashboard, /recipes).
 *
 * Provides a centered max-width container plus a single banner pointing back
 * to the workstation, so the focused pages still feel like part of the same
 * product rather than disconnected screens.
 */
export function LegacyPageShell({
  title,
  description,
  studioHint,
  children,
}: {
  title: string;
  description?: string;
  studioHint?: string;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-[1500px] px-4 py-4">
      <div className="mb-4 flex flex-col gap-2 border border-line bg-white p-3 shadow-thin md:flex-row md:items-center md:justify-between" style={{ borderRadius: 8 }}>
        <div>
          <h1 className="text-base font-semibold text-ink">{title}</h1>
          {description ? (
            <p className="mt-0.5 text-xs text-slate-600">{description}</p>
          ) : null}
        </div>
        <Link
          href="/studio"
          className="inline-flex items-center gap-2 self-start border border-teal-200 bg-teal-50 px-3 py-1.5 text-xs font-medium text-teal-900 transition hover:bg-teal-100"
          style={{ borderRadius: 6 }}
          title={studioHint ?? "Open the workstation"}
        >
          <Microscope className="h-3.5 w-3.5" />
          Open in Studio
        </Link>
      </div>
      {children}
    </div>
  );
}
