import type { SnapshotRepository } from "./repository.ts";
import { isSQLiteStorage } from "./runtime.ts";

export { getRuntimeSetting, isSQLiteStorage } from "./runtime.ts";

let cachedSQLiteRepository: SnapshotRepository | null = null;
let cachedSQLitePath: string | null = null;

export async function createSnapshotRepository(): Promise<SnapshotRepository> {
  if (isSQLiteStorage()) {
    const { SQLiteSnapshotRepository } = await import("./sqlite-repository.ts");
    const databasePath = process.env.RDHS_DB_PATH || "./runtime/rdhs.sqlite";
    if (!cachedSQLiteRepository || cachedSQLitePath !== databasePath) {
      cachedSQLiteRepository = new SQLiteSnapshotRepository(databasePath);
      cachedSQLitePath = databasePath;
    }
    return cachedSQLiteRepository;
  }

  const { D1SnapshotRepository } = await import("./d1-repository.ts");
  return new D1SnapshotRepository();
}
