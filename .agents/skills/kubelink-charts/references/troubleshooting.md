# 常见问题定位顺序

1. 先看 `helm lint` 和 `helm template` 的原始 stderr；
2. 检查生产 values 是否被完整覆盖到构建目录；
3. 在实际目标 Kubernetes 版本渲染；
4. 检查镜像 tag、pull Secret 和 registry 权限；
5. 进入同一个 Web/CronJob Pod 检查 `HOME`、`which meegle`、`meegle auth status`；
6. 执行原始 `meegle chart get`，保留 stderr；
7. 再检查数据库、网络策略、Ingress 和 Kubelinks 平台策略。

不要因 CLI auth/profile 失败修改业务 Chart；不要把外部权限问题误判为 Helm 模板问题。
