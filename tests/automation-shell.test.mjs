import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("scheduled jobs load their private sync environment before invoking Python", async () => {
  const wrapper = await readFile(new URL("../scripts/run-sync-job.sh", import.meta.url), "utf8");
  const installer = await readFile(new URL("../scripts/install-launchd.sh", import.meta.url), "utf8");
  const localRunner = await readFile(new URL("../scripts/local-refresh-runner.py", import.meta.url), "utf8");
  const localMigration = await readFile(new URL("../scripts/migrate-local-d1.py", import.meta.url), "utf8");

  assert.match(wrapper, /\.env\.sync/);
  assert.match(wrapper, /source "\$env_file"/);
  assert.match(wrapper, /sync-rdhs-snapshot\.py/);
  assert.match(localRunner, /sync-rdhs-snapshot\.py/);
  assert.match(localRunner, /RDHS_REFRESH_WEBHOOK_TOKEN/);
  assert.match(localRunner, /version_info.*3, 10/);
  assert.match(localRunner, /--current-month-cache/);
  assert.match(localMigration, /miniflare-D1DatabaseObject/);
  assert.match(localMigration, /0000_normal_zemo\.sql/);
  assert.match(wrapper, /version_info.*3, 10/);
  assert.match(installer, /run-sync-job\.sh/);
  assert.match(installer, /com\.rdhs\.operations\.monthly/);
  assert.doesNotMatch(installer, /com\.rdhs\.operations\.weekly/);
  assert.doesNotMatch(installer, /RDHS_INGEST_TOKEN.*<string>/);
});

test("the chart build script follows the versioned meegle-mcp release flow", async () => {
  const script = await readFile(new URL("../charts/build-chart.sh", import.meta.url), "utf8");

  assert.match(script, /PROJECT_VERSION/);
  assert.match(script, /BUILD_ID/);
  assert.match(script, /SERVICE_NAME/);
  assert.match(script, /values-\$\{ENV\}\.example\.yaml/);
  assert.match(script, /helm lint/);
  assert.match(script, /helm package/);
  assert.match(script, /helm push-artifactory/);
  assert.match(script, /meegle-rdhs-report/);
});
