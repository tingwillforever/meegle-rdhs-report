import { authorizeBearer } from "../../../../../../lib/rdhs/http.ts";
import {
  createSyncStateRepository,
  getRuntimeSetting,
} from "../../../../../../lib/rdhs/storage.ts";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!authorizeBearer(
    request.headers.get("authorization"),
    getRuntimeSetting("RDHS_INGEST_TOKEN"),
  )) {
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
  const name = typeof input.name === "string" ? input.name : "";
  const owner = typeof input.owner === "string" ? input.owner : "";
  if (!/^[a-z0-9-]{1,64}$/.test(name) || !/^[A-Za-z0-9._:-]{1,128}$/.test(owner)) {
    return Response.json({ error: "invalid lease name or owner" }, { status: 400 });
  }
  try {
    const released = await (await createSyncStateRepository()).releaseLease(name, owner);
    return Response.json({ released });
  } catch {
    return Response.json({ error: "lease storage unavailable" }, { status: 503 });
  }
}
