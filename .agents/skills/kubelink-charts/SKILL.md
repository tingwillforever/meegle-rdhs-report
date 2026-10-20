---
name: kubelink-charts
description: >-
  Use when 用户提到 charts、Chart.yaml、values.yaml、values-prod.yaml、build-chart.sh、Helm
  部署、Kubelinks、Chart lint/render 失败，或要求参照 meegle-mcp 最佳实践时。
---

# kubelink-charts

## 目标

把一个应用项目整理到“项目内已具备 Kubelinks 基础部署条件”的状态。这里的就绪只覆盖仓库内能验证的内容：Chart 结构、配置闭环、Helm 渲染、目标 Kubernetes API、镜像和发布脚本合同。镜像仓库权限、集群 Secret、网络、数据库、Meegle 登录态和平台策略属于外部依赖，必须单独列出，不能伪装成本地通过。

## 两阶段变更门禁（强制）

- 每次请求先进入“检查阶段”：只读盘点、audit、lint、render 和报告，不运行生成器、fix 脚本或其他写操作。
- 即使用户一次请求同时写了“检查并修正”，也必须先返回检查结果和待修改清单，停止并请用户确认。
- 只有在检查报告返回后，用户在后续消息中明确表达“确认修改”、“开始修正”等意图时，才进入“修改阶段”。工作区发生变更后原确认失效，需重新检查。
- 修改阶段只修改仓库文件，必须备份并展示差异；不执行 `git commit` 或 `git push`。发布是另一个需要用户单独明确授权的动作。

## 必须遵循的来源

Chart 和发布脚本优先复用 `references/canonical-meegle-mcp-contract.md` 指定的 `meegle-mcp` canonical 实现。模板位于 `assets/meegle-mcp-chart-template/`，只能替换服务名、Chart 名、镜像仓库、环境变量和项目必需字段；不要重新设计一套发布流程。

## 默认配置政策

- 镜像仓库必须沿用模板 `assets/meegle-mcp-chart-template/values.yaml` 中 `image.repository` 的 canonical 前缀（当前为 `artifacts.iflytek.com/cbg-docker-repo/cbbywkf/`），只把最后一段替换为当前项目镜像名。脚本从该模板读取前缀，避免多处硬编码漂移；不得保留 `registry.example.invalid`、`artifacts.example.invalid` 或其他非 canonical 前缀，严格验收必须失败。
- 非敏感运行变量同时写入 `values.yaml` 和环境 values；密钥类变量（如 `OPENAI_API_KEY` 、`*_TOKEN` 、`*_SECRET` 、`*_PASSWORD`）默认写入 `values-prod.yaml` 的 `env` 配置，`values.yaml` 不写入实际密钥。
- 检查阶段只盘点密钥变量并脱敏；用户确认后的修改阶段才可使用 `inventory-config.py --include-secret-values` 将本地已配置的密钥写入生产 values。报告、日志和命令输出不得显示密钥原文。
- 明文密钥保留 `PLAINTEXT_SECRET` 告警，按当前约定不因此阻塞 lint/render；如本地无法推断密钥值，只写入空占位并报告待配置。

## 工作流

### 1. 检查阶段（默认只读）

在项目根目录执行：

```bash
find . -name AGENTS.md -print
find . -path '*/charts/*' -type f -print
find . -name 'build-chart.sh' -o -name 'build-charts.sh' -print
```

项目无论是否已有 Chart，都先只读盘点和审计，不要生成、修正或覆盖任何 values。如果没有 Chart，只报告 canonical 模板、待补充字段和建议的输出路径，然后停止并请用户确认。检查报告必须列出阻塞项、非阻塞告警和拟修改清单。

#### 现有 Chart

```bash
bash <skill-root>/scripts/audit-chart.sh \
  --project-root "$PWD" \
  --chart charts/<service-name> \
  --values charts/<service-name>/values-prod.yaml \
  --kube-version <target-version>
```

#### 无 Chart

只运行 `inventory-config.py`，不运行 `generate-chart.sh`；生成必须在用户明确确认后进入修改阶段。

### 2. 盘点本地配置变量

先运行 `inventory-config.py`。至少扫描 Dockerfile、Compose、`.env*`、启动脚本、CI/Jenkins 文件、现有 Kubernetes YAML，以及 Node/Python/Go 代码中的环境变量读取。

配置闭环必须覆盖：

```text
本地配置来源
  → values.yaml 默认值或 Secret 引用
  → values-<env>.yaml 环境覆盖
  → Helm 模板 env/envFrom/volume
  → 最终 Deployment/CronJob/Worker 工作负载
```

报告以下差异：

- `MISSING_IN_VALUES`：本地发现但 values 未声明；
- `MISSING_IN_TEMPLATE`：values 声明但模板没有消费；
- `MISSING_IN_PRODUCTION`：生产覆盖后丢失；
- `UNUSED_VALUE`：values 有值但没有工作负载消费；
- `CONFLICTING_VALUE`：env、envFrom、Secret 多处定义同一变量；
- `UNRESOLVED_VALUE`：发现变量但不能安全推断默认值。

能确定的非敏感默认值应补入 `values.yaml` 和环境 values；密钥类变量仅在用户确认后补入 `values-prod.yaml` 的 `env`，并保留明文告警。只有变量名时补入空占位并标记待配置；不得在报告和日志中显示密钥原文。

### 3. 修改阶段（仅在用户确认后）

只执行上一次检查报告中的拟修改项。没有 Chart 时从 `assets/meegle-mcp-chart-template/` 复制，填入 canonical 镜像前缀、可确认的服务名、端口、启动命令和配置变量；已有 Chart 时只做安全修正和配置同步。两种操作都必须显式携带 `--confirm`：

```bash
# 没有 Chart：按检查报告中的路径执行生成
bash <skill-root>/scripts/generate-chart.sh \
  --project-root "$PWD" \
  --output charts/<service-name> \
  --confirm
```

```bash
# 已有 Chart：按检查报告执行安全修正
bash <skill-root>/scripts/fix-chart.sh \
  --chart charts/<service-name> \
  --values charts/<service-name>/values-prod.yaml \
  --confirm
```

修正前必须备份，修正后展示 `git diff` 并重新执行检查。安全修正范围是 nil-safe values 读取、缺失可选默认结构、旧 Kubernetes API 条件、版本/tag 替换、配置变量同步、构建脚本失败码和明显的引用错误；不要擅自更改已有业务 token值、Meegle ID、Ingress 真实域名、数据库或集群网络配置。修改阶段不执行 commit 或 push。

### 4. 验收

```bash
bash <skill-root>/scripts/release-check.sh \
  --project-root "$PWD" \
  --chart charts/<service-name> \
  --values charts/<service-name>/values-prod.yaml \
  --env prod \
  --kube-version <target-version>
```

验收至少包含：Chart 元数据、values/template 双向索引、生产 values、`helm lint`、默认和生产 `helm template`、目标 Kubernetes 版本渲染、1.15.12 兼容基线、镜像 tag、Service/Ingress/探针/resources/securityContext、CronJob API 和 build script dry-run。默认不执行 commit 或 push；验收通过仅表示仓库内条件满足，不代表已发布。

## 结果状态

报告必须使用以下状态之一：

- `scaffolded`：已生成 Chart 骨架，仍有必填项目配置；
- `renderable`：默认和环境 values 可以 lint/render；
- `deployment-ready`：配置闭环、目标 API 和发布脚本均通过；
- `externally-verified`：另有真实仓库推送、镜像拉取和 Kubelinks 部署证据；
- `blocked`：存在仓库内可修复的阻塞错误。

`renderable-but-missing-config` 不得报告为 `deployment-ready`。

## 阻塞与告警

阻塞项包括 YAML/Helm/template 失败、必需变量缺失、生产覆盖丢值、空镜像 repository、`latest`、目标 Kubernetes 不支持的 API、push 失败却返回成功。

严格模式只把“已经进入 `values.yaml` 的 Chart 管理变量在生产覆盖中丢失”视为配置闭环阻塞；代码默认值、镜像内置变量和无法可靠映射的本地变量先报告为查漏补缺告警，避免静态推断误阻塞配置流程。

非阻塞告警包括明文 Secret、缺少可选探针/resources/PDB/NetworkPolicy、缺少 `imagePullSecrets`、未声明 `tzdata`、可选变量未配置、未做容器内 Meegle auth 检查。

## Meegle 运行态边界

Meegle CLI 的 profile、`HOME`、`meegle auth login`、权限和网络由基础镜像/运行环境负责。可以提示并在同一容器内执行：

```bash
meegle auth status
meegle chart get --project-key <project> --chart-id <chart> --format json
```

不要为解决 CLI 失败而在 Chart 中臆造 `MEEGLE_*` Secret 或认证逻辑。子进程错误必须保留完整 stderr。

## 直接调用脚本

技能没有虚构的全局 CLI；真实入口是本目录的脚本：

```bash
python3 <skill-root>/scripts/inventory-config.py
bash <skill-root>/scripts/audit-chart.sh --help
bash <skill-root>/scripts/generate-chart.sh --help
bash <skill-root>/scripts/fix-chart.sh --help
bash <skill-root>/scripts/release-check.sh --help
```

`inventory-config.py` 应使用 `python3` 调用。所有脚本都必须从任意当前工作目录运行，路径参数使用绝对/项目根路径解析。
