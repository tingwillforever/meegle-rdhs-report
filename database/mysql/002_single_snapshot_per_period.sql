-- Retain the current snapshot for each month, then make the period the unique key.
-- Run once after database/mysql/001_initial.sql on existing MySQL deployments.

DELETE stale
FROM rdhs_snapshots AS stale
INNER JOIN rdhs_snapshots AS current_snapshot
  ON current_snapshot.cadence = stale.cadence
 AND current_snapshot.period_key = stale.period_key
 AND current_snapshot.is_current = 1
WHERE stale.id <> current_snapshot.id;

UPDATE rdhs_snapshots
SET version = 1,
    is_current = 1;

ALTER TABLE rdhs_snapshots
  DROP INDEX uq_rdhs_snapshots_period_source,
  DROP INDEX uq_rdhs_snapshots_period_version,
  ADD UNIQUE KEY uq_rdhs_snapshots_period (cadence, period_key);
