import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  calculateAverageRdhs,
  calculateBusinessLineRankings,
  calculateSublineDistribution,
  detectCompositionChange,
  findPreviousSnapshot,
  getLineGovernanceCandidates,
  getTopFocusLines,
  previousCalendarMonth,
  summarizeProducts,
} from "../lib/rdhs/aggregate.ts";
import {
  filterProducts,
  sortBusinessLines,
  sortProducts,
} from "../lib/rdhs/filter.ts";

const products = [
  {
    businessLine: "开放平台业务群",
    subLine: "星火业务线",
    product: "开放平台控制台",
    rdhs: null,
    governanceBand: "重点治理",
  },
  {
    businessLine: "AI营销业务群",
    subLine: "营销云业务线",
    product: "营销云",
    rdhs: 52,
    governanceBand: "风险改进",
  },
  {
    businessLine: "AI营销业务群",
    subLine: "智能投放业务线",
    product: "智能投放",
    rdhs: 72,
    governanceBand: "常规跟踪",
  },
];

test("product filters compose business line, band, search, and unmeasured state", () => {
  assert.deepEqual(
    filterProducts(products, {
      businessLine: "AI营销业务群",
      band: "风险改进",
      query: "营销",
      unmeasuredOnly: false,
    }).map((product) => product.product),
    ["营销云"],
  );

  assert.deepEqual(
    filterProducts(products, {
      businessLine: "全部业务线",
      band: "全部分档",
      query: "",
      unmeasuredOnly: true,
    }).map((product) => product.product),
    ["开放平台控制台"],
  );
});

test("product search includes secondary business line names", () => {
  assert.deepEqual(
    filterProducts(products, {
      businessLine: "全部业务线",
      band: "全部分档",
      query: "智能投放业务线",
      unmeasuredOnly: false,
    }).map((product) => product.product),
    ["智能投放"],
  );
});

test("score sorting keeps unmeasured products after measured scores", () => {
  assert.deepEqual(
    sortProducts(products, "rdhs-asc").map((product) => product.product),
    ["营销云", "智能投放", "开放平台控制台"],
  );
  assert.deepEqual(
    sortProducts(products, "rdhs-desc").map((product) => product.product),
    ["智能投放", "营销云", "开放平台控制台"],
  );
});

test("business lines sort by product volume and then stable Chinese name", () => {
  const lines = [
    { businessLine: "讯飞听见", productTotal: 14 },
    { businessLine: "AI文娱业务群", productTotal: 8 },
    { businessLine: "开放平台业务群", productTotal: 21 },
  ];

  assert.deepEqual(
    sortBusinessLines(lines).map((line) => line.businessLine),
    ["开放平台业务群", "讯飞听见", "AI文娱业务群"],
  );
});

test("calculateAverageRdhs handles empty scope, zero scores, and unmeasured null", () => {
  assert.deepEqual(calculateAverageRdhs([]), { averageRdhs: null, rawAverageRdhs: null });

  assert.deepEqual(calculateAverageRdhs([{ rdhs: null }, { rdhs: null }]), {
    averageRdhs: 0,
    rawAverageRdhs: 0,
  });

  assert.deepEqual(calculateAverageRdhs([{ rdhs: 0 }, { rdhs: 60 }]), {
    averageRdhs: 30,
    rawAverageRdhs: 30,
  });
  assert.deepEqual(calculateAverageRdhs([{ rdhs: null }, { rdhs: 60 }]), {
    averageRdhs: 30,
    rawAverageRdhs: 30,
  });

  assert.deepEqual(calculateAverageRdhs([{ rdhs: 70 }, { rdhs: 80 }, { rdhs: null }]), {
    averageRdhs: 50,
    rawAverageRdhs: 50,
  });
  assert.equal(calculateAverageRdhs([{ rdhs: 100 }, { rdhs: null }, { rdhs: null }]).averageRdhs, 33.3);
});

test("business line average is product-weighted arithmetic mean, not average of sublines", () => {
  const lineProducts = [
    { businessLine: "L1", subLine: "SubA", product: "P1", rdhs: 100, governanceBand: "常规跟踪", components: {} },
    ...Array.from({ length: 9 }, (_, i) => ({
      businessLine: "L1",
      subLine: "SubB",
      product: `P_B${i}`,
      rdhs: null,
      governanceBand: "重点治理",
      components: {},
    })),
  ];

  const sublines = calculateSublineDistribution(lineProducts);
  const subA = sublines.find((s) => s.name === "SubA");
  const subB = sublines.find((s) => s.name === "SubB");

  assert.equal(subA?.averageRdhs, 100);
  assert.equal(subB?.averageRdhs, 0);

  const lineSummary = summarizeProducts(lineProducts);
  assert.equal(lineSummary.averageRdhs, 10);
});

test("previousCalendarMonth handles year boundary and findPreviousSnapshot rejects non-adjacent history", () => {
  assert.equal(previousCalendarMonth("2026-10"), "2026-09");
  assert.equal(previousCalendarMonth("2026-01"), "2025-12");
  assert.equal(previousCalendarMonth("invalid"), "");

  const snapshots = [
    { periodKey: "2026-07", cadence: "monthly", products: [], businessLines: [] },
    { periodKey: "2026-09", cadence: "monthly", products: [], businessLines: [] },
  ];

  assert.equal(findPreviousSnapshot(snapshots, "2026-09"), null);
  assert.equal(findPreviousSnapshot(snapshots, "2026-08")?.periodKey, "2026-07");
});

test("business line rankings assign standard competition rank with ties and unrounded sorting", () => {
  const mockSnapshot = {
    periodKey: "2026-08",
    cadence: "monthly",
    businessLines: [
      { businessLine: "LineA", productTotal: 2, focus: "" },
      { businessLine: "LineB", productTotal: 2, focus: "" },
      { businessLine: "LineC", productTotal: 2, focus: "" },
    ],
    products: [
      { businessLine: "LineA", product: "A1", rdhs: 70, governanceBand: "常规跟踪", components: {} },
      { businessLine: "LineA", product: "A2", rdhs: null, governanceBand: "重点治理", components: {} },
      { businessLine: "LineB", product: "B1", rdhs: 35, governanceBand: "重点治理", components: {} },
      { businessLine: "LineB", product: "B2", rdhs: 35, governanceBand: "重点治理", components: {} },
      { businessLine: "LineC", product: "C1", rdhs: 20, governanceBand: "重点治理", components: {} },
      { businessLine: "LineC", product: "C2", rdhs: 20, governanceBand: "重点治理", components: {} },
    ],
  };

  const rankings = calculateBusinessLineRankings(mockSnapshot, null);
  assert.equal(rankings[0].rank, 1);
  assert.equal(rankings[0].isTie, true);
  assert.equal(rankings[1].rank, 1);
  assert.equal(rankings[1].isTie, true);
  assert.equal(rankings[2].rank, 3);
  assert.equal(rankings[2].isTie, false);
});

test("rankings use unrounded scores for delta and ordering", () => {
  const snapshot = (periodKey, scores) => ({
    periodKey, cadence: "monthly",
    businessLines: scores.map((_, i) => ({ businessLine: `L${i}`, productTotal: 3, focus: "" })),
    products: scores.flatMap((values, i) => values.map((rdhs, j) => ({
      businessLine: `L${i}`, product: `P${j}`, rdhs, components: {},
    }))),
  });
  const current = snapshot("2026-09", [[66, 66, 65], [65.65, 65.65, 65.65]]);
  const previous = snapshot("2026-08", [[65, 65, 65], [65, 65, 65]]);
  const rankings = calculateBusinessLineRankings(current, previous);
  assert.equal(rankings[0].businessLine, "L0");
  assert.equal(rankings[0].avgScore, 65.7);
  assert.equal(rankings[1].avgScore, 65.7);
  assert.equal(rankings[0].isTie, false);
  assert.equal(rankings[0].delta, 0.7);
  assert.equal(rankings[1].delta, 0.7);
});

test("calculateSublineDistribution buckets empty, missing, and whitespace sublines into explicit bucket", () => {
  const prods = [
    { businessLine: "L", subLine: "正规二级线", product: "P1", rdhs: 80, governanceBand: "常规跟踪", components: {} },
    { businessLine: "L", subLine: undefined, product: "P2", rdhs: 50, governanceBand: "风险改进", components: {} },
    { businessLine: "L", subLine: "", product: "P3", rdhs: null, governanceBand: "重点治理", components: {} },
    { businessLine: "L", subLine: "   ", product: "P4", rdhs: 40, governanceBand: "重点治理", components: {} },
  ];

  const sublines = calculateSublineDistribution(prods);
  assert.equal(sublines.length, 2);

  const regular = sublines.find((s) => s.name === "正规二级线");
  assert.equal(regular?.count, 1);
  assert.equal(regular?.averageRdhs, 80);

  const fallback = sublines.find((s) => s.name === "未分二级业务线");
  assert.equal(fallback?.count, 3);
  assert.equal(fallback?.unmeasuredCount, 1);
  assert.equal(fallback?.averageRdhs, 30);
});

test("getLineGovernanceCandidates prioritizes P0, P1, P2 with maximum 3 items", () => {
  const prods = [
    { product: "合格1", rdhs: 75, governanceBand: "常规跟踪" },
    { product: "P2优化", rdhs: 65, governanceBand: "持续优化" },
    { product: "P1风险", rdhs: 50, governanceBand: "风险改进" },
    { product: "P0治理低分", rdhs: 30, governanceBand: "重点治理" },
    { product: "P0未度量", rdhs: null, governanceBand: "重点治理" },
  ];

  const top3 = getLineGovernanceCandidates(prods, 3);
  assert.equal(top3.length, 3);
  assert.equal(top3[0].product, "P0未度量");
  assert.equal(top3[1].product, "P0治理低分");
  assert.equal(top3[2].product, "P1风险");
  assert.deepEqual(getLineGovernanceCandidates([{ product: "健康产品", rdhs: 80 }]), []);
  assert.equal(getLineGovernanceCandidates([
    { product: "实测零分", rdhs: 0 }, { product: "未度量", rdhs: null },
  ])[0].product, "未度量");
});

test("subline and band filters do not affect whole-line aggregates", () => {
  const lineProducts = [
    { businessLine: "L", subLine: "SubA", product: "P1", rdhs: 80, governanceBand: "常规跟踪", components: {} },
    { businessLine: "L", subLine: "SubB", product: "P2", rdhs: 40, governanceBand: "重点治理", components: {} },
  ];

  const wholeSummary = summarizeProducts(lineProducts);
  assert.equal(wholeSummary.averageRdhs, 60);

  const subAProducts = lineProducts.filter((p) => p.subLine === "SubA");
  assert.equal(subAProducts.length, 1);

  assert.equal(wholeSummary.averageRdhs, 60);
  assert.equal(wholeSummary.productTotal, 2);
});

test("detectCompositionChange detects added and removed products", () => {
  const prev = [{ product: "A" }, { product: "B" }];
  const curr = [{ product: "B" }, { product: "C" }];

  const change = detectCompositionChange(curr, prev);
  assert.equal(change.hasChanged, true);
  assert.equal(change.addedCount, 1);
  assert.deepEqual(change.addedNames, ["C"]);
  assert.equal(change.removedCount, 1);
  assert.deepEqual(change.removedNames, ["A"]);
  assert.equal(change.currentCount, 2);
  assert.equal(change.previousCount, 2);
});

test("getTopFocusLines prioritizes P0 and P1 struggling lines over higher-scoring lines with high volume", () => {
  const data09 = JSON.parse(
    fs.readFileSync(new URL("../data/snapshots/2026-09.json", import.meta.url), "utf8"),
  );
  const focus = getTopFocusLines(data09);
  assert.equal(focus.length, 3);
  assert.equal(focus[0].name, "企业数字化业务群");
  assert.equal(focus[0].priority, "P0");
  assert.equal(focus[1].name, "开放平台业务群");
  assert.equal(focus[1].priority, "P0");
  assert.equal(focus[2].name, "C端硬件创新中心");
  assert.equal(focus[2].priority, "P1");

  // 讯飞听见 (2026-09 均分 65.0, 全 BG 排名第 5) 不应进入 Top 3 攻坚重点
  assert.ok(!focus.some((f) => f.name === "讯飞听见"));
});

test("getTopFocusLines: synthetic test that volume cannot outrank severity", () => {
  const syntheticSnapshot = {
    periodKey: "2026-09",
    cadence: "monthly",
    businessLines: [
      { businessLine: "大体量健康线", productTotal: 20, focus: "ok", keyGovernanceCount: 1 },
      { businessLine: "中小体量危重线", productTotal: 2, focus: "bad", keyGovernanceCount: 2 },
      { businessLine: "轻度风险线", productTotal: 2, focus: "warn", keyGovernanceCount: 0 },
    ],
    products: [
      // 大体量健康线: 19 款 100 分, 1 款未度量 (计0), avg = 95.0 (P3), keyGov = 1
      ...Array.from({ length: 19 }, (_, i) => ({
        businessLine: "大体量健康线", product: `HP${i}`, rdhs: 100, components: {},
      })),
      { businessLine: "大体量健康线", product: "HP_unmeasured", rdhs: null, components: {} },

      // 中小体量危重线: 2 款 20 分, avg = 20.0 (P0), keyGov = 2
      { businessLine: "中小体量危重线", product: "CP1", rdhs: 20, components: {} },
      { businessLine: "中小体量危重线", product: "CP2", rdhs: 20, components: {} },

      // 轻度风险线: 2 款 50 分, avg = 50.0 (P1), keyGov = 0
      { businessLine: "轻度风险线", product: "WP1", rdhs: 50, components: {} },
      { businessLine: "轻度风险线", product: "WP2", rdhs: 50, components: {} },
    ],
  };

  const focus = getTopFocusLines(syntheticSnapshot);
  assert.equal(focus[0].name, "中小体量危重线");
  assert.equal(focus[0].priority, "P0");
  assert.equal(focus[1].name, "轻度风险线");
  assert.equal(focus[1].priority, "P1");
  // 大体量健康线虽然 keyGovCount = 1，但均分 95，属于及格线，排在末位
  assert.equal(focus[2].name, "大体量健康线");
});
