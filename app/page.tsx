import { ReportDashboard } from "@/app/components/report-dashboard";
import type { RdhsSnapshot } from "@/lib/rdhs/types";
import { loadStaticSnapshots } from "@/lib/rdhs/static-snapshots";

export const dynamic = "force-dynamic";

type HomeProps = {
  searchParams?: Array<[string, string]> | Promise<Array<[string, string]>>;
};

export default async function Home({ searchParams }: HomeProps) {
  const params = new URLSearchParams(await searchParams ?? []);
  const requestedPeriod = params.get("period") ?? undefined;
  const requestedView = params.get("view") === "workbench" ? "workbench" : "bg";
  const requestedLine = requestedView === "bg" ? undefined : (params.get("line") ?? undefined);

  const snapshots: RdhsSnapshot[] = loadStaticSnapshots();
  const dataMode: "live" | "preview" = snapshots.length > 0 ? "live" : "preview";

  return (
    <ReportDashboard
      initialSnapshots={snapshots}
      dataMode={dataMode}
      initialPeriodKey={requestedPeriod}
      initialView={requestedView}
      initialLine={requestedLine}
    />
  );
}
