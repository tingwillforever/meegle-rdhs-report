import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { SnapshotService } from "../lib/rdhs/repository.ts";
import { SQLiteSnapshotRepository } from "../lib/rdhs/sqlite-repository.ts";

function snapshot({ periodKey = "2026-08", sha = "a", rdhs = 42 } = {}) {
  const governanceBand =
    rdhs < 45 ? "重点治理" : rdhs < 60 ? "风险改进" : rdhs < 70 ? "持续优化" : "常规跟踪";
  return {
    schemaVersion: 1,
    cadence: "monthly",
    periodKey,
    asOf: `${periodKey}-28`,
    fetchedAt: "2026-08-31T09:00:00+08:00",
    source: {
      chartId: "chart-current",
      chartName: "RDHS By 产品",
      sha256: sha.repeat(64),
    },
    audit: {
      rawRowCount: 10,
      acceptedRowCount: 1,
      zeroScoreRowCount: 9,
      emptyDimensionRowCount: 0,
      researchProductCount: 1,
      measuredProductCount: 1,
      unmeasuredProductCount: 0,
      excludedTestBusinessLineCount: 2,
      status: "validated",
      warning: null,
    },
    overview: {
      conclusion: "本期处于重点治理阶段。",
      focus: "优先修复价值链路。",
    },
    businessLines: [
      {
        businessLine: "业务线A",
        productTotal: 1,
        keyGovernanceCount: rdhs < 45 ? 1 : 0,
        riskImprovementCount: rdhs >= 45 && rdhs < 60 ? 1 : 0,
        continuousOptimizationCount: rdhs >= 60 && rdhs < 70 ? 1 : 0,
        regularTrackingCount: rdhs >= 70 ? 1 : 0,
        mode: governanceBand,
        focus: "优先修复价值链路。",
      },
    ],
    products: [
      {
        businessLine: "业务线A",
        product: "产品A",
        productStatus: "研发中",
        rdhs,
        governanceBand,
        priority: rdhs < 45 ? "P0" : rdhs < 60 ? "P1" : rdhs < 70 ? "P2" : null,
        components: {
          linkClosure: 8,
          deliveryClosure: 8,
          timeliness: 8,
          granularity: 8,
          quality: 10,
        },
        lowestComponent: "链路闭环得分",
        problem: "链路闭环偏低",
        action: "补齐需求与缺陷关联。",
      },
    ],
  };
}

test("SQLite repository keeps one replaceable snapshot for each month", async () => {
  const root = await mkdtemp(join(tmpdir(), "rdhs-sqlite-"));
  const databasePath = join(root, "rdhs.sqlite");
  try {
    const firstRepository = new SQLiteSnapshotRepository(databasePath);
    const service = new SnapshotService(firstRepository, () => "snapshot-1");
    await service.ingest(snapshot());
    await new SnapshotService(firstRepository, () => "snapshot-2").ingest(
      snapshot({ sha: "b", rdhs: 58 }),
    );

    const database = new DatabaseSync(databasePath);
    assert.equal(database.prepare("SELECT COUNT(*) AS count FROM rdhs_business_line_metrics").get().count, 0);
    assert.equal(database.prepare("SELECT COUNT(*) AS count FROM rdhs_product_metrics").get().count, 0);
    database.close();

    const secondRepository = new SQLiteSnapshotRepository(databasePath);
    const current = await secondRepository.getCurrent("monthly", "2026-08");
    assert.equal(current?.snapshot.source.sha256, "b".repeat(64));
    assert.equal(current?.version, 1);
    assert.equal(
      new DatabaseSync(databasePath)
        .prepare("SELECT COUNT(*) AS count FROM rdhs_snapshots")
        .get().count,
      1,
    );
    assert.deepEqual(
      (await secondRepository.listPeriods("monthly")).map((record) => record.periodKey),
      ["2026-08"],
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("SQLite repository updates an idempotent source without creating a version", async () => {
  const repository = new SQLiteSnapshotRepository(":memory:");
  const service = new SnapshotService(repository, (() => {
    let value = 0;
    return () => `snapshot-${++value}`;
  })());

  const first = await service.ingest(snapshot());
  const duplicate = await service.ingest(snapshot());

  assert.deepEqual(first, { snapshotId: "snapshot-1", version: 1, created: true });
  assert.deepEqual(duplicate, { snapshotId: "snapshot-1", version: 1, created: false });
});

test("SQLite repository refreshes the snapshot JSON for an idempotent source", async () => {
  const root = await mkdtemp(join(tmpdir(), "rdhs-sqlite-refresh-"));
  const databasePath = join(root, "rdhs.sqlite");
  try {
    const repository = new SQLiteSnapshotRepository(databasePath);
    const service = new SnapshotService(repository, () => "snapshot-1");
    await service.ingest(snapshot());

    const enriched = snapshot();
    enriched.businessLines[0].focus = "新的业务线关注点";
    enriched.products[0].action = "新的产品动作";
    await service.ingest(enriched);

    const current = await repository.getCurrent("monthly", "2026-08");
    assert.equal(current?.snapshot.businessLines[0].focus, "新的业务线关注点");
    assert.equal(current?.snapshot.products[0].action, "新的产品动作");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
