"use client";

import { RotateCcw, Wand2 } from "lucide-react";
import { useMemo, useState } from "react";
import type { PreprocessingOperation } from "@/lib/types";

type PreprocessingPanelProps = {
  operations: PreprocessingOperation[];
  onChange: (operations: PreprocessingOperation[]) => void;
  windowNm: [number, number];
  onWindowChange: (windowNm: [number, number]) => void;
};

export function PreprocessingPanel({
  operations,
  onChange,
  windowNm,
  onWindowChange,
}: PreprocessingPanelProps) {
  const [calibrationPairsText, setCalibrationPairsText] = useState("656.10,656.279\n486.00,486.135");
  const [calibrationOrder, setCalibrationOrder] = useState(1);
  const calibrationPairs = useMemo(() => parseCalibrationPairs(calibrationPairsText), [calibrationPairsText]);
  const calibrationReady = calibrationPairs.length >= calibrationOrder + 1;

  function toggleOperation(operation: PreprocessingOperation, enabled: boolean) {
    const next = operations.filter((item) => item.operation !== operation.operation);
    if (enabled) next.push(operation);
    onChange(next);
  }

  const has = (name: string) => operations.some((operation) => operation.operation === name);

  function updateCalibrationOperation(nextPairs = calibrationPairs, nextOrder = calibrationOrder) {
    if (!has("wavelength_calibration") || nextPairs.length < nextOrder + 1) return;
    const next = operations.filter((item) => item.operation !== "wavelength_calibration");
    next.push(calibrationOperation(nextPairs, nextOrder));
    onChange(next);
  }

  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Preprocessing</h2>
        <button className="icon-button" title="Reset preprocessing" onClick={() => onChange([])}>
          <RotateCcw className="h-4 w-4" />
        </button>
      </div>
      <div className="grid gap-3">
        <div className="grid grid-cols-2 gap-2">
          <label className="grid gap-1">
            <span className="control-label">Window min nm</span>
            <input
              className="field"
              type="number"
              step="0.01"
              value={windowNm[0]}
              onChange={(event) => onWindowChange([Number(event.target.value), windowNm[1]])}
            />
          </label>
          <label className="grid gap-1">
            <span className="control-label">Window max nm</span>
            <input
              className="field"
              type="number"
              step="0.01"
              value={windowNm[1]}
              onChange={(event) => onWindowChange([windowNm[0], Number(event.target.value)])}
            />
          </label>
        </div>
        <ToggleRow
          label="Crop to window"
          hint="Restrict the spectrum to the wavelength window above. Subsequent operations only see the cropped region."
          checked={has("crop")}
          onChange={(checked) => toggleOperation({ operation: "crop", params: { window_nm: windowNm } }, checked)}
        />
        <div className="grid gap-2 border border-line bg-white px-3 py-2" style={{ borderRadius: 6 }}>
          <div className="grid grid-cols-[1fr_96px] gap-2">
            <label className="grid gap-1">
              <span className="control-label">Measured, reference nm pairs</span>
              <textarea
                className="field min-h-16 resize-y"
                value={calibrationPairsText}
                onChange={(event) => {
                  const nextText = event.target.value;
                  const nextPairs = parseCalibrationPairs(nextText);
                  setCalibrationPairsText(nextText);
                  updateCalibrationOperation(nextPairs, calibrationOrder);
                }}
              />
            </label>
            <label className="grid gap-1">
              <span className="control-label">Order</span>
              <select
                className="field"
                value={calibrationOrder}
                onChange={(event) => {
                  const nextOrder = Number(event.target.value);
                  setCalibrationOrder(nextOrder);
                  updateCalibrationOperation(calibrationPairs, nextOrder);
                }}
              >
                <option value={1}>1</option>
                <option value={2}>2</option>
                <option value={3}>3</option>
              </select>
            </label>
          </div>
          <ToggleRow
            label="Wavelength calibration"
            hint="Fit measured/reference line pairs and remap the wavelength axis before analysis."
            checked={has("wavelength_calibration")}
            disabled={!calibrationReady}
            onChange={(checked) => toggleOperation(calibrationOperation(calibrationPairs, calibrationOrder), checked)}
          />
        </div>
        <ToggleRow
          label="ALS baseline"
          hint="Asymmetric Least Squares (Eilers-Boelens). lambda=1e5 (smoothness), p=0.01 (asymmetry). Larger lambda = smoother baseline; smaller p favors fitting below peaks."
          checked={has("baseline_als")}
          onChange={(checked) =>
            toggleOperation({ operation: "baseline_als", params: { lambda: 100000, p: 0.01 } }, checked)
          }
        />
        <ToggleRow
          label="Max normalize"
          hint="Divide intensity by the global maximum so the peak equals 1. Use for overlaying spectra with different absolute scales."
          checked={has("normalize")}
          onChange={(checked) => toggleOperation({ operation: "normalize", params: { method: "max" } }, checked)}
        />
        <ToggleRow
          label="Spike removal"
          hint="Median-filter outliers > 6 sigma above local trend. Removes cosmic-ray spikes without smoothing real lines."
          checked={has("remove_spikes")}
          onChange={(checked) =>
            toggleOperation({ operation: "remove_spikes", params: { window_points: 5, threshold_sigma: 6 } }, checked)
          }
        />
        <ToggleRow
          label="Savitzky-Golay"
          hint="Polynomial smoothing (window=9 points, order=2). Useful for noise but can broaden narrow lines - don't apply before precise FWHM extraction."
          checked={has("smooth_savgol")}
          onChange={(checked) =>
            toggleOperation({ operation: "smooth_savgol", params: { window_points: 9, polyorder: 2 } }, checked)
          }
        />
        {has("smooth_savgol") ? (
          <div className="border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" style={{ borderRadius: 6 }}>
            Smoothing can distort narrow line shapes.
          </div>
        ) : null}
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <Wand2 className="h-4 w-4 text-plasma" />
          {operations.length} operation{operations.length === 1 ? "" : "s"} in recipe
        </div>
      </div>
    </section>
  );
}

function ToggleRow({
  label,
  checked,
  onChange,
  hint,
  disabled = false,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-center justify-between gap-3 border border-line bg-white px-3 py-2 text-sm studio-hover ${
        disabled ? "opacity-50" : "hover:bg-slate-50"
      }`}
      style={{ borderRadius: 6 }}
      title={hint}
    >
      <span className="flex items-center">
        {label}
        {hint ? <span className="hint-pill" aria-label={hint}>?</span> : null}
      </span>
      <input
        type="checkbox"
        className="h-4 w-4 accent-teal-700"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  );
}

function calibrationOperation(
  pairs: Array<{ measured_nm: number; reference_nm: number }>,
  order: number,
): PreprocessingOperation {
  return {
    operation: "wavelength_calibration",
    params: {
      pairs,
      order,
    },
  };
}

function parseCalibrationPairs(text: string) {
  return text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line
        .split(/[,;\s]+/)
        .map((part) => Number(part))
        .filter((value) => Number.isFinite(value));
      if (parts.length < 2) return null;
      return { measured_nm: parts[0], reference_nm: parts[1] };
    })
    .filter((pair): pair is { measured_nm: number; reference_nm: number } => pair !== null);
}
