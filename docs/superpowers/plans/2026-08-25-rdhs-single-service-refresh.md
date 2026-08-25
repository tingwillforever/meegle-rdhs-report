# RDHS Single-Service Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the standalone refresh runner and execute current-month refreshes from the Web service.

**Architecture:** The Node Web route starts one bounded Python sync child process guarded by an in-process lock. Web and CronJob keep using the existing Web ingest/internal APIs and MySQL lease state; only CronJob remains a separate Kubernetes workload.

**Tech Stack:** Node.js 22, Vinext, Python 3.10+, Meegle CLI, MySQL, Helm 3, Kubernetes.

**Spec:** `docs/superpowers/specs/2026-08-25-rdhs-single-service-refresh-design.md`

## Global Constraints

- Keep one application image and require no runtime package installation.
- Keep `POST /api/report/refresh` current-month-only and return 409 for overlapping local refreshes.
- Keep historical synchronization on the existing Shanghai 09:00 monthly CronJob.
- Do not retain a 8765 listener, `RDHS_REFRESH_WEBHOOK_*` setting, or runner Helm resource.
- Web and CronJob use `emptyDir`; MySQL remains the only production persistence service.

---

### Task 1: In-process current-month refresh executor

**Files:**
- Create: `lib/rdhs/current-month-refresh.ts`
- Modify: `app/api/report/refresh/route.ts`
- Modify: `tests/local-runtime.test.mjs`

**Interfaces:**
- Produces `refreshCurrentMonth(): Promise<{ message: string }>` and `CurrentRefreshInProgressError`.
- Consumes `RDHS_PYTHON_BIN`, `RDHS_OUTPUT_ROOT`, `RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS`, `RDHS_SITE_URL`, and `RDHS_INGEST_TOKEN`.

- [ ] **Step 1: Write failing tests**

```js
test("refresh API runs the current-month sync without a webhook runner", async () => {
  // Stub the Python child at the process boundary and assert a 200 result.
});

test("refresh API returns 409 while a local refresh is running", async () => {
  // Keep the first child pending, then issue a second request.
});
```

- [ ] **Step 2: Run the tests and confirm they fail because the executor does not exist.**

Run: `node --test tests/local-runtime.test.mjs`

- [ ] **Step 3: Implement the executor.**

```ts
spawn(pythonBin, ["scripts/sync-rdhs-snapshot.py", "--current-month-cache", "--as-of", today]);
```

Use the environment inherited from Web, add no shell interpolation, cap execution at the configured timeout, and include stderr/stdout in a bounded error message.

- [ ] **Step 4: Replace webhook forwarding in the route with the executor and map busy to 409, failures to 502.**

- [ ] **Step 5: Run `node --test tests/local-runtime.test.mjs` and `npx tsc --noEmit`.**

- [ ] **Step 6: Commit.**

```bash
git add lib/rdhs/current-month-refresh.ts app/api/report/refresh/route.ts tests/local-runtime.test.mjs
git commit -m "feat(refresh): run current sync in web service"
```

### Task 2: Collapse local development to Web

**Files:**
- Modify: `package.json`
- Delete: `scripts/dev-local.mjs`
- Delete: `scripts/local-refresh-runner.py`
- Modify: `README.md`
- Modify: `tests/local-runtime.test.mjs`

- [ ] **Step 1: Write a failing test that `npm run dev -- --dry-run` has no runner command or port 8765 dependency.**
- [ ] **Step 2: Run `node --test tests/local-runtime.test.mjs` and confirm failure.**
- [ ] **Step 3: Set `dev` directly to the existing Vinext command; remove the runner scripts and their package command.**
- [ ] **Step 4: Document that one `npm run dev` starts the only local service at port 3000.**
- [ ] **Step 5: Run the focused tests and start `npm run dev`; verify `/api/health/live` at 3000 and no listener at 8765.**
- [ ] **Step 6: Commit.**

### Task 3: Remove Runner from Helm and give Web refresh capability

**Files:**
- Modify: `charts/rdhs-report/templates/deployment-web.yaml`
- Delete: `charts/rdhs-report/templates/deployment-runner.yaml`
- Delete: `charts/rdhs-report/templates/service-runner.yaml`
- Modify: `charts/rdhs-report/templates/networkpolicy.yaml`
- Modify: `charts/rdhs-report/templates/_helpers.tpl`
- Modify: `charts/rdhs-report/templates/secrets.yaml`
- Modify: `charts/rdhs-report/templates/NOTES.txt`
- Modify: `charts/rdhs-report/values.yaml`
- Modify: `charts/rdhs-report/values-prod.yaml`
- Modify: `tests/helm-chart.test.mjs`

- [ ] **Step 1: Write failing render assertions requiring no `component: runner`, no port 8765, and Web environment entries for report execution.**
- [ ] **Step 2: Run `node --test tests/helm-chart.test.mjs` and confirm failure.**
- [ ] **Step 3: Move report command, workspace, output and timeout environment plus `emptyDir` mount from Runner to Web. Set `RDHS_SITE_URL` to the internal Web service path.**
- [ ] **Step 4: Delete Runner templates/helper/values and webhook secret validation. Move Meegle egress from Runner to Web policy.**
- [ ] **Step 5: Run Helm focused tests and `helm template` with production values; verify no runner manifests or webhook secret key.**
- [ ] **Step 6: Commit.**

### Task 4: Image and operations alignment

**Files:**
- Modify: `Dockerfile`
- Modify: `.env.example`
- Modify: `docs/operations.md`
- Modify: `README.md`
- Modify: `tests/dockerfiles.test.mjs`

- [ ] **Step 1: Write failing Docker/documentation assertions for the single port/service model.**
- [ ] **Step 2: Run the focused test and confirm failure.**
- [ ] **Step 3: Remove `EXPOSE 8765`; remove webhook Runner configuration and replace operating instructions with Web direct-refresh and CronJob-only instructions.**
- [ ] **Step 4: Run `npm test`, `npm run lint`, `npx tsc --noEmit`, `npm run build:k8s`, and `helm lint charts/rdhs-report -f charts/rdhs-report/values-prod.yaml`.**
- [ ] **Step 5: Commit.**
