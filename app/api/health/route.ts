import { createSnapshotRepository, isSQLiteStorage } from "../../../lib/rdhs/storage.ts";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await (await createSnapshotRepository()).listCurrent("monthly");
    return Response.json({ status: "ok", storage: isSQLiteStorage() ? "sqlite" : "d1" });
  } catch {
    return Response.json({ status: "error" }, { status: 503 });
  }
}
