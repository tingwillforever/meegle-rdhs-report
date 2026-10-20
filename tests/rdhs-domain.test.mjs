import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMonthlyTrend,
  governanceBandForScore,
  summarizeSnapshot,
} from "../lib/rdhs/aggregate.ts";
import { validateSnapshot } from "../lib/rdhs/validate.ts";

function product(productName, rdhs, components = {}, businessLine = "业务线A") {
  return {
    businessLine,
    product: productName,
    productStatus: "研发中",
    rdhs,
    governanceBand: governanceBandForScore(rdhs),
    priority: rdhs === null || rdhs < 45 ? "P0" : rdhs < 60 ? "P1" : rdhs < 70 ? "P2" : null,
    components: {
      linkClosure: components.linkClosure ?? null,
      deliveryClosure: components.deliveryClosure ?? null,
      timeliness: components.timeliness ?? null,
      granularity: components.granularity ?? null,
      quality: components.quality ?? null,
    },
    lowestComponent: rdhs === null ? "未形成有效 RDHS 度量" : "链路闭环得分",
    problem: rdhs === null ? "产品未关联到有效度量" : "链路闭环偏低",
    action: "确认产品责任人与过程记录。",
  };
}

function snapshot(overrides = {}) {
  const products = overrides.products ?? [
    product("产品A", 40, {
      linkClosure: 8,
      deliveryClosure: 10,
      timeliness: 8,
      granularity: 7,
      quality: 7,
    }),
    product("产品B", 72, {
      linkClosure: 18,
      deliveryClosure: 11,
      timeliness: 15,
      granularity: 14,
      quality: 14,
    }),
    product("产品C", null),
  ];
  return {
    schemaVersion: 1,
    cadence: "monthly",
    periodKey: "2026-08",
    asOf: "2026-08-31",
    fetchedAt: "2026-08-31T09:00:00+08:00",
    source: {
      chartId: "chart-current",
      chartName: "本月 RDHS By 产品",
      sha256: "a".repeat(64),
    },
    audit: {
      rawRowCount: 610,
      acceptedRowCount: 2,
      zeroScoreRowCount: 605,
      emptyDimensionRowCount: 3,
      researchProductCount: 3,
      measuredProductCount: 2,
      unmeasuredProductCount: 1,
      excludedTestBusinessLineCount: 2,
      status: "validated",
      warning: null,
    },
    overview: {
      conclusion: "本期仍处于重点治理阶段。",
      focus: "优先补齐未度量产品关联。",
    },
    businessLines: [
      {
        businessLine: "业务线A",
        productTotal: 3,
        keyGovernanceCount: 2,
        riskImprovementCount: 0,
        continuousOptimizationCount: 0,
        regularTrackingCount: 1,
        mode: "重点治理",
        focus: "优先补齐未度量产品关联。",
      },
    ],
    products,
    ...overrides,
  };
}

test("unmeasured products stay in key governance and contribute 0 to RDHS arithmetic mean", () => {
  const valid = validateSnapshot(snapshot());
  const summary = summarizeSnapshot(valid);

  assert.equal(governanceBandForScore(null), "重点治理");
  assert.equal(summary.averageRdhs, 37.3);
  assert.equal(summary.measurementCoverage, 2 / 3);
  assert.equal(summary.complianceCount, 1);
  assert.equal(summary.pendingGovernanceCount, 2);
  assert.equal(summary.complianceRate, 1 / 3);
  assert.equal(summary.pendingGovernanceRate, 2 / 3);
  assert.deepEqual(summary.bandCounts, {
    keyGovernance: 2,
    riskImprovement: 0,
    continuousOptimization: 0,
    regularTracking: 1,
  });
  assert.equal(summary.componentAverages.linkClosure, 13);
});

test("snapshot validation preserves secondary line and dependency metrics for product detail", () => {
  const valid = validateSnapshot(snapshot({
    products: [
      {
        ...product("产品A", 40),
        subLine: "输入法业务线",
        dependencyMetrics: [
          { label: "月人均需求吞吐量", value: 0.1, unit: "个/人", tone: "critical" },
          { label: "需求发布闭环率", value: 0.42, unit: "%", tone: "critical" },
        ],
      },
      product("产品B", 72),
      product("产品C", null),
    ],
  }));

  assert.equal(valid.products[0].subLine, "输入法业务线");
  assert.deepEqual(
    valid.products[0].dependencyMetrics.map((metric) => [metric.label, metric.value, metric.unit, metric.tone]),
    [
      ["月人均需求吞吐量", 0.1, "个/人", "critical"],
      ["需求发布闭环率", 0.42, "%", "critical"],
    ],
  );
});

test("snapshot validation rejects overview counts that do not reconcile", () => {
  const invalid = snapshot({
    businessLines: [
      {
        businessLine: "业务线A",
        productTotal: 3,
        keyGovernanceCount: 1,
        riskImprovementCount: 0,
        continuousOptimizationCount: 0,
        regularTrackingCount: 1,
        mode: "重点治理",
        focus: "错误数据",
      },
    ],
  });

  assert.throws(
    () => validateSnapshot(invalid),
    /businessLines\[0\].*band counts.*productTotal/,
  );
});

test("monthly trend sorts periods ascending and keeps product-level rates", () => {
  const july = validateSnapshot(snapshot({ periodKey: "2026-07", asOf: "2026-07-31" }));
  const august = validateSnapshot(snapshot());

  const trend = buildMonthlyTrend([august, july]);

  assert.deepEqual(
    trend.map((point) => point.periodKey),
    ["2026-07", "2026-08"],
  );
  assert.equal(trend[0].averageRdhs, 37.3);
  assert.equal(trend[0].measuredProductCount, 2);
  assert.equal(trend[0].complianceRate, 1 / 3);
});

test("monthly trend excludes months after the selected reporting period", () => {
  const july = validateSnapshot(snapshot({ periodKey: "2026-07", asOf: "2026-07-31" }));
  const august = validateSnapshot(snapshot());
  const september = validateSnapshot(snapshot({ periodKey: "2026-09", asOf: "2026-09-30" }));

  const trend = buildMonthlyTrend([september, august, july], { throughPeriod: "2026-08" });

  assert.deepEqual(
    trend.map((point) => point.periodKey),
    ["2026-07", "2026-08"],
  );
});

test("monthly trend can be scoped to one business line without product drilldown series", () => {
  const july = validateSnapshot(snapshot({
    periodKey: "2026-07",
    asOf: "2026-07-31",
    products: [
      product("A低分", 40, {}, "业务线A"),
      product("A规范", 78, {}, "业务线A"),
      product("B规范", 90, {}, "业务线B"),
    ],
    audit: {
      rawRowCount: 3,
      acceptedRowCount: 3,
      zeroScoreRowCount: 0,
      emptyDimensionRowCount: 0,
      researchProductCount: 3,
      measuredProductCount: 3,
      unmeasuredProductCount: 0,
      excludedTestBusinessLineCount: 0,
      status: "validated",
      warning: null,
    },
    businessLines: [
      {
        businessLine: "业务线A",
        productTotal: 2,
        keyGovernanceCount: 1,
        riskImprovementCount: 0,
        continuousOptimizationCount: 0,
        regularTrackingCount: 1,
        mode: "重点治理",
        focus: "业务线A治理。",
      },
      {
        businessLine: "业务线B",
        productTotal: 1,
        keyGovernanceCount: 0,
        riskImprovementCount: 0,
        continuousOptimizationCount: 0,
        regularTrackingCount: 1,
        mode: "常规跟踪",
        focus: "业务线B常规跟踪。",
      },
    ],
  }));

  const trend = buildMonthlyTrend([july], { businessLine: "业务线A" });

  assert.equal(trend[0].averageRdhs, 59);
  assert.equal(trend[0].productTotal, 2);
  assert.equal(trend[0].complianceRate, 0.5);
  assert.equal(Object.hasOwn(trend[0], "productSeries"), false);
});

test("weekly snapshots are rejected by the monthly-only contract", () => {
  assert.throws(
    () => validateSnapshot(snapshot({ cadence: "weekly", periodKey: "2026-08-30", asOf: "2026-08-30" })),
    /cadence: must be monthly/,
  );
});
