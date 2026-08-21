# RDHS Code Simplifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce maintained and runtime surface area without changing the current RDHS HTTP contract or requiring a destructive database migration during this rollout.

**Architecture:** Keep the validated snapshot JSON as the application-facing source of truth. Stop generating unused normalized child projections while retaining the existing SQLite/D1 columns for backward compatibility. Package only the periodic-report import closure in the sync image and remove the unused D1 notes example/Drizzle runtime facade.

**Tech Stack:** TypeScript, Node test runner, Python, SQLite/D1, Dockerfile, Drizzle migration schema.

**Spec:** Findings from the repository-wide `find-code-simplifications` investigation completed on 2026-08-21.

## Global Constraints

- Preserve the existing monthly snapshot contract and all HTTP response shapes.
- Preserve the existing D1/SQLite migration history; do not rewrite `drizzle/0000_normal_zemo.sql`.
- Do not copy unreachable release-deploy, browser-auth, LLM, or legacy pipeline modules into the sync image.
- Keep `drizzle-orm` available for schema generation, but remove it from the production dependency set if no runtime import remains.
- Preserve all unrelated user modifications already present in the working tree.

### Task 1: Narrow the sync image and vendor snapshot

**Files:**
- Modify: `Dockerfile`
- Modify: `tests/dockerfiles.test.mjs`
- Delete: the 21 unreachable Python modules under `vendor/rdhs-workspace/topics/rdhs-operations/impl/`

**Interfaces:**
- Consumes: `vendor/rdhs-workspace/topics/rdhs-operations/run_periodic_report.py`.
- Produces: an image containing only the six `impl.periodic_report_*` / `impl.product_improvement_enrichment` modules needed by the production entry point.

- [x] **Step 1: Write the failing test**

Add a test that asserts the Dockerfile has explicit copies for the six reachable modules and does not copy the whole `impl` directory.

- [x] **Step 2: Run test to verify it fails**

Run: `node --test tests/dockerfiles.test.mjs`

Expected: FAIL because the Dockerfile currently contains `COPY vendor/.../impl /opt/.../impl`.

- [x] **Step 3: Write minimal implementation**

Replace the broad `COPY` with six explicit module copies and remove the unreachable vendor modules. Keep the entry script, periodic config, and mapping CSV unchanged.

- [x] **Step 4: Run test to verify it passes**

Run: `node --test tests/dockerfiles.test.mjs && python3 - <<'PY'
import ast
from pathlib import Path
root = Path("vendor/rdhs-workspace/topics/rdhs-operations")
ast.parse((root / "run_periodic_report.py").read_text())
print("periodic report entry parses")
PY`

Expected: PASS.

### Task 2: Remove the unused D1 example adapter

**Files:**
- Modify: `db/index.ts`
- Modify: `package.json`
- Modify: `package-lock.json`
- Modify: `tests/automation-shell.test.mjs`
- Delete: `examples/d1/app/api/notes/route.ts`
- Delete: `examples/d1/db/schema.ts`

**Interfaces:**
- Consumes: `getD1()` from the production D1 repository.
- Produces: a lightweight `db/index.ts` with only the D1 binding type and accessor; Drizzle remains a development-time schema-generation dependency.

- [x] **Step 1: Write the failing test**

Add structural assertions that `db/index.ts` does not import `drizzle-orm`, exports no `getDb`, and the unsupported `examples/d1` route is absent.

- [x] **Step 2: Run test to verify it fails**

Run: `node --test tests/automation-shell.test.mjs`

Expected: FAIL because `db/index.ts` currently imports Drizzle and exports `getDb`.

- [x] **Step 3: Write minimal implementation**

Remove the Drizzle import/schema import and `getDb()`, delete the unused notes example, and move `drizzle-orm` from `dependencies` to `devDependencies`. Regenerate the lockfile without upgrading unrelated packages.

- [x] **Step 4: Run test to verify it passes**

Run: `node --test tests/automation-shell.test.mjs && npm ls drizzle-orm --depth=0`

Expected: PASS; `drizzle-orm` appears as a development dependency.

### Task 3: Stop maintaining unused normalized child projections

**Files:**
- Modify: `lib/rdhs/d1-repository.ts`
- Modify: `lib/rdhs/sqlite-repository.ts`
- Modify: `tests/rdhs-sqlite-repository.test.mjs`
- Modify: `docs/superpowers/specs/2026-08-17-rdhs-live-operations-site-design.md`

**Interfaces:**
- Consumes: the existing `SnapshotRepository` API and legacy database schema.
- Produces: the same snapshot/version/read behavior without inserting or refreshing `rdhs_business_line_metrics` and `rdhs_product_metrics`.

- [x] **Step 1: Write the failing test**

Change the SQLite persistence test to assert that ingest succeeds and the stored `snapshot_json` contains the latest enriched fields without requiring normalized child-table rows.

- [x] **Step 2: Run test to verify it fails**

Run: `node --test tests/rdhs-sqlite-repository.test.mjs`

Expected: FAIL after the child-table expectations are changed because the current implementation still writes the normalized tables and the test will assert they are absent or unused.

- [x] **Step 3: Write minimal implementation**

Remove the D1 child-table batch statements and the SQLite child-table insert/replace helpers. Leave the legacy table definitions in place so existing databases remain readable and no destructive migration is needed in this rollout.

- [x] **Step 4: Run test to verify it passes**

Run: `node --test tests/rdhs-sqlite-repository.test.mjs tests/rdhs-repository.test.mjs`

Expected: PASS, including idempotent replacement and latest JSON fields.

### Task 4: Full verification and diff audit

**Files:**
- No additional source files.

- [x] **Step 1: Run focused and full checks**

Run: `npm test && npm run lint && npx tsc --noEmit --pretty false && npm run build:k8s && helm lint charts/rdhs-report -f charts/rdhs-report/values-prod.yaml && git diff --check`

- [x] **Step 2: Inspect the final diff**

Run: `git status --short && git diff --stat && rg -n "COPY vendor/rdhs-workspace/topics/rdhs-operations/impl |getDb\(|rdhs_business_line_metrics|rdhs_product_metrics" Dockerfile db lib tests examples`

Expected: only the pre-existing user changes plus the three focused simplifications and this plan are present; no production read path references the removed projections.
