import { getD1 } from "@/db";
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

function rowToStored(row: SnapshotRow): StoredSnapshot {
  const snapshot = validateSnapshot(JSON.parse(row.snapshot_json));
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

export class D1SnapshotRepository implements SnapshotRepository {
  async save(
    record: Omit<StoredSnapshot, "version" | "isCurrent">,
  ): Promise<SaveSnapshotResult> {
    const d1 = getD1();
    const duplicate = await d1
      .prepare(
        `SELECT id, version FROM rdhs_snapshots
         WHERE cadence = ? AND period_key = ? AND source_sha256 = ?
         LIMIT 1`,
      )
      .bind(record.cadence, record.periodKey, record.snapshot.source.sha256)
      .first<{ id: string; version: number }>();
    if (duplicate) {
      const summary = record.summary;
      await d1
        .prepare(
          `UPDATE rdhs_snapshots SET is_current = 0
           WHERE cadence = ? AND period_key = ? AND is_current = 1`,
        )
        .bind(record.cadence, record.periodKey)
        .run();
      await d1
        .prepare(
          `UPDATE rdhs_snapshots SET
             is_current = 1, as_of = ?, fetched_at = ?, product_total = ?,
             measured_product_count = ?, unmeasured_product_count = ?,
             below_70_count = ?, average_rdhs = ?, measurement_coverage = ?,
             key_governance_count = ?, risk_improvement_count = ?,
             continuous_optimization_count = ?, regular_tracking_count = ?,
             link_closure_average = ?, delivery_closure_average = ?,
             timeliness_average = ?, granularity_average = ?, quality_average = ?,
             conclusion = ?, focus = ?, audit_json = ?, snapshot_json = ?
           WHERE id = ?`,
        )
        .bind(
          record.snapshot.asOf,
          record.snapshot.fetchedAt,
          summary.productTotal,
          summary.measuredProductCount,
          summary.unmeasuredProductCount,
          summary.below70Count,
          summary.averageRdhs,
          summary.measurementCoverage,
          summary.bandCounts.keyGovernance,
          summary.bandCounts.riskImprovement,
          summary.bandCounts.continuousOptimization,
          summary.bandCounts.regularTracking,
          summary.componentAverages.linkClosure,
          summary.componentAverages.deliveryClosure,
          summary.componentAverages.timeliness,
          summary.componentAverages.granularity,
          summary.componentAverages.quality,
          record.snapshot.overview.conclusion,
          record.snapshot.overview.focus,
          JSON.stringify(record.snapshot.audit),
          JSON.stringify(record.snapshot),
          duplicate.id,
        )
        .run();
      return { snapshotId: duplicate.id, version: duplicate.version, created: false };
    }

    const versionRow = await d1
      .prepare(
        `SELECT COALESCE(MAX(version), 0) AS max_version
         FROM rdhs_snapshots WHERE cadence = ? AND period_key = ?`,
      )
      .bind(record.cadence, record.periodKey)
      .first<{ max_version: number }>();
    const version = Number(versionRow?.max_version ?? 0) + 1;
    const summary = record.summary;
    const statements = [
      d1
        .prepare(
          `UPDATE rdhs_snapshots SET is_current = 0
           WHERE cadence = ? AND period_key = ? AND is_current = 1`,
        )
        .bind(record.cadence, record.periodKey),
      d1
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
        .bind(
          record.id,
          record.cadence,
          record.periodKey,
          version,
          record.snapshot.source.sha256,
          record.snapshot.source.chartId,
          record.snapshot.source.chartName,
          record.snapshot.asOf,
          record.snapshot.fetchedAt,
          summary.productTotal,
          summary.measuredProductCount,
          summary.unmeasuredProductCount,
          summary.below70Count,
          summary.averageRdhs,
          summary.measurementCoverage,
          summary.bandCounts.keyGovernance,
          summary.bandCounts.riskImprovement,
          summary.bandCounts.continuousOptimization,
          summary.bandCounts.regularTracking,
          summary.componentAverages.linkClosure,
          summary.componentAverages.deliveryClosure,
          summary.componentAverages.timeliness,
          summary.componentAverages.granularity,
          summary.componentAverages.quality,
          record.snapshot.overview.conclusion,
          record.snapshot.overview.focus,
          JSON.stringify(record.snapshot.audit),
          JSON.stringify(record.snapshot),
        ),
    ];

    for (const line of record.snapshot.businessLines) {
      const lineProducts = record.snapshot.products.filter(
        (product) => product.businessLine === line.businessLine,
      );
      const lineSummary = summarizeSnapshot({ ...record.snapshot, products: lineProducts });
      statements.push(
        d1
          .prepare(
            `INSERT INTO rdhs_business_line_metrics (
               snapshot_id, business_line, product_total, measured_product_count,
               average_rdhs, measurement_coverage, key_governance_count,
               risk_improvement_count, continuous_optimization_count,
               regular_tracking_count, link_closure_average,
               delivery_closure_average, timeliness_average, granularity_average,
               quality_average, mode, focus
             ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          )
          .bind(
            record.id,
            line.businessLine,
            line.productTotal,
            lineSummary.measuredProductCount,
            lineSummary.averageRdhs,
            lineSummary.measurementCoverage,
            line.keyGovernanceCount,
            line.riskImprovementCount,
            line.continuousOptimizationCount,
            line.regularTrackingCount,
            lineSummary.componentAverages.linkClosure,
            lineSummary.componentAverages.deliveryClosure,
            lineSummary.componentAverages.timeliness,
            lineSummary.componentAverages.granularity,
            lineSummary.componentAverages.quality,
            line.mode,
            line.focus,
          ),
      );
    }

    for (const product of record.snapshot.products) {
      statements.push(
        d1
          .prepare(
            `INSERT INTO rdhs_product_metrics (
               snapshot_id, business_line, product, product_status, rdhs,
               governance_band, priority, link_closure, delivery_closure,
               timeliness, granularity, quality, lowest_component, problem, action
             ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          )
          .bind(
            record.id,
            product.businessLine,
            product.product,
            product.productStatus,
            product.rdhs,
            product.governanceBand,
            product.priority,
            product.components.linkClosure,
            product.components.deliveryClosure,
            product.components.timeliness,
            product.components.granularity,
            product.components.quality,
            product.lowestComponent,
            product.problem,
            product.action,
          ),
      );
    }

    await d1.batch(statements);
    return { snapshotId: record.id, version, created: true };
  }

  async getCurrent(cadence: Cadence, periodKey?: string): Promise<StoredSnapshot | null> {
    const d1 = getD1();
    const statement = periodKey
      ? d1
          .prepare(
            `SELECT id, cadence, period_key, version, is_current, snapshot_json
             FROM rdhs_snapshots
             WHERE cadence = ? AND period_key = ? AND is_current = 1 LIMIT 1`,
          )
          .bind(cadence, periodKey)
      : d1
          .prepare(
            `SELECT id, cadence, period_key, version, is_current, snapshot_json
             FROM rdhs_snapshots
             WHERE cadence = ? AND is_current = 1
             ORDER BY period_key DESC LIMIT 1`,
          )
          .bind(cadence);
    const row = await statement.first<SnapshotRow>();
    return row ? rowToStored(row) : null;
  }

  async listCurrent(cadence: Cadence): Promise<StoredSnapshot[]> {
    const results = await getD1()
      .prepare(
        `SELECT id, cadence, period_key, version, is_current, snapshot_json
         FROM rdhs_snapshots WHERE cadence = ? AND is_current = 1
         ORDER BY period_key ASC`,
      )
      .bind(cadence)
      .all<SnapshotRow>();
    return results.results.map(rowToStored);
  }

  async listPeriods(cadence: Cadence): Promise<StoredSnapshot[]> {
    const results = await getD1()
      .prepare(
        `SELECT id, cadence, period_key, version, is_current, snapshot_json
         FROM rdhs_snapshots WHERE cadence = ? AND is_current = 1
         ORDER BY period_key DESC`,
      )
      .bind(cadence)
      .all<SnapshotRow>();
    return results.results.map(rowToStored);
  }

  async recordFailure(input: unknown, error: string): Promise<void> {
    const candidate =
      typeof input === "object" && input !== null ? (input as Record<string, unknown>) : {};
    const source =
      typeof candidate.source === "object" && candidate.source !== null
        ? (candidate.source as Record<string, unknown>)
        : {};
    await getD1()
      .prepare(
        `INSERT INTO rdhs_ingest_failures (cadence, period_key, source_sha256, error)
         VALUES (?, ?, ?, ?)`,
      )
      .bind(
        typeof candidate.cadence === "string" ? candidate.cadence : null,
        typeof candidate.periodKey === "string" ? candidate.periodKey : null,
        typeof source.sha256 === "string" ? source.sha256 : null,
        error,
      )
      .run();
  }
}
