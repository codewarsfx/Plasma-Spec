"use client";

import { Activity, Atom, Beaker, LineChart } from "lucide-react";

export type DiagnosticId =
  | "hbeta_voigt"
  | "peak_area"
  | "oh_ax"
  | "n2_cb"
  | "n2plus_bx"
  | "nh_ax"
  | "no_bx"
  | "line_identification";

export const DIAGNOSTICS: Array<{
  id: DiagnosticId;
  label: string;
  window: [number, number];
  icon: "activity" | "beaker" | "atom" | "line";
}> = [
  { id: "hbeta_voigt", label: "Hβ Voigt", window: [484, 488], icon: "activity" },
  { id: "oh_ax", label: "OH(A-X)", window: [306, 312], icon: "beaker" },
  { id: "n2_cb", label: "N₂(C-B)", window: [334, 339], icon: "atom" },
  { id: "n2plus_bx", label: "N₂⁺(B-X)", window: [388, 392], icon: "atom" },
  { id: "nh_ax", label: "NH(A-X)", window: [335, 338], icon: "beaker" },
  { id: "no_bx", label: "NO(B-X)", window: [357, 425], icon: "beaker" },
  { id: "peak_area", label: "Peak area", window: [484, 488], icon: "line" },
  { id: "line_identification", label: "Line ID", window: [300, 850], icon: "line" },
];

type DiagnosticSelectorProps = {
  diagnostic: DiagnosticId;
  onChange: (diagnostic: DiagnosticId, windowNm: [number, number]) => void;
};

export function DiagnosticSelector({ diagnostic, onChange }: DiagnosticSelectorProps) {
  return (
    <section className="panel p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink">Diagnostic</h2>
      <div className="grid grid-cols-2 gap-2">
        {DIAGNOSTICS.map((item) => {
          const Icon = iconFor(item.icon);
          const active = item.id === diagnostic;
          return (
            <button
              key={item.id}
              className={`flex h-10 items-center gap-2 border px-3 text-left text-sm font-medium focus-ring ${
                active
                  ? "border-plasma bg-teal-50 text-teal-900"
                  : "border-line bg-white text-slate-700 hover:bg-slate-50"
              }`}
              style={{ borderRadius: 6 }}
              onClick={() => onChange(item.id, item.window)}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function iconFor(name: string) {
  if (name === "activity") return Activity;
  if (name === "beaker") return Beaker;
  if (name === "atom") return Atom;
  return LineChart;
}
