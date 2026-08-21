import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

const chart = "charts/rdhs-report";
const productionValues = "charts/rdhs-report/values-prod.yaml";

function renderHelm(extraArguments = [], releaseName = "rdhs-report") {
  return spawnSync(
    "helm",
    ["template", releaseName, chart, "-f", productionValues, ...extraArguments],
    { cwd: process.cwd(), encoding: "utf8" },
  );
}

test("production render creates one Web replica with RWO storage and a monthly sync CronJob", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);

  assert.match(
    result.stdout,
    /kind: Deployment\nmetadata:\n {2}name: rdhs-report-web[\s\S]*?replicas: 1[\s\S]*?strategy:\n {4}type: Recreate/,
  );
  assert.match(
    result.stdout,
    /kind: PersistentVolumeClaim\nmetadata:\n {2}name: rdhs-report[\s\S]*?accessModes:\n {4}- ReadWriteOnce/,
  );
  assert.match(
    result.stdout,
    /kind: CronJob\nmetadata:\n {2}name: rdhs-report-sync[\s\S]*?schedule: "0 9 1 \* \*"[\s\S]*?timeZone: Asia\/Shanghai[\s\S]*?concurrencyPolicy: Forbid[\s\S]*?jobTemplate:\n {4}spec:\n {6}activeDeadlineSeconds: 1500\n {6}backoffLimit: 2\n {6}ttlSecondsAfterFinished: 604800/,
  );
  assert.doesNotMatch(result.stdout, /\n {2}activeDeadlineSeconds:/);
  assert.doesNotMatch(result.stdout, /\n {2}ttlSecondsAfterFinished:/);
  assert.doesNotMatch(result.stdout, /^kind: Secret$/m);
});

test("quick validation can render the application Secret from a local override", () => {
  const result = renderHelm([
    "--set", "secrets.create=true",
    "--set-string", "secrets.web.data.RDHS_INGEST_TOKEN=ingest-test-token",
    "--set-string", "secrets.web.data.RDHS_REFRESH_WEBHOOK_TOKEN=refresh-test-token",
  ]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /kind: Secret\nmetadata:\n {2}name: rdhs-report-web-secrets/);
  assert.match(result.stdout, /RDHS_INGEST_TOKEN: "ingest-test-token"/);
  assert.doesNotMatch(result.stdout, /MEEGLE_HOST|MEEGLE_USER_ACCESS_TOKEN|rdhs-report-meegle-secrets/);
});

test("inline Secret mode fails closed when a credential is missing", () => {
  const result = renderHelm(["--set", "secrets.create=true"]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /secrets\.web\.data\.RDHS_INGEST_TOKEN is required/);
});

test("production render follows the meegle-mcp domain and registry conventions without path rewrite", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /host: "ossptest\.voicecloud\.cn"/);
  assert.match(result.stdout, /path: \/meegle-rdhs-report\(\/\|\$\)\(\.\*\)/);
  assert.doesNotMatch(result.stdout, /nginx\.ingress\.kubernetes\.io\/rewrite-target/);
  assert.match(result.stdout, /nginx\.ingress\.kubernetes\.io\/use-regex: "true"/);
  assert.match(
    result.stdout,
    /image: "artifacts\.iflytek\.com\/cbg-docker-repo\/cbbywkf\/meegle-rdhs-report:4\.0\.4"/,
  );
  assert.equal(
    (result.stdout.match(/image: "artifacts\.iflytek\.com\/cbg-docker-repo\/cbbywkf\/meegle-rdhs-report:4\.0\.4"/g) ?? []).length,
    3,
  );
  assert.match(result.stdout, /imagePullSecrets:\n {8}- name: hub4iflytek/);
  assert.doesNotMatch(result.stdout, /auth-url|required_group|rdhs-operators/);
  assert.match(result.stdout, /path: "\/meegle-rdhs-report\/api\/health\/live"/);
  assert.match(result.stdout, /path: "\/meegle-rdhs-report\/api\/health"/);
});

test("the production path prefix is normalized and release names flow to workloads", () => {
  const result = renderHelm([], "meegle-rdhs-report");
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /name: meegle-rdhs-report-web/);
  assert.match(result.stdout, /name: meegle-rdhs-report-refresh/);
  assert.match(result.stdout, /name: meegle-rdhs-report-sync/);

  const invalid = renderHelm(["--set", "ingress.pathPrefix=/bad/"]);
  assert.notEqual(invalid.status, 0);
  assert.match(invalid.stderr, /ingress\.pathPrefix must not end with \/?/);
});

test("sync workloads receive a bounded report-command timeout", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);
  const timeoutReferences = result.stdout.match(/name: RDHS_REPORT_COMMAND_TIMEOUT_SECONDS/g) ?? [];
  assert.equal(timeoutReferences.length, 2);

  const deadline = renderHelm(["--set", "sync.cron.activeDeadlineSeconds=1000"]);
  assert.notEqual(deadline.status, 0);
  assert.match(deadline.stderr, /sync\.cron\.activeDeadlineSeconds must allow two report commands/);
});

test("render rejects mutable image tags", () => {
  const result = renderHelm(["--set", "image.tag=latest"]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /must not use the mutable latest tag/);
});

test("render rejects SQLite access modes other than exactly ReadWriteOnce", () => {
  const result = renderHelm([
    "--set-json",
    'persistence.accessModes=["ReadWriteOnce","ReadWriteMany"]',
  ]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /persistence\.accessModes must be exactly \[ReadWriteOnce\]/);
});

test("render fixes the monthly schedule to Shanghai 09:00 on the first day", () => {
  const schedule = renderHelm(["--set", "sync.cron.schedule=0 10 1 * *"]);
  assert.notEqual(schedule.status, 0);
  assert.match(schedule.stderr, /sync\.cron\.schedule must be 0 9 1 \* \*/);

  const timeZone = renderHelm(["--set", "sync.cron.timeZone=UTC"]);
  assert.notEqual(timeZone.status, 0);
  assert.match(timeZone.stderr, /sync\.cron\.timeZone must be Asia\/Shanghai/);
});

test("a recovery values file can keep the CronJob suspended across Helm upgrades", () => {
  const result = renderHelm(["--set", "sync.cron.suspend=true"]);
  assert.equal(result.status, 0, result.stderr);
  const cronJob = result.stdout.match(
    /kind: CronJob\nmetadata:\n {2}name: rdhs-report-sync[\s\S]*?(?=\n---|$)/,
  )?.[0];
  assert.ok(cronJob);
  assert.match(cronJob, /suspend: true/);
});

test("render fixes the Runner at one replica and requires shared NFS storage", () => {
  const replicas = renderHelm(["--set", "sync.replicaCount=2"]);
  assert.notEqual(replicas.status, 0);
  assert.match(replicas.stderr, /sync\.replicaCount must be 1/);

  const nfs = renderHelm(["--set", "syncStorage.nfs.path="]);
  assert.notEqual(nfs.status, 0);
  assert.match(nfs.stderr, /syncStorage\.nfs\.path is required/);
});

test("runner and CronJob share the NFS-backed report output directory", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);
  for (const name of ["rdhs-report-refresh", "rdhs-report-sync"]) {
    const workload = result.stdout.match(
      new RegExp(`kind: (?:Deployment|CronJob)\\nmetadata:\\n {2}name: ${name}[\\s\\S]*?(?=\\n---|$)`),
    )?.[0];
    assert.ok(workload, `${name} workload must render`);
    assert.match(workload, /name: RDHS_OUTPUT_ROOT\n\s+value: "\/var\/lib\/rdhs-sync"/);
    assert.match(workload, /name: sync-output\n\s+mountPath: "\/var\/lib\/rdhs-sync"/);
    assert.match(workload, /name: sync-output\n\s+nfs:\n\s+server: "nfs\.company\.internal"\n\s+path: "\/exports\/rdhs-report"/);
    assert.match(workload, /name: RDHS_SITE_URL\n\s+value: "http:\/\/rdhs-report-web:3000\/meegle-rdhs-report"/);
    assert.match(workload, /name: RDHS_ALLOW_INSECURE_SITE_URL\n\s+value: "true"/);
  }
});

test("production values do not render a separate refresh Ingress", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);
  assert.doesNotMatch(result.stdout, /name: rdhs-report-web-refresh/);
  assert.doesNotMatch(result.stdout, /auth-url|required_group|rdhs-operators/);
});

test("NetworkPolicy keeps the runner and monthly sync upload path to Web open", () => {
  const result = renderHelm([
    "--set",
    "networkPolicy.enabled=true",
    "--set-json",
    'networkPolicy.ingressController.namespaceSelector={"matchLabels":{"kubernetes.io/metadata.name":"ingress-nginx"}}',
    "--set-json",
    'networkPolicy.ingressController.podSelector={"matchLabels":{"app.kubernetes.io/component":"controller"}}',
    "--set-json",
    'networkPolicy.meegleEgress=[{"ipBlock":{"cidr":"10.0.0.0/8"}}]',
  ]);
  assert.equal(result.status, 0, result.stderr);

  const webPolicy = result.stdout.match(
    /kind: NetworkPolicy\nmetadata:\n {2}name: rdhs-report-web[\s\S]*?(?=\n---|$)/,
  )?.[0];
  assert.ok(webPolicy);
  assert.match(webPolicy, /app\.kubernetes\.io\/component: runner/);
  assert.match(webPolicy, /app\.kubernetes\.io\/component: sync/);
});

test("private registries can supply pull credentials without putting them in values", () => {
  const result = renderHelm([
    "--set",
    "imagePullSecrets[0].name=rdhs-registry-credentials",
  ]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /imagePullSecrets:\n {8}- name: rdhs-registry-credentials/);
});

test("a restored SQLite PVC can replace the chart-managed claim without deleting the original", () => {
  const defaultRender = renderHelm();
  assert.equal(defaultRender.status, 0, defaultRender.stderr);
  assert.match(
    defaultRender.stdout,
    /kind: PersistentVolumeClaim\nmetadata:\n {2}name: rdhs-report[\s\S]*?annotations:\n {4}helm\.sh\/resource-policy: keep/,
  );

  const result = renderHelm([
    "--set",
    "persistence.existingClaim=rdhs-report-restored",
  ]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /claimName: rdhs-report-restored/);
  assert.doesNotMatch(result.stdout, /^kind: PersistentVolumeClaim$/m);
});

test("the monthly job receives only the Web write token it needs", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);
  const cronJob = result.stdout.match(
    /kind: CronJob\nmetadata:\n {2}name: rdhs-report-sync[\s\S]*?(?=\n---|$)/,
  )?.[0];
  assert.ok(cronJob);
  assert.match(cronJob, /name: RDHS_INGEST_TOKEN/);
  assert.doesNotMatch(cronJob, /RDHS_REFRESH_WEBHOOK_TOKEN/);
});

test("the refresh runner starts its image command before passing the timeout argument", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);
  const runner = result.stdout.match(
    /kind: Deployment\nmetadata:\n {2}name: rdhs-report-refresh[\s\S]*?(?=\n---|$)/,
  )?.[0];
  assert.ok(runner);
  assert.match(
    runner,
    /command:\n {12}- python3\n {12}- scripts\/local-refresh-runner\.py\n {12}- --host\n {12}- 0\.0\.0\.0/,
  );
  assert.match(runner, /args:\n {12}- --timeout\n {12}- "600"/);
});
