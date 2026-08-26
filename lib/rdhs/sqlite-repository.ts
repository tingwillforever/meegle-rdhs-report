import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { DatabaseSync } from "node:sqlite";

import { summarizeSnapshot } from "./aggregate.ts";
import type { Cadence } from "./types.ts";
import type {
  SaveSnapshotResult,
  SnapshotRepository,
  StoredSnapshot,
} from "./repository.ts";
import { validateSnapshot } from "./validate.ts";

type SnapshotRow = {
  id: string;
  cadence: Cadence;
  period_key: string;
  version: number;
  is_current: number;
  snapshot_json: string;
};

const SQLITE_SCHEMA = `
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
CREATE TABLE IF NOT EXISTS rdhs_snapshots (
  id TEXT PRIMARY KEY NOT NULL,
  cadence TEXT NOT NULL,
  period_key TEXT NOT NULL,
  version INTEGER NOT NULL,
  is_current INTEGER NOT NULL DEFAULT 0,
  source_sha256 TEXT NOT NULL,
  source_chart_id TEXT NOT NULL,
  source_chart_name TEXT NOT NULL,
  as_of TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  product_total INTEGER NOT NULL,
  measured_product_count INTEGER NOT NULL,
  unmeasured_product_count INTEGER NOT NULL,
  below_70_count INTEGER NOT NULL,
  average_rdhs REAL,
  measurement_coverage REAL NOT NULL,
  key_governance_count INTEGER NOT NULL,
  risk_improvement_count INTEGER NOT NULL,
  continuous_optimization_count INTEGER NOT NULL,
  regular_tracking_count INTEGER NOT NULL,
  link_closure_average REAL,
  delivery_closure_average REAL,
  timeliness_average REAL,
  granularity_average REAL,
  quality_average REAL,
  conclusion TEXT NOT NULL,
  focus TEXT NOT NULL,
  audit_json TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (cadence, period_key)
);
CREATE INDEX IF NOT EXISTS idx_rdhs_snapshots_current_period
  ON rdhs_snapshots (cadence, is_current, period_key);
CREATE TABLE IF NOT EXISTS rdhs_business_line_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id TEXT NOT NULL REFERENCES rdhs_snapshots(id) ON DELETE CASCADE,
  business_line TEXT NOT NULL,
  product_total INTEGER NOT NULL,
  measured_product_count INTEGER NOT NULL,
  average_rdhs REAL,
  measurement_coverage REAL NOT NULL,
  key_governance_count INTEGER NOT NULL,
  risk_improvement_count INTEGER NOT NULL,
  continuous_optimization_count INTEGER NOT NULL,
  regular_tracking_count INTEGER NOT NULL,
  link_closure_average REAL,
  delivery_closure_average REAL,
  timeliness_average REAL,
  granularity_average REAL,
  quality_average REAL,
  mode TEXT NOT NULL,
  focus TEXT NOT NULL,
  UNIQUE (snapshot_id, business_line)
);
CREATE TABLE IF NOT EXISTS rdhs_product_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id TEXT NOT NULL REFERENCES rdhs_snapshots(id) ON DELETE CASCADE,
  business_line TEXT NOT NULL,
  product TEXT NOT NULL,
  product_status TEXT NOT NULL,
  rdhs REAL,
  governance_band TEXT NOT NULL,
  priority TEXT,
  link_closure REAL,
  delivery_closure REAL,
  timeliness REAL,
  granularity REAL,
  quality REAL,
  lowest_component TEXT NOT NULL,
  problem TEXT NOT NULL,
  action TEXT NOT NULL,
  UNIQUE (snapshot_id, business_line, product)
);
CREATE TABLE IF NOT EXISTS rdhs_ingest_failures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cadence TEXT,
  period_key TEXT,
  source_sha256 TEXT,
  error TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rdhs_ingest_failures_created
  ON rdhs_ingest_failures (created_at);
`;

function rowToStored(row: SnapshotRow): StoredSnapshot {
  const snapshot = validateSnapshot(JSON.parse(row.snapshot_json) as unknown);
  return {
    id: row.id,
    cadence: row.cadence,
    periodKey: row.period_key,
    version: row.version,
    isCurrent: row.is_current === 1,
    snapshot,
    summary: summarizeSnapshot(snapshot),
  };
}

function valueOrNull(value: number | null): number | null {
  return value;
}

export class SQLiteSnapshotRepository implements SnapshotRepository {
  private readonly database: DatabaseSync;

  constructor(databasePath = process.env.RDHS_DB_PATH || "./runtime/rdhs.sqlite") {
    if (databasePath !== ":memory:") {
      mkdirSync(dirname(databasePath), { recursive: true });
    }
    this.database = new DatabaseSync(databasePath);
    this.database.exec(SQLITE_SCHEMA);
  }

  async save(
    record: Omit<StoredSnapshot, "version" | "isCurrent">,
  ): Promise<SaveSnapshotResult> {
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const existing = this.database
        .prepare(
          `SELECT id, version FROM rdhs_snapshots
           WHERE cadence = ? AND period_key = ? LIMIT 1`,
        )
        .get(record.cadence, record.periodKey) as
        | { id: string; version: number }
        | undefined;

      if (existing) {
        this.updateSnapshot(existing.id, record);
        this.database.exec("COMMIT");
        return { snapshotId: existing.id, version: existing.version, created: false };
      }
      this.insertSnapshot(record, 1);
      this.database.exec("COMMIT");
      return { snapshotId: record.id, version: 1, created: true };
    } catch (error) {
      this.database.exec("ROLLBACK");
      throw error;
    }
  }

  async getCurrent(cadence: Cadence, periodKey?: string): Promise<StoredSnapshot | null> {
    const statement = periodKey
      ? this.database
          .prepare(
            `SELECT id, cadence, period_key, version, is_current, snapshot_json
             FROM rdhs_snapshots
             WHERE cadence = ? AND period_key = ? AND is_current = 1 LIMIT 1`,
          )
          .get(cadence, periodKey)
      : this.database
          .prepare(
            `SELECT id, cadence, period_key, version, is_current, snapshot_json
             FROM rdhs_snapshots
             WHERE cadence = ? AND is_current = 1
             ORDER BY period_key DESC LIMIT 1`,
          )
          .get(cadence);
    return statement ? rowToStored(statement as SnapshotRow) : null;
  }

  async listCurrent(cadence: Cadence): Promise<StoredSnapshot[]> {
    const rows = this.database
      .prepare(
        `SELECT id, cadence, period_key, version, is_current, snapshot_json
         FROM rdhs_snapshots WHERE cadence = ? AND is_current = 1
         ORDER BY period_key ASC`,
      )
      .all(cadence) as unknown as SnapshotRow[];
    return rows.map(rowToStored);
  }

  async listPeriods(cadence: Cadence): Promise<StoredSnapshot[]> {
    const rows = this.database
      .prepare(
        `SELECT id, cadence, period_key, version, is_current, snapshot_json
         FROM rdhs_snapshots WHERE cadence = ? AND is_current = 1
         ORDER BY period_key DESC`,
      )
      .all(cadence) as unknown as SnapshotRow[];
    return rows.map(rowToStored);
  }

  async recordFailure(input: unknown, error: string): Promise<void> {
    const candidate =
      typeof input === "object" && input !== null ? (input as Record<string, unknown>) : {};
    const source =
      typeof candidate.source === "object" && candidate.source !== null
        ? (candidate.source as Record<string, unknown>)
        : {};
    this.database
      .prepare(
        `INSERT INTO rdhs_ingest_failures (cadence, period_key, source_sha256, error)
         VALUES (?, ?, ?, ?)`,
      )
      .run(
        typeof candidate.cadence === "string" ? candidate.cadence : null,
        typeof candidate.periodKey === "string" ? candidate.periodKey : null,
        typeof source.sha256 === "string" ? source.sha256 : null,
        error,
      );
  }

  private insertSnapshot(
    record: Omit<StoredSnapshot, "version" | "isCurrent">,
    version: number,
  ): void {
    const snapshot = record.snapshot;
    const summary = record.summary;
    this.database
      .prepare(
        `INSERT INTO rdhs_snapshots (
           id, cadence, period_key, version, is_current,
           source_sha256, source_chart_id, source_chart_name, as_of, fetched_at,
           product_total, measured_product_count, unmeasured_product_count,
           below_70_count, average_rdhs, measurement_coverage,
           key_governance_count, risk_improvement_count,
           continuous_optimization_count, regular_tracking_count,
           link_closure_average, delivery_closure_average, timeliness_average,
           granularity_average, quality_average, conclusion, focus,
           audit_json, snapshot_json
         ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(
        record.id,
        record.cadence,
        record.periodKey,
        version,
        snapshot.source.sha256,
        snapshot.source.chartId,
        snapshot.source.chartName,
        snapshot.asOf,
        snapshot.fetchedAt,
        summary.productTotal,
        summary.measuredProductCount,
        summary.unmeasuredProductCount,
        summary.below70Count,
        valueOrNull(summary.averageRdhs),
        summary.measurementCoverage,
        summary.bandCounts.keyGovernance,
        summary.bandCounts.riskImprovement,
        summary.bandCounts.continuousOptimization,
        summary.bandCounts.regularTracking,
        valueOrNull(summary.componentAverages.linkClosure),
        valueOrNull(summary.componentAverages.deliveryClosure),
        valueOrNull(summary.componentAverages.timeliness),
        valueOrNull(summary.componentAverages.granularity),
        valueOrNull(summary.componentAverages.quality),
        snapshot.overview.conclusion,
        snapshot.overview.focus,
        JSON.stringify(snapshot.audit),
        JSON.stringify(snapshot),
      );

  }

  private updateSnapshot(
    id: string,
    record: Omit<StoredSnapshot, "version" | "isCurrent">,
  ): void {
    const snapshot = record.snapshot;
    const summary = record.summary;
    this.database
      .prepare(
        `UPDATE rdhs_snapshots SET
           is_current = 1, source_sha256 = ?, source_chart_id = ?, source_chart_name = ?,
           as_of = ?, fetched_at = ?, product_total = ?,
           measured_product_count = ?, unmeasured_product_count = ?,
           below_70_count = ?, average_rdhs = ?, measurement_coverage = ?,
           key_governance_count = ?, risk_improvement_count = ?,
           continuous_optimization_count = ?, regular_tracking_count = ?,
           link_closure_average = ?, delivery_closure_average = ?,
           timeliness_average = ?, granularity_average = ?, quality_average = ?,
           conclusion = ?, focus = ?, audit_json = ?, snapshot_json = ?
         WHERE id = ?`,
      )
      .run(
        snapshot.source.sha256,
        snapshot.source.chartId,
        snapshot.source.chartName,
        snapshot.asOf,
        snapshot.fetchedAt,
        summary.productTotal,
        summary.measuredProductCount,
        summary.unmeasuredProductCount,
        summary.below70Count,
        valueOrNull(summary.averageRdhs),
        summary.measurementCoverage,
        summary.bandCounts.keyGovernance,
        summary.bandCounts.riskImprovement,
        summary.bandCounts.continuousOptimization,
        summary.bandCounts.regularTracking,
        valueOrNull(summary.componentAverages.linkClosure),
        valueOrNull(summary.componentAverages.deliveryClosure),
        valueOrNull(summary.componentAverages.timeliness),
        valueOrNull(summary.componentAverages.granularity),
        valueOrNull(summary.componentAverages.quality),
        snapshot.overview.conclusion,
        snapshot.overview.focus,
        JSON.stringify(snapshot.audit),
        JSON.stringify(snapshot),
        id,
      );
  }
}
