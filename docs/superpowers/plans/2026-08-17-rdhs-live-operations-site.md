# RDHS 实时运营报告网页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一个由 Meegle CLI 同步、Sites+D1 托管、支持周/月历史查询与月度趋势的 RDHS 运营工作台。

**Architecture:** 本机/内网 Python 同步器复用现有周期报告流水线并上传稳定快照合同；Vinext 服务端校验后写入 D1，React 页面读取当前和历史快照。写入采用不可变版本和当前指针，失败数据不会覆盖有效报告。

**Tech Stack:** Python 3.13、Meegle CLI、Vinext/React 19、TypeScript 5.9、Cloudflare D1、Drizzle、Node test runner、Playwright CLI、OpenAI Sites。

## Global Constraints

- 产品底表仅包含 `In Progress`，排除 `测试业务线`，按 `一级业务线 + 产品` 左关联。
- 未度量/待关联纳入重点治理，RDHS 必须保持 `null`。
- 治理阈值固定为 `<45`、`45~<60`、`60~<70`、`>=70`。
- 月度平均 RDHS 只统计已度量产品，覆盖率单独计算。
- 页面和接口使用简体中文，时间使用 `Asia/Shanghai`。
- Sites 托管端不得执行或持有 Meegle CLI 凭据。
- 失败快照不得替换最近有效快照。

---

### Task 1: 快照合同与趋势聚合

**Files:**
- Create: `lib/rdhs/types.ts`
- Create: `lib/rdhs/validate.ts`
- Create: `lib/rdhs/aggregate.ts`
- Create: `tests/rdhs-domain.test.mjs`

**Interfaces:**
- Consumes: 站点同步快照 JSON。
- Produces: `validateSnapshot(input): RdhsSnapshot`、`summarizeSnapshot(snapshot): SnapshotSummary`、`buildMonthlyTrend(snapshots): TrendPoint[]`。

- [ ] **Step 1: Write the failing test**：用手工 fixture 断言未度量产品进入重点治理、平均 RDHS 不含空值、四档合计校验和月度趋势排序。
- [ ] **Step 2: Run test to verify it fails**：运行 `node --test tests/rdhs-domain.test.mjs`，预期因模块不存在失败。
- [ ] **Step 3: Write minimal implementation**：实现类型、合同校验、分档函数和聚合函数；错误包含 JSON 字段路径。
- [ ] **Step 4: Run test to verify it passes**：再次运行同一命令，预期全部通过。
- [ ] **Step 5: Commit**：提交 `test: define RDHS snapshot contract`。

### Task 2: D1 快照存储与查询接口

**Files:**
- Modify: `.openai/hosting.json`
- Modify: `db/schema.ts`
- Modify: `db/index.ts`
- Create: `lib/rdhs/repository.ts`
- Create: `app/api/snapshots/route.ts`
- Create: `app/api/report/route.ts`
- Create: `app/api/periods/route.ts`
- Create: `app/api/trends/route.ts`
- Create: `tests/rdhs-repository.test.mjs`

**Interfaces:**
- Consumes: `RdhsSnapshot`、D1 `DB` binding、`RDHS_INGEST_TOKEN`。
- Produces: 幂等上传接口和只读报告/周期/趋势接口。

- [ ] **Step 1: Write the failing test**：使用内存仓储 fixture 验证同源哈希幂等、非法快照不提升当前版本、周期查询返回当前版本、趋势只包含月报。
- [ ] **Step 2: Run test to verify it fails**：运行 `node --test tests/rdhs-repository.test.mjs`，预期缺少仓储模块失败。
- [ ] **Step 3: Write minimal implementation**：定义三张表、索引、事务写入和查询接口；配置 D1 逻辑绑定 `DB`。
- [ ] **Step 4: Run test to verify it passes**：运行仓储测试与 `npm run db:generate`，检查生成迁移只有预期表和索引。
- [ ] **Step 5: Commit**：提交 `feat: persist validated RDHS snapshots`。

### Task 3: Meegle 同步器与历史导入

**Files:**
- Create: `scripts/sync-rdhs-snapshot.py`
- Create: `scripts/import-existing-reports.py`
- Create: `scripts/install-launchd.sh`
- Create: `tests/test_rdhs_web_sync.py`
- Create: `.env.example`

**Interfaces:**
- Consumes: 现有 `run_periodic_report.py` 的 `report_data.json`、`audit_manifest.json`、站点 URL 和写入令牌。
- Produces: schema v1 快照、HTTPS 上传、周/月运行命令和已有报告批量导入。

- [ ] **Step 1: Write the failing test**：断言正确转换 67 个研发中产品、排除测试业务线、未度量 RDHS 为 `None`、周期键正确，以及远端拒绝时退出非零。
- [ ] **Step 2: Run test to verify it fails**：运行 `pytest -q tests/test_rdhs_web_sync.py`，预期因同步模块不存在失败。
- [ ] **Step 3: Write minimal implementation**：调用现有 CLI、读取审计产物、转换合同、使用标准库 HTTPS 上传并提供 launchd/cron 入口。
- [ ] **Step 4: Run test to verify it passes**：运行同步器测试并用现有 2026-08 快照执行 `--dry-run`，核对输出汇总。
- [ ] **Step 5: Commit**：提交 `feat: sync Meegle RDHS snapshots`。

### Task 4: 第一屏与核心报告页面

**Files:**
- Modify: `app/page.tsx`
- Modify: `app/layout.tsx`
- Modify: `app/globals.css`
- Create: `app/components/report-dashboard.tsx`
- Create: `app/components/score-rail.tsx`
- Create: `app/components/trend-chart.tsx`
- Create: `lib/rdhs/demo-data.ts`
- Modify: `package.json`

**Interfaces:**
- Consumes: 报告和趋势接口；无 D1 数据时使用明确标注的内置演示快照。
- Produces: 可识别的 RDHS 工作台第一屏、周/月与周期选择、核心指标和趋势。

- [ ] **Step 1: Write the failing test**：扩展渲染测试，断言页面包含周期切换、四个核心指标、70 分基线和数据状态。
- [ ] **Step 2: Run test to verify it fails**：运行 `npm test`，预期 starter 页面不满足断言。
- [ ] **Step 3: Write minimal implementation**：完成第一屏与设计令牌，移除 starter skeleton 和 `react-loading-skeleton`。
- [ ] **Step 4: Run test to verify it passes**：启动开发服务，检查目标路由返回成功并打开首次有效预览。
- [ ] **Step 5: Commit**：提交 `feat: build RDHS operations overview`。

### Task 5: 业务线与产品下钻

**Files:**
- Modify: `app/components/report-dashboard.tsx`
- Create: `app/components/business-line-table.tsx`
- Create: `app/components/product-table.tsx`
- Create: `app/components/data-audit.tsx`
- Create: `tests/dashboard-interactions.test.mjs`

**Interfaces:**
- Consumes: 当前快照业务线、产品和审计字段。
- Produces: 排序、业务线选择、产品搜索、治理分档筛选、未度量筛选和异常说明。

- [ ] **Step 1: Write the failing test**：断言业务线选择收窄产品、搜索匹配产品名、未度量筛选只显示空 RDHS、清除筛选恢复全量。
- [ ] **Step 2: Run test to verify it fails**：运行 `node --test tests/dashboard-interactions.test.mjs`，预期交互模块不存在失败。
- [ ] **Step 3: Write minimal implementation**：实现纯筛选/排序函数和响应式表格组件，按钮使用 Lucide 图标并提供 tooltip/aria-label。
- [ ] **Step 4: Run test to verify it passes**：运行交互测试和 `npm test`。
- [ ] **Step 5: Commit**：提交 `feat: add business and product drilldowns`。

### Task 6: 社交预览、运行文档与最终验证

**Files:**
- Create: `public/og.png`
- Modify: `app/layout.tsx`
- Modify: `README.md`
- Create: `docs/operations.md`

**Interfaces:**
- Consumes: 完成的页面、同步命令、Sites 配置。
- Produces: 站点元数据、自动运行手册、故障诊断手册和可部署构建。

- [ ] **Step 1: Write the failing test**：在渲染测试中断言站点标题、描述和无 starter 元数据。
- [ ] **Step 2: Run test to verify it fails**：运行 `npm test`，预期元数据断言失败。
- [ ] **Step 3: Write minimal implementation**：生成并检查一张站点社交预览图，写入元数据与运行文档。
- [ ] **Step 4: Run test to verify it passes**：运行 Python 全量测试、Node 测试、Lint、D1 迁移检查和 `npm run build`；随后用 Playwright 在 1440×900、390×844 验证周期切换、下钻、筛选、无重叠和无横向溢出。
- [ ] **Step 5: Commit**：提交 `docs: finish RDHS operations site`。

### Task 7: Sites 发布与部署后验收

**Files:**
- Modify: `.openai/hosting.json`

**Interfaces:**
- Consumes: 已验证构建、D1 migration、精确源码提交。
- Produces: 私有 Sites URL 和部署状态证据。

- [ ] **Step 1: Create Site**：仅调用一次 Sites 创建接口并保存 `project_id`。
- [ ] **Step 2: Configure runtime**：绑定 D1，设置 `RDHS_INGEST_TOKEN` 为 secret。
- [ ] **Step 3: Save version**：推送精确提交，打包 `dist` 和迁移并保存版本。
- [ ] **Step 4: Deploy privately**：部署私有版本并轮询至成功。
- [ ] **Step 5: Verify production**：打开部署 URL，检查首页、周期接口和当前报告；确认站点默认不公开。

