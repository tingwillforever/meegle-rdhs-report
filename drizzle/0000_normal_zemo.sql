CREATE TABLE `rdhs_business_line_metrics` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`snapshot_id` text NOT NULL,
	`business_line` text NOT NULL,
	`product_total` integer NOT NULL,
	`measured_product_count` integer NOT NULL,
	`average_rdhs` real,
	`measurement_coverage` real NOT NULL,
	`key_governance_count` integer NOT NULL,
	`risk_improvement_count` integer NOT NULL,
	`continuous_optimization_count` integer NOT NULL,
	`regular_tracking_count` integer NOT NULL,
	`link_closure_average` real,
	`delivery_closure_average` real,
	`timeliness_average` real,
	`granularity_average` real,
	`quality_average` real,
	`mode` text NOT NULL,
	`focus` text NOT NULL,
	FOREIGN KEY (`snapshot_id`) REFERENCES `rdhs_snapshots`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_rdhs_business_line_snapshot` ON `rdhs_business_line_metrics` (`snapshot_id`,`business_line`);--> statement-breakpoint
CREATE TABLE `rdhs_ingest_failures` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`cadence` text,
	`period_key` text,
	`source_sha256` text,
	`error` text NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_rdhs_ingest_failures_created` ON `rdhs_ingest_failures` (`created_at`);--> statement-breakpoint
CREATE TABLE `rdhs_product_metrics` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`snapshot_id` text NOT NULL,
	`business_line` text NOT NULL,
	`product` text NOT NULL,
	`product_status` text NOT NULL,
	`rdhs` real,
	`governance_band` text NOT NULL,
	`priority` text,
	`link_closure` real,
	`delivery_closure` real,
	`timeliness` real,
	`granularity` real,
	`quality` real,
	`lowest_component` text NOT NULL,
	`problem` text NOT NULL,
	`action` text NOT NULL,
	FOREIGN KEY (`snapshot_id`) REFERENCES `rdhs_snapshots`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_rdhs_product_snapshot` ON `rdhs_product_metrics` (`snapshot_id`,`business_line`,`product`);--> statement-breakpoint
CREATE INDEX `idx_rdhs_product_line` ON `rdhs_product_metrics` (`snapshot_id`,`business_line`);--> statement-breakpoint
CREATE INDEX `idx_rdhs_product_band` ON `rdhs_product_metrics` (`snapshot_id`,`governance_band`);--> statement-breakpoint
CREATE TABLE `rdhs_snapshots` (
	`id` text PRIMARY KEY NOT NULL,
	`cadence` text NOT NULL,
	`period_key` text NOT NULL,
	`version` integer NOT NULL,
	`is_current` integer DEFAULT false NOT NULL,
	`source_sha256` text NOT NULL,
	`source_chart_id` text NOT NULL,
	`source_chart_name` text NOT NULL,
	`as_of` text NOT NULL,
	`fetched_at` text NOT NULL,
	`product_total` integer NOT NULL,
	`measured_product_count` integer NOT NULL,
	`unmeasured_product_count` integer NOT NULL,
	`below_70_count` integer NOT NULL,
	`average_rdhs` real,
	`measurement_coverage` real NOT NULL,
	`key_governance_count` integer NOT NULL,
	`risk_improvement_count` integer NOT NULL,
	`continuous_optimization_count` integer NOT NULL,
	`regular_tracking_count` integer NOT NULL,
	`link_closure_average` real,
	`delivery_closure_average` real,
	`timeliness_average` real,
	`granularity_average` real,
	`quality_average` real,
	`conclusion` text NOT NULL,
	`focus` text NOT NULL,
	`audit_json` text NOT NULL,
	`snapshot_json` text NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_rdhs_snapshots_period_source` ON `rdhs_snapshots` (`cadence`,`period_key`,`source_sha256`);--> statement-breakpoint
CREATE INDEX `idx_rdhs_snapshots_current_period` ON `rdhs_snapshots` (`cadence`,`is_current`,`period_key`);--> statement-breakpoint
PRAGMA optimize;
