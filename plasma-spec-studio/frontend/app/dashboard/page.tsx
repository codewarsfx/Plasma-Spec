import { DashboardComparison } from "@/components/DashboardComparison";
import { LegacyPageShell } from "@/components/LegacyPageShell";

export default function DashboardPage() {
  return (
    <LegacyPageShell
      title="Dashboard"
      description="Compare fit outputs against metadata: frequency, cycles, burst period, gas, replicate."
    >
      <DashboardComparison />
    </LegacyPageShell>
  );
}
