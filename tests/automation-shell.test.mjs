import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("scheduled jobs load their private sync environment before invoking Python", async () => {
  const wrapper = await readFile(new URL("../scripts/run-sync-job.sh", import.meta.url), "utf8");
  const installer = await readFile(new URL("../scripts/install-launchd.sh", import.meta.url), "utf8");

  assert.match(wrapper, /\.env\.sync/);
  assert.match(wrapper, /source "\$env_file"/);
  assert.match(wrapper, /sync-rdhs-snapshot\.py/);
  assert.match(installer, /run-sync-job\.sh/);
  assert.doesNotMatch(installer, /RDHS_INGEST_TOKEN.*<string>/);
});
