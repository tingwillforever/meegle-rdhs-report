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

test("production render creates one MySQL-backed Web replica and a monthly sync CronJob", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);

  assert.match(
    result.stdout,
    /kind: Deployment\nmetadata:\n {2}name: rdhs-report-web[\s\S]*?replicas: 1/,
  );
  assert.doesNotMatch(result.stdout, /^kind: PersistentVolumeClaim$/m);
  assert.match(result.stdout, /name: RDHS_STORAGE\n\s+value: mysql/);
  assert.match(result.stdout, /name: MYSQL_HOST\n\s+value: "172\.31\.114\.194"/);
  assert.match(result.stdout, /name: MYSQL_PORT\n\s+value: "4302"/);
  assert.match(result.stdout, /name: MYSQL_DATABASE\n\s+value: "rdhs_report"/);
  assert.match(result.stdout, /secretRef:\n\s+name: rdhs-report-db-secrets/);
  assert.match(
    result.stdout,
    /kind: CronJob\nmetadata:\n {2}name: rdhs-report-sync[\s\S]*?schedule: "0 9 1 \* \*"[\s\S]*?timeZone: Asia\/Shanghai[\s\S]*?concurrencyPolicy: Forbid[\s\S]*?jobTemplate:\n {4}spec:\n {6}activeDeadlineSeconds: 1500\n {6}backoffLimit: 2\n {6}ttlSecondsAfterFinished: 604800/,
  );
  assert.doesNotMatch(result.stdout, /\n {2}activeDeadlineSeconds:/);
  assert.doesNotMatch(result.stdout, /\n {2}ttlSecondsAfterFinished:/);
  assert.match(result.stdout, /^kind: Secret$/m);
  assert.match(result.stdout, /name: rdhs-report-db-secrets/);
});

test("production chart renders on Kubernetes 1.15 using legacy API versions", () => {
  const result = renderHelm([
    "--kube-version", "1.15.12",
    "--set", "pdb.enabled=true",
  ]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /apiVersion: networking\.k8s\.io\/v1beta1\nkind: Ingress/);
  assert.match(result.stdout, /apiVersion: batch\/v1beta1\nkind: CronJob/);
  assert.match(result.stdout, /apiVersion: policy\/v1beta1\nkind: PodDisruptionBudget/);
  assert.doesNotMatch(result.stdout, /timeZone: Asia\/Shanghai/);
  assert.doesNotMatch(result.stdout, /seccompProfile:/);
  assert.match(result.stdout, /kubernetes\.io\/ingress\.class: nginx/);
  assert.match(result.stdout, /serviceName: rdhs-report-web\n\s+servicePort: http/);
});

test("quick validation can render the application Secret from a local override", () => {
  const result = renderHelm([
    "--set", "secrets.create=true",
    "--set-string", "secrets.web.data.RDHS_INGEST_TOKEN=ingest-test-token",
  ]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /kind: Secret\nmetadata:\n {2}name: rdhs-report-web-secrets/);
  assert.match(result.stdout, /RDHS_INGEST_TOKEN: "ingest-test-token"/);
  assert.doesNotMatch(result.stdout, /RDHS_REFRESH_WEBHOOK_TOKEN/);
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
    2,
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
  assert.doesNotMatch(result.stdout, /name: meegle-rdhs-report-refresh/);
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

test("render requires the MySQL host, database, and credential Secret", () => {
  const result = renderHelm(["--set", "database.mysql.host="]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /database\.mysql\.host is required/);

  const secret = renderHelm(["--set", "database.mysql.secretName="]);
  assert.notEqual(secret.status, 0);
  assert.match(secret.stderr, /database\.mysql\.secretName is required/);
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

test("Web and CronJob use disposable local report output without NFS", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);
  for (const name of ["rdhs-report-web", "rdhs-report-sync"]) {
    const workload = result.stdout.match(
      new RegExp(`kind: (?:Deployment|CronJob)\\nmetadata:\\n {2}name: ${name}[\\s\\S]*?(?=\\n---|$)`),
    )?.[0];
    assert.ok(workload, `${name} workload must render`);
    assert.match(workload, /name: RDHS_OUTPUT_ROOT\n\s+value: "\/var\/lib\/rdhs-sync"/);
    assert.match(workload, /name: sync-output\n\s+mountPath: "\/var\/lib\/rdhs-sync"/);
    assert.match(workload, /name: sync-output\n\s+emptyDir: \{\}/);
    assert.doesNotMatch(workload, /\bnfs:/);
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

test("NetworkPolicy lets Web and monthly sync reach Meegle without a runner", () => {
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
  assert.match(webPolicy, /app\.kubernetes\.io\/component: sync/);
  assert.match(webPolicy, /cidr: 172\.31\.114\.194\/32/);
  assert.match(webPolicy, /cidr: 10\.0\.0\.0\/8/);
  assert.match(webPolicy, /port: 4302/);
});

test("private registries can supply pull credentials without putting them in values", () => {
  const result = renderHelm([
    "--set",
    "imagePullSecrets[0].name=rdhs-registry-credentials",
  ]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /imagePullSecrets:\n {8}- name: rdhs-registry-credentials/);
});

test("database credentials are injected into Web only", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);
  const web = result.stdout.match(
    /kind: Deployment\nmetadata:\n {2}name: rdhs-report-web[\s\S]*?(?=\n---|$)/,
  )?.[0];
  assert.ok(web);
  assert.match(web, /name: rdhs-report-db-secrets/);
  for (const name of ["rdhs-report-sync"]) {
    const workload = result.stdout.match(
      new RegExp(`kind: (?:Deployment|CronJob)\\nmetadata:\\n {2}name: ${name}[\\s\\S]*?(?=\\n---|$)`),
    )?.[0];
    assert.ok(workload, `${name} workload must render`);
    assert.doesNotMatch(workload, /rdhs-report-db-secrets/);
  }
});

test("local values can render the MySQL Secret for smoke testing", () => {
  const result = renderHelm([
    "--set", "database.mysql.credentials.create=true",
    "--set-string", "database.mysql.credentials.user=rdhs_report",
    "--set-string", "database.mysql.credentials.password=smoke-db-password",
  ]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /kind: Secret\nmetadata:\n {2}name: rdhs-report-db-secrets/);
  assert.match(result.stdout, /MYSQL_USER: "rdhs_report"/);
  assert.match(result.stdout, /MYSQL_PASSWORD: "smoke-db-password"/);
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

test("single-service render has no runner workload, port, or webhook token", () => {
  const result = renderHelm();
  assert.equal(result.status, 0, result.stderr);
  assert.doesNotMatch(result.stdout, /app\.kubernetes\.io\/component: runner/);
  assert.doesNotMatch(result.stdout, /8765|RDHS_REFRESH_WEBHOOK_/);
  assert.match(result.stdout, /name: RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS/);
  assert.match(result.stdout, /name: RDHS_CURRENT_REPORT_COMMAND/);
});
