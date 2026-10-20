# 配置盘点与闭环规则

## 配置来源

按以下优先级扫描：

1. Dockerfile `ENV`/`ARG`；
2. Compose `environment`/`env_file`；
3. `.env*` 和项目配置文件；
4. 启动脚本和 CI/Jenkins 脚本；
5. Node/Python/Go 源码中的环境变量读取；
6. 现有 Kubernetes YAML 和 Helm values。

## 变量分类

| kind | 处理方式 |
| --- | --- |
| required-runtime | values 中声明，模板 `required` 或报告阻塞 |
| optional-runtime | values 中声明默认值，缺失只告警 |
| environment-override | `values-<env>.yaml` 覆盖，默认值仍在 values.yaml |
| secret | 检查阶段脱敏；用户确认后可写入 `values-prod.yaml` env，`values.yaml` 不写入实际密钥，并保留明文告警 |
| external | 列为外部依赖，不伪造默认值 |
| system | 过滤或标记为系统变量，不迁移到业务 values |

## 双向检查

```text
local-source → values.yaml → values-<env>.yaml → template → rendered workload
```

差异代码：

- `MISSING_IN_VALUES`
- `MISSING_IN_TEMPLATE`
- `MISSING_IN_PRODUCTION`
- `UNUSED_VALUE`
- `CONFLICTING_VALUE`
- `UNRESOLVED_VALUE`

动态环境变量无法可靠静态推断时，保留来源、行号和 `confidence: inferred`，不能把推断当成已配置。
