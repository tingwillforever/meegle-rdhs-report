import { D1SnapshotRepository } from "@/lib/rdhs/d1-repository";
import { cadenceFromUrl } from "@/lib/rdhs/http";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const cadence = cadenceFromUrl(new URL(request.url));
    const records = await new D1SnapshotRepository().listPeriods(cadence);
    return Response.json({
      periods: records.map((record) => ({
        periodKey: record.periodKey,
        asOf: record.snapshot.asOf,
        fetchedAt: record.snapshot.fetchedAt,
        version: record.version,
      })),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "周期读取失败";
    return Response.json({ error: message }, { status: 400 });
  }
}

