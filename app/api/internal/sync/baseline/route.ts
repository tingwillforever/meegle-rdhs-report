import { authorizeBearer } from "../../../../../lib/rdhs/http.ts";
import {
  createSyncStateRepository,
  getRuntimeSetting,
} from "../../../../../lib/rdhs/storage.ts";

export const dynamic = "force-dynamic";

const PERIOD_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

function authorized(request: Request): boolean {
  return authorizeBearer(
    request.headers.get("authorization"),
    getRuntimeSetting("RDHS_INGEST_TOKEN"),
  );
}

export async function GET(request: Request) {
  if (!authorized(request)) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  const periodKey = new URL(request.url).searchParams.get("period") ?? "";
  if (!PERIOD_PATTERN.test(periodKey)) {
    return Response.json({ error: "period must use YYYY-MM" }, { status: 400 });
  }
  try {
    const baseline = await (await createSyncStateRepository()).getBaseline(periodKey);
    if (!baseline) return Response.json({ error: "baseline not found" }, { status: 404 });
    return Response.json(baseline);
  } catch {
    return Response.json({ error: "baseline storage unavailable" }, { status: 503 });
  }
}

export async function PUT(request: Request) {
  if (!authorized(request)) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "request body must be JSON" }, { status: 400 });
  }
  const input = typeof payload === "object" && payload !== null
    ? payload as Record<string, unknown>
    : {};
  const periodKey = typeof input.periodKey === "string" ? input.periodKey : "";
  const baselinePayload = input.payload;
  const metadata = input.metadata;
  if (!PERIOD_PATTERN.test(periodKey)) {
    return Response.json({ error: "periodKey must use YYYY-MM" }, { status: 400 });
  }
  if (typeof baselinePayload !== "object" || baselinePayload === null || Array.isArray(baselinePayload)) {
    return Response.json({ error: "payload must be a JSON object" }, { status: 400 });
  }
  if (typeof metadata !== "object" || metadata === null || Array.isArray(metadata)) {
    return Response.json({ error: "metadata must be a JSON object" }, { status: 400 });
  }
  try {
    await (await createSyncStateRepository()).putBaseline({
      periodKey,
      payload: baselinePayload as Record<string, unknown>,
      metadata: metadata as Record<string, unknown>,
    });
    return Response.json({ stored: true, periodKey });
  } catch {
    return Response.json({ error: "baseline storage unavailable" }, { status: 503 });
  }
}
