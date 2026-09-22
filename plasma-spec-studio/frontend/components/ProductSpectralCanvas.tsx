"use client";

import { useEffect, useRef } from "react";

const spectralLines = [
  { wavelength: 309, label: "OH", strength: 0.76, color: "rgba(96, 211, 255, 0.95)" },
  { wavelength: 337, label: "N2", strength: 0.92, color: "rgba(0, 102, 255, 1)" },
  { wavelength: 391, label: "N2+", strength: 0.82, color: "rgba(148, 92, 255, 0.95)" },
  { wavelength: 656, label: "H-alpha", strength: 0.86, color: "rgba(255, 98, 112, 0.92)" },
  { wavelength: 777, label: "O I", strength: 0.64, color: "rgba(255, 183, 77, 0.9)" },
  { wavelength: 844, label: "O I", strength: 0.58, color: "rgba(255, 209, 102, 0.9)" },
];

function xForWavelength(width: number, wavelength: number) {
  const min = 280;
  const max = 900;
  return ((wavelength - min) / (max - min)) * width;
}

export function ProductSpectralCanvas() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const pointerRef = useRef({ x: 0.62, y: 0.34 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const context = canvas.getContext("2d");
    if (!context) return;

    let frame = 0;
    let animationId = 0;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.floor(rect.width * ratio));
      canvas.height = Math.max(1, Math.floor(rect.height * ratio));
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const handlePointerMove = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointerRef.current = {
        x: (event.clientX - rect.left) / Math.max(rect.width, 1),
        y: (event.clientY - rect.top) / Math.max(rect.height, 1),
      };
    };

    const draw = () => {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      frame += 1;

      context.clearRect(0, 0, width, height);
      context.fillStyle = "#07111f";
      context.fillRect(0, 0, width, height);

      const gridAlpha = 0.12;
      context.strokeStyle = `rgba(196, 211, 231, ${gridAlpha})`;
      context.lineWidth = 1;
      for (let x = 0; x <= width; x += 72) {
        context.beginPath();
        context.moveTo(x, 0);
        context.lineTo(x, height);
        context.stroke();
      }
      for (let y = 0; y <= height; y += 54) {
        context.beginPath();
        context.moveTo(0, y);
        context.lineTo(width, y);
        context.stroke();
      }

      const pointer = pointerRef.current;
      const baseline = height * 0.74;
      const amplitude = height * 0.18;

      context.beginPath();
      for (let x = 0; x <= width; x += 2) {
        const phase = x / 42 + frame / 72;
        const low = Math.sin(phase) * 0.18 + Math.sin(x / 101 - frame / 96) * 0.12;
        const response = Math.exp(-Math.abs(x / width - pointer.x) * 3.2) * 0.18;
        let y = baseline - amplitude * (0.42 + low + response);
        for (const line of spectralLines) {
          const lx = xForWavelength(width, line.wavelength);
          const distance = Math.abs(x - lx);
          y -= Math.exp(-(distance * distance) / 58) * amplitude * line.strength * 0.95;
        }
        if (x === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.strokeStyle = "rgba(96, 211, 255, 0.78)";
      context.lineWidth = 2;
      context.shadowBlur = 12;
      context.shadowColor = "rgba(0, 102, 255, 0.55)";
      context.stroke();
      context.shadowBlur = 0;

      for (const line of spectralLines) {
        const x = xForWavelength(width, line.wavelength);
        const lineHeight = height * (0.34 + line.strength * 0.34);
        context.strokeStyle = line.color;
        context.lineWidth = 1.5;
        context.beginPath();
        context.moveTo(x, baseline);
        context.lineTo(x, baseline - lineHeight);
        context.stroke();

        context.fillStyle = line.color;
        context.font = "12px system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
        context.fillText(line.label, x + 6, Math.max(24, baseline - lineHeight - 8));
      }

      context.fillStyle = "rgba(226, 232, 240, 0.62)";
      context.font = "12px system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
      context.fillText("wavelength calibrated OES spectrum", 24, height - 30);
      context.fillText("NIST + molecular line data", width - 196, height - 30);

      animationId = window.requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener("resize", resize);
    canvas.addEventListener("pointermove", handlePointerMove);

    return () => {
      window.cancelAnimationFrame(animationId);
      window.removeEventListener("resize", resize);
      canvas.removeEventListener("pointermove", handlePointerMove);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden="true" />;
}
