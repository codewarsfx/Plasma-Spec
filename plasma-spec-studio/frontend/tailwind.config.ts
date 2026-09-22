import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        panel: "rgb(var(--color-panel) / <alpha-value>)",
        line: "rgb(var(--color-line) / <alpha-value>)",
        plasma: "rgb(var(--color-plasma) / <alpha-value>)",
        caution: "rgb(var(--color-caution) / <alpha-value>)",
        fit: "rgb(var(--color-fit) / <alpha-value>)",
        residual: "rgb(var(--color-residual) / <alpha-value>)"
      },
      boxShadow: {
        "thin": "0 1px 2px rgba(15, 23, 42, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
