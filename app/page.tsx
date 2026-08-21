import demoJuly from "@/data/demo-monthly-2026-07.json";
import demoAugust from "@/data/demo-monthly-2026-08.json";
import { ReportDashboard } from "@/app/components/report-dashboard";
import type { RdhsSnapshot } from "@/lib/rdhs/types";
import { allowPreviewFallback } from "@/lib/rdhs/runtime";
import { validateSnapshot } from "@/lib/rdhs/validate";

export const dynamic = "force-dynamic";

export default async function Home() {
  let snapshots: RdhsSnapshot[] = [];
  let dataMode: "live" | "preview" = "preview";

  try {
    const { createSnapshotRepository } = await import("@/lib/rdhs/storage");
    const repository = await createSnapshotRepository();
    const monthly = await repository.listCurrent("monthly");
    snapshots = monthly.map((record) => record.snapshot);
    dataMode = snapshots.length > 0 ? "live" : "preview";
  } catch {
    // Local preview and first deployment remain useful before D1 receives its first snapshot.
  }

  if (snapshots.length === 0) {
    if (!allowPreviewFallback()) {
      return (
        <main className="mx-auto flex min-h-screen max-w-2xl items-center px-6 py-16">
          <section className="rounded-xl border border-amber-200 bg-amber-50 p-8 text-amber-950">
            <h1 className="text-xl font-semibold">RDHS 数据暂不可用</h1>
            <p className="mt-3 text-sm leading-6">
              当前未找到有效月度快照。请等待同步任务完成，或联系运营管理员检查同步状态。
            </p>
          </section>
        </main>
      );
    }
    snapshots = [validateSnapshot(demoJuly), validateSnapshot(demoAugust)];
  }

  return <ReportDashboard initialSnapshots={snapshots} dataMode={dataMode} />;
}
