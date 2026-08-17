import { buildMonthlyTrend } from "@/lib/rdhs/aggregate";
import { D1SnapshotRepository } from "@/lib/rdhs/d1-repository";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const records = await new D1SnapshotRepository().listCurrent("monthly");
    return Response.json({ trend: buildMonthlyTrend(records.map((record) => record.snapshot)) });
  } catch (error) {
    const message = error instanceof Error ? error.message : "趋势读取失败";
    return Response.json({ error: message }, { status: 500 });
  }
}

