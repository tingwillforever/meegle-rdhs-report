export type Cadence = "monthly";

export type GovernanceBand =
  | "重点治理"
  | "风险改进"
  | "持续优化"
  | "常规跟踪";

export type Priority = "P0" | "P1" | "P2" | null;

export type ComponentScores = {
  linkClosure: number | null;
  deliveryClosure: number | null;
  timeliness: number | null;
  granularity: number | null;
  quality: number | null;
};

export type DependencyMetricTone = "critical" | "risk" | "track" | "neutral";

export type ProductDependencyMetric = {
  label: string;
  value: number | null;
  unit: string;
  tone: DependencyMetricTone;
};

export type ProductMetric = {
  businessLine: string;
  subLine: string | null;
  product: string;
  productStatus: "研发中";
  rdhs: number | null;
  governanceBand: GovernanceBand;
  priority: Priority;
  components: ComponentScores;
  dependencyMetrics: ProductDependencyMetric[];
  lowestComponent: string;
  problem: string;
  action: string;
  prodRep?: string | null;
  pmRep?: string | null;
};

export type BusinessLineMetric = {
  businessLine: string;
  productTotal: number;
  keyGovernanceCount: number;
  riskImprovementCount: number;
  continuousOptimizationCount: number;
  regularTrackingCount: number;
  mode: GovernanceBand;
  focus: string;
};

export type SnapshotAudit = {
  rawRowCount: number;
  acceptedRowCount: number;
  zeroScoreRowCount: number;
  emptyDimensionRowCount: number;
  researchProductCount: number;
  measuredProductCount: number;
  unmeasuredProductCount: number;
  excludedTestBusinessLineCount: number;
  excludedProductAttributeCount: number;
  status: "validated";
  warning: string | null;
};

export type RdhsSnapshot = {
  schemaVersion: 1;
  cadence: Cadence;
  periodKey: string;
  asOf: string;
  fetchedAt: string;
  source: {
    chartId: string;
    chartName: string;
    sha256: string;
  };
  audit: SnapshotAudit;
  overview: {
    conclusion: string;
    focus: string;
  };
  businessLines: BusinessLineMetric[];
  products: ProductMetric[];
};

export type BandCounts = {
  keyGovernance: number;
  riskImprovement: number;
  continuousOptimization: number;
  regularTracking: number;
};

export type SnapshotSummary = {
  productTotal: number;
  measuredProductCount: number;
  unmeasuredProductCount: number;
  below70Count: number;
  complianceCount: number;
  pendingGovernanceCount: number;
  averageRdhs: number | null;
  rawAverageRdhs: number | null;
  measurementCoverage: number;
  complianceRate: number;
  pendingGovernanceRate: number;
  bandCounts: BandCounts;
  componentAverages: ComponentScores;
};

export type CompositionChange = {
  hasChanged: boolean;
  addedCount: number;
  removedCount: number;
  addedNames: string[];
  removedNames: string[];
  currentCount: number;
  previousCount: number;
};

export type BusinessLineRankingItem = {
  businessLine: string;
  rank: number;
  total: number;
  measuredCount: number;
  unmeasuredCount: number;
  avgScore: number | null;
  rawAvgScore: number | null;
  prevAvgScore: number | null;
  delta: number | null;
  passRate: number;
  passCount: number;
  isTie: boolean;
  lead: string;
  lag: string;
  focus: string;
  compositionChange?: CompositionChange | null;
};

export type SublineStat = {
  name: string;
  count: number;
  unmeasuredCount: number;
  averageRdhs: number | null;
  rawAverageRdhs: number | null;
  passCount: number;
  passRate: number;
  keyGovCount: number;
};

export type TrendPoint = SnapshotSummary & {
  periodKey: string;
  asOf: string;
};

export type FocusLineItem = {
  name: string;
  unmeasuredCount: number;
  keyGovCount: number;
  productTotal: number;
  avgScore: number;
  lowest: string;
  focus: string;
  priority: "P0" | "P1" | "P2";
};

