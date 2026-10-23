# Agent Guidelines (rdhs-report)

## 双重定位
本项目是消费者 BG 产研健康度（RDHS）的双重视角载体：
1. **宏观运营大盘**：Next.js Web 站点，提供月度例会大盘、历史快照与业务线看板。
2. **微观诊断 Skill**：`.agents/skills/meegle-rdhs-diagnosis`，是 Agent 交互式实时诊断与归因的事实源（SSOT）。

## 协同铁律（禁止口径漂移）
- 凡涉及 RDHS 分档阈值（45/60/70）、五维指标权重、纳管枚举（标准产品 vs 交付定制）或图表 ID 的变更，**必须同时修改站点与 Skill**。
- 微观诊断归因以 Skill 的 7 阶归因引擎为标准；宏观聚合与均分计算以 `PRODUCT.md` 为标准。
- 当前诊断必须运行 Skill 实时查询入口（图表、主数据、业务线、姓名均不读写缓存）；禁止直接打开 `~/.cache`、CSV 或历史快照替代报数，失败不降级旧数据。Web 历史报告保留指定月快照，不用当前责任人冒充历史责任人。

## 必跑命令
- **全量测试**：`npm test`（已包含站点单元测试、快照同步测试及 Skill 单测）
- **Skill 分发同步**：`./scripts/sync-rdhs-skill.sh`（改动 Skill 内部逻辑后必须执行，保证外部渠道与全局软链最新）
