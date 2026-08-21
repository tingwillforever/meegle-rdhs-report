import { cadenceFromUrl, periodFromUrl } from "@/lib/rdhs/http";
import { createSnapshotRepository } from "@/lib/rdhs/storage";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const cadence = cadenceFromUrl(url);
    const period = periodFromUrl(url, cadence);
    const record = await (await createSnapshotRepository()).getCurrent(cadence, period);
    if (!record) return Response.json({ error: "该周期暂无有效报告" }, { status: 404 });
    return Response.json({ record });
  } catch (error) {
    const message = error instanceof Error ? error.message : "报告读取失败";
    return Response.json({ error: message }, { status: 400 });
  }
}
