import { BatchProcessor } from "@/components/BatchProcessor";
import { LegacyPageShell } from "@/components/LegacyPageShell";

export default function BatchPage() {
  return (
    <LegacyPageShell
      title="Batch"
      description="Run a saved recipe across many spectra and download long-form CSV/XLSX results."
    >
      <BatchProcessor />
    </LegacyPageShell>
  );
}
