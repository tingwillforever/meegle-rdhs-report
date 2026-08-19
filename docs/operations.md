# RDHS 运营站点运行手册

## 1. 数据口径

站点只呈现月报。产品视角采用固定加工链路：

```text
研发中产品主数据 -> 排除测试业务线 -> left join RDHS Chart -> 未度量/待关联纳入重点治理 -> 产品明细 -> 业务线/CBG 汇总
```

核心指标口径：

- `常规跟踪`：RDHS >= 70。
- `产品规范率`：常规跟踪产品数 / 研发中产品总数。
- `待治理占比`：非常规跟踪产品数 / 研发中产品总数。
- `平均 RDHS`：仅统计已度量产品，不用未度量产品拉低均值。
- `度量覆盖率`：已度量产品数 / 研发中产品总数。
- `未度量/待关联`：纳入重点治理，同时进入待治理产品数。

## 2. 当月缓存与历史快照

当月默认读取站点缓存，不在页面加载时实时查询 Meegle。顶部「更新数据」按钮会调用 `POST /api/report/refresh`：

- 配置了 `RDHS_REFRESH_WEBHOOK_URL` 时，接口触发内网任务机实时拉取 Meegle 并覆盖当月缓存。
- 未配置刷新服务时，接口返回清晰错误，页面继续展示最近一次当月缓存。
- 历史月份不支持实时刷新，均读取月初固化快照。

历史快照由每月 1 日任务生成上一个完整月，并写入站点。快照必须包含当时的产品主数据、业务线归属、RDHS 度量结果和未度量/待关联产品。

## 3. 前置检查

同步任务必须运行在能够访问内网 Meegle 私有部署的 Mac 或任务机上。

```bash
meegle auth status
meegle chart get \
  --project-key cbg_product_develop \
  --chart-id 7659618575337915254 \
  --format json
```

站点只接收经过周期报告流水线校验的月度快照。Chart 原始行数异常、有效产品覆盖异常、产品总数不一致、测试业务线混入、分档不一致等情况都会中止同步，最近有效报告保持不变。

## 4. 同步环境

在项目根目录创建本机专用环境文件并限制权限：

```bash
install -m 600 .env.sync.example .env.sync
```

填写：

```dotenv
RDHS_SITE_URL=https://<private-sites-url>
RDHS_INGEST_TOKEN=<sites-secret-token>
```

`.env.sync` 已被 Git 忽略。令牌仅用于 `POST /api/snapshots`，不得写入报告、日志或仓库。

## 5. 手工同步

生成并上传上一个完整月：

```bash
./scripts/run-sync-job.sh
```

指定日期或使用已有报告目录做无上传校验：

```bash
python3 scripts/sync-rdhs-snapshot.py \
  --as-of 2026-08-31 \
  --dry-run

python3 scripts/sync-rdhs-snapshot.py \
  --source-dir ../reports/periodic-rerun-20260817/2026-08/monthly-report \
  --dry-run
```

刷新当月缓存：

```bash
python3 scripts/sync-rdhs-snapshot.py --current-month-cache
```

当月缓存模式使用 `run_periodic_report.py --mode monthly`，读取当前 Meegle Chart；月初固化历史快照仍使用默认的上一个完整月。

生成的 schema-v1 快照位于 `runtime/sync-runs/site-snapshots/`。同周期同源哈希重复上传为幂等成功；修正后的不同哈希会形成新版本并成为当前版本。

## 6. 历史导入

导入一个或多个已验证月报目录：

```bash
python3 scripts/import-existing-reports.py \
  ../reports/command-smoke/2026-07/monthly-report \
  ../reports/periodic-rerun-20260817/2026-08/monthly-report
```

先检查转换结果但不上传：

```bash
python3 scripts/import-existing-reports.py --dry-run <report-root...>
```

导入器只读取同时存在的 `report_data.json` 和 `audit_manifest.json`，并跳过重复源哈希。

## 7. 自动运行

```bash
./scripts/install-launchd.sh
```

安装用户级任务：

- `com.rdhs.operations.monthly`：每月 1 日 09:00 生成上个完整月。

任务通过 `scripts/run-sync-job.sh` 加载 `.env.sync`。日志位于：

```text
runtime/sync.log
runtime/sync-error.log
```

状态检查：

```bash
launchctl print gui/$(id -u)/com.rdhs.operations.monthly
```

## 8. 站点接口

- `GET /api/periods`：有效月度周期列表。
- `GET /api/report?period=YYYY-MM`：指定月度报告；不传 period 时返回最近月度报告。
- `GET /api/trends`：月度趋势。
- `POST /api/report/refresh`：触发当月缓存刷新。
- `POST /api/snapshots`：Bearer 保护的快照写入。

D1 保存不可变版本、业务线汇总、产品明细和失败诊断。只有完整批量写入成功后，新版本才可见。

## 9. 发布检查

每次变更至少执行：

```bash
npm test
npm run lint
sqlite3 /tmp/rdhs-migration-check.db < drizzle/0000_normal_zemo.sql
```

发布前在桌面 `1440x900` 和移动 `390x844` 检查月份选择、更新数据、业务线筛选、趋势切换、未度量筛选、产品详情、表格滚动和数据审计。
