# RDHS K8s Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an internal Kubernetes deployment package for RDHS with persistent single-writer SQLite, secure Meegle synchronization, and verified operations.

**Architecture:** The Web Deployment runs Vinext in Node/SQLite mode against one RWO PVC. A separate synchronization image contains Python, Meegle CLI, the externally supplied RDHS report workspace and the current-refresh HTTP runner. Runner and CronJob share an NFS output directory for month-start baselines; a CronJob uses the same image to generate and upload the monthly immutable snapshot without calling the runner.

**Tech Stack:** Node.js 22.13, Vinext, `node:sqlite`, Python 3.11, Meegle CLI, Kubernetes, Helm v3, NGINX Ingress.

**Spec:** `docs/superpowers/specs/2026-08-20-rdhs-k8s-production-readiness-design.md`

## Global Constraints

- Web uses `DEPLOY_TARGET=k8s`, `RDHS_STORAGE=sqlite` and `RDHS_DB_PATH=/var/lib/rdhs/rdhs.sqlite`.
- SQLite uses one writer only: `replicaCount: 1`, RWO PVC, no HPA and `Recreate` updates.
- Production tokens are provided by pre-existing Kubernetes Secrets; the chart can optionally render temporary Secrets for a local smoke-test override, but that override must not be committed.
- Meegle CLI exists only in the synchronization image, never the Web image.
- Runner and CronJob share an NFS output directory with advisory file locking; it is separate from the SQLite PVC.
- Runner fails closed without a webhook token; report commands, CronJob duration, NFS retention and capacity are bounded.
- All image tags are immutable deployment values; no `latest` tag.
- The report workspace is supplied at sync-image build time through BuildKit context `rdhs-workspace`.

---

### Task 1: Production data visibility guard and SQLite readiness

**Files:**
- Modify: `lib/rdhs/runtime.ts`, `app/page.tsx`, `app/api/health/route.ts`
- Create: `tests/rdhs-runtime.test.mjs`

**Interfaces:**
- Produces `allowPreviewFallback(): boolean`; false in K8s unless `RDHS_ALLOW_DEMO_FALLBACK=true`.
- Produces `GET /api/health/live` for process liveness and keeps `GET /api/health` as SQLite readiness.

- [ ] **Step 1: Write the failing test**

```js
test("Kubernetes mode rejects preview fallback unless explicitly enabled", () => {
  process.env.DEPLOY_TARGET = "k8s";
  assert.equal(allowPreviewFallback(), false);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/rdhs-runtime.test.mjs`

Expected: FAIL because `allowPreviewFallback` does not exist.

- [ ] **Step 3: Write minimal implementation**

```ts
export function allowPreviewFallback(): boolean {
  return !isSQLiteStorage() || process.env.RDHS_ALLOW_DEMO_FALLBACK === "true";
}
```

Render an explicit unavailable state in `app/page.tsx` when no valid snapshot exists and fallback is disabled. Add a liveness route which returns `{ status: "ok" }` without touching storage.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/rdhs-runtime.test.mjs tests/rdhs-health.test.mjs`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/rdhs/runtime.ts app/page.tsx app/api/health tests/rdhs-runtime.test.mjs
git commit -m "feat: guard production preview fallback"
```

### Task 2: Configurable external report generator contract

**Files:**
- Modify: `scripts/rdhs_snapshot_sync.py`, `.env.sync.example`, `docs/operations.md`
- Modify: `tests/test_rdhs_web_sync.py`

**Interfaces:**
- Produces `RDHS_MONTHLY_BASELINE_COMMAND`, `RDHS_MONTHLY_REPORT_COMMAND` and `RDHS_CURRENT_REPORT_COMMAND`.
- Each command receives `--no-publish --output-root <path> --as-of <date>`; the baseline uses the next month's first day and the uploadable report uses the previous month's final day.

- [ ] **Step 1: Write the failing test**

```python
def test_monthly_sync_runs_baseline_before_generating_the_uploadable_report() -> None:
    os.environ["RDHS_MONTHLY_BASELINE_COMMAND"] = "python3 report.py --mode monthly-baseline"
    os.environ["RDHS_MONTHLY_REPORT_COMMAND"] = "python3 report.py --mode weekly"
    generate_report("monthly", Path("/tmp/output"), "2026-09-01")
    self.assertEqual(captured["commands"][0][:4], ["python3", "report.py", "--mode", "monthly-baseline"])
    self.assertEqual(captured["commands"][1][:4], ["python3", "report.py", "--mode", "weekly"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_rdhs_web_sync.py`

Expected: FAIL because the generator command is still hard-coded to `last-month`/`monthly` and cannot execute the required baseline/report sequence.

- [ ] **Step 3: Write minimal implementation**

Use `shlex.split` to parse each configured command, fail with an explicit error if empty, append fixed no-publish/output/as-of arguments, execute the optional monthly baseline before the uploadable monthly report command, and retain a weekly default only for developer compatibility. Document the production commands for the supplied RDHS workspace.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests/test_rdhs_web_sync.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/rdhs_snapshot_sync.py .env.sync.example docs/operations.md tests/test_rdhs_web_sync.py
git commit -m "feat: configure RDHS report generation commands"
```

### Task 3: Production Web and sync images

**Files:**
- Modify: `Dockerfile`, `package.json`, `package-lock.json`, `.dockerignore`
- Modify: `Dockerfile`, `tests/dockerfiles.test.mjs`

**Interfaces:**
- Web image runs `npm run start:k8s` as UID 1000 and stores SQLite only under `/var/lib/rdhs`.
- 应用镜像通过 `RDHS_BASE_IMAGE` 引用预构建依赖镜像，并接受 BuildKit context `rdhs-workspace`；Runner 以 `scripts/local-refresh-runner.py` 和 K8s env-file 配置启动。

- [ ] **Step 1: Write the failing test**

```js
test("sync image requires the external report workspace build context", async () => {
  const result = await runDockerBuild("Dockerfile", { contexts: { "rdhs-workspace": reviewedWorkspace } });
  assert.equal(result.exitCode, 1);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/dockerfiles.test.mjs`

Expected: FAIL because the unified image dependencies are not yet included.

- [ ] **Step 3: Write minimal implementation**

Create a Node 22 Debian-based sync image that installs Python 3.11, PyYAML and the configured Meegle CLI package. Copy the named external build context to `/opt/rdhs-workspace`, configure `RDHS_WORKSPACE_ROOT`, run non-root, and use no token-bearing build arguments. Move only server-start dependencies from `devDependencies` to `dependencies` so the Web runtime can use `npm ci --omit=dev`.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/dockerfiles.test.mjs && docker buildx build --load --build-context rdhs-workspace=/absolute/path/to/reviewed/daily-data-ops -t meegle-rdhs-report:verify .`

Expected: PASS; skip the actual image build only if the local Docker daemon is unavailable and record that limitation.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore package.json package-lock.json tests/dockerfiles.test.mjs
git commit -m "build: add production RDHS images"
```

### Task 4: Helm production chart

**Files:**
- Create: `charts/rdhs-report/Chart.yaml`, `charts/rdhs-report/values.yaml`, `charts/rdhs-report/values-prod.example.yaml`
- Create: `charts/rdhs-report/templates/{_helpers.tpl,deployment-web.yaml,deployment-runner.yaml,service-web.yaml,service-runner.yaml,ingress.yaml,pvc.yaml,cronjob-sync.yaml,serviceaccount.yaml,networkpolicy.yaml,NOTES.txt}`
- Create: `tests/helm-chart.test.mjs`

**Interfaces:**
- `secrets.web.name` supplies `RDHS_INGEST_TOKEN` and `RDHS_REFRESH_WEBHOOK_TOKEN`.
- `secrets.meegle.name` supplies `MEEGLE_USER_ACCESS_TOKEN` to sync workloads only.
- The chart has one primary Ingress; the refresh API is routed through it and access control remains owned by the existing internal gateway.

- [ ] **Step 1: Write the failing test**

```js
test("production render creates one Web replica with RWO storage and a monthly sync CronJob", async () => {
  const resources = await renderHelm("charts/rdhs-report", "values-prod.example.yaml");
  assert.equal(deployment(resources, "rdhs-report-web").spec.replicas, 1);
  assert.equal(pvc(resources).spec.accessModes[0], "ReadWriteOnce");
  assert.equal(cronJob(resources).spec.schedule, "0 9 1 * *");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/helm-chart.test.mjs`

Expected: FAIL because the chart does not exist.

- [ ] **Step 3: Write minimal implementation**

Create the chart described in the spec. Enforce a one-replica Web Deployment and `Recreate`, mount the RWO PVC only into Web, mount a shared NFS report-output directory into Runner/CronJob, expose Runner by ClusterIP only, fail closed without its webhook token, mount Meegle Secret only into runner/CronJob, and give CronJob `Forbid` concurrency, bounded command/deadline values and Asia/Shanghai time zone. Fail Helm rendering if mutable image tags or missing NFS storage are present. Keep NetworkPolicy opt-in but provide safe named-pod selector rules and DNS egress.

- [ ] **Step 4: Run test to verify it passes**

Run: `helm lint charts/rdhs-report -f charts/rdhs-report/values-prod.example.yaml && helm template rdhs-report charts/rdhs-report -f charts/rdhs-report/values-prod.example.yaml > /tmp/rdhs-rendered.yaml && node --test tests/helm-chart.test.mjs`

Expected: PASS, and no `kind: Secret` in `/tmp/rdhs-rendered.yaml`.

- [ ] **Step 5: Commit**

```bash
git add charts/rdhs-report tests/helm-chart.test.mjs
git commit -m "feat: add RDHS production Helm chart"
```

### Task 5: Production operations guide and final verification

**Files:**
- Modify: `README.md`, `docs/operations.md`, `.env.example`, `.env.sync.example`
- Modify: `package.json`

**Interfaces:**
- Documents exact web/sync image builds, Secret creation keys, Bootstrap import, deploy, probes, restore and rollback commands.

- [ ] **Step 1: Write the documentation acceptance checklist**

Document these executable acceptance commands: `npm test`, `npm run lint`, `npx tsc --noEmit`, `npm run build:k8s`, `helm lint`, `helm template`, and `kubectl rollout status`.

- [ ] **Step 2: Verify current documentation fails the checklist**

Run: `rg "Dockerfile|RDHS_MONTHLY_REPORT_COMMAND|replicaCount: 1" README.md docs/operations.md`

Expected: missing required production instructions.

- [ ] **Step 3: Write minimal documentation**

Add production preflight, build-context, secret, import, deploy, health, backup/restore and rollback instructions. Explicitly state that a VolumeSnapshot schedule and the existing internal gateway's access-control route are cluster prerequisites.

- [ ] **Step 4: Run final verification**

Run: `npm test && npm run lint && npx tsc --noEmit && npm run build:k8s && helm lint charts/rdhs-report -f charts/rdhs-report/values-prod.example.yaml`

Expected: PASS; record blocked external validations (registry push, Meegle auth, Kubernetes apply) separately.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/operations.md .env.example .env.sync.example package.json
git commit -m "docs: complete RDHS production runbook"
```
