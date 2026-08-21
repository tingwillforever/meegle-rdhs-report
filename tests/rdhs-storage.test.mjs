import assert from "node:assert/strict";
import test from "node:test";

import { SQLiteSnapshotRepository } from "../lib/rdhs/sqlite-repository.ts";
import { createSnapshotRepository, isSQLiteStorage } from "../lib/rdhs/storage.ts";

test("Kubernetes storage mode selects SQLite without requiring Cloudflare bindings", async () => {
  const previousStorage = process.env.RDHS_STORAGE;
  const previousPath = process.env.RDHS_DB_PATH;
  process.env.RDHS_STORAGE = "sqlite";
  process.env.RDHS_DB_PATH = ":memory:";
  try {
    assert.equal(isSQLiteStorage(), true);
    const repository = await createSnapshotRepository();
    assert.equal(repository instanceof SQLiteSnapshotRepository, true);
  } finally {
    if (previousStorage === undefined) delete process.env.RDHS_STORAGE;
    else process.env.RDHS_STORAGE = previousStorage;
    if (previousPath === undefined) delete process.env.RDHS_DB_PATH;
    else process.env.RDHS_DB_PATH = previousPath;
  }
});
