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

test("MySQL repository replaces a monthly snapshot instead of creating a new version", async () => {
  const calls = [];
  const replacement = structuredClone(snapshot);
  replacement.source.sha256 = "b".repeat(64);
  const connection = {
    async beginTransaction() { calls.push("begin"); },
    async execute(sql, parameters) {
      calls.push({ sql, parameters });
      if (/is_current = 1/.test(sql)) {
        return [[{
          id: "snapshot-1",
          cadence: "monthly",
          period_key: "2026-08",
          version: 1,
          is_current: 1,
          snapshot_json: JSON.stringify(snapshot),
        }], []];
      }
      return [{ affectedRows: 1 }, []];
    },
    async commit() { calls.push("commit"); },
    async rollback() { calls.push("rollback"); },
    release() { calls.push("release"); },
  };
  const repository = new MySQLSnapshotRepository({
    async getConnection() { return connection; },
  });

  const result = await repository.save({
    id: "snapshot-2",
    cadence: "monthly",
    periodKey: "2026-08",
    snapshot: replacement,
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
      bandCounts: { keyGovernance: 29, riskImprovement: 10, continuousOptimization: 5, regularTracking: 17 },
      componentAverages: { linkClosure: 10, deliveryClosure: 10, timeliness: 10, granularity: 10, quality: 10 },
    },
  });

  assert.deepEqual(result, { snapshotId: "snapshot-1", version: 1, created: false });
  assert.ok(calls.some((call) => typeof call === "object" && /UPDATE rdhs_snapshots SET/.test(call.sql)));
  assert.ok(!calls.some((call) => typeof call === "object" && /INSERT INTO rdhs_snapshots/.test(call.sql)));
});

test("MySQL repository refuses a coverage regression before changing the current snapshot", async () => {
  const calls = [];
  const complete = structuredClone(snapshot);
  const partial = structuredClone(snapshot);
  partial.source.sha256 = "b".repeat(64);
  partial.products = partial.products.slice(0, 9);
  partial.businessLines = [{
    ...partial.businessLines[0],
    productTotal: 9,
    keyGovernanceCount: 9,
    riskImprovementCount: 0,
    continuousOptimizationCount: 0,
    regularTrackingCount: 0,
  }];
  partial.audit.researchProductCount = 9;
  partial.audit.measuredProductCount = 9;
  partial.audit.unmeasuredProductCount = 0;

  const connection = {
    async beginTransaction() {
      calls.push("begin");
    },
    async execute(sql, parameters) {
      calls.push({ sql, parameters });
      if (/is_current = 1/.test(sql)) {
        return [[{
          id: "complete-snapshot",
          cadence: "monthly",
          period_key: "2026-08",
          version: 1,
          is_current: 1,
          snapshot_json: JSON.stringify(complete),
        }], []];
      }
      return [[], []];
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
  const repository = new MySQLSnapshotRepository({
    async getConnection() { return connection; },
  });

  await assert.rejects(
    () => repository.save({
      id: "partial-snapshot",
      cadence: "monthly",
      periodKey: "2026-08",
      snapshot: partial,
      summary: {
        productTotal: 9,
        measuredProductCount: 9,
        unmeasuredProductCount: 0,
        below70Count: 9,
        complianceCount: 0,
        pendingGovernanceCount: 9,
        averageRdhs: 42,
        measurementCoverage: 1,
        complianceRate: 0,
        pendingGovernanceRate: 1,
        bandCounts: {
          keyGovernance: 9,
          riskImprovement: 0,
          continuousOptimization: 0,
          regularTracking: 0,
        },
        componentAverages: {
          linkClosure: 8,
          deliveryClosure: 8,
          timeliness: 8,
          granularity: 8,
          quality: 10,
        },
      },
    }),
    /snapshot coverage regressed/,
  );

  assert.ok(calls.includes("rollback"));
  assert.ok(!calls.includes("commit"));
  assert.ok(!calls.some((call) => typeof call === "object" && /UPDATE rdhs_snapshots SET is_current = 0/.test(call.sql)));
});
