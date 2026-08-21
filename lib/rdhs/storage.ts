import type { SnapshotRepository } from "./repository.ts";
import { isMySQLStorage, isSQLiteStorage } from "./runtime.ts";

export { getRuntimeSetting, isMySQLStorage, isSQLiteStorage } from "./runtime.ts";

let cachedSQLiteRepository: SnapshotRepository | null = null;
let cachedSQLitePath: string | null = null;
let cachedMySQLRepository: SnapshotRepository | null = null;

export async function createSnapshotRepository(): Promise<SnapshotRepository> {
  if (isMySQLStorage()) {
    const { MySQLSnapshotRepository } = await import("./mysql-repository.ts");
    cachedMySQLRepository ??= new MySQLSnapshotRepository();
    return cachedMySQLRepository;
  }

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

export async function createSyncStateRepository() {
  if (!isMySQLStorage()) {
    throw new Error("sync state storage requires RDHS_STORAGE=mysql");
  }
  const { MySQLSyncStateRepository } = await import("./mysql-repository.ts");
  return new MySQLSyncStateRepository();
}
