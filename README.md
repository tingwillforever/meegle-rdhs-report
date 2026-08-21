# RDHS 产研过程效能运营报告

消费者 BG 的月度 RDHS 运营工作台。站点以研发中产品主数据为底表，排除测试业务线及产品属性为交付定制的产品，左关联产品维度 RDHS 数据，并将未度量/待关联产品纳入重点治理。

## 数据口径

- 产品范围：状态为 `In Progress` 的产品主数据。
- 排除范围：`测试业务线`，以及产品属性为 `交付定制` 的产品主数据。
- 关联键：规范化后的 `一级业务线 + 产品`。
- 治理分档：`<45 + 未度量/待关联`、`45~<60`、`60~<70`、`>=70`。
- 平均 RDHS：仅统计已度量产品；覆盖率单独展示。
- 发布保护：不完整或不一致的源数据不得替换最近有效快照。

完整语义定义见 [设计说明](docs/superpowers/specs/2026-08-17-rdhs-live-operations-site-design.md)，日常操作见 [运行手册](docs/operations.md)。

## 架构

```text
Meegle CLI -> run_periodic_report.py -> report_data/audit
          -> snapshot sync -> ingest API -> history storage
          -> React operations dashboard
```

Cloudflare/Sites 模式使用 D1；Kubernetes 模式使用 Node/Vinext + SQLite。通过
`DEPLOY_TARGET=k8s` 选择 K8s 构建，领域层和快照合同保持一致。生产集群中 Meegle CLI
只在同步工作负载中注入，浏览器和 Web 工作负载均不会接触 Meegle 凭据。

```text
业务用户 -> SSO Ingress -> Web（单副本 Vinext + SQLite/RWO PVC）
                              |                    ^
                              v                    |
                      内网 Refresh Runner ----- 快照写入 API
                              |                    ^
                              +--- 共享 NFS：月初基线与报告运行产物 ---+
                              ^
每月 1 日 09:00 ---------------|
                         Sync CronJob（Python + Meegle CLI）
```

当月刷新由 `POST /api/report/refresh` 触发内网 runner；历史月份由每月 1 日任务生成并写入。
同一任务会先以**当月 1 日**固化供当月刷新复用的上月基线，再以**上月末**生成可上传报告。基线和
报告运行目录位于 Runner/CronJob 共同挂载的 NFS；它与 SQLite 的 RWO PVC 完全分离。详细上线、备份和恢复流程见[运行手册](docs/operations.md)。

## 本地开发

前置版本：Node.js `>=22.13.0`、Python `>=3.10`。

```bash
npm install
npm run dev
```

本地地址为 `http://localhost:3000`。D1 尚无数据时，首页使用仓库内两份已验证月度快照并明确标记为预览快照。

## 内网 K8s 生产部署

第一阶段不需要引入 PostgreSQL/MySQL：SQLite 文件固定在 `/var/lib/rdhs/rdhs.sqlite`，由
`ReadWriteOnce` PVC 持久化。Chart 强制 Web 单副本和 `Recreate` 更新策略，且没有 HPA；若要
多副本或跨可用区写入，再迁移到 PostgreSQL。

生产交付在 [charts/rdhs-report](charts/rdhs-report) 中，包含 Web、内网 Runner、月度 CronJob、
Ingress、PVC 与可选 NetworkPolicy。必须由集群预先提供：RWO StorageClass、CSI
VolumeSnapshot 能力、可被 Runner/CronJob 同时读写且支持文件锁的 NFS 目录、企业 SSO 注解、两个业务
Secret，以及可拉取内部镜像的凭据（如需要）。

现网入口沿用 meegle-mcp 的域名和镜像仓库约定：
`https://ossptest.voicecloud.cn/meegle-rdhs-report/`。生产 values 已将统一镜像指向
`artifacts.iflytek.com/cbg-docker-repo/cbbywkf/meegle-rdhs-report`，并引用集群预置的 `hub4iflytek` pull Secret；
令牌仍由 Secret/ExternalSecret 注入，Chart 不创建 Secret。

共享 NFS 默认只保留最近 6 个自然月的报告运行目录和站点快照；月初基线、运行产物与日志容量应按此窗口
预留，并由存储团队设置配额和告警。每条 Meegle 报告命令最多运行 540 秒，CronJob 最多运行 1,500 秒，
超时后失败并按 Job 重试策略处理。

构建命令、Secret Key、Helm 发布、首次导入、监控、备份恢复和回滚命令均在
[运行手册](docs/operations.md#10-kubernetes-生产部署) 中。开发或本地冒烟可使用：

```bash
npm run build:k8s
RDHS_DB_PATH=/tmp/rdhs.sqlite npm run start:k8s
```

生产镜像入口为 `Dockerfile`，它直接依赖预构建的 Node 22、Python、Meegle CLI 基础镜像，并复制
报告代码和同步脚本；Web、Refresh Runner、Sync CronJob 通过不同启动命令复用同一个应用镜像。`/api/health/live` 是进程存活探针，
`/api/health` 是 SQLite 就绪探针。

## 验证

```bash
npm test
npm run lint
npx tsc --noEmit
npm run build:k8s
helm lint charts/rdhs-report -f charts/rdhs-report/values-prod.example.yaml
bash -n charts/build-chart.sh scripts/run-sync-job.sh scripts/install-launchd.sh
bash -c 'PROJECT_VERSION=1.0 BUILD_ID=0 charts/build-chart.sh'
```

`npm test` 依次执行领域/接口/筛选单元测试、Python 同步器测试、生产构建和服务端渲染测试。

## 目录

- `app/`：页面、交互组件和 API 路由。
- `lib/rdhs/`：快照合同、校验、聚合、筛选和仓储。
- `db/`、`drizzle/`：D1 模型与迁移。
- `scripts/`：快照同步、历史导入和定时任务安装。
- `data/`：首次部署前可用的已验证历史快照。
- `tests/`：Node、Python 与渲染测试。
