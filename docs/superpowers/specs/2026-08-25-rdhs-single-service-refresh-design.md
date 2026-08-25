# RDHS 单服务刷新设计

## 目标

将本地与 Kubernetes 的常驻运行面收敛为一个 Web 服务：页面、API 与当月刷新均由 Web（3000）承载。用户以一个命令启动或停止本地服务；生产 Chart 不再创建 Refresh Runner Deployment、Service 或 8765 端口。

## 架构

```text
浏览器 -> Web（Node/Vinext :3000） -> MySQL
              |
              +-> Python + Meegle CLI 子进程 -> 同一 Web 的 ingest/internal API

每月 1 日 CronJob -> Python + Meegle CLI -> Web :3000 -> MySQL
```

`POST /api/report/refresh` 仅接受当月请求，并在 Web 进程内以受控子进程运行
`python3 scripts/sync-rdhs-snapshot.py --current-month-cache`。子进程使用 Web Pod 的
`RDHS_SITE_URL`、`RDHS_INGEST_TOKEN`、报告命令和 `emptyDir` 输出目录；在 MySQL 模式下，既有
基线与租约内部 API 继续保证跨请求/POD 的同步安全。

## 行为与约束

- `npm run dev` 只启动 Vinext Web；删除本地 8765 HTTP Runner 和双进程启动器。
- 刷新请求仍同步等待结果；默认上限为 600 秒，可由 `RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS` 调整。
- 同一 Web 进程内的刷新通过内存互斥锁拒绝并发请求（HTTP 409）；MySQL 租约继续覆盖多副本或 CronJob 并发。
- 任何子进程异常、超时或非零退出均转为有明确消息的 HTTP 502；未成功生成并入库的快照不替换当前版本。
- 生产 Web 容器接收 `RDHS_WORKSPACE_ROOT`、`RDHS_OUTPUT_ROOT`、三条报告命令、保留期和同步租约配置，并挂载自己的 `emptyDir`。
- CronJob 保留，继续在上海时区每月 1 日 09:00 固化历史快照；它是短时批处理任务，不是常驻服务。
- 删除 `RDHS_REFRESH_WEBHOOK_URL`、`RDHS_REFRESH_WEBHOOK_TOKEN`、`sync.runner`、runner Kubernetes 工作负载、8765 Service/NetworkPolicy 规则与相关文档。
- Dockerfile 仍使用同一基础镜像，但只暴露 3000。
- NetworkPolicy 启用时，Web 负责访问 MySQL、DNS 与 Meegle 出口；CronJob 保持访问 Web、DNS 与 Meegle 出口。

## 验收

1. `npm run dev` 后只存在 Web 监听端口 3000，`POST /api/report/refresh` 能直接刷新当月数据。
2. Chart 渲染只包含 Web Deployment、Web Service、CronJob 与主 Ingress，不含 runner/8765。
3. 生产 Web 因刷新缺少 Python/Meegle 配置时返回可读失败；配置完整时可写入 MySQL。
4. `npm test`、lint、类型检查、K8s 构建与 Helm 渲染均通过。
