import { buildMonthlyTrend } from "@/lib/rdhs/aggregate";
import { createSnapshotRepository } from "@/lib/rdhs/storage";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const records = await (await createSnapshotRepository()).listCurrent("monthly");
    return Response.json({ trend: buildMonthlyTrend(records.map((record) => record.snapshot)) });
  } catch (error) {
    const message = error instanceof Error ? error.message : "趋势读取失败";
    return Response.json({ error: message }, { status: 500 });
  }
}
