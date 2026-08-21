import { authorizeBearer } from "@/lib/rdhs/http";
import {
  SnapshotService,
  supportsFailureRecording,
} from "@/lib/rdhs/repository";
import { createSnapshotRepository, getRuntimeSetting } from "@/lib/rdhs/storage";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const expectedToken = await getRuntimeSetting("RDHS_INGEST_TOKEN");
  if (!authorizeBearer(request.headers.get("authorization"), expectedToken)) {
    return Response.json({ error: "未授权的快照写入" }, { status: 401 });
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "请求体必须是 JSON" }, { status: 400 });
  }

  const repository = await createSnapshotRepository();
  try {
    const result = await new SnapshotService(repository).ingest(payload);
    return Response.json(result, { status: result.created ? 201 : 200 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "快照写入失败";
    try {
      if (supportsFailureRecording(repository)) {
        await repository.recordFailure(payload, message);
      }
    } catch {
      // Keep the original validation or persistence error as the API response.
    }
    const isValidationError = !message.includes("D1") && !message.includes("SQL");
    return Response.json({ error: message }, { status: isValidationError ? 422 : 500 });
  }
}
