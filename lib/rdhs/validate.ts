import { governanceBandForScore } from "./aggregate.ts";
import type {
  BusinessLineMetric,
  ComponentScores,
  DependencyMetricTone,
  GovernanceBand,
  Priority,
  ProductDependencyMetric,
  ProductMetric,
  RdhsSnapshot,
  SnapshotAudit,
} from "./types.ts";

function fail(path: string, message: string): never {
  throw new Error(`${path}: ${message}`);
}

function objectAt(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(path, "must be an object");
  }
  return value as Record<string, unknown>;
}

function stringAt(value: unknown, path: string, allowEmpty = false): string {
  if (typeof value !== "string" || (!allowEmpty && value.trim() === "")) {
    fail(path, "must be a non-empty string");
  }
  return value;
}

function optionalStringAt(value: unknown, path: string): string | null {
  if (value === undefined || value === null || value === "") return null;
  if (typeof value !== "string") fail(path, "must be a string or null");
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function countAt(value: unknown, path: string): number {
  if (!Number.isInteger(value) || (value as number) < 0) {
    fail(path, "must be a non-negative integer");
  }
  return value as number;
}

function scoreAt(value: unknown, path: string, maximum: number): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > maximum) {
    fail(path, `must be null or a finite number from 0 to ${maximum}`);
  }
  return value;
}

function governanceBandAt(value: unknown, path: string): GovernanceBand {
  if (!(["重点治理", "风险改进", "持续优化", "常规跟踪"] as unknown[]).includes(value)) {
    fail(path, "has an unknown governance band");
  }
  return value as GovernanceBand;
}

function priorityAt(value: unknown, path: string): Priority {
  if (value !== null && value !== "P0" && value !== "P1" && value !== "P2") {
    fail(path, "must be P0, P1, P2, or null");
  }
  return value as Priority;
}

function componentsAt(value: unknown, path: string): ComponentScores {
  const input = objectAt(value, path);
  return {
    linkClosure: scoreAt(input.linkClosure, `${path}.linkClosure`, 25),
    deliveryClosure: scoreAt(input.deliveryClosure, `${path}.deliveryClosure`, 15),
    timeliness: scoreAt(input.timeliness, `${path}.timeliness`, 20),
    granularity: scoreAt(input.granularity, `${path}.granularity`, 20),
    quality: scoreAt(input.quality, `${path}.quality`, 20),
  };
}

function dependencyMetricToneAt(value: unknown, path: string): DependencyMetricTone {
  if (!(["critical", "risk", "track", "neutral"] as unknown[]).includes(value)) {
    fail(path, "has an unknown dependency metric tone");
  }
  return value as DependencyMetricTone;
}

function finiteNumberOrNullAt(value: unknown, path: string): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail(path, "must be null or a finite number");
  }
  return value;
}

function dependencyMetricAt(value: unknown, path: string): ProductDependencyMetric {
  const input = objectAt(value, path);
  return {
    label: stringAt(input.label, `${path}.label`),
    value: finiteNumberOrNullAt(input.value, `${path}.value`),
    unit: stringAt(input.unit, `${path}.unit`, true),
    tone: dependencyMetricToneAt(input.tone, `${path}.tone`),
  };
}

function dependencyMetricsAt(value: unknown, path: string): ProductDependencyMetric[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) fail(path, "must be an array");
  return value.map((metric, index) => dependencyMetricAt(metric, `${path}[${index}]`));
}

function productAt(value: unknown, index: number): ProductMetric {
  const path = `products[${index}]`;
  const input = objectAt(value, path);
  const businessLine = stringAt(input.businessLine, `${path}.businessLine`);
  if (businessLine === "测试业务线") fail(`${path}.businessLine`, "测试业务线 is excluded");
  const rdhs = scoreAt(input.rdhs, `${path}.rdhs`, 100);
  const governanceBand = governanceBandAt(input.governanceBand, `${path}.governanceBand`);
  const expectedBand = governanceBandForScore(rdhs);
  if (governanceBand !== expectedBand) {
    fail(`${path}.governanceBand`, `expected ${expectedBand} for RDHS ${rdhs}`);
  }
  if (input.productStatus !== "研发中") fail(`${path}.productStatus`, "must be 研发中");
  return {
    businessLine,
    subLine: optionalStringAt(input.subLine, `${path}.subLine`),
    product: stringAt(input.product, `${path}.product`),
    productStatus: "研发中",
    rdhs,
    governanceBand,
    priority: priorityAt(input.priority, `${path}.priority`),
    components: componentsAt(input.components, `${path}.components`),
    dependencyMetrics: dependencyMetricsAt(input.dependencyMetrics, `${path}.dependencyMetrics`),
    lowestComponent: stringAt(input.lowestComponent, `${path}.lowestComponent`),
    problem: stringAt(input.problem, `${path}.problem`),
    action: stringAt(input.action, `${path}.action`),
  };
}

function businessLineAt(value: unknown, index: number): BusinessLineMetric {
  const path = `businessLines[${index}]`;
  const input = objectAt(value, path);
  const row: BusinessLineMetric = {
    businessLine: stringAt(input.businessLine, `${path}.businessLine`),
    productTotal: countAt(input.productTotal, `${path}.productTotal`),
    keyGovernanceCount: countAt(input.keyGovernanceCount, `${path}.keyGovernanceCount`),
    riskImprovementCount: countAt(input.riskImprovementCount, `${path}.riskImprovementCount`),
    continuousOptimizationCount: countAt(
      input.continuousOptimizationCount,
      `${path}.continuousOptimizationCount`,
    ),
    regularTrackingCount: countAt(input.regularTrackingCount, `${path}.regularTrackingCount`),
    mode: governanceBandAt(input.mode, `${path}.mode`),
    focus: stringAt(input.focus, `${path}.focus`),
  };
  const bandTotal =
    row.keyGovernanceCount +
    row.riskImprovementCount +
    row.continuousOptimizationCount +
    row.regularTrackingCount;
  if (bandTotal !== row.productTotal) {
    fail(path, `band counts ${bandTotal} do not equal productTotal ${row.productTotal}`);
  }
  return row;
}

function auditAt(value: unknown): SnapshotAudit {
  const input = objectAt(value, "audit");
  if (input.status !== "validated") fail("audit.status", "must be validated");
  return {
    rawRowCount: countAt(input.rawRowCount, "audit.rawRowCount"),
    acceptedRowCount: countAt(input.acceptedRowCount, "audit.acceptedRowCount"),
    zeroScoreRowCount: countAt(input.zeroScoreRowCount, "audit.zeroScoreRowCount"),
    emptyDimensionRowCount: countAt(
      input.emptyDimensionRowCount,
      "audit.emptyDimensionRowCount",
    ),
    researchProductCount: countAt(input.researchProductCount, "audit.researchProductCount"),
    measuredProductCount: countAt(input.measuredProductCount, "audit.measuredProductCount"),
    unmeasuredProductCount: countAt(
      input.unmeasuredProductCount,
      "audit.unmeasuredProductCount",
    ),
    excludedTestBusinessLineCount: countAt(
      input.excludedTestBusinessLineCount,
      "audit.excludedTestBusinessLineCount",
    ),
    excludedProductAttributeCount: countAt(
      input.excludedProductAttributeCount ?? 0,
      "audit.excludedProductAttributeCount",
    ),
    status: "validated",
    warning:
      input.warning === null ? null : stringAt(input.warning, "audit.warning", true),
  };
}

export function validateSnapshot(value: unknown): RdhsSnapshot {
  const input = objectAt(value, "snapshot");
  if (input.schemaVersion !== 1) fail("schemaVersion", "must equal 1");
  if (input.cadence !== "monthly") {
    fail("cadence", "must be monthly");
  }
  const cadence = input.cadence;
  const periodKey = stringAt(input.periodKey, "periodKey");
  if (!/^\d{4}-\d{2}$/.test(periodKey)) fail("periodKey", "invalid monthly period");

  const sourceInput = objectAt(input.source, "source");
  const sha256 = stringAt(sourceInput.sha256, "source.sha256");
  if (!/^[a-f0-9]{64}$/i.test(sha256)) fail("source.sha256", "must be a SHA-256 hex digest");

  if (!Array.isArray(input.products)) fail("products", "must be an array");
  if (!Array.isArray(input.businessLines)) fail("businessLines", "must be an array");
  const products = input.products.map(productAt);
  const businessLines = input.businessLines.map(businessLineAt);
  const audit = auditAt(input.audit);

  const seenProducts = new Set<string>();
  for (const product of products) {
    const key = `${product.businessLine}\u0000${product.product}`;
    if (seenProducts.has(key)) fail("products", `duplicate key ${product.businessLine} / ${product.product}`);
    seenProducts.add(key);
  }
  const seenLines = new Set<string>();
  for (let index = 0; index < businessLines.length; index += 1) {
    const line = businessLines[index];
    if (seenLines.has(line.businessLine)) fail(`businessLines[${index}]`, "duplicate business line");
    seenLines.add(line.businessLine);
    const lineProducts = products.filter((product) => product.businessLine === line.businessLine);
    if (lineProducts.length !== line.productTotal) {
      fail(`businessLines[${index}]`, `productTotal does not match ${lineProducts.length} products`);
    }
  }

  const measured = products.filter((product) => product.rdhs !== null).length;
  if (audit.researchProductCount !== products.length) {
    fail("audit.researchProductCount", `expected ${products.length}`);
  }
  if (audit.measuredProductCount !== measured) {
    fail("audit.measuredProductCount", `expected ${measured}`);
  }
  if (audit.unmeasuredProductCount !== products.length - measured) {
    fail("audit.unmeasuredProductCount", `expected ${products.length - measured}`);
  }

  const overviewInput = objectAt(input.overview, "overview");
  return {
    schemaVersion: 1,
    cadence,
    periodKey,
    asOf: stringAt(input.asOf, "asOf"),
    fetchedAt: stringAt(input.fetchedAt, "fetchedAt"),
    source: {
      chartId: stringAt(sourceInput.chartId, "source.chartId"),
      chartName: stringAt(sourceInput.chartName, "source.chartName"),
      sha256,
    },
    audit,
    overview: {
      conclusion: stringAt(overviewInput.conclusion, "overview.conclusion"),
      focus: stringAt(overviewInput.focus, "overview.focus"),
    },
    businessLines,
    products,
  };
}
