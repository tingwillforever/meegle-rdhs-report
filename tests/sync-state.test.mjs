import assert from "node:assert/strict";
import test from "node:test";

import { MySQLSyncStateRepository } from "../lib/rdhs/mysql-repository.ts";

test("MySQL sync state stores and loads a monthly baseline", async () => {
  const calls = [];
  const pool = {
    async execute(sql, parameters) {
      calls.push({ sql, parameters });
      if (/^\s*SELECT/.test(sql)) {
        return [[{
          period_key: "2026-07",
          payload_json: JSON.stringify({ rows: [["product-a", 60]] }),
          metadata_json: JSON.stringify({ chart_id: "chart-previous", fetched_at: "2026-08-01T09:00:00+08:00" }),
          updated_at: "2026-08-01T01:00:00.000Z",
        }], []];
      }
      return [{ affectedRows: 1 }, []];
    },
  };
  const repository = new MySQLSyncStateRepository(pool);

  await repository.putBaseline({
    periodKey: "2026-07",
    payload: { rows: [["product-a", 60]] },
    metadata: { chart_id: "chart-previous", fetched_at: "2026-08-01T09:00:00+08:00" },
  });
  const baseline = await repository.getBaseline("2026-07");

  assert.deepEqual(baseline?.payload, { rows: [["product-a", 60]] });
  assert.equal(baseline?.metadata.chart_id, "chart-previous");
  assert.match(calls[0].sql, /ON DUPLICATE KEY UPDATE/);
});

test("MySQL sync lease replaces an expired owner under a transaction", async () => {
  const calls = [];
  const connection = {
    async beginTransaction() { calls.push("begin"); },
    async execute(sql, parameters) {
      calls.push({ sql, parameters });
      if (/SELECT owner_id/.test(sql)) {
        assert.match(sql, /FOR UPDATE/);
        return [[{ owner_id: "old-owner", expires_at: new Date(0) }], []];
      }
      return [{ affectedRows: 1 }, []];
    },
    async commit() { calls.push("commit"); },
    async rollback() { calls.push("rollback"); },
    release() { calls.push("release"); },
  };
  const repository = new MySQLSyncStateRepository({
    async getConnection() { return connection; },
  });

  const result = await repository.acquireLease({
    name: "report-sync",
    owner: "new-owner",
    ttlSeconds: 1800,
  });

  assert.equal(result.acquired, true);
  assert.equal(result.owner, "new-owner");
  assert.ok(calls.some((call) => typeof call === "object" && /UPDATE rdhs_sync_leases/.test(call.sql)));
  assert.ok(calls.includes("commit"));
  assert.ok(calls.includes("release"));
});
