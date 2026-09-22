"""Per-result HTML / PDF report generator.

Produces a single self-contained file per result that captures:

- preprocessing pipeline (what was applied before the fit)
- fit model + free parameters with stderr + units
- intermediate-value chain (e.g. Lorentz / vdW / Stark FWHM -> n_e for the
  electron-density workflow; instrument FWHM + Trot + Tvib for molecular)
- embedded plot (measured + fit + residuals)
- fit quality classification + warnings
- calibration provenance and assumptions

The HTML report is self-contained (PNG embedded as base64) so the user can
email it, paste it into a notebook, or print to PDF from a browser. The PDF
path uses matplotlib's PdfPages backend - lighter than WeasyPrint, and we
already depend on matplotlib for plot exports.
"""

from __future__ import annotations

import base64
import html
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.constants import SOFTWARE_NAME, SOFTWARE_VERSION
from app.services.spectrum_service import EXPORTS_DIR, save_export_record


def export_report_html(result: dict[str, Any]) -> dict[str, Any]:
    """Render the result as a self-contained HTML report and save it."""

    export_id = str(uuid4())
    path = EXPORTS_DIR / f"{export_id}_report.html"
    html_text = _render_html_report(result)
    path.write_text(html_text, encoding="utf-8")
    save_export_record(export_id, path, "html")
    return {"export_id": export_id, "path": str(path), "kind": "html"}


def export_report_pdf(result: dict[str, Any]) -> dict[str, Any]:
    """Render the result as a one-page PDF using matplotlib's PdfPages backend."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    export_id = str(uuid4())
    path = EXPORTS_DIR / f"{export_id}_report.pdf"

    measured = result.get("measured_curve") or []
    fit_curve = result.get("fit_curve") or []
    residual = result.get("residual_curve") or []

    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(8.5, 11))  # US letter
        # Layout: title at top, plot in upper half, parameter table in lower half
        gs = fig.add_gridspec(
            4, 1, height_ratios=[1, 5, 2, 6], hspace=0.5, top=0.95, bottom=0.05
        )

        title_ax = fig.add_subplot(gs[0])
        title_ax.axis("off")
        title_ax.text(
            0.0,
            0.5,
            _report_title(result),
            fontsize=14,
            fontweight="bold",
            family="sans-serif",
        )
        title_ax.text(
            0.0,
            -0.5,
            _report_subtitle(result),
            fontsize=9,
            color="#475569",
            family="sans-serif",
        )

        plot_ax = fig.add_subplot(gs[1])
        if measured:
            plot_ax.plot(
                [p["wavelength_nm"] for p in measured],
                [p["value"] for p in measured],
                color="#0f766e",
                lw=1.6,
                label="Measured",
            )
        if fit_curve:
            plot_ax.plot(
                [p["wavelength_nm"] for p in fit_curve],
                [p["value"] for p in fit_curve],
                color="#4338ca",
                lw=1.6,
                label="Fit",
            )
        plot_ax.set_xlabel("Wavelength (nm)")
        plot_ax.set_ylabel("Intensity (a.u.)")
        plot_ax.legend(loc="best", fontsize=8)
        plot_ax.grid(True, alpha=0.3)

        residual_ax = fig.add_subplot(gs[2])
        if residual:
            residual_ax.plot(
                [p["wavelength_nm"] for p in residual],
                [p["value"] for p in residual],
                color="#be123c",
                lw=1.0,
            )
            residual_ax.axhline(0.0, color="#94a3b8", lw=0.8)
        residual_ax.set_xlabel("Wavelength (nm)")
        residual_ax.set_ylabel("Residual")
        residual_ax.grid(True, alpha=0.3)

        table_ax = fig.add_subplot(gs[3])
        table_ax.axis("off")
        text_lines = _pdf_table_text(result)
        table_ax.text(
            0.0,
            1.0,
            text_lines,
            fontsize=8,
            family="monospace",
            verticalalignment="top",
        )

        pdf.savefig(fig)
        plt.close(fig)

        metadata = pdf.infodict()
        metadata["Title"] = _report_title(result)
        metadata["Author"] = SOFTWARE_NAME
        metadata["Producer"] = f"{SOFTWARE_NAME} {SOFTWARE_VERSION}"
        metadata["CreationDate"] = datetime.now(timezone.utc)

    save_export_record(export_id, path, "pdf")
    return {"export_id": export_id, "path": str(path), "kind": "pdf"}


# --- HTML rendering --------------------------------------------------------


def _render_html_report(result: dict[str, Any]) -> str:
    title = _report_title(result)
    subtitle = _report_subtitle(result)
    plot_data_uri = _plot_png_data_uri(result)
    quality = result.get("fit_quality", "")
    quality_class = {
        "good": "ok",
        "warning": "warn",
        "bad": "bad",
    }.get(quality, "")

    sections: list[str] = []
    sections.append(_html_preprocessing(result))
    sections.append(_html_parameters(result))
    sections.append(_html_metrics(result))
    sections.append(_html_intermediate_values(result))
    sections.append(_html_warnings(result))
    sections.append(_html_provenance(result))

    sections_html = "\n".join(s for s in sections if s)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 24px;
    color: #172026;
    background: #ffffff;
    max-width: 960px;
  }}
  h1 {{ font-size: 20px; margin: 0 0 4px 0; }}
  h2 {{ font-size: 14px; margin: 22px 0 8px 0; color: #475569; text-transform: uppercase; letter-spacing: 0.04em; }}
  .meta {{ font-size: 12px; color: #64748b; margin-bottom: 18px; }}
  .quality {{
    display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 600;
    border: 1px solid #d7dde3;
  }}
  .quality.ok {{ background: #f0fdfa; color: #115e59; border-color: #99f6e4; }}
  .quality.warn {{ background: #fffbeb; color: #78350f; border-color: #fde68a; }}
  .quality.bad {{ background: #fef2f2; color: #991b1b; border-color: #fecaca; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th, td {{ border-bottom: 1px solid #e2e8f0; padding: 6px 10px; text-align: left; }}
  th {{ background: #f8fafc; color: #475569; font-weight: 600; }}
  td.num {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; text-align: right; }}
  ul.warnings {{ padding-left: 20px; }}
  ul.warnings li {{ color: #78350f; background: #fffbeb; border-left: 3px solid #f59e0b; padding: 4px 8px; margin: 4px 0; list-style: none; border-radius: 3px; }}
  .plot {{ margin: 10px 0; }}
  .plot img {{ max-width: 100%; height: auto; border: 1px solid #e2e8f0; border-radius: 6px; }}
  footer {{ margin-top: 30px; font-size: 11px; color: #94a3b8; }}
</style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="meta">{html.escape(subtitle)} &middot; <span class="quality {quality_class}">{html.escape(quality)}</span></div>

  <div class="plot">
    {f'<img src="{plot_data_uri}" alt="fit overlay">' if plot_data_uri else '<em>No plot available.</em>'}
  </div>

  {sections_html}

  <footer>
    Generated by {html.escape(SOFTWARE_NAME)} {html.escape(SOFTWARE_VERSION)}
    on {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}.
  </footer>
</body>
</html>
"""


def _report_title(result: dict[str, Any]) -> str:
    diagnostic = result.get("diagnostic") or result.get("recipe_kind") or "Analysis"
    filename = result.get("filename") or "(no filename)"
    return f"{_pretty_diagnostic(diagnostic)} - {filename}"


def _report_subtitle(result: dict[str, Any]) -> str:
    parts: list[str] = []
    window = result.get("window_nm")
    if isinstance(window, (list, tuple)) and len(window) == 2 and None not in window:
        parts.append(f"window {window[0]:.1f}-{window[1]:.1f} nm")
    if result.get("Tg_K") is not None:
        parts.append(f"Tg = {result['Tg_K']:.0f} K")
    if result.get("species"):
        parts.append(f"species {result['species']}")
    if result.get("database_source"):
        parts.append(f"db {result['database_source']}")
    return " · ".join(parts) if parts else ""


def _pretty_diagnostic(diagnostic: str) -> str:
    mapping = {
        "peak_list": "Wavelength-list peak analysis",
        "electron_density": "Electron density (Stark / Gigosos)",
        "oh_ax": "OH(A-X) molecular fit",
        "n2_cb": "N2(C-B) molecular fit",
        "hbeta_voigt": "H-beta Voigt fit",
        "peak_area": "Peak area",
        "line_identification": "Line identification",
    }
    if diagnostic in mapping:
        return mapping[diagnostic]
    if diagnostic.startswith("molecular_"):
        return f"Molecular fit ({diagnostic.split('_', 1)[1].upper()})"
    return diagnostic.replace("_", " ").title()


def _plot_png_data_uri(result: dict[str, Any]) -> str | None:
    """Render the measured/fit/residual overlay as PNG, embedded as base64."""

    measured = result.get("measured_curve") or []
    fit_curve = result.get("fit_curve") or []
    residual = result.get("residual_curve") or []
    if not measured and not fit_curve:
        return None

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        2, 1, figsize=(8, 4.2), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    if measured:
        axes[0].plot(
            [p["wavelength_nm"] for p in measured],
            [p["value"] for p in measured],
            color="#0f766e",
            lw=1.6,
            label="Measured",
        )
    if fit_curve:
        axes[0].plot(
            [p["wavelength_nm"] for p in fit_curve],
            [p["value"] for p in fit_curve],
            color="#4338ca",
            lw=1.6,
            label="Fit",
        )
    axes[0].set_ylabel("Intensity (a.u.)")
    axes[0].legend(loc="best", fontsize=9)
    axes[0].grid(True, alpha=0.3)

    if residual:
        axes[1].plot(
            [p["wavelength_nm"] for p in residual],
            [p["value"] for p in residual],
            color="#be123c",
            lw=1.0,
        )
        axes[1].axhline(0.0, color="#94a3b8", lw=0.8)
    axes[1].set_xlabel("Wavelength (nm)")
    axes[1].set_ylabel("Residual")
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# --- HTML sections ---------------------------------------------------------


def _html_preprocessing(result: dict[str, Any]) -> str:
    history = result.get("preprocessing_history") or []
    if not history:
        return (
            "<h2>Preprocessing</h2>"
            "<p style='font-size:12px;color:#64748b;'>No preprocessing applied (raw spectrum).</p>"
        )
    rows = []
    for entry in history:
        op = html.escape(str(entry.get("operation", "")))
        params = entry.get("params") or {}
        formatted = ", ".join(
            f"{html.escape(k)} = {html.escape(_format_value(v))}" for k, v in params.items()
        )
        rows.append(f"<tr><td>{op}</td><td>{formatted}</td></tr>")
    body = "".join(rows)
    return f"""
    <h2>Preprocessing pipeline</h2>
    <table><thead><tr><th>Operation</th><th>Parameters</th></tr></thead>
    <tbody>{body}</tbody></table>
    """


def _html_parameters(result: dict[str, Any]) -> str:
    params = result.get("parameters") or {}
    stderrs = result.get("parameter_stderr") or {}
    if not params:
        return ""
    rows: list[str] = []
    for key, value in params.items():
        if value is None:
            continue
        stderr = stderrs.get(key) if isinstance(stderrs, dict) else None
        stderr_str = f"± {_format_value(stderr)}" if isinstance(stderr, (int, float)) else ""
        rows.append(
            f"<tr><td>{html.escape(str(key))}</td>"
            f"<td class='num'>{_format_value(value)}</td>"
            f"<td>{stderr_str}</td></tr>"
        )
    body = "".join(rows)
    return f"""
    <h2>Fit parameters</h2>
    <table><thead><tr><th>Name</th><th>Value</th><th>Stderr</th></tr></thead>
    <tbody>{body}</tbody></table>
    """


def _html_metrics(result: dict[str, Any]) -> str:
    metrics = result.get("metrics") or {}
    if not metrics:
        return ""
    rows = []
    for key, value in metrics.items():
        if value is None:
            continue
        rows.append(
            f"<tr><td>{html.escape(str(key))}</td>"
            f"<td class='num'>{_format_value(value)}</td></tr>"
        )
    if not rows:
        return ""
    return f"""
    <h2>Fit quality</h2>
    <table><thead><tr><th>Metric</th><th>Value</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table>
    """


def _html_intermediate_values(result: dict[str, Any]) -> str:
    parts: list[str] = []

    # Electron density: surface the full width-chain
    breakdown = result.get("fwhm_breakdown_nm")
    ed = result.get("electron_density")
    if breakdown or ed:
        rows: list[str] = []
        if breakdown:
            for key, value in breakdown.items():
                if value is None:
                    continue
                rows.append(
                    f"<tr><td>{html.escape(str(key))}</td>"
                    f"<td class='num'>{_format_value(value)} nm</td></tr>"
                )
        if isinstance(ed, dict):
            ne = ed.get("electron_density_cm3")
            if ne is not None:
                rows.append(
                    f"<tr><td><strong>electron_density_cm3</strong></td>"
                    f"<td class='num'><strong>{_format_value(ne)}</strong></td></tr>"
                )
            ci = ed.get("confidence_interval_95") or {}
            if ci.get("lower_cm3") is not None and ci.get("upper_cm3") is not None:
                rows.append(
                    f"<tr><td>n_e 95% CI</td>"
                    f"<td class='num'>{_format_value(ci['lower_cm3'])} - {_format_value(ci['upper_cm3'])} cm⁻³</td></tr>"
                )
        if rows:
            parts.append(
                f"""
                <h2>Width breakdown &amp; electron density</h2>
                <table><thead><tr><th>Field</th><th>Value</th></tr></thead>
                <tbody>{''.join(rows)}</tbody></table>
                """
            )

    # Molecular: surface instrument widths
    instrument_widths = result.get("instrument_widths_nm")
    if isinstance(instrument_widths, dict) and instrument_widths:
        rows = []
        for key, value in instrument_widths.items():
            if value is None:
                continue
            rows.append(
                f"<tr><td>{html.escape(str(key))}</td>"
                f"<td class='num'>{_format_value(value)} nm</td></tr>"
            )
        if rows:
            parts.append(
                f"""
                <h2>Instrument widths</h2>
                <table><thead><tr><th>Field</th><th>Value</th></tr></thead>
                <tbody>{''.join(rows)}</tbody></table>
                """
            )

    return "\n".join(parts)


def _html_warnings(result: dict[str, Any]) -> str:
    warnings = result.get("warnings") or []
    if not warnings:
        return ""
    items = "".join(f"<li>{html.escape(str(w))}</li>" for w in warnings)
    return f"""
    <h2>Warnings &amp; assumptions</h2>
    <ul class="warnings">{items}</ul>
    """


def _html_provenance(result: dict[str, Any]) -> str:
    rows: list[str] = []
    metadata = result.get("metadata") or {}
    for key, value in metadata.items():
        if value is None or value == "":
            continue
        rows.append(
            f"<tr><td>metadata_{html.escape(str(key))}</td>"
            f"<td>{html.escape(_format_value(value))}</td></tr>"
        )
    if result.get("database_source"):
        rows.append(
            f"<tr><td>database_source</td>"
            f"<td>{html.escape(str(result['database_source']))}</td></tr>"
        )
    if result.get("calibration_source"):
        rows.append(
            f"<tr><td>calibration_source</td>"
            f"<td>{html.escape(str(result['calibration_source']))}</td></tr>"
        )
    if result.get("timestamp"):
        rows.append(
            f"<tr><td>timestamp</td>"
            f"<td>{html.escape(str(result['timestamp']))}</td></tr>"
        )
    if not rows:
        return ""
    return f"""
    <h2>Provenance</h2>
    <table><thead><tr><th>Field</th><th>Value</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table>
    """


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return ""
        if abs(value) >= 1e5 or (0 < abs(value) < 1e-3):
            return f"{value:.4e}"
        return f"{value:.6g}"
    return str(value)


# --- PDF text table --------------------------------------------------------


def _pdf_table_text(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Parameters")
    lines.append("-" * 48)
    params = result.get("parameters") or {}
    stderrs = result.get("parameter_stderr") or {}
    for key, value in params.items():
        if value is None:
            continue
        stderr = stderrs.get(key) if isinstance(stderrs, dict) else None
        stderr_str = f"  +/- {_format_value(stderr)}" if isinstance(stderr, (int, float)) else ""
        lines.append(f"  {key:<28s} {_format_value(value):>14s}{stderr_str}")

    lines.append("")
    lines.append("Fit quality")
    lines.append("-" * 48)
    metrics = result.get("metrics") or {}
    for key, value in metrics.items():
        if value is None:
            continue
        lines.append(f"  {key:<28s} {_format_value(value):>14s}")

    breakdown = result.get("fwhm_breakdown_nm") or {}
    if breakdown:
        lines.append("")
        lines.append("Width breakdown (nm)")
        lines.append("-" * 48)
        for key, value in breakdown.items():
            if value is None:
                continue
            lines.append(f"  {key:<28s} {_format_value(value):>14s}")

    ed = result.get("electron_density") or {}
    if isinstance(ed, dict) and ed.get("electron_density_cm3") is not None:
        lines.append("")
        lines.append("Electron density")
        lines.append("-" * 48)
        lines.append(f"  n_e (cm^-3)                {_format_value(ed['electron_density_cm3']):>14s}")
        ci = ed.get("confidence_interval_95") or {}
        if ci.get("lower_cm3") and ci.get("upper_cm3"):
            lines.append(
                f"  95% CI                     "
                f"{_format_value(ci['lower_cm3'])} - {_format_value(ci['upper_cm3'])}"
            )

    warnings = result.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("Warnings")
        lines.append("-" * 48)
        for w in warnings:
            lines.append(f"  * {w}")

    return "\n".join(lines)
