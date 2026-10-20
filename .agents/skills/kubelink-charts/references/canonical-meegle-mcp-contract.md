# meegle-mcp Chart canonical contract

来源：`/Users/ting/Develop/meegle-infra-workspace/meegle-mcp`，commit `9aca0854f492d42f945263db3e88beacd3fe62b1`。

本参考文件只记录可复用的结构合同，不复制生产凭证。

## build-chart.sh 合同

canonical 流程必须保留以下顺序：

1. 要求 `PROJECT_VERSION`、`BUILD_ID`、`SERVICE_NAME`；
2. 确认 Chart 源目录存在；
3. 生成 `<service>-<env>` 构建目录；
4. 修改 `Chart.yaml` 的 name/version/appVersion 和 values 镜像 tag；
5. 生产环境使用 `values-prod.yaml` 覆盖构建目录的 `values.yaml`；
6. 对构建目录运行 `helm lint`；
7. 调用 `helm push-artifactory <build-dir> cbg-helm-local --skip-reindex`；
8. push 失败必须退出非零。

脚本必须从脚本所在目录工作，兼容 Linux/macOS 的 `sed`，不要依赖 Jenkins 当前工作目录。项目只能替换服务名、Chart 源目录和镜像仓库等必要变量。

## Chart 模板合同

- canonical 镜像仓库前缀为 `artifacts.iflytek.com/cbg-docker-repo/cbbywkf/`；复用模板时只替换最后的项目镜像名，不使用 `registry.example.invalid` 或 `artifacts.example.invalid` 占位前缀。
- `Chart.yaml` 使用 `apiVersion: v2`，版本字段可解析；
- helpers 统一提供 name、fullname、chart labels、selector labels、ServiceAccount name；
- Deployment、Service、Ingress 使用同一套 selector labels；
- 私有镜像通过 `imagePullSecrets` 引用；
- Service/Ingress 端口由 values 驱动；
- Ingress 按 Kubernetes 版本条件渲染 `apiVersion`、`pathType`、`ingressClassName` 和 backend 结构；
- 不在应用 Chart 中加入错误的 `kubeVersion: >=1.27.0-0` 约束来阻塞 1.15 集群；
- 可选配置必须 nil-safe，必填配置使用 `required`；
- 生产镜像使用不可变版本 tag，不使用 `latest`。

## 已验证的踩坑

- 生产 values 覆盖 `values.yaml` 后若丢失 `secrets` 节点，`.Values.secrets.create` 会产生 nil pointer；读取可选 map 时使用 `default dict`。
- Kubernetes 1.15.12 不支持 `batch/v1` CronJob、`networking.k8s.io/v1` Ingress、`policy/v1` PDB；按版本渲染 legacy API。
- `CronJob.timeZone` 和 `seccompProfile` 不能无条件渲染到旧集群。
- Web 与 CronJob 的应用 token 必须按确认方案一致注入；不要强制依赖不存在的 Web Secret。
- Python `ZoneInfo("Asia/Shanghai")` 依赖镜像 tzdata；镜像应安装 tzdata，代码容错不能替代镜像依赖治理。
- 容器内 `meegle auth login`、profile 和 `HOME` 是运行态前置条件；本机 auth 成功不代表 Pod 内 auth 成功。
- CLI 失败必须保留 stderr，否则只能看到笼统的 `command failed (1)`。
