import { sql } from "drizzle-orm";
import {
  index,
  integer,
  real,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

export const rdhsSnapshots = sqliteTable(
  "rdhs_snapshots",
  {
    id: text("id").primaryKey(),
    cadence: text("cadence", { enum: ["weekly", "monthly"] }).notNull(),
    periodKey: text("period_key").notNull(),
    version: integer("version").notNull(),
    isCurrent: integer("is_current", { mode: "boolean" }).notNull().default(false),
    sourceSha256: text("source_sha256").notNull(),
    sourceChartId: text("source_chart_id").notNull(),
    sourceChartName: text("source_chart_name").notNull(),
    asOf: text("as_of").notNull(),
    fetchedAt: text("fetched_at").notNull(),
    productTotal: integer("product_total").notNull(),
    measuredProductCount: integer("measured_product_count").notNull(),
    unmeasuredProductCount: integer("unmeasured_product_count").notNull(),
    below70Count: integer("below_70_count").notNull(),
    averageRdhs: real("average_rdhs"),
    measurementCoverage: real("measurement_coverage").notNull(),
    keyGovernanceCount: integer("key_governance_count").notNull(),
    riskImprovementCount: integer("risk_improvement_count").notNull(),
    continuousOptimizationCount: integer("continuous_optimization_count").notNull(),
    regularTrackingCount: integer("regular_tracking_count").notNull(),
    linkClosureAverage: real("link_closure_average"),
    deliveryClosureAverage: real("delivery_closure_average"),
    timelinessAverage: real("timeliness_average"),
    granularityAverage: real("granularity_average"),
    qualityAverage: real("quality_average"),
    conclusion: text("conclusion").notNull(),
    focus: text("focus").notNull(),
    auditJson: text("audit_json").notNull(),
    snapshotJson: text("snapshot_json").notNull(),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    uniqueIndex("uq_rdhs_snapshots_period").on(
      table.cadence,
      table.periodKey,
    ),
    index("idx_rdhs_snapshots_current_period").on(
      table.cadence,
      table.isCurrent,
      table.periodKey,
    ),
  ],
);

export const businessLineMetrics = sqliteTable(
  "rdhs_business_line_metrics",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    snapshotId: text("snapshot_id")
      .notNull()
      .references(() => rdhsSnapshots.id, { onDelete: "cascade" }),
    businessLine: text("business_line").notNull(),
    productTotal: integer("product_total").notNull(),
    measuredProductCount: integer("measured_product_count").notNull(),
    averageRdhs: real("average_rdhs"),
    measurementCoverage: real("measurement_coverage").notNull(),
    keyGovernanceCount: integer("key_governance_count").notNull(),
    riskImprovementCount: integer("risk_improvement_count").notNull(),
    continuousOptimizationCount: integer("continuous_optimization_count").notNull(),
    regularTrackingCount: integer("regular_tracking_count").notNull(),
    linkClosureAverage: real("link_closure_average"),
    deliveryClosureAverage: real("delivery_closure_average"),
    timelinessAverage: real("timeliness_average"),
    granularityAverage: real("granularity_average"),
    qualityAverage: real("quality_average"),
    mode: text("mode").notNull(),
    focus: text("focus").notNull(),
  },
  (table) => [
    uniqueIndex("uq_rdhs_business_line_snapshot").on(table.snapshotId, table.businessLine),
  ],
);

export const productMetrics = sqliteTable(
  "rdhs_product_metrics",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    snapshotId: text("snapshot_id")
      .notNull()
      .references(() => rdhsSnapshots.id, { onDelete: "cascade" }),
    businessLine: text("business_line").notNull(),
    product: text("product").notNull(),
    productStatus: text("product_status").notNull(),
    rdhs: real("rdhs"),
    governanceBand: text("governance_band").notNull(),
    priority: text("priority"),
    linkClosure: real("link_closure"),
    deliveryClosure: real("delivery_closure"),
    timeliness: real("timeliness"),
    granularity: real("granularity"),
    quality: real("quality"),
    lowestComponent: text("lowest_component").notNull(),
    problem: text("problem").notNull(),
    action: text("action").notNull(),
  },
  (table) => [
    uniqueIndex("uq_rdhs_product_snapshot").on(
      table.snapshotId,
      table.businessLine,
      table.product,
    ),
    index("idx_rdhs_product_line").on(table.snapshotId, table.businessLine),
    index("idx_rdhs_product_band").on(table.snapshotId, table.governanceBand),
  ],
);

export const ingestFailures = sqliteTable(
  "rdhs_ingest_failures",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    cadence: text("cadence"),
    periodKey: text("period_key"),
    sourceSha256: text("source_sha256"),
    error: text("error").notNull(),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [index("idx_rdhs_ingest_failures_created").on(table.createdAt)],
);
