# RDHS 运营站点运行手册

## 1. 数据口径

站点只呈现月报。产品视角采用固定加工链路：

```text
研发中产品主数据 -> 排除测试业务线和交付定制产品 -> left join RDHS Chart -> 未度量/待关联纳入重点治理 -> 产品明细 -> 业务线/CBG 汇总
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

历史快照由每月 1 日任务生成上一个完整月，并写入站点。任务先以**当月 1 日**运行
`monthly-baseline`，将上月比较基线固化到当月目录；再以**上月末**运行 `weekly`，生成上一完整月
的可上传报告。该基线被当月刷新复用，生产环境通过 Web 内部 API 按月份保存到 MySQL；
Runner/CronJob 的本地报告目录可以是一次性的 `emptyDir`。快照必须包含当时的产品主数据、业务线归属、RDHS 度量结果和未度量/待关联产品。

## 3. 前置检查

本地同步任务必须运行在能够访问内网 Meegle 私有部署的 Mac 或任务机上；生产环境则由
统一生产镜像承载 Meegle CLI，不依赖任何 Kubernetes 宿主机已安装的 CLI。

```bash
meegle auth status
meegle chart get \
  --project-key cbg_product_develop \
  --chart-id 7659618575337915254 \
  --format json
```

站点只接收经过周期报告流水线校验的月度快照。Chart 原始行数异常、有效产品覆盖异常、产品总数不一致、测试业务线或交付定制产品混入、分档不一致等情况都会中止同步，最近有效报告保持不变。

## 4. 同步环境

在项目根目录创建本机专用环境文件并限制权限：

```bash
install -m 600 .env.sync.example .env.sync
```

填写：

```dotenv
RDHS_SITE_URL=https://<private-sites-url>
RDHS_INGEST_TOKEN=<sites-secret-token>
RDHS_MONTHLY_BASELINE_COMMAND=python3 /absolute/path/to/rdhs-workspace/topics/rdhs-operations/run_periodic_report.py --mode monthly-baseline
RDHS_MONTHLY_REPORT_COMMAND=python3 /absolute/path/to/rdhs-workspace/topics/rdhs-operations/run_periodic_report.py --mode weekly
RDHS_CURRENT_REPORT_COMMAND=python3 /absolute/path/to/rdhs-workspace/topics/rdhs-operations/run_periodic_report.py --mode weekly
# 本机可以使用同一目录；K8s 中每个 Pod 使用自己的 emptyDir
RDHS_OUTPUT_ROOT=/absolute/path/to/persistent/rdhs-sync
RDHS_REPORT_COMMAND_TIMEOUT_SECONDS=540
RDHS_SYNC_LEASE_TTL_SECONDS=1800
RDHS_OUTPUT_RETENTION_MONTHS=6
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

月度任务先以当月 1 日运行 `monthly-baseline` 固化比较基线，再以上月末运行 `weekly` 生成包含
`report_data.json` 的可上传报告；`monthly-baseline` 自身不会生成可上传快照。当前月缓存使用
`weekly` 模式读取当前 Meegle Chart。生产同步器先从 Web 下载所需月份的基线到本地目录，运行后再上传
新生成或回补的基线；MySQL 租约用于避免 CronJob 与刷新任务并发执行，本地文件锁只保护单个 Pod 内部写入。

成功写入站点后，同步器只清理按 `YYYY-MM` 命名且超过 `RDHS_OUTPUT_RETENTION_MONTHS`（默认 6 个自然月）的
报告运行目录及 `site-snapshots/monthly-YYYY-MM.json`；不会删除其他路径。K8s 中这些文件位于 `emptyDir`，
Pod 退出时自动删除，真正需要备份的是 MySQL。单条报告命令最多运行 `RDHS_REPORT_COMMAND_TIMEOUT_SECONDS`（默认 540）秒，
超时会明确失败，不能无限占用同步任务。

生成的 schema-v1 快照位于 `runtime/sync-runs/site-snapshots/`。同周期同源哈希重复上传为幂等成功；修正后的不同哈希会形成新版本并成为当前版本。

本地点击页面「更新数据」前，需要启动本机刷新 runner：

```bash
npm run dev
npm run db:migrate:local
npm run dev:refresh-runner
```

`.dev.vars` 中至少需要配置 `RDHS_INGEST_TOKEN`、`RDHS_REFRESH_WEBHOOK_URL=http://127.0.0.1:8765/rdhs/refresh` 和 `RDHS_REFRESH_WEBHOOK_TOKEN`。如本机默认 `python3` 低于 3.10，可额外配置 `RDHS_PYTHON_BIN`。站点 API 只触发 runner；真正的 Meegle CLI 查询仍在本机 runner 内执行。

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

安装本机用户级任务（仅用于本地/任务机，不用于 Kubernetes 生产环境）：

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
- `GET/PUT /api/internal/sync/baseline`：Runner/CronJob 读写按月基线。
- `POST /api/internal/sync/lock/acquire|release`：Runner/CronJob 管理 MySQL 租约。

D1、SQLite（本地兼容）和 MySQL 模式均保存不可变快照版本。K8s 生产只使用 MySQL；快照切换在事务中完成，
只有完整写入成功后新版本才可见。内部同步接口与快照写入共用 `RDHS_INGEST_TOKEN`，且只由集群内工作负载调用。

## 9. 发布检查

每次变更至少执行：

```bash
npm test
npm run lint
mysql --host=<mysql-host> --port=<mysql-port> --user=<migration-user> -p <rdhs_report> \
  < database/mysql/001_initial.sql
sqlite3 /tmp/rdhs-migration-check.db < drizzle/0000_normal_zemo.sql
```

发布前在桌面 `1440x900` 和移动 `390x844` 检查月份选择、更新数据、业务线筛选、趋势切换、未度量筛选、产品详情、表格滚动和数据审计。

## 10. Kubernetes 生产部署

### 10.1 架构与前置依赖

生产环境使用 MySQL 作为唯一持久化数据库，迁移脚本为 `database/mysql/001_initial.sql`。
Web 是 MySQL 的唯一客户端；Runner/CronJob 通过 Web 内部 API 管理基线与租约，不直接连接数据库。
报告运行目录位于 Pod 自己的 `emptyDir`，Pod 重建后丢弃，不承担持久化职责。

同步能力不在 Kubernetes 节点安装：Node、Python、指定版本 Meegle CLI 预先打入基础镜像，
`Dockerfile` 直接依赖该基础镜像并复制经过审查的报告代码。Web、Runner 和 CronJob 复用一个应用镜像，只通过 Kubernetes command
区分启动角色。Runner 仅通过 ClusterIP 接收 Web 的刷新请求；CronJob 在
`Asia/Shanghai` 时区每月 1 日 09:00 运行：先以当月 1 日固化上月基线，再以上月末生成并上传月度快照。
两者都使用 `/var/lib/rdhs-sync` 的 `emptyDir` 保存临时基线副本和运行产物；基线写回 Web 后进入 MySQL。
Chart 默认每条报告命令超时 540 秒，CronJob 的 `activeDeadlineSeconds` 为 1,500 秒，防止卡住的任务因
`concurrencyPolicy: Forbid` 长期阻塞下个月执行。

集群/构建环境必须在发布前提供：

- Kubernetes 1.27+、Helm 与 NGINX Ingress；访问控制由现有内网网关负责，Chart 不配置或创建网关认证。
- 已创建 `rdhs_report` 数据库、生产账号和最小权限；Web Pod 可访问 `172.31.114.194:4302`。
- 已执行 `database/mysql/001_initial.sql`，并为 MySQL 备份和恢复设置策略（建议至少保留 180 天）。
- 可拉取统一生产镜像的内部镜像仓库；若仓库受保护，提供现有 `kubernetes.io/dockerconfigjson` Secret。
- 基础镜像已包含 Node `>=22.13`、Python `>=3.10`、`bash`、PyYAML、Meegle CLI `@tingwillforever/meegle-cli@1.1.5`，以及完整的 Meegle CLI Skill（`SKILL.md` 和 `references/`）；应用镜像构建不再访问 apt、PyPI 或全局 npm。
- 本仓库 `vendor/rdhs-workspace` 中已审核、固定版本的 RDHS 报告运行源码。更新该快照时，只能同步报告实际所需文件，不能带入 `.env`、临时输出或未审核工作目录。
- 基础镜像或运行时提供可用的 Meegle CLI profile/auth；NetworkPolicy 启用前还需由网络团队提供 Meegle 出口 CIDR。

### 10.2 预创建 Secret

应用令牌不写入仓库或镜像，生产通过现有 ExternalSecret/KMS 流程创建
`rdhs-report-web-secrets`；下列命令仅说明 Key，执行时从受控终端提供真实值。当前上线前验证的
`values-prod.yaml` 临时以内联方式生成 `rdhs-report-db-secrets`，验证完成后必须改回托管 Secret 并轮换密码。
`RDHS_REFRESH_WEBHOOK_TOKEN`
必须是非空高熵随机值；Runner 会在该 Key 缺失或为空时拒绝启动：

```bash
kubectl -n <namespace> create secret generic rdhs-report-web-secrets \
  --from-literal=RDHS_INGEST_TOKEN='<write-token>' \
  --from-literal=RDHS_REFRESH_WEBHOOK_TOKEN='<runner-token>'

kubectl -n <namespace> create secret generic rdhs-report-db-secrets \
  --from-literal=MYSQL_USER='<rdhs-db-user>' \
  --from-literal=MYSQL_PASSWORD='<rdhs-db-password>'

```

快速验证时可使用未提交的 `charts/rdhs-report/values-prod.local.yaml` 覆盖文件：

```yaml
secrets:
  create: true
  web:
    name: rdhs-report-web-secrets
    data:
      RDHS_INGEST_TOKEN: "<write-token>"
      RDHS_REFRESH_WEBHOOK_TOKEN: "<runner-token>"
```

使用时追加 `-f charts/rdhs-report/values-prod.local.yaml`；验证完成后删除该文件，并将
`secrets.create` 恢复为 `false`。Helm 会把这类覆盖值保存到 Release Secret，因此不要将其用于正式生产。

Web 使用 Web Secret 和数据库 Secret；Runner 使用两个 RDHS Key；CronJob 使用 `RDHS_INGEST_TOKEN`。
Meegle 数据访问由容器内 `meegle` CLI 的 profile/auth 运行态负责，不再通过 `MEEGLE_*` 环境变量注入。
为私有仓库创建的 pull Secret 通过 `imagePullSecrets` 引用，不放在应用 Secret 中。

### 10.3 构建并推送镜像

`Dockerfile` 使用预构建基础镜像构建应用镜像，并直接复制本仓库已固定的报告源码快照。现网镜像沿用
meegle-mcp 的内网仓库前缀，使用不可变的受保护发布 tag（或在镜像仓库策略中强制 tag
不可覆盖），不要使用 `latest`。Web 镜像默认以 `RDHS_BASE_PATH=/meegle-rdhs-report` 构建，若调整
Ingress path 后缀，必须同时传入相同的 `--build-arg RDHS_BASE_PATH=/your-prefix` 并修改 values：

Dockerfile 不声明远端 Dockerfile frontend，也不使用 named context，避免 Jenkins 在内网构建时访问 Docker Hub。Ingress 只转发
`/meegle-rdhs-report` 前缀，不做 rewrite；应用镜像、Web 探针和 Runner/CronJob 内部站点 URL 使用同一个前缀。

```bash
BASE_IMAGE=artifacts.iflytek.com/cbg-docker-repo/cbbywkf/meegle-rdhs-report-base:node22-python3-meegle-cli-1.1.5

docker build --platform linux/amd64 \
  --build-arg RDHS_BASE_IMAGE="$BASE_IMAGE" \
  --build-arg RDHS_BASE_PATH=/meegle-rdhs-report \
  -t artifacts.iflytek.com/cbg-docker-repo/cbbywkf/meegle-rdhs-report:v1.0.0 .

docker push artifacts.iflytek.com/cbg-docker-repo/cbbywkf/meegle-rdhs-report:v1.0.0
```

Chart 构建脚本与 meegle-mcp 保持相同的版本化变量约定。脚本默认只打包不发布；CI 发布时显式设置
`PUSH_CHART=true`，由 `helm push-artifactory` 推送到 `cbg-helm-local`：

```bash
PROJECT_VERSION=1.0 BUILD_ID=42 SERVICE_NAME=meegle-rdhs-report ENV=prod \
  PUSH_CHART=false charts/build-chart.sh
```

### 10.4 配置与发布

使用仓库内的 `charts/rdhs-report/values-prod.yaml`。当前文件仅为上线前验证临时包含数据库明文凭据，
不得作为长期生产配置；验证完成后改回外部 `rdhs-report-db-secrets` 并轮换密码。
至少确认：

- 统一 `image.repository`、不可变 `tag`、Ingress 域名，以及 `database.mysql.host/port/database`。
- 如有容量或时长要求，调整 `sync.outputRetentionMonths`、`sync.reportCommandTimeoutSeconds` 与
  `sync.cron.activeDeadlineSeconds`；Chart 要求 Cron deadline 能容纳两次报告命令和 60 秒退出余量。
- `secrets.web.name`；确认基础镜像或运行时提供 Meegle CLI profile/auth；如需镜像凭据，配置 `imagePullSecrets` 的现有 Secret 名称。
- Chart 不渲染独立 refresh Ingress；刷新 API 随主 Ingress 转发，由现有内网网关负责访问控制。
- 启用 NetworkPolicy 时，同时允许 Web 到 `172.31.114.194:4302` 的 egress。
- 仅在填入 ingress controller selector 与 Meegle CIDR 后设置 `networkPolicy.enabled: true`。

发布前先渲染检查，再执行升级：

```bash
helm lint charts/rdhs-report -f values-prod.yaml
helm template meegle-rdhs-report charts/rdhs-report \
  --namespace <namespace> -f values-prod.yaml > /tmp/rdhs-rendered.yaml

helm upgrade --install meegle-rdhs-report charts/rdhs-report \
  --namespace <namespace> --create-namespace \
  -f values-prod.yaml --wait --timeout 10m

kubectl -n <namespace> rollout status deployment/meegle-rdhs-report-web --timeout=5m
kubectl -n <namespace> rollout status deployment/meegle-rdhs-report-refresh --timeout=5m
kubectl -n <namespace> get cronjob meegle-rdhs-report-sync
```

上线后入口和探针地址为：

```text
https://ossptest.voicecloud.cn/meegle-rdhs-report/
https://ossptest.voicecloud.cn/meegle-rdhs-report/api/health/live
https://ossptest.voicecloud.cn/meegle-rdhs-report/api/health
```

正式生产加固后渲染结果不得出现数据库明文或由 Chart 管理的 Secret；本轮快速验证会生成数据库 Secret，
应用令牌 Secret 仍由外部流程提供。`/api/health/live` 用于 liveness，`/api/health`
会读取 MySQL，作为 readiness；首次部署在导入快照前返回就绪但页面会明确显示“数据暂不可用”，不会展示演示数据。

### 10.5 首次历史导入和月度验收

在受控运维环境中，把 `RDHS_SITE_URL` 指向由 `kubectl port-forward` 暴露的 Web Service 或内网域名（生产 Chart 已自动设置为
`http://<web-service>:3000/meegle-rdhs-report`，并显式开启集群内 HTTP），
以已获授权的 `RDHS_INGEST_TOKEN` 执行一次导入；令牌不可写入 shell 历史或脚本：

```bash
python3 scripts/import-existing-reports.py --dry-run <verified-report-root...>
python3 scripts/import-existing-reports.py <verified-report-root...>
```

首月发布后，手工创建一次 Job 验证 Meegle 连通、报告基线、报告生成和写入链路：

```bash
kubectl -n <namespace> create job --from=cronjob/meegle-rdhs-report-sync meegle-rdhs-report-sync-smoke
kubectl -n <namespace> logs -f job/meegle-rdhs-report-sync-smoke
```

### 10.6 备份、恢复与回滚

生产持久化数据全部位于 MySQL：快照版本、失败诊断、按月基线和同步租约都由
`database/mysql/001_initial.sql` 创建的表保存。运维只需为 `rdhs_report` 数据库配置备份、
恢复演练和权限审计；`emptyDir` 中的报告中间文件不需要备份。

恢复时先将 `sync.cron.suspend: true` 通过 Helm 发布，停止 Runner/CronJob 写入，再按数据库平台流程将
`rdhs_report` 恢复到目标时间点。恢复后检查 `/api/health`、周期列表、最近快照及一次受控当月刷新，确认无误后
将 `sync.cron.suspend` 改回 `false` 并执行 Helm upgrade。应用回滚使用 Helm，数据库回滚按 MySQL 备份流程单独处理。

应用回滚使用 Helm，数据回滚按 MySQL 备份流程单独处理：

```bash
helm -n <namespace> history meegle-rdhs-report
helm -n <namespace> rollback meegle-rdhs-report <revision> --wait --timeout 10m
kubectl -n <namespace> rollout status deployment/meegle-rdhs-report-web --timeout=5m
```
