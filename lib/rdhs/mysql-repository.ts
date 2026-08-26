import { createPool, type PoolOptions } from "mysql2/promise";

import { summarizeSnapshot } from "./aggregate.ts";
import type {
  SaveSnapshotResult,
  SnapshotRepository,
  StoredSnapshot,
} from "./repository.ts";
import { hasCoverageRegression } from "./repository.ts";
import type { Cadence } from "./types.ts";
import { validateSnapshot } from "./validate.ts";

type QueryResult = [unknown, unknown];

type Executor = {
  execute(sql: string, values?: unknown[]): Promise<QueryResult>;
};

type Connection = Executor & {
  beginTransaction(): Promise<void>;
  commit(): Promise<void>;
  rollback(): Promise<void>;
  release(): void;
};

type PoolLike = Executor & {
  getConnection?(): Promise<Connection>;
};

type SnapshotRow = {
  id: string;
  cadence: Cadence;
  period_key: string;
  version: number;
  is_current: number | boolean;
  snapshot_json: string | Record<string, unknown>;
};

export type SyncBaseline = {
  periodKey: string;
  payload: Record<string, unknown>;
  metadata: Record<string, unknown>;
  updatedAt?: string;
};

export type LeaseResult = {
  acquired: boolean;
  name: string;
  owner: string;
  expiresAt: string;
};

let sharedPool: PoolLike | null = null;

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required for MySQL storage`);
  return value;
}

function mysqlPort(): number {
  const value = Number(process.env.MYSQL_PORT || "3306");
  if (!Number.isInteger(value) || value < 1 || value > 65535) {
    throw new Error("MYSQL_PORT must be an integer between 1 and 65535");
  }
  return value;
}

export function createMySQLPool(): PoolLike {
  if (sharedPool) return sharedPool;
  const tlsEnabled = process.env.MYSQL_TLS === "true";
  const options: PoolOptions = {
    host: requiredEnvironment("MYSQL_HOST"),
    port: mysqlPort(),
    user: requiredEnvironment("MYSQL_USER"),
    password: requiredEnvironment("MYSQL_PASSWORD"),
    database: requiredEnvironment("MYSQL_DATABASE"),
    charset: "utf8mb4",
    timezone: "Z",
    waitForConnections: true,
    connectionLimit: Number(process.env.MYSQL_CONNECTION_LIMIT || "10"),
    enableKeepAlive: true,
    keepAliveInitialDelay: 10_000,
    ssl: tlsEnabled
      ? { rejectUnauthorized: process.env.MYSQL_TLS_REJECT_UNAUTHORIZED !== "false" }
      : undefined,
  };
  sharedPool = createPool(options) as unknown as PoolLike;
  return sharedPool;
}

function rows(result: QueryResult): Record<string, unknown>[] {
  return Array.isArray(result[0]) ? result[0] as Record<string, unknown>[] : [];
}

function resultHeader(result: QueryResult): { affectedRows?: number } {
  return typeof result[0] === "object" && result[0] !== null
    ? result[0] as { affectedRows?: number }
    : {};
}

function jsonObject(value: unknown, label: string): Record<string, unknown> {
  const parsed = typeof value === "string" ? JSON.parse(value) as unknown : value;
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(`${label} is not a JSON object`);
  }
  return parsed as Record<string, unknown>;
}

function rowToStored(row: SnapshotRow): StoredSnapshot {
  const payload = typeof row.snapshot_json === "string"
    ? JSON.parse(row.snapshot_json) as unknown
    : row.snapshot_json;
  const snapshot = validateSnapshot(payload);
  return {
    id: row.id,
    cadence: row.cadence,
    periodKey: row.period_key,
    version: Number(row.version),
    isCurrent: row.is_current === 1 || row.is_current === true,
    snapshot,
    summary: summarizeSnapshot(snapshot),
  };
}

function requireConnection(pool: PoolLike): Promise<Connection> {
  if (!pool.getConnection) throw new Error("MySQL pool does not support transactions");
  return pool.getConnection();
}

function snapshotValues(
  record: Omit<StoredSnapshot, "version" | "isCurrent">,
): unknown[] {
  const { snapshot, summary } = record;
  return [
    snapshot.source.sha256,
    snapshot.source.chartId,
    snapshot.source.chartName,
    snapshot.asOf,
    snapshot.fetchedAt,
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
    snapshot.overview.conclusion,
    snapshot.overview.focus,
    JSON.stringify(snapshot.audit),
    JSON.stringify(snapshot),
  ];
}

export class MySQLSnapshotRepository implements SnapshotRepository {
  private readonly pool: PoolLike;

  constructor(pool: PoolLike = createMySQLPool()) {
    this.pool = pool;
  }

  async save(
    record: Omit<StoredSnapshot, "version" | "isCurrent">,
  ): Promise<SaveSnapshotResult> {
    const connection = await requireConnection(this.pool);
    await connection.beginTransaction();
    try {
      const currentResult = await connection.execute(
        `SELECT id, cadence, period_key, version, is_current, snapshot_json
         FROM rdhs_snapshots
         WHERE cadence = ? AND period_key = ? AND is_current = 1
         LIMIT 1 FOR UPDATE`,
        [record.cadence, record.periodKey],
      );
      const currentRow = rows(currentResult)[0] as SnapshotRow | undefined;
      if (currentRow && hasCoverageRegression(rowToStored(currentRow), record.snapshot)) {
        throw new Error(
          `snapshot coverage regressed for ${record.periodKey}; refusing to replace the current snapshot`,
        );
      }
      if (currentRow) {
        await connection.execute(
          `UPDATE rdhs_snapshots SET
             source_sha256 = ?, source_chart_id = ?, source_chart_name = ?, as_of = ?,
             fetched_at = ?, product_total = ?, measured_product_count = ?,
             unmeasured_product_count = ?, below_70_count = ?, average_rdhs = ?,
             measurement_coverage = ?, key_governance_count = ?,
             risk_improvement_count = ?, continuous_optimization_count = ?,
             regular_tracking_count = ?, link_closure_average = ?,
             delivery_closure_average = ?, timeliness_average = ?, granularity_average = ?,
             quality_average = ?, conclusion = ?, focus = ?, audit_json = ?, snapshot_json = ?
           WHERE id = ?`,
          [...snapshotValues(record), currentRow.id],
        );
        await connection.commit();
        return { snapshotId: currentRow.id, version: Number(currentRow.version), created: false };
      }

      await connection.execute(
        `INSERT INTO rdhs_snapshots (
           id, cadence, period_key, version, is_current, source_sha256,
           source_chart_id, source_chart_name, as_of, fetched_at, product_total,
           measured_product_count, unmeasured_product_count, below_70_count,
           average_rdhs, measurement_coverage, key_governance_count,
           risk_improvement_count, continuous_optimization_count,
           regular_tracking_count, link_closure_average, delivery_closure_average,
           timeliness_average, granularity_average, quality_average, conclusion,
           focus, audit_json, snapshot_json
         ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [record.id, record.cadence, record.periodKey, 1, ...snapshotValues(record)],
      );
      await connection.commit();
      return { snapshotId: record.id, version: 1, created: true };
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  }

  async getCurrent(cadence: Cadence, periodKey?: string): Promise<StoredSnapshot | null> {
    const result = periodKey
      ? await this.pool.execute(
          `SELECT id, cadence, period_key, version, is_current, snapshot_json
           FROM rdhs_snapshots
           WHERE cadence = ? AND period_key = ? AND is_current = 1 LIMIT 1`,
          [cadence, periodKey],
        )
      : await this.pool.execute(
          `SELECT id, cadence, period_key, version, is_current, snapshot_json
           FROM rdhs_snapshots WHERE cadence = ? AND is_current = 1
           ORDER BY period_key DESC LIMIT 1`,
          [cadence],
        );
    const row = rows(result)[0] as SnapshotRow | undefined;
    return row ? rowToStored(row) : null;
  }

  async listCurrent(cadence: Cadence): Promise<StoredSnapshot[]> {
    const result = await this.pool.execute(
      `SELECT id, cadence, period_key, version, is_current, snapshot_json
       FROM rdhs_snapshots WHERE cadence = ? AND is_current = 1
       ORDER BY period_key ASC`,
      [cadence],
    );
    return rows(result).map((row) => rowToStored(row as SnapshotRow));
  }

  async listPeriods(cadence: Cadence): Promise<StoredSnapshot[]> {
    const result = await this.pool.execute(
      `SELECT id, cadence, period_key, version, is_current, snapshot_json
       FROM rdhs_snapshots WHERE cadence = ? AND is_current = 1
       ORDER BY period_key DESC`,
      [cadence],
    );
    return rows(result).map((row) => rowToStored(row as SnapshotRow));
  }

  async recordFailure(input: unknown, error: string): Promise<void> {
    const candidate = typeof input === "object" && input !== null
      ? input as Record<string, unknown>
      : {};
    const source = typeof candidate.source === "object" && candidate.source !== null
      ? candidate.source as Record<string, unknown>
      : {};
    await this.pool.execute(
      `INSERT INTO rdhs_ingest_failures (cadence, period_key, source_sha256, error)
       VALUES (?, ?, ?, ?)`,
      [
        typeof candidate.cadence === "string" ? candidate.cadence : null,
        typeof candidate.periodKey === "string" ? candidate.periodKey : null,
        typeof source.sha256 === "string" ? source.sha256 : null,
        error,
      ],
    );
  }
}

export class MySQLSyncStateRepository {
  private readonly pool: PoolLike;

  constructor(pool: PoolLike = createMySQLPool()) {
    this.pool = pool;
  }

  async getBaseline(periodKey: string): Promise<SyncBaseline | null> {
    const result = await this.pool.execute(
      `SELECT period_key, payload_json, metadata_json, updated_at
       FROM rdhs_sync_baselines WHERE period_key = ? LIMIT 1`,
      [periodKey],
    );
    const row = rows(result)[0];
    if (!row) return null;
    return {
      periodKey: String(row.period_key),
      payload: jsonObject(row.payload_json, "baseline payload"),
      metadata: jsonObject(row.metadata_json, "baseline metadata"),
      updatedAt: new Date(String(row.updated_at)).toISOString(),
    };
  }

  async putBaseline(input: Omit<SyncBaseline, "updatedAt">): Promise<void> {
    await this.pool.execute(
      `INSERT INTO rdhs_sync_baselines (period_key, payload_json, metadata_json)
       VALUES (?, ?, ?)
       ON DUPLICATE KEY UPDATE
         payload_json = VALUES(payload_json),
         metadata_json = VALUES(metadata_json),
         updated_at = CURRENT_TIMESTAMP(6)`,
      [input.periodKey, JSON.stringify(input.payload), JSON.stringify(input.metadata)],
    );
  }

  async acquireLease(input: {
    name: string;
    owner: string;
    ttlSeconds: number;
  }): Promise<LeaseResult> {
    const connection = await requireConnection(this.pool);
    await connection.beginTransaction();
    try {
      const result = await connection.execute(
        `SELECT owner_id, expires_at FROM rdhs_sync_leases
         WHERE lease_name = ? LIMIT 1 FOR UPDATE`,
        [input.name],
      );
      const current = rows(result)[0];
      const now = new Date();
      const expiresAt = new Date(now.getTime() + input.ttlSeconds * 1000);
      const currentExpiry = current ? new Date(String(current.expires_at)) : null;
      const canAcquire = !current || current.owner_id === input.owner ||
        (currentExpiry !== null && currentExpiry.getTime() <= now.getTime());

      if (canAcquire) {
        if (current) {
          await connection.execute(
            `UPDATE rdhs_sync_leases SET owner_id = ?, expires_at = ?
             WHERE lease_name = ?`,
            [input.owner, expiresAt, input.name],
          );
        } else {
          await connection.execute(
            `INSERT INTO rdhs_sync_leases (lease_name, owner_id, expires_at)
             VALUES (?, ?, ?)`,
            [input.name, input.owner, expiresAt],
          );
        }
        await connection.commit();
        return {
          acquired: true,
          name: input.name,
          owner: input.owner,
          expiresAt: expiresAt.toISOString(),
        };
      }

      await connection.commit();
      return {
        acquired: false,
        name: input.name,
        owner: String(current.owner_id),
        expiresAt: currentExpiry?.toISOString() ?? now.toISOString(),
      };
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  }

  async releaseLease(name: string, owner: string): Promise<boolean> {
    const result = await this.pool.execute(
      `DELETE FROM rdhs_sync_leases WHERE lease_name = ? AND owner_id = ?`,
      [name, owner],
    );
    return Number(resultHeader(result).affectedRows ?? 0) > 0;
  }
}
