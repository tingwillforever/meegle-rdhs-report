# RDHS 产研过程效能运营报告

消费者 BG 的周/月 RDHS 运营工作台。站点以研发中产品主数据为底表，排除测试业务线，左关联产品维度 RDHS 数据，并将未度量/待关联产品纳入重点治理。

## 数据口径

- 产品范围：状态为 `In Progress` 的产品主数据。
- 排除范围：`测试业务线`。
- 关联键：规范化后的 `一级业务线 + 产品`。
- 治理分档：`<45 + 未度量/待关联`、`45~<60`、`60~<70`、`>=70`。
- 平均 RDHS：仅统计已度量产品；覆盖率单独展示。
- 发布保护：不完整或不一致的源数据不得替换最近有效快照。

完整语义定义见 [设计说明](docs/superpowers/specs/2026-08-17-rdhs-live-operations-site-design.md)，日常操作见 [运行手册](docs/operations.md)。

## 架构

```text
Meegle CLI -> run_periodic_report.py -> report_data/audit
          -> snapshot sync -> Sites ingest API -> D1 history
          -> React operations dashboard
```

Meegle CLI 只在本机或内网任务机运行。Sites 运行时不持有 Meegle 凭据，浏览器也不会接触快照写入密钥。

## 本地开发

前置版本：Node.js `>=22.13.0`、Python `>=3.10`。

```bash
npm install
npm run dev
```

本地地址为 `http://localhost:3000`。D1 尚无数据时，首页使用仓库内两份已验证月度快照并明确标记为历史快照。

## 验证

```bash
npm test
npm run lint
bash -n scripts/run-sync-job.sh scripts/install-launchd.sh
```

`npm test` 依次执行领域/接口/筛选单元测试、Python 同步器测试、生产构建和服务端渲染测试。

## 目录

- `app/`：页面、交互组件和 API 路由。
- `lib/rdhs/`：快照合同、校验、聚合、筛选和仓储。
- `db/`、`drizzle/`：D1 模型与迁移。
- `scripts/`：快照同步、历史导入和定时任务安装。
- `data/`：首次部署前可用的已验证历史快照。
- `tests/`：Node、Python 与渲染测试。
