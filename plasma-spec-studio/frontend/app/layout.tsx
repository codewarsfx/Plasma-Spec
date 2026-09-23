import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { BarChart3, Database, FlaskConical, Layers, Microscope, MonitorDown, Upload } from "lucide-react";
import { AuthButton } from "@/components/AuthButton";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ToastHost } from "@/components/Toast";
import "./globals.css";

export const metadata: Metadata = {
  title: "PlasmaSpec Studio",
  description: "Low-temperature plasma OES fitting platform",
};

// /analysis has been folded into /studio (workstation supersedes it).
// /spectra, /batch, /dashboard, /recipes remain as standalone focused workflows.
const nav = [
  { href: "/", label: "Project", icon: FlaskConical },
  { href: "/#download", label: "Download", icon: MonitorDown },
  { href: "/studio", label: "Studio", icon: Microscope },
  { href: "/spectra", label: "Spectra", icon: Upload },
  { href: "/batch", label: "Batch", icon: Layers },
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/recipes", label: "Recipes", icon: Database },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (() => {
                try {
                  const stored = localStorage.getItem("plasma-spec-theme");
                  const theme = stored === "dark" || stored === "light"
                    ? stored
                    : (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
                  document.documentElement.dataset.theme = theme;
                  document.documentElement.classList.toggle("dark", theme === "dark");
                } catch {
                  document.documentElement.dataset.theme = "light";
                }
              })();
            `,
          }}
        />
      </head>
      <body>
        <div className="min-h-screen">
          <header className="sticky top-0 z-50 border-b border-line bg-panel/90 backdrop-blur-xl">
            <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-4 px-4 py-2">
              <Link href="/" className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center border border-teal-200 bg-teal-50 text-teal-900" style={{ borderRadius: 8 }}>
                  <FlaskConical className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-base font-semibold text-ink">PlasmaSpec Studio</div>
                  <div className="hidden text-xs text-slate-500 sm:block">OES fitting for low-temperature plasma</div>
                </div>
              </Link>
              <nav className="hidden flex-wrap gap-1 md:flex">
                {nav.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="inline-flex h-9 items-center gap-2 px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                    style={{ borderRadius: 6 }}
                  >
                    <item.icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                ))}
              </nav>
              <div className="flex items-center gap-2">
                <AuthButton />
                <ThemeToggle />
              </div>
            </div>
          </header>
          <main className="w-full">{children}</main>
          <ToastHost />
        </div>
      </body>
    </html>
  );
}
