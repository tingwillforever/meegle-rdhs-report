import type {
  BandCounts,
  BusinessLineRankingItem,
  ComponentScores,
  CompositionChange,
  GovernanceBand,
  ProductMetric,
  RdhsSnapshot,
  SnapshotSummary,
  SublineStat,
  TrendPoint,
} from "./types.ts";

const COMPONENT_KEYS = [
  "linkClosure",
  "deliveryClosure",
  "timeliness",
  "granularity",
  "quality",
] as const;

function rounded(value: number): number {
  return Math.round(value * 10) / 10;
}

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return rounded(values.reduce((sum, value) => sum + value, 0) / values.length);
}

export function governanceBandForScore(rdhs: number | null): GovernanceBand {
  if (rdhs === null || rdhs < 45) return "重点治理";
  if (rdhs < 60) return "风险改进";
  if (rdhs < 70) return "持续优化";
  return "常规跟踪";
}

/**
 * Calculates RDHS arithmetic mean across an eligible product scope.
 * - All eligible products in scope form the denominator.
 * - Null / unmeasured products contribute 0 to the arithmetic mean.
 * - Empty scope returns null (no data, not 0).
 */
export function calculateAverageRdhs(products: Array<Pick<ProductMetric, "rdhs">>): {
  averageRdhs: number | null;
  rawAverageRdhs: number | null;
} {
  if (products.length === 0) {
    return { averageRdhs: null, rawAverageRdhs: null };
  }
  const sum = products.reduce((acc, p) => acc + (p.rdhs ?? 0), 0);
  const raw = sum / products.length;
  return {
    averageRdhs: rounded(raw),
    rawAverageRdhs: raw,
  };
}

/**
 * Computes exact preceding calendar month string in YYYY-MM format.
 * (e.g. "2026-10" -> "2026-09", "2026-01" -> "2025-12").
 */
export function previousCalendarMonth(periodKey: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(periodKey.trim());
  if (!match) return "";
  const year = parseInt(match[1], 10);
  const month = parseInt(match[2], 10);
  if (month < 1 || month > 12) return "";
  if (month === 1) {
    return `${year - 1}-12`;
  }
  return `${year}-${String(month - 1).padStart(2, "0")}`;
}

/**
 * Finds the exact preceding calendar month snapshot.
 * Never falls back to nearest earlier snapshot.
 */
export function findPreviousSnapshot(
  snapshots: RdhsSnapshot[],
  currentPeriodKey: string,
): RdhsSnapshot | null {
  const targetPeriod = previousCalendarMonth(currentPeriodKey);
  if (!targetPeriod) return null;
  return snapshots.find((s) => s.periodKey === targetPeriod) ?? null;
}

/**
 * Compares two product sets to detect composition changes.
 */
export function detectCompositionChange(
  currentProducts: Pick<ProductMetric, "product">[],
  previousProducts: Pick<ProductMetric, "product">[],
): CompositionChange {
  const currentSet = new Set(currentProducts.map((p) => p.product));
  const prevSet = new Set(previousProducts.map((p) => p.product));
  const added = currentProducts.filter((p) => !prevSet.has(p.product)).map((p) => p.product);
  const removed = previousProducts.filter((p) => !currentSet.has(p.product)).map((p) => p.product);
  return {
    hasChanged: added.length > 0 || removed.length > 0 || currentProducts.length !== previousProducts.length,
    addedCount: added.length,
    removedCount: removed.length,
    addedNames: added,
    removedNames: removed,
    currentCount: currentProducts.length,
    previousCount: previousProducts.length,
  };
}

/**
 * Summarizes an arbitrary list of products adhering to the unified RDHS aggregation contract.
 */
export function summarizeProducts(products: ProductMetric[]): SnapshotSummary {
  const measuredProducts = products.filter((p) => p.rdhs !== null);
  const unmeasuredProducts = products.filter((p) => p.rdhs === null);
  const productTotal = products.length;

  const bandCounts: BandCounts = {
    keyGovernance: 0,
    riskImprovement: 0,
    continuousOptimization: 0,
    regularTracking: 0,
  };

  for (const product of products) {
    if (product.governanceBand === "重点治理") bandCounts.keyGovernance += 1;
    if (product.governanceBand === "风险改进") bandCounts.riskImprovement += 1;
    if (product.governanceBand === "持续优化") bandCounts.continuousOptimization += 1;
    if (product.governanceBand === "常规跟踪") bandCounts.regularTracking += 1;
  }

  const { averageRdhs, rawAverageRdhs } = calculateAverageRdhs(products);

  const componentAverages = Object.fromEntries(
    COMPONENT_KEYS.map((key) => [
      key,
      average(
        products.flatMap((product) => {
          const value = product.components[key];
          return value === null ? [] : [value];
        }),
      ),
    ]),
  ) as ComponentScores;

  const complianceCount = bandCounts.regularTracking; // >=70
  const pendingGovernanceCount = productTotal - complianceCount; // all below 70

  return {
    productTotal,
    measuredProductCount: measuredProducts.length,
    unmeasuredProductCount: unmeasuredProducts.length,
    below70Count: pendingGovernanceCount,
    complianceCount,
    pendingGovernanceCount,
    averageRdhs,
    rawAverageRdhs,
    measurementCoverage: productTotal === 0 ? 0 : measuredProducts.length / productTotal,
    complianceRate: productTotal === 0 ? 0 : complianceCount / productTotal,
    pendingGovernanceRate: productTotal === 0 ? 0 : pendingGovernanceCount / productTotal,
    bandCounts,
    componentAverages,
  };
}

export function summarizeSnapshot(snapshot: RdhsSnapshot): SnapshotSummary {
  return summarizeProducts(snapshot.products);
}

/**
 * Calculates business line ranking and comparisons against the exact previous calendar month.
 * - Arithmetic mean uses the unified contract: null contributes 0, empty scope is null.
 * - Ranks are sorted by unrounded rawAverageRdhs desc with sensible ties.
 */
export function calculateBusinessLineRankings(
  snapshot: RdhsSnapshot,
  previousSnapshot: RdhsSnapshot | null,
): BusinessLineRankingItem[] {
  type LineIntermediate = {
    businessLine: string;
    productTotal: number;
    focus: string;
    summary: SnapshotSummary;
    prevSummary: SnapshotSummary | null;
    rawAvg: number | null;
    prevRawAvg: number | null;
    compositionChange: CompositionChange | null;
    lead: string;
    lag: string;
  };

  const lineStats: LineIntermediate[] = [];

  for (const b of snapshot.businessLines) {
    const prods = snapshot.products.filter((p) => p.businessLine === b.businessLine);
    const summary = summarizeProducts(prods);

    let prevSummary: SnapshotSummary | null = null;
    let prevRawAvg: number | null = null;
    let compChange: CompositionChange | null = null;

    if (previousSnapshot) {
      const prevProds = previousSnapshot.products.filter((p) => p.businessLine === b.businessLine);
      if (prevProds.length > 0) {
        prevSummary = summarizeProducts(prevProds);
        prevRawAvg = prevSummary.rawAverageRdhs;
      }
      compChange = detectCompositionChange(prods, prevProds);
    }

    const measured = prods.filter((p) => p.rdhs !== null);
    const unmeasured = prods.filter((p) => p.rdhs === null);
    const sortedMeasured = [...measured].sort((a, b) => (b.rdhs ?? 0) - (a.rdhs ?? 0));
    const lead = sortedMeasured[0] ? `${sortedMeasured[0].product} (${sortedMeasured[0].rdhs}分)` : "-";
    const lag =
      unmeasured.length > 0
        ? `${unmeasured[0].product} (未度量，考核计0)`
        : sortedMeasured.length > 0
          ? `${sortedMeasured[sortedMeasured.length - 1].product} (${sortedMeasured[sortedMeasured.length - 1].rdhs}分)`
          : "-";

    lineStats.push({
      businessLine: b.businessLine,
      productTotal: b.productTotal,
      focus: b.focus,
      summary,
      prevSummary,
      rawAvg: summary.rawAverageRdhs,
      prevRawAvg,
      compositionChange: compChange,
      lead,
      lag,
    });
  }

  // Sort descending by unrounded raw score (null score treated as lowest -1),
  // secondary by product volume desc, tertiary by stable Chinese name.
  lineStats.sort((a, b) => {
    const scoreA = a.rawAvg ?? -1;
    const scoreB = b.rawAvg ?? -1;
    if (Math.abs(scoreA - scoreB) > 1e-9) {
      return scoreB - scoreA;
    }
    if (a.productTotal !== b.productTotal) {
      return b.productTotal - a.productTotal;
    }
    return a.businessLine.localeCompare(b.businessLine, "zh-CN");
  });

  // Assign standard competition ranking (1, 2, 2, 4) with tie indicators
  const results: BusinessLineRankingItem[] = [];
  let currentRank = 1;

  for (let i = 0; i < lineStats.length; i++) {
    const item = lineStats[i];
    if (i > 0) {
      const prevItem = lineStats[i - 1];
      const scorePrev = prevItem.rawAvg ?? -1;
      const scoreCurr = item.rawAvg ?? -1;
      if (Math.abs(scorePrev - scoreCurr) > 1e-9) {
        currentRank = i + 1;
      }
    }

    const isTie = lineStats.some(
      (other, otherIdx) =>
        otherIdx !== i &&
        Math.abs((other.rawAvg ?? -1) - (item.rawAvg ?? -1)) < 1e-9,
    );

    const delta =
      item.rawAvg !== null && item.prevRawAvg !== null
        ? Math.round((item.rawAvg - item.prevRawAvg) * 10) / 10
        : null;

    results.push({
      businessLine: item.businessLine,
      rank: currentRank,
      total: item.productTotal,
      measuredCount: item.summary.measuredProductCount,
      unmeasuredCount: item.summary.unmeasuredProductCount,
      avgScore: item.summary.averageRdhs,
      rawAvgScore: item.rawAvg,
      prevAvgScore: item.prevSummary?.averageRdhs ?? null,
      delta,
      passRate: Math.round(item.summary.complianceRate * 1000) / 10,
      passCount: item.summary.complianceCount,
      isTie,
      lead: item.lead,
      lag: item.lag,
      focus: item.focus,
      compositionChange: item.compositionChange,
    });
  }

  return results;
}

export function buildMonthlyTrend(
  snapshots: RdhsSnapshot[],
  options: { businessLine?: string; throughPeriod?: string } = {},
): TrendPoint[] {
  return snapshots
    .filter(
      (snapshot) =>
        snapshot.cadence === "monthly" &&
        (options.throughPeriod === undefined || snapshot.periodKey <= options.throughPeriod),
    )
    .sort((left, right) => left.periodKey.localeCompare(right.periodKey))
    .map((snapshot) => {
      const products = options.businessLine
        ? snapshot.products.filter((product) => product.businessLine === options.businessLine)
        : snapshot.products;
      return {
        periodKey: snapshot.periodKey,
        asOf: snapshot.asOf,
        ...summarizeProducts(products),
      };
    });
}

export function calculateSublineDistribution(products: ProductMetric[]): SublineStat[] {
  const groups = new Map<string, ProductMetric[]>();
  for (const product of products) {
    const subLine =
      product.subLine && product.subLine.trim().length > 0
        ? product.subLine.trim()
        : "未分二级业务线";
    const list = groups.get(subLine) ?? [];
    list.push(product);
    groups.set(subLine, list);
  }

  const result: SublineStat[] = [];
  for (const [name, prods] of groups.entries()) {
    const summary = summarizeProducts(prods);
    result.push({
      name,
      count: prods.length,
      unmeasuredCount: summary.unmeasuredProductCount,
      averageRdhs: summary.averageRdhs,
      rawAverageRdhs: summary.rawAverageRdhs,
      passCount: summary.complianceCount,
      passRate: Math.round(summary.complianceRate * 1000) / 10,
      keyGovCount: summary.bandCounts.keyGovernance,
    });
  }

  result.sort((a, b) => {
    if (a.name === "未分二级业务线" && b.name !== "未分二级业务线") return 1;
    if (b.name === "未分二级业务线" && a.name !== "未分二级业务线") return -1;
    if (b.count !== a.count) return b.count - a.count;
    return a.name.localeCompare(b.name, "zh-CN");
  });

  return result;
}

export function getLineGovernanceCandidates(
  products: ProductMetric[],
  limit = 3,
): ProductMetric[] {
  return products
    .filter((product) => product.rdhs === null || product.rdhs < 70)
    .sort((a, b) => (a.rdhs ?? -1) - (b.rdhs ?? -1))
    .slice(0, limit);
}
