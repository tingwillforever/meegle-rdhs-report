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

export type ProductMetric = {
  businessLine: string;
  product: string;
  productStatus: "研发中";
  rdhs: number | null;
  governanceBand: GovernanceBand;
  priority: Priority;
  components: ComponentScores;
  lowestComponent: string;
  problem: string;
  action: string;
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
  measurementCoverage: number;
  complianceRate: number;
  pendingGovernanceRate: number;
  bandCounts: BandCounts;
  componentAverages: ComponentScores;
};

export type TrendPoint = SnapshotSummary & {
  periodKey: string;
  asOf: string;
};
