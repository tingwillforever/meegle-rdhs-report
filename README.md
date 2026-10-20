# RDHS 产研过程效能运营报告

消费者 BG 的月度 RDHS 运营工作台。站点以研发中产品主数据为底表，排除测试业务线及产品属性为交付定制的产品，左关联产品维度 RDHS 数据，并将未度量/待关联产品纳入重点治理。

## 数据口径

- 产品范围：状态为 `In Progress` 的产品主数据。
- 排除范围：`测试业务线`，以及产品属性为 `交付定制` 的产品主数据。
- 关联键：规范化后的 `一级业务线 + 产品`。
- 治理分档：`<45 + 未度量/待关联`、`45~<60`、`60~<70`、`>=70`。
- 平均 RDHS：全部符合月度快照口径的产品纳入分母，未度量产品考核计 0；原始评分仍保留 `null`，覆盖率单独展示。空范围显示无数据。
- 环比：只对比上一个自然月；缺月不跳月。当月累计（MTD）与上月整月不同口径，不能直接归因为效能退步。

## 业务线 CTO 工作台

从 BG 大盘业务线排名点击下钻，或直接打开：
`https://tingwillforever.github.io/meegle-rdhs-report/?period=2026-09&view=workbench&line=开放平台业务群`。

工作台展示业务线考核均分、上月对比、BG 排名、达标率、覆盖率、二级业务线分布和最多 3 项治理核查事项。
二级线、搜索、分档等列表筛选不会改变上方整条业务线指标；产品详情沿用现有快照，不推断缺失责任人或平均汇总人数/周期/比例。

回归后可使用真实 Chrome 验收静态站点（需 Python Playwright 和 Chrome）：

```bash
RDHS_BASE_PATH=/meegle-rdhs-report npm run build:pages
# 本地静态服务器需映射 /meegle-rdhs-report/ 到 dist/static/。
RDHS_E2E_URL=http://localhost:8089/meegle-rdhs-report/ python3 scripts/browser-acceptance.py
```

`RDHS_E2E_EVIDENCE` 可指定截图与日志目录。推送 `github/main` 后由 GitHub Actions 构建并发布；正式验收还需检查 Actions 结果与线上浏览器路径。
- 发布保护：不完整或不一致的源数据不得替换最近有效快照。

完整语义定义见 [设计说明](docs/superpowers/specs/2026-08-17-rdhs-live-operations-site-design.md)，日常操作见 [运行手册](docs/operations.md)。

## 架构

```text
Meegle CLI -> run_periodic_report.py -> report_data/audit
          -> snapshot sync -> ingest API -> history storage
          -> React operations dashboard
```

Cloudflare/Sites 模式使用 D1；Kubernetes 模式使用 Node/Vinext + MySQL。通过
`DEPLOY_TARGET=k8s` 选择 K8s 构建，领域层和快照合同保持一致。生产集群中 Meegle CLI
只在同步工作负载中注入，浏览器和 Web 工作负载均不会接触 Meegle 凭据。

```text
业务用户 -> 现有内网网关 -> Web（Vinext + Python + Meegle CLI + emptyDir） -> MySQL（快照、基线、租约）
每月 1 日 09:00 -> Sync CronJob（Python + Meegle CLI + emptyDir） -----------^
```

当月刷新由 `POST /api/report/refresh` 在 Web 进程内直接执行 Python + Meegle CLI；历史月份由每月 1 日任务生成并写入。
同一任务会先以**当月 1 日**固化供当月刷新复用的上月基线，再以**上月末**生成可上传报告。基线和
跨 Pod 租约经 Web 内部 API 保存到 MySQL；报告运行目录只使用 Pod 的 `emptyDir`，不需要 NFS 或 PVC。
详细上线、备份和恢复流程见[运行手册](docs/operations.md)。

## 本地开发

前置版本：Node.js `>=22.13.0`、Python `>=3.10`。

```bash
npm install
npm run dev
```

`npm run dev` 只启动 Web（`3000`）：页面、API 与当月 Python + Meegle CLI 刷新都由该进程承载。
该命令使用 Node 运行时（不使用 Workers），并自动加载 `.dev.vars`；实际刷新时在其中配置
`RDHS_SITE_URL` 与 `RDHS_INGEST_TOKEN`（可从 `.env.example` 复制）。
D1 尚无数据时，首页使用仓库内两份已验证月度快照并明确标记为预览快照。

## 内网 K8s 生产部署

Kubernetes 生产环境使用 MySQL 作为唯一持久化存储。Web 是唯一 MySQL 客户端；Web 刷新和 CronJob
通过 Bearer 保护的 Web 内部 API 读写月初基线和分布式租约，不安装 Python MySQL 驱动。

生产交付在 [charts/rdhs-report](charts/rdhs-report) 中，包含 Web、月度 CronJob、
Ingress 与可选 NetworkPolicy。必须预先提供：MySQL 数据库与应用账号、应用 Secret、
Kubernetes 到 `172.31.114.194:4302` 的网络连通，以及可拉取内部镜像的凭据（如需要）。
数据库初始化脚本为 [`database/mysql/001_initial.sql`](database/mysql/001_initial.sql)。当前
`values-prod.yaml` 为上线前验证临时以内联方式创建 `rdhs-report-db-secrets`；验证完成后应改回
托管 Secret 并轮换数据库密码。

现网入口沿用 meegle-mcp 的域名和镜像仓库约定：
`https://ossptest.voicecloud.cn/meegle-rdhs-report/`。生产 values 已将统一镜像指向
`artifacts.iflytek.com/cbg-docker-repo/cbbywkf/meegle-rdhs-report`，并引用集群预置的 `hub4iflytek` pull Secret；
生产 `RDHS_INGEST_TOKEN` 由 `values-prod.yaml` 直接注入 Web 与 CronJob；数据库凭据的明文配置仅用于本轮快速验证，
不得作为长期生产配置保留。

`database/mysql/001_initial.sql` 创建快照、基线和租约表。每条 Meegle 报告命令最多运行 540 秒，
CronJob 最多运行 1,500 秒，MySQL 租约为 1,800 秒；超时后失败并按 Job 重试策略处理。

构建命令、Secret Key、Helm 发布、首次导入、监控、备份恢复和回滚命令均在
[运行手册](docs/operations.md#10-kubernetes-生产部署) 中。开发或本地冒烟可使用：

```bash
npm run build:k8s
RDHS_STORAGE=mysql MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 \
  MYSQL_DATABASE=rdhs_report MYSQL_USER=rdhs_report MYSQL_PASSWORD='<password>' \
  npm run start:k8s
```

生产镜像入口为 `Dockerfile`，它直接依赖预构建的 Node 22、Python、Meegle CLI 基础镜像，并复制
报告代码和同步脚本；Web 和 Sync CronJob 通过不同启动命令复用同一个应用镜像。`/api/health/live` 是进程存活探针，
`/api/health` 是 MySQL 就绪探针。

## 验证

```bash
npm test
npm run lint
npx tsc --noEmit
npm run build:k8s
helm lint charts/rdhs-report -f charts/rdhs-report/values-prod.yaml
bash -n charts/build-chart.sh scripts/run-sync-job.sh scripts/install-launchd.sh
```

`npm test` 依次执行领域/接口/筛选单元测试、Python 同步器测试、生产构建和服务端渲染测试。

## 目录

- `app/`：页面、交互组件和 API 路由。
- `lib/rdhs/`：快照合同、校验、聚合、筛选和仓储。
- `db/`、`drizzle/`：D1 模型与迁移；`database/mysql/`：MySQL 生产迁移。
- `scripts/`：快照同步、历史导入和定时任务安装。
- `data/`：首次部署前可用的已验证历史快照。
- `tests/`：Node、Python 与渲染测试。
