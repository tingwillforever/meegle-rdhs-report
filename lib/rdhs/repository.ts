import { summarizeSnapshot } from "./aggregate.ts";
import type { Cadence, RdhsSnapshot, SnapshotSummary } from "./types.ts";
import { validateSnapshot } from "./validate.ts";

export type StoredSnapshot = {
  id: string;
  cadence: Cadence;
  periodKey: string;
  version: number;
  isCurrent: boolean;
  snapshot: RdhsSnapshot;
  summary: SnapshotSummary;
};

export type SaveSnapshotResult = {
  snapshotId: string;
  version: number;
  created: boolean;
};

export interface SnapshotRepository {
  save(record: Omit<StoredSnapshot, "version" | "isCurrent">): Promise<SaveSnapshotResult>;
  getCurrent(cadence: Cadence, periodKey?: string): Promise<StoredSnapshot | null>;
  listCurrent(cadence: Cadence): Promise<StoredSnapshot[]>;
  listPeriods(cadence: Cadence): Promise<StoredSnapshot[]>;
}

export class MemorySnapshotRepository implements SnapshotRepository {
  readonly records: StoredSnapshot[] = [];

  async save(
    record: Omit<StoredSnapshot, "version" | "isCurrent">,
  ): Promise<SaveSnapshotResult> {
    const duplicate = this.records.find(
      (existing) =>
        existing.cadence === record.cadence &&
        existing.periodKey === record.periodKey &&
        existing.snapshot.source.sha256 === record.snapshot.source.sha256,
    );
    if (duplicate) {
      for (const existing of this.records) {
        if (existing.cadence === record.cadence && existing.periodKey === record.periodKey) {
          existing.isCurrent = false;
        }
      }
      duplicate.snapshot = record.snapshot;
      duplicate.summary = record.summary;
      duplicate.isCurrent = true;
      return { snapshotId: duplicate.id, version: duplicate.version, created: false };
    }

    const samePeriod = this.records.filter(
      (existing) =>
        existing.cadence === record.cadence && existing.periodKey === record.periodKey,
    );
    for (const existing of samePeriod) existing.isCurrent = false;
    const version = Math.max(0, ...samePeriod.map((existing) => existing.version)) + 1;
    this.records.push({ ...record, version, isCurrent: true });
    return { snapshotId: record.id, version, created: true };
  }

  async getCurrent(cadence: Cadence, periodKey?: string): Promise<StoredSnapshot | null> {
    const records = this.records
      .filter(
        (record) =>
          record.cadence === cadence &&
          record.isCurrent &&
          (periodKey === undefined || record.periodKey === periodKey),
      )
      .sort((left, right) => right.periodKey.localeCompare(left.periodKey));
    return records[0] ?? null;
  }

  async listCurrent(cadence: Cadence): Promise<StoredSnapshot[]> {
    return this.records
      .filter((record) => record.cadence === cadence && record.isCurrent)
      .sort((left, right) => left.periodKey.localeCompare(right.periodKey));
  }

  async listPeriods(cadence: Cadence): Promise<StoredSnapshot[]> {
    return this.records
      .filter((record) => record.cadence === cadence && record.isCurrent)
      .sort((left, right) => right.periodKey.localeCompare(left.periodKey));
  }
}

export class SnapshotService {
  private readonly repository: SnapshotRepository;
  private readonly idFactory: () => string;

  constructor(
    repository: SnapshotRepository,
    idFactory: () => string = () => crypto.randomUUID(),
  ) {
    this.repository = repository;
    this.idFactory = idFactory;
  }

  async ingest(input: unknown): Promise<SaveSnapshotResult> {
    const snapshot = validateSnapshot(input);
    const id = this.idFactory();
    if (!id) throw new Error("snapshot id factory returned an empty value");
    return this.repository.save({
      id,
      cadence: snapshot.cadence,
      periodKey: snapshot.periodKey,
      snapshot,
      summary: summarizeSnapshot(snapshot),
    });
  }
}
