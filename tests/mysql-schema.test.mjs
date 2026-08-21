import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("MySQL migration owns snapshots, baselines, and synchronization leases", async () => {
  const sql = await readFile(
    new URL("../database/mysql/001_initial.sql", import.meta.url),
    "utf8",
  );

  for (const table of [
    "rdhs_snapshots",
    "rdhs_business_line_metrics",
    "rdhs_product_metrics",
    "rdhs_ingest_failures",
    "rdhs_sync_baselines",
    "rdhs_sync_leases",
  ]) {
    assert.match(sql, new RegExp(`CREATE TABLE IF NOT EXISTS ${table}`));
  }
  assert.match(sql, /ENGINE=InnoDB/);
  assert.match(sql, /DEFAULT CHARSET=utf8mb4/);
});

test("mysql2 is a production dependency", async () => {
  const manifest = JSON.parse(
    await readFile(new URL("../package.json", import.meta.url), "utf8"),
  );
  assert.ok(manifest.dependencies.mysql2);
});
