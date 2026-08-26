DELETE FROM `rdhs_snapshots`
WHERE `id` NOT IN (
  SELECT `id`
  FROM `rdhs_snapshots`
  WHERE `is_current` = 1
);
--> statement-breakpoint
UPDATE `rdhs_snapshots` SET `version` = 1, `is_current` = 1;
--> statement-breakpoint
DROP INDEX `uq_rdhs_snapshots_period_source`;--> statement-breakpoint
CREATE UNIQUE INDEX `uq_rdhs_snapshots_period` ON `rdhs_snapshots` (`cadence`,`period_key`);
