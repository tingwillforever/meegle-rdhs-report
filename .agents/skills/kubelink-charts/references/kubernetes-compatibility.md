# Kubernetes/Kubelinks 兼容检查

## 版本输入

优先级：命令行 `--kube-version` > 当前集群 `kubectl version` > Helm 当前版本提示。没有目标版本时，至少渲染历史兼容基线 `1.15.12`，并报告用户需要补充真实 Kubelinks 版本。

## 必查 API

| 资源 | 新版本 | 1.15 兼容分支 |
| --- | --- | --- |
| Ingress | `networking.k8s.io/v1` | `networking.k8s.io/v1beta1` 或 `extensions/v1beta1` |
| CronJob | `batch/v1` | `batch/v1beta1` |
| PDB | `policy/v1` | `policy/v1beta1` |

`Ingress.pathType`、`ingressClassName`、CronJob `timeZone`、Pod `seccompProfile` 必须按版本条件渲染。Chart 不应设置会把目标集群排除在外的最低版本约束。
