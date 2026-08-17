import { env } from "cloudflare:workers";

import { D1SnapshotRepository } from "@/lib/rdhs/d1-repository";
import { authorizeBearer } from "@/lib/rdhs/http";
import { SnapshotService } from "@/lib/rdhs/repository";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const expectedToken = String(env.RDHS_INGEST_TOKEN ?? "");
  if (!authorizeBearer(request.headers.get("authorization"), expectedToken)) {
    return Response.json({ error: "未授权的快照写入" }, { status: 401 });
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "请求体必须是 JSON" }, { status: 400 });
  }

  const repository = new D1SnapshotRepository();
  try {
    const result = await new SnapshotService(repository).ingest(payload);
    return Response.json(result, { status: result.created ? 201 : 200 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "快照写入失败";
    try {
      await repository.recordFailure(payload, message);
    } catch {
      // Keep the original validation or persistence error as the API response.
    }
    const isValidationError = !message.includes("D1") && !message.includes("SQL");
    return Response.json({ error: message }, { status: isValidationError ? 422 : 500 });
  }
}

