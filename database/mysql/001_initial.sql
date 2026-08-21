CREATE TABLE IF NOT EXISTS rdhs_snapshots (
  id VARCHAR(64) NOT NULL,
  cadence VARCHAR(16) NOT NULL,
  period_key CHAR(7) NOT NULL,
  version INT UNSIGNED NOT NULL,
  is_current TINYINT(1) NOT NULL DEFAULT 0,
  source_sha256 CHAR(64) NOT NULL,
  source_chart_id VARCHAR(128) NOT NULL,
  source_chart_name VARCHAR(255) NOT NULL,
  as_of DATE NOT NULL,
  fetched_at VARCHAR(64) NOT NULL,
  product_total INT UNSIGNED NOT NULL,
  measured_product_count INT UNSIGNED NOT NULL,
  unmeasured_product_count INT UNSIGNED NOT NULL,
  below_70_count INT UNSIGNED NOT NULL,
  average_rdhs DOUBLE NULL,
  measurement_coverage DOUBLE NOT NULL,
  key_governance_count INT UNSIGNED NOT NULL,
  risk_improvement_count INT UNSIGNED NOT NULL,
  continuous_optimization_count INT UNSIGNED NOT NULL,
  regular_tracking_count INT UNSIGNED NOT NULL,
  link_closure_average DOUBLE NULL,
  delivery_closure_average DOUBLE NULL,
  timeliness_average DOUBLE NULL,
  granularity_average DOUBLE NULL,
  quality_average DOUBLE NULL,
  conclusion TEXT NOT NULL,
  focus TEXT NOT NULL,
  audit_json JSON NOT NULL,
  snapshot_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_rdhs_snapshots_period_source (cadence, period_key, source_sha256),
  UNIQUE KEY uq_rdhs_snapshots_period_version (cadence, period_key, version),
  KEY idx_rdhs_snapshots_current_period (cadence, is_current, period_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rdhs_business_line_metrics (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  snapshot_id VARCHAR(64) NOT NULL,
  business_line VARCHAR(255) NOT NULL,
  product_total INT UNSIGNED NOT NULL,
  measured_product_count INT UNSIGNED NOT NULL,
  average_rdhs DOUBLE NULL,
  measurement_coverage DOUBLE NOT NULL,
  key_governance_count INT UNSIGNED NOT NULL,
  risk_improvement_count INT UNSIGNED NOT NULL,
  continuous_optimization_count INT UNSIGNED NOT NULL,
  regular_tracking_count INT UNSIGNED NOT NULL,
  mode VARCHAR(32) NOT NULL,
  focus TEXT NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_rdhs_business_line_snapshot (snapshot_id, business_line),
  CONSTRAINT fk_rdhs_business_line_snapshot
    FOREIGN KEY (snapshot_id) REFERENCES rdhs_snapshots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rdhs_product_metrics (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  snapshot_id VARCHAR(64) NOT NULL,
  business_line VARCHAR(255) NOT NULL,
  sub_line VARCHAR(255) NULL,
  product VARCHAR(255) NOT NULL,
  product_status VARCHAR(32) NOT NULL,
  rdhs DOUBLE NULL,
  governance_band VARCHAR(32) NOT NULL,
  priority VARCHAR(8) NULL,
  components_json JSON NOT NULL,
  dependency_metrics_json JSON NOT NULL,
  lowest_component TEXT NOT NULL,
  problem TEXT NOT NULL,
  action TEXT NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_rdhs_product_snapshot (snapshot_id, business_line, product),
  KEY idx_rdhs_product_line (snapshot_id, business_line),
  KEY idx_rdhs_product_band (snapshot_id, governance_band),
  CONSTRAINT fk_rdhs_product_snapshot
    FOREIGN KEY (snapshot_id) REFERENCES rdhs_snapshots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rdhs_ingest_failures (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  cadence VARCHAR(16) NULL,
  period_key CHAR(7) NULL,
  source_sha256 CHAR(64) NULL,
  error TEXT NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_rdhs_ingest_failures_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rdhs_sync_baselines (
  period_key CHAR(7) NOT NULL,
  payload_json JSON NOT NULL,
  metadata_json JSON NOT NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (period_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rdhs_sync_leases (
  lease_name VARCHAR(64) NOT NULL,
  owner_id VARCHAR(128) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (lease_name),
  KEY idx_rdhs_sync_leases_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
