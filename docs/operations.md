# RDHS 运营站点运行手册

## 1. 前置检查

同步任务必须运行在能够访问内网 Meegle 私有部署的 Mac 或任务机上。

```bash
meegle auth status
meegle chart get \
  --project-key cbg_product_develop \
  --chart-id 7659618575337915254 \
  --format json
```

站点本身只接收经过现有周期报告流水线校验的快照。Chart 原始行数异常、有效产品覆盖异常、产品总数不一致、测试业务线混入、分档不一致等情况都会中止同步，最近有效报告保持不变。

## 2. 同步环境

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

## 3. 手工同步

生成并上传上一个完整月：

```bash
./scripts/run-sync-job.sh monthly
```

生成并上传上一个完整周：

```bash
./scripts/run-sync-job.sh weekly
```

指定日期或使用已有报告目录做无上传校验：

```bash
python3 scripts/sync-rdhs-snapshot.py \
  --cadence monthly \
  --as-of 2026-08-31 \
  --dry-run

python3 scripts/sync-rdhs-snapshot.py \
  --cadence monthly \
  --source-dir ../reports/periodic-rerun-20260817/2026-08/monthly-report \
  --dry-run
```

生成的 schema-v1 快照位于 `runtime/sync-runs/site-snapshots/`。同周期同源哈希重复上传为幂等成功；修正后的不同哈希会形成新版本并成为当前版本。

## 4. 历史导入

导入一个或多个已验证报告目录：

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

## 5. 自动运行

```bash
./scripts/install-launchd.sh
```

安装两个用户级任务：

- `com.rdhs.operations.weekly`：每周一 09:00 生成上个完整周。
- `com.rdhs.operations.monthly`：每月 1 日 09:00 生成上个完整月。

任务统一通过 `scripts/run-sync-job.sh` 加载 `.env.sync`。日志位于：

```text
runtime/sync.log
runtime/sync-error.log
```

状态检查：

```bash
launchctl print gui/$(id -u)/com.rdhs.operations.weekly
launchctl print gui/$(id -u)/com.rdhs.operations.monthly
```

## 6. 站点接口

- `GET /api/periods?cadence=monthly|weekly`：有效周期列表。
- `GET /api/report?cadence=monthly&period=YYYY-MM`：当前月度快照。
- `GET /api/report?cadence=weekly&period=YYYY-MM-DD`：当前周度快照。
- `GET /api/trends`：月度趋势。
- `POST /api/snapshots`：Bearer 保护的快照写入。

D1 保存不可变版本、业务线汇总、产品明细和失败诊断。只有完整批量写入成功后，新版本才可见。

## 7. 故障处理

### Meegle 拉取失败

运行 `meegle auth status`，再直接执行本期 Chart 查询。确认内网、登录态、项目 key 和 Chart ID。同步器返回非零状态，不会影响线上最近有效报告。

### 覆盖率保护拒绝

检查运行目录中的 `audit_manifest.json`：重点核对 `raw_row_count`、`accepted_row_count`、`clean_research_product_total`、`measured_research_product_total` 和源哈希。不得通过手工补 0 绕过保护；应修复产品关联或重新获取完整 Chart。

### 站点拒绝 401

确认 `.env.sync` 的 URL 指向当前私有部署，并让本机令牌与 Sites 环境变量 `RDHS_INGEST_TOKEN` 一致。不要在命令行回显令牌。

### 站点拒绝 422

响应会给出合同字段路径。修复源报告或转换逻辑后生成新快照。非法快照会记录失败诊断，但不会提升当前版本。

### 页面仍显示历史快照

先访问 `/api/periods` 确认 D1 已有周期，再检查页面数据状态。成功上传后刷新页面；若 D1 为空，页面会继续使用内置已验证快照并显示“已验证历史快照”。

## 8. 发布检查

每次变更至少执行：

```bash
npm test
npm run lint
sqlite3 /tmp/rdhs-migration-check.db < drizzle/0000_normal_zemo.sql
```

发布前在桌面 `1440x900` 和移动 `390x844` 检查周/月切换、周期选择、业务线筛选、未度量筛选、产品详情、表格滚动和数据审计。站点默认使用私有访问策略。
