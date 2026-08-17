import demoJuly from "@/data/demo-monthly-2026-07.json";
import demoAugust from "@/data/demo-monthly-2026-08.json";
import { ReportDashboard } from "@/app/components/report-dashboard";
import type { RdhsSnapshot } from "@/lib/rdhs/types";
import { validateSnapshot } from "@/lib/rdhs/validate";

export const dynamic = "force-dynamic";

export default async function Home() {
  let snapshots: RdhsSnapshot[] = [];
  let dataMode: "live" | "preview" = "preview";

  try {
    const { D1SnapshotRepository } = await import("@/lib/rdhs/d1-repository");
    const repository = new D1SnapshotRepository();
    const [monthly, weekly] = await Promise.all([
      repository.listCurrent("monthly"),
      repository.listCurrent("weekly"),
    ]);
    snapshots = [...monthly, ...weekly].map((record) => record.snapshot);
    dataMode = snapshots.length > 0 ? "live" : "preview";
  } catch {
    // Local preview and first deployment remain useful before D1 receives its first snapshot.
  }

  if (snapshots.length === 0) {
    snapshots = [validateSnapshot(demoJuly), validateSnapshot(demoAugust)];
  }

  return <ReportDashboard initialSnapshots={snapshots} dataMode={dataMode} />;
}
