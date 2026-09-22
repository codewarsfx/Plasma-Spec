"use client";

import { useEffect, useMemo, useState } from "react";

export type ThemePalette = {
  theme: "light" | "dark";
  paper: string;
  plot: string;
  grid: string;
  text: string;
  muted: string;
  plasma: string;
  fit: string;
  residual: string;
};

export function useThemePalette(): ThemePalette {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const sync = () => {
      setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
    };
    sync();
    window.addEventListener("plasma-spec-themechange", sync);
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => {
      window.removeEventListener("plasma-spec-themechange", sync);
      observer.disconnect();
    };
  }, []);

  return useMemo(
    () => theme === "dark"
      ? {
          theme,
          paper: "#111827",
          plot: "#0f172a",
          grid: "#334155",
          text: "#e2e8f0",
          muted: "#94a3b8",
          plasma: "#60a5fa",
          fit: "#818cf8",
          residual: "#fb7185",
        }
      : {
          theme,
          paper: "#ffffff",
          plot: "#ffffff",
          grid: "#e6ebf0",
          text: "#172026",
          muted: "#475569",
          plasma: "#0066ff",
          fit: "#4338ca",
          residual: "#be123c",
        },
    [theme],
  );
}
