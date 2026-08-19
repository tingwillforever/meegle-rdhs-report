import assert from "node:assert/strict";
import test from "node:test";

import {
  MemorySnapshotRepository,
  SnapshotService,
} from "../lib/rdhs/repository.ts";

function snapshot({ cadence = "monthly", periodKey = "2026-08", sha = "a", rdhs = 42 } = {}) {
  return {
    schemaVersion: 1,
    cadence,
    periodKey,
    asOf: cadence === "monthly" ? `${periodKey}-28` : periodKey,
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
        mode:
          rdhs < 45 ? "重点治理" : rdhs < 60 ? "风险改进" : rdhs < 70 ? "持续优化" : "常规跟踪",
        focus: "优先修复价值链路。",
      },
    ],
    products: [
      {
        businessLine: "业务线A",
        product: "产品A",
        productStatus: "研发中",
        rdhs,
        governanceBand:
          rdhs < 45 ? "重点治理" : rdhs < 60 ? "风险改进" : rdhs < 70 ? "持续优化" : "常规跟踪",
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

test("ingest is idempotent for the same period and source hash", async () => {
  const repository = new MemorySnapshotRepository();
  const service = new SnapshotService(repository, (() => {
    let value = 0;
    return () => `snapshot-${++value}`;
  })());

  const first = await service.ingest(snapshot());
  const duplicate = await service.ingest(snapshot());

  assert.deepEqual(first, { snapshotId: "snapshot-1", version: 1, created: true });
  assert.deepEqual(duplicate, { snapshotId: "snapshot-1", version: 1, created: false });
  assert.equal((await repository.listPeriods("monthly")).length, 1);
});

test("same source hash refreshes enriched snapshot contract fields without a new version", async () => {
  const repository = new MemorySnapshotRepository();
  const service = new SnapshotService(repository, (() => {
    let value = 0;
    return () => `snapshot-${++value}`;
  })());

  await service.ingest(snapshot());
  const enriched = snapshot();
  enriched.products[0].subLine = "二级业务线";
  enriched.products[0].dependencyMetrics = [
    { label: "需求发布闭环率", value: 0.5, unit: "%", tone: "critical" },
  ];
  const refresh = await service.ingest(enriched);

  const current = await repository.getCurrent("monthly", "2026-08");
  assert.deepEqual(refresh, { snapshotId: "snapshot-1", version: 1, created: false });
  assert.equal(repository.records.length, 1);
  assert.equal(current.snapshot.products[0].subLine, "二级业务线");
  assert.equal(current.snapshot.products[0].dependencyMetrics[0].label, "需求发布闭环率");
});

test("refreshing an existing source hash makes that snapshot current for the period", async () => {
  const repository = new MemorySnapshotRepository();
  const ids = ["snapshot-1", "snapshot-2", "snapshot-3"];
  const service = new SnapshotService(repository, () => ids.shift());

  await service.ingest(snapshot());
  await service.ingest(snapshot({ sha: "b", rdhs: 58 }));
  await service.ingest(snapshot());

  const current = await repository.getCurrent("monthly", "2026-08");
  assert.equal(current.snapshot.source.sha256, "a".repeat(64));
  assert.equal(current.version, 1);
  assert.equal(repository.records.length, 2);
  assert.equal(repository.records.filter((record) => record.isCurrent).length, 1);
});

test("a newer validated version becomes current without deleting history", async () => {
  const repository = new MemorySnapshotRepository();
  const ids = ["snapshot-1", "snapshot-2"];
  const service = new SnapshotService(repository, () => ids.shift());

  await service.ingest(snapshot());
  await service.ingest(snapshot({ sha: "b", rdhs: 58 }));

  const current = await repository.getCurrent("monthly", "2026-08");
  assert.equal(current.snapshot.source.sha256, "b".repeat(64));
  assert.equal(current.version, 2);
  assert.equal(repository.records.length, 2);
  assert.equal(repository.records.filter((record) => record.isCurrent).length, 1);
});

test("an invalid replacement cannot change the current snapshot", async () => {
  const repository = new MemorySnapshotRepository();
  const service = new SnapshotService(repository, () => "snapshot-1");
  await service.ingest(snapshot());
  const invalid = snapshot({ sha: "b" });
  invalid.businessLines[0].productTotal = 2;

  await assert.rejects(() => service.ingest(invalid), /band counts.*productTotal/);
  const current = await repository.getCurrent("monthly", "2026-08");
  assert.equal(current.snapshot.source.sha256, "a".repeat(64));
  assert.equal(repository.records.length, 1);
});

test("period queries return current snapshots in reverse chronological order", async () => {
  const repository = new MemorySnapshotRepository();
  const ids = ["july", "august"];
  const service = new SnapshotService(repository, () => ids.shift());

  await service.ingest(snapshot({ periodKey: "2026-07", sha: "b" }));
  await service.ingest(snapshot());

  assert.deepEqual(
    (await repository.listPeriods("monthly")).map((record) => record.periodKey),
    ["2026-08", "2026-07"],
  );
  assert.equal((await repository.listCurrent("monthly")).length, 2);
});
