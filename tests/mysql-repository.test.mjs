import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { MySQLSnapshotRepository } from "../lib/rdhs/mysql-repository.ts";

const snapshot = JSON.parse(
  await readFile(new URL("../data/demo-monthly-2026-08.json", import.meta.url), "utf8"),
);

test("MySQL repository reads a validated current snapshot", async () => {
  const calls = [];
  const pool = {
    async execute(sql, parameters) {
      calls.push({ sql, parameters });
      return [[{
        id: "snapshot-1",
        cadence: "monthly",
        period_key: "2026-08",
        version: 2,
        is_current: 1,
        snapshot_json: JSON.stringify(snapshot),
      }], []];
    },
  };

  const repository = new MySQLSnapshotRepository(pool);
  const current = await repository.getCurrent("monthly", "2026-08");

  assert.equal(current?.id, "snapshot-1");
  assert.equal(current?.version, 2);
  assert.equal(current?.snapshot.source.sha256, snapshot.source.sha256);
  assert.match(calls[0].sql, /is_current = 1/);
  assert.deepEqual(calls[0].parameters, ["monthly", "2026-08"]);
});

test("MySQL repository writes a new snapshot atomically", async () => {
  const calls = [];
  const connection = {
    async beginTransaction() {
      calls.push("begin");
    },
    async execute(sql, parameters) {
      calls.push({ sql, parameters });
      if (/SELECT id, version/.test(sql)) return [[], []];
      if (/SELECT COALESCE\(MAX\(version\)/.test(sql)) {
        assert.match(sql, /FOR UPDATE/);
        return [[{ max_version: 0 }], []];
      }
      return [{ affectedRows: 1 }, []];
    },
    async commit() {
      calls.push("commit");
    },
    async rollback() {
      calls.push("rollback");
    },
    release() {
      calls.push("release");
    },
  };
  const pool = { async getConnection() { return connection; } };
  const repository = new MySQLSnapshotRepository(pool);

  const result = await repository.save({
    id: "snapshot-1",
    cadence: "monthly",
    periodKey: "2026-08",
    snapshot,
    summary: {
      productTotal: 61,
      measuredProductCount: 55,
      unmeasuredProductCount: 6,
      below70Count: 44,
      complianceCount: 17,
      pendingGovernanceCount: 44,
      averageRdhs: 52.4,
      measurementCoverage: 55 / 61,
      complianceRate: 17 / 61,
      pendingGovernanceRate: 44 / 61,
      bandCounts: {
        keyGovernance: 29,
        riskImprovement: 10,
        continuousOptimization: 5,
        regularTracking: 17,
      },
      componentAverages: {
        linkClosure: 10,
        deliveryClosure: 10,
        timeliness: 10,
        granularity: 10,
        quality: 10,
      },
    },
  });

  assert.deepEqual(result, { snapshotId: "snapshot-1", version: 1, created: true });
  assert.equal(calls[0], "begin");
  assert.ok(calls.some((call) => typeof call === "object" && /INSERT INTO rdhs_snapshots/.test(call.sql)));
  assert.ok(calls.includes("commit"));
  assert.ok(calls.includes("release"));
  assert.ok(!calls.includes("rollback"));
});
