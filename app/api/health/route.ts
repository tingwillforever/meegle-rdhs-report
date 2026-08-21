import {
  createSnapshotRepository,
  isMySQLStorage,
  isSQLiteStorage,
} from "../../../lib/rdhs/storage.ts";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await (await createSnapshotRepository()).listCurrent("monthly");
    const storage = isMySQLStorage() ? "mysql" : isSQLiteStorage() ? "sqlite" : "d1";
    return Response.json({ status: "ok", storage });
  } catch {
    return Response.json({ status: "error" }, { status: 503 });
  }
}
