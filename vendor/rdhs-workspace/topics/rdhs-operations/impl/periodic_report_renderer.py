"""渲染与既有飞书模板同构的周期 RDHS 报告 XML。"""

from __future__ import annotations

from html import escape
import re

from impl.periodic_report_models import PeriodicReportData


def _text(value: object) -> str:
    return escape(str(value), quote=False)


def _period_title(period: str) -> str:
    return period.replace("-", "")


def report_document_title(period: str, snapshot_label: str) -> str:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})\b", snapshot_label)
    if not match:
        raise ValueError(f"snapshot label must start with an ISO date: {snapshot_label!r}")
    return f"产研过程效能运营报告-{_period_title(period)}-{match.group(2)}{match.group(3)}快照"


def render_periodic_report_xml(
    *,
    report: PeriodicReportData,
    period: str,
    snapshot_label: str,
    full_product_url: str,
) -> str:
    """生成新文档正文；模板与历史嵌入表格均不参与写入。"""
    overview_count = len(report.overview_rows)
    improvement_count = len(report.improvement_rows)
    todo_items = "".join(f"<li>{_text(item)}</li>" for item in report.todo_items)
    focus_lines = "；".join(
        f"{row.business_line}：{row.focus}" for row in report.overview_rows if row.mode != "常规跟踪"
    )
    focus_paragraph = (
        f"<p>本期关注重点：{_text(focus_lines)}</p>" if focus_lines else ""
    )
    return f"""<title>{report_document_title(period, snapshot_label)}</title>
<callout emoji="🍰" background-color="light-blue" border-color="blue">
  <p>R&amp;D Digital Health Score（RDHS）通过校验飞书项目中的产研数据，评估消费者BG产研过程真实性、完整性与规范性。</p>
  <ul>
    <li><b><span text-color="green">80分以上</span></b>：优秀健康，有优秀的过程管理实践，作为样板产品</li>
    <li><b>70-80分</b>：基本健康，存在局部短板，常规跟踪优化即可</li>
    <li><b><span text-color="blue">60-70分</span></b>：存在些许不足，需定位短板并持续优化</li>
    <li><b><span text-color="orange">45-60分</span></b>：存在明显风险，建议重点分析并关注改进</li>
    <li><b><span text-color="red">45分以下</span></b>：存在阻塞问题，建议专题分析并重点治理</li>
  </ul>
  <p>依托RDHS综合性聚焦产研过程管理健康度情况，重点关注产品级产研过程线上化与规范化系统治理，让产研效能由超级个体/超级团队穿透到产品。</p>
  <p>注：业务线交付效能相关数据可参考月报/周报快照从飞书项目度量图表中实时获取。</p>
</callout>
<h1>RDHS总览</h1>
<p>本期快照：{_text(snapshot_label)}。本月共识别 {overview_count} 条业务线、{report.audit.get("current_accepted_row_count", 0)} 个有效产品记录；其中纳入本期治理清单 {improvement_count} 个产品。请优先围绕各业务线最低分分项、环比下降项和过程有效样本不足项推进改进。</p>
{focus_paragraph}
<sheet type="blank"></sheet>
<h1>产品改进清单</h1>
<p>本期改进清单按业务线排序展示，每条业务线原则上聚焦3个产品，按照重点治理、风险改进、持续优化的优先级依次纳入，作为本期重点跟踪对象。</p>
<p>主要问题与建议本期动作均由本期快照的参与人数、吞吐、积压、周期、质量、发布和RDHS分项数据生成；存在可比上月记录时同步标出显著下降。</p>
<sheet type="blank"></sheet>
<h1>重要待办项</h1>
<ul>{todo_items}</ul>
<h1>附录</h1>
<h2>产研过程治理运作机制</h2>
<blockquote><p>主数据正确 -&gt; 产研过程线上化 -&gt; 产研过程规范化 -&gt; 产研效能量化呈现</p></blockquote>
<p>本机制用于支撑 CBG 产研过程治理落地。月报只负责识别本期治理对象，后续通过周快照、线下推进和月末复盘推动问题真正解决。</p>
<ol>
  <li><b>治理对象。</b> 仅围绕本期治理清单中的产品推进，重点关注产品主数据是否健康，以及产品过程关键问题是否在改。（清单选取标准：仅从 RDHS &lt; 70 产品中选取，按重点治理、风险改进、持续优化的优先级依次纳入；每条业务线每期原则上聚焦 3 个产品，同档内按 RDHS 从低到高选取，不足 3 个按实际数量纳入。）</li>
  <li><b>运作节奏。</b> 月初归档上月基线并确认本月治理清单；每周一基于截至周一前的本月快照更新一次改进清单并同步到改进沟通群；月末基于最后一次快照复盘，判断是否改善、是否继续纳入下期。</li>
  <li><b>角色分工。</b> 消费者BG PMO输出产品改进清单、更新周快照、识别卡点并推进治理落实；业务侧质量改进负责人负责认领本线产品，确认主数据、责任人和本期动作，并推动产品和研发责任人落实具体改进动作。</li>
  <li><b>群内机制。</b> 群内只同步月报、周快照和重点改进事项；对未反馈或推进慢的事项，先协商原因和解决方案，必要时再升级到业务线技术总监处理。</li>
  <li><b>每周重点。</b> 每周不做泛汇报，只看三件事：主数据是否补齐、本期动作是否启动、关键问题是否出现改善迹象。</li>
  <li><b>月末结论。</b> 改善明显的产品可降级或退出治理；有推进但未完成的继续纳入下期；长期无反馈或无动作的，作为异常项上升到消费者BG月例会处理。</li>
</ol>
<h2>产品主数据治理</h2>
<p><cite type="doc" doc-id="Vrl7wLOJIiC0c1kLMMUrtYrpz3e" file-type="wiki" title="产品主数据管理规约V1.0"></cite></p>
<h2>RDHS规则说明</h2>
<ul><li><cite type="doc" doc-id="EGtmwoVKgiAgEhkPnnrrbnqMzWf" file-type="wiki" title="RDHS规则说明V2.2"></cite></li></ul>
<h2><b>度量图表链接</b></h2>
<blockquote><p>注：实时度量数据参考专题度量图表，可结合筛选器 + 快捷筛选查看具体产线数据</p></blockquote>
<ul>
  <li><a type="url-preview" href="https://project.xfchat.iflytek.com/cbg_product_develop/multiProjectView/lBNg66BvR?scope=workspaces&amp;node=19684">[视图]【产品】产研过程-效能分析V1.0</a></li>
</ul>
<h2>全量产品改进清单</h2>
<p>全量清单保留所有通过校验且 RDHS 小于 70 的产品，并展示产品状态、超级团队关联和主问题标签，用于治理核对与推进。</p>
<p><a type="url-preview" href="{_text(full_product_url)}">全量产品改进清单-{_period_title(period)}</a></p>
"""
