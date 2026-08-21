import { cadenceFromUrl } from "@/lib/rdhs/http";
import { createSnapshotRepository } from "@/lib/rdhs/storage";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const cadence = cadenceFromUrl(new URL(request.url));
    const records = await (await createSnapshotRepository()).listPeriods(cadence);
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
