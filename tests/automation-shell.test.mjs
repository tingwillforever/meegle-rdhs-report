import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

test("scheduled jobs load their private sync environment before invoking Python", async () => {
  const wrapper = await readFile(new URL("../scripts/run-sync-job.sh", import.meta.url), "utf8");
  const installer = await readFile(new URL("../scripts/install-launchd.sh", import.meta.url), "utf8");
  const localMigration = await readFile(new URL("../scripts/migrate-local-d1.py", import.meta.url), "utf8");

  assert.match(wrapper, /\.env\.sync/);
  assert.match(wrapper, /source "\$env_file"/);
  assert.match(wrapper, /sync-rdhs-snapshot\.py/);
  await assert.rejects(
    () => access(new URL("../scripts/local-refresh-runner.py", import.meta.url)),
  );
  assert.match(localMigration, /miniflare-D1DatabaseObject/);
  assert.match(localMigration, /0000_normal_zemo\.sql/);
  assert.match(wrapper, /version_info.*3, 10/);
  assert.match(installer, /run-sync-job\.sh/);
  assert.match(installer, /com\.rdhs\.operations\.monthly/);
  assert.doesNotMatch(installer, /com\.rdhs\.operations\.weekly/);
  assert.doesNotMatch(installer, /RDHS_INGEST_TOKEN.*<string>/);
});

test("production D1 access does not retain the unused Drizzle notes adapter", async () => {
  const dbIndex = await readFile(new URL("../db/index.ts", import.meta.url), "utf8");

  assert.doesNotMatch(dbIndex, /drizzle-orm/);
  assert.doesNotMatch(dbIndex, /export function getDb/);
  await assert.rejects(
    () => access(new URL("../examples/d1/app/api/notes/route.ts", import.meta.url)),
  );
});
