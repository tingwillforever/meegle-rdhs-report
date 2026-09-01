import type {
  BandCounts,
  ComponentScores,
  GovernanceBand,
  RdhsSnapshot,
  SnapshotSummary,
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

export function summarizeSnapshot(snapshot: RdhsSnapshot): SnapshotSummary {
  const measuredScores = snapshot.products.flatMap((product) =>
    product.rdhs === null ? [] : [product.rdhs],
  );
  const productTotal = snapshot.products.length;
  const bandCounts: BandCounts = {
    keyGovernance: 0,
    riskImprovement: 0,
    continuousOptimization: 0,
    regularTracking: 0,
  };

  for (const product of snapshot.products) {
    if (product.governanceBand === "重点治理") bandCounts.keyGovernance += 1;
    if (product.governanceBand === "风险改进") bandCounts.riskImprovement += 1;
    if (product.governanceBand === "持续优化") bandCounts.continuousOptimization += 1;
    if (product.governanceBand === "常规跟踪") bandCounts.regularTracking += 1;
  }

  const componentAverages = Object.fromEntries(
    COMPONENT_KEYS.map((key) => [
      key,
      average(
        snapshot.products.flatMap((product) => {
          const value = product.components[key];
          return value === null ? [] : [value];
        }),
      ),
    ]),
  ) as ComponentScores;

  return {
    productTotal,
    measuredProductCount: measuredScores.length,
    unmeasuredProductCount: productTotal - measuredScores.length,
    below70Count: snapshot.products.filter(
      (product) => product.rdhs === null || product.rdhs < 70,
    ).length,
    complianceCount: bandCounts.regularTracking,
    pendingGovernanceCount: productTotal - bandCounts.regularTracking,
    averageRdhs: average(measuredScores),
    measurementCoverage:
      productTotal === 0 ? 0 : measuredScores.length / productTotal,
    complianceRate:
      productTotal === 0 ? 0 : bandCounts.regularTracking / productTotal,
    pendingGovernanceRate:
      productTotal === 0 ? 0 : (productTotal - bandCounts.regularTracking) / productTotal,
    bandCounts,
    componentAverages,
  };
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
    .map((snapshot) => ({
      periodKey: snapshot.periodKey,
      asOf: snapshot.asOf,
      ...summarizeSnapshot({
        ...snapshot,
        products: options.businessLine
          ? snapshot.products.filter((product) => product.businessLine === options.businessLine)
          : snapshot.products,
      }),
    }));
}
