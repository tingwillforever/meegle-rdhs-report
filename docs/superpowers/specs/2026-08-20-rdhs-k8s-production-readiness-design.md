# RDHS K8s 生产上线整改设计

## 目标

将 RDHS 运营报告从 Cloudflare/D1 运行方式补齐为可在内网 Kubernetes 集群上线的交付物：单副本 Node + SQLite 站点、内网 Meegle 同步 Runner、月度快照 CronJob、Secret 注入、网络边界及可验证的运维流程。

## 范围与约束

- 站点运行时使用 Node.js `>=22.13.0`、Vinext 和 SQLite；不引入 PostgreSQL/MySQL 服务。
- SQLite 文件固定在 `/var/lib/rdhs/rdhs.sqlite`，由 RWO PVC 持久化。
- SQLite 工作负载始终只有一个 Web Pod：`replicaCount: 1`、禁用 HPA、Deployment 使用 `Recreate`。
- Runner 与 CronJob 必须使用同一可读写、支持文件锁的 NFS 导出目录 `/var/lib/rdhs-sync`；它保存月初比较基线和报告运行产物，与 SQLite RWO PVC 隔离。
- Runner 必须以非空 `RDHS_REFRESH_WEBHOOK_TOKEN` 启动；每条报告命令和 CronJob 都有可配置的超时上限，NFS 运行产物默认保留最近 6 个自然月并受配额/告警监控。
- Node、Python、Meegle CLI 预先打入基础镜像，报告代码由应用镜像复制；Web 容器不注入 Meegle CLI 运行态，
  因此不会实际访问 Meegle。集群节点上安装的 CLI 不作为生产依赖。
- 站点写入令牌和刷新令牌由预先创建的 Kubernetes Secret 提供，Chart 不创建或保存明文机密；Meegle 访问由容器内 `meegle` CLI 的 profile/auth 运行态负责。
- 外部 RDHS 报告工作区通过 Docker BuildKit named context 提供；其路径、报告生成命令和 Meegle CLI 包名均为部署参数，不在站点源码中写死。

## 架构

```text
业务用户 -> 现有内网网关 -> rdhs-report-web Service -> Web Pod -> SQLite PVC
                                        |
                                        | POST /api/report/refresh
                                        v
                                  rdhs-refresh-runner Service -> Runner Pod
                                                                     |
                                                              Meegle CLI + Python
                                                                     |
                                                           Shared NFS report output
                                                                     |
                                        POST /api/snapshots <--------+

每月 1 日 09:00 -> rdhs-sync CronJob -> 统一生产镜像 -> Meegle CLI -> Shared NFS + Web Service
```

### Web

统一应用镜像由 `Dockerfile` 构建，直接依赖预构建的 Node/Python/Meegle CLI 基础镜像，设置 `DEPLOY_TARGET=k8s`、`RDHS_STORAGE=sqlite` 和 `RDHS_DB_PATH=/var/lib/rdhs/rdhs.sqlite`，并复制报告代码和同步脚本。Web、Runner、CronJob 通过 command 区分角色。`/api/health` 检查 SQLite 可读性，作为 readiness probe。生产模式没有有效快照时不得回退展示仓库演示数据。

### SQLite

SQLite 仓储负责快照主表、业务线明细、产品明细及失败记录。单次写入在 `BEGIN IMMEDIATE` 事务中完成：源哈希查重、当前版本切换、版本计算和子表写入必须原子执行。相同源哈希更新时同步重建两张子表。储存由集群提供 RWO PVC；备份由存储团队为 PVC 配置每天一次 CSI `VolumeSnapshot` 并保留 180 天，恢复操作先缩容 Web 再还原卷。

### 同步依赖和 Runner

`Dockerfile` 直接依赖包含 Node 22、Python 和指定版本 `@tingwillforever/meegle-cli` 的基础镜像，并从 BuildKit context `rdhs-workspace` 复制外部报告工作区到 `/opt/rdhs-workspace`。镜像包含本仓库 `scripts/`，Runner 使用 `scripts/local-refresh-runner.py --host 0.0.0.0 --env-file /etc/rdhs/runtime.env` 启动。

`rdhs-refresh-runner` 是一个单副本、仅 ClusterIP 暴露的 Deployment。它使用基础镜像或运行时提供的 Meegle CLI profile/auth，且仅接收来自 Web Pod 的 `RDHS_REFRESH_WEBHOOK_TOKEN` 认证请求；缺少或为空时进程拒绝启动。Web 写入令牌仅由 Runner 和 CronJob 使用。Runner 与 CronJob 共同挂载 `syncStorage.nfs` 到 `/var/lib/rdhs-sync`；同步器使用该目录的 advisory file lock 串行化两类工作负载，避免在写入/读取基线时并发。

### 周期同步

CronJob 不通过 Runner HTTP 触发，而是直接执行 `scripts/run-sync-job.sh monthly`。它设置 `concurrencyPolicy: Forbid`、`backoffLimit: 2`、`timeZone: Asia/Shanghai`，排程为每月 1 日 09:00。每条报告命令的默认超时为 540 秒，CronJob `activeDeadlineSeconds` 默认为 1,500 秒，避免失联的 Meegle 请求长期占用排程。

报告生成命令由三项非机密环境变量驱动：

- `RDHS_MONTHLY_BASELINE_COMMAND`：生产值为 `python3 /opt/rdhs-workspace/topics/rdhs-operations/run_periodic_report.py --mode monthly-baseline`；该模式只固化比较基线。
- `RDHS_MONTHLY_REPORT_COMMAND`：生产值为 `python3 /opt/rdhs-workspace/topics/rdhs-operations/run_periodic_report.py --mode weekly`；该模式生成包含 `report_data.json` 的可上传报告。
- `RDHS_CURRENT_REPORT_COMMAND`：生产值为 `python3 /opt/rdhs-workspace/topics/rdhs-operations/run_periodic_report.py --mode weekly`。

月度同步器先以**当月 1 日**执行基线命令、再以**上月最后一天**执行月度报告命令；每个命令均追加
`--no-publish --output-root <path> --as-of <date>`，并消费报告命令输出 JSON 的 `run_dir`。前者写入当月
目录并供当月 `weekly` 刷新复用，后者生成上一个完整月的可上传快照。这消除了现有同步器对不存在的
`last-month` 和 `monthly` 生成模式的假设，也避免把只产生基线的命令当作可上传报告。

上传成功后，同步器只清理按日期命名且超过 `sync.outputRetentionMonths`（默认 6 个自然月）的报告目录和站点快照；不会清理其他 NFS 内容。NFS 必须设置容量配额、用量告警与匹配恢复窗口的快照保留。

### 网络与身份

一般读请求和刷新接口均通过主 Ingress 转发，由现有内网网关负责访问控制；Chart 不创建独立的 refresh Ingress，也不配置网关认证 annotation。Runner 无 Ingress。可选 NetworkPolicy 允许：Ingress -> Web、Web -> Runner、Runner/CronJob -> Web、Runner/CronJob -> Meegle 内网与 DNS。

## Helm 接口

Chart 路径为 `charts/rdhs-report`，包含 Web Deployment、Runner Deployment、两个 ClusterIP Service、Ingress、PVC、CronJob、ServiceAccount、可选 NetworkPolicy 和 PDB。

必须由部署环境提供：

- `secrets.web.name`：含 `RDHS_INGEST_TOKEN`、`RDHS_REFRESH_WEBHOOK_TOKEN`。
- 基础镜像或运行时必须提供可用的 Meegle CLI profile/auth，容器内 `meegle auth status` 应返回 active。
- `persistence.storageClass` 和 Ingress 域名；访问控制由现有内网网关提供。
- `syncStorage.nfs.server`、`syncStorage.nfs.path`，且 NFS 导出目录以 UID/GID 1000 可读写并支持文件锁。
- 恢复专用 values 必须能设置 `sync.cron.suspend: true`，令 CronJob 暂停状态跨 Helm 升级保留。
- `sync.reportCommandTimeoutSeconds`、`sync.cron.activeDeadlineSeconds`、`sync.outputRetentionMonths`；Cron deadline 必须容纳两条报告命令与退出余量。
- 统一生产镜像仓库及不可变 image tag。

## 验收

- `helm lint` 和 `helm template` 均通过；无 Secret 资源或明文 token 出现在渲染结果。
- 渲染结果固定 Web/Runner 单副本、SQLite RWO PVC、Recreate 策略、无 HPA；Runner/CronJob 都挂载共享 NFS 输出目录。
- Runner 不创建 Ingress；CronJob 使用同一生产镜像，排程和并发策略正确。
- K8s 构建不解析 Cloudflare runtime 依赖；默认构建仍通过。
- 生产模式的空 SQLite 只展示数据不可用状态，不展示演示快照。
- 同步器按环境配置的生成命令运行，月度和当月缓存模式传入不同 command。
- 全量 Node/Python 测试、TypeScript 检查及镜像构建上下文验证通过；真实 Meegle 登录和集群发布由持有凭据的运维人员执行。
