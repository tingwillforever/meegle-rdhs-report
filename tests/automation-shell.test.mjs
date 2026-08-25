import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { access, chmod, cp, mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import test from "node:test";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

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

test("chart build publishes after a successful build without an opt-in flag", async (t) => {
  const tempRoot = await mkdtemp(join(tmpdir(), "rdhs-chart-publish-"));
  t.after(() => rm(tempRoot, { force: true, recursive: true }));

  const chartsDir = join(tempRoot, "charts");
  const binDir = join(tempRoot, "bin");
  const pushLog = join(tempRoot, "push.log");
  const helmPath = join(binDir, "helm");
  await cp(new URL("../charts", import.meta.url), chartsDir, { recursive: true });
  await mkdir(binDir);
  await writeFile(
    helmPath,
    `#!/usr/bin/env bash
case "$1" in
  lint) exit 0 ;;
  package)
    while [[ "$#" -gt 0 ]]; do
      if [[ "$1" == "--destination" ]]; then
        shift
        mkdir -p "$1"
        touch "$1/test-chart.tgz"
        echo "Successfully packaged chart and saved it to: $1/test-chart.tgz"
        exit 0
      fi
      shift
    done
    exit 1
    ;;
  push-artifactory)
    printf '%s\\n' "$*" >> "$PUSH_LOG"
    exit 0
    ;;
esac
exit 1
`,
  );
  await chmod(helmPath, 0o755);

  await execFileAsync("bash", [join(chartsDir, "build-chart.sh")], {
    cwd: tempRoot,
    env: {
      ...process.env,
      BUILD_ID: "42",
      ENV: "prod",
      PATH: `${binDir}:${process.env.PATH}`,
      PROJECT_VERSION: "0.1",
      PUSH_LOG: pushLog,
      SERVICE_NAME: "meegle-rdhs-report",
    },
  });

  const pushed = await readFile(pushLog, "utf8");
  assert.match(pushed, /^push-artifactory meegle-rdhs-report-prod cbg-helm-local --skip-reindex$/m);
  const builtValues = await readFile(
    join(chartsDir, "meegle-rdhs-report-prod", "values.yaml"),
    "utf8",
  );
  assert.match(builtValues, /^web:\n/m);
  assert.match(builtValues, /^sync:\n/m);
  assert.match(builtValues, /^report:\n/m);
  assert.match(builtValues, /^serviceAccount:\n/m);
  assert.match(builtValues, /^pdb:\n/m);
  assert.match(builtValues, /^\x20{4}host: 172\.31\.114\.194$/m);
});
