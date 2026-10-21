"use client";

import {
  AlertTriangle,
  ArrowRight,
  Award,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { FocusLineItem, RdhsSnapshot, SnapshotSummary } from "@/lib/rdhs/types";
import {
  calculateBusinessLineRankings,
  getTopFocusLines,
  summarizeSnapshot,
} from "@/lib/rdhs/aggregate";

type BgWarReportProps = {
  snapshot: RdhsSnapshot;
  previousSnapshot: RdhsSnapshot | null;
  onDrilldown: (businessLine?: string) => void;
};

export function BgWarReport({
  snapshot,
  previousSnapshot,
  onDrilldown,
}: BgWarReportProps) {
  const summary: SnapshotSummary = summarizeSnapshot(snapshot);
  const prevSummary: SnapshotSummary | null = previousSnapshot ? summarizeSnapshot(previousSnapshot) : null;
  const rankings = calculateBusinessLineRankings(snapshot, previousSnapshot);
  const focusLines = getTopFocusLines(snapshot);

  // Overall Pass rate (>=70 is passing)
  const measuredTotal = snapshot.products.filter((p) => p.rdhs !== null && p.rdhs !== undefined);
  const passTotal = measuredTotal.filter((p) => (p.rdhs ?? 0) >= 70).length;
  const overallPassRate =
    snapshot.products.length > 0
      ? Math.round((passTotal / snapshot.products.length) * 1000) / 10
      : 0;

  const scoreDelta =
    prevSummary && summary.rawAverageRdhs !== null && prevSummary.rawAverageRdhs !== null
      ? Math.round((summary.rawAverageRdhs - prevSummary.rawAverageRdhs) * 10) / 10
      : null;

  const scoreVal = summary.averageRdhs ?? 0;
  // Standardized thresholds: <45 重点治理, 45~<60 风险改进, 60~<70 持续改进区间, >=70 及格达标
  const stageName =
    summary.productTotal === 0 ? "暂无纳管产品" : scoreVal < 45
      ? "重点治理阶段"
      : scoreVal < 60
        ? "风险改进阶段"
        : scoreVal < 70
          ? "持续改进区间 (未及格)"
          : "及格达标阶段 (健康)";

  const stageTone =
    scoreVal < 45
      ? "status-重点治理"
      : scoreVal < 60
        ? "status-风险改进"
        : scoreVal < 70
          ? "status-持续优化"
          : "status-常规跟踪";

  return (
    <div className="bentoWarReportContainer">
      {/* Bento Row 1: Asymmetric Hero & Metrics Capsules */}
      <div className="bentoGridRow">
        {/* Bento Hero Card (1.45fr) */}
        <div className="bentoCard bentoHero">
          <div>
            <div className="heroMetaTop">
              <span className="periodChip">{snapshot.periodKey} 运营大盘 · 平均 RDHS</span>
              <span className={`statusChip ${stageTone}`}>
                {stageName}
              </span>
            </div>

            <p className="sourceNote">本期 {snapshot.products.length} 款；{previousSnapshot ? `上月 ${previousSnapshot.products.length} 款，产品名单变化需结合口径核实。` : "未获取上个自然月快照，不提供环比。"} 当月累计（MTD）与上月完整月不可直接认定效能升降。</p>
            <div className="heroScoreBlock">
              <div className="heroScoreNum">
                {summary.averageRdhs !== null ? summary.averageRdhs.toFixed(1) : "—"}
              </div>
              <div className="heroMetaPills">
                {scoreDelta !== null ? (
                  <span className={`heroDeltaPill ${scoreDelta >= 0 ? "deltaUp" : "deltaDown"}`}>
                    {scoreDelta >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                    {scoreDelta >= 0 ? `+${scoreDelta}` : scoreDelta} 环比
                  </span>
                ) : (
                  <span className="heroDeltaPill deltaNeutral">基线固化</span>
                )}
                <span className="heroPassPill">
                  及格达标率 (≥70及格线) <b>{overallPassRate}%</b>
                </span>
              </div>
            </div>

            <p className="heroSummaryText">
              {snapshot.overview.conclusion} {snapshot.overview.focus}
            </p>
          </div>

          <div>
            <div className="scaleBar">
              <div
                className="scaleBarFill"
                style={{ width: `${Math.min(100, Math.max(0, scoreVal))}%` }}
              />
            </div>
            <div className="scaleLabels">
              <span>0分 阻塞</span>
              <span>45分 风险改进</span>
              <span className="scaleWarning">60分 持续改进区间</span>
              <span className="scaleTarget">70分 及格达标线</span>
              <span>100分</span>
            </div>
          </div>
        </div>

        {/* Bento Metric Capsules (1fr in 2x2) */}
        <div className="bentoCard metricCapsulesGrid">
          <div className="metricCapsule">
            <div className="capsuleLabel">在研产品总数</div>
            <div className="capsuleNum">
              {summary.productTotal}<span className="capsuleUnit"> 款</span>
            </div>
            <div className="capsuleDesc">状态为 In Progress 研发中</div>
          </div>

          <div className="metricCapsule">
            <div className="capsuleLabel">度量覆盖率</div>
            <div className="capsuleNum textGreen">
              {Math.round(summary.measurementCoverage * 1000) / 10}<span className="capsuleUnit">%</span>
            </div>
            <div className="capsuleDesc">
              已度量 {summary.measuredProductCount} / 待关联 {summary.unmeasuredProductCount}
            </div>
          </div>

          <div className="metricCapsule">
            <div className="capsuleLabel">重点治理敞口 (P0/&lt;45)</div>
            <div className="capsuleNum textRed">
              {summary.bandCounts.keyGovernance}<span className="capsuleUnit"> 款</span>
            </div>
            <div className="capsuleDesc">
              含未度量计0；待治理(&lt;70)共 {summary.pendingGovernanceCount} 款
            </div>
          </div>

          <div className="metricCapsule">
            <div className="capsuleLabel">及格达标产品 (≥70)</div>
            <div className="capsuleNum textGreen">
              {passTotal}<span className="capsuleUnit"> 款</span>
            </div>
            <div className="capsuleDesc">
              未及格持续改进 {summary.productTotal - passTotal} 款
            </div>
          </div>
        </div>
      </div>

      {/* Bento Row 2: Universal Common Problems Analysis & Recommendations (全盘通用共性问题剖析与改进建议) */}
      <div className="commonProblemsSection">
        <div className="sectionHeader">
          <div className="sectionTitle">
            <AlertTriangle size={18} className="textAmber" />
            <span>全盘通用共性问题剖析与改进建议</span>
          </div>
          <span className="sectionSubtitle">全 BG 产研过程失分主要敞口与行动抓手</span>
        </div>

        <div className="commonProblemsGrid">
          <div className="problemCard cardBorderRed">
            <div className="problemCardHead">
              <span className="problemBadge badgeRed">核查事项 01</span>
              <span className="problemImpactTag">本期未度量 {summary.unmeasuredProductCount} 款</span>
            </div>
            <strong className="problemCardTitle">未度量产品核查（考核计 0 分）</strong>
            <p className="problemDesc">
              本期 {summary.unmeasuredProductCount} 款产品无有效评分，纳入考核分母并计 0。需区分图表范围、关联缺失与实际研发状态，不能仅凭缺分认定过程失管。
            </p>
            <div className="problemActionBox">
              <span className="actionBadge">改进建议与抓手</span>
              <p>业务线确认产品状态、图表范围与主数据关联；补齐真实过程记录后重新核算，不承诺自动提分。</p>
            </div>
          </div>

          <div className="problemCard cardBorderAmber">
            <div className="problemCardHead">
              <span className="problemBadge badgeAmber">核查事项 02</span>
              <span className="problemImpactTag">结合产品过程指标核实</span>
            </div>
            <strong className="problemCardTitle">发布与需求闭环核查</strong>
            <p className="problemDesc">
              发布登记与实际交付是不同口径。出现分项偏低或登记差额时，需核实发布记录、需求关联及实际验收凭证，不能直接认定漏登或未上线。
            </p>
            <div className="problemActionBox">
              <span className="actionBadge">改进建议与抓手</span>
              <p>核对实际上线及验收记录，仅对真实满足完成条件的工作项补齐登记，不为提分虚假结项。</p>
            </div>
          </div>

          <div className="problemCard cardBorderBlue">
            <div className="problemCardHead">
              <span className="problemBadge badgeBlue">核查事项 03</span>
              <span className="problemImpactTag">结合在途与周期样本核实</span>
            </div>
            <strong className="problemCardTitle">时效与在途积压核查</strong>
            <p className="problemDesc">
              时效分项偏低仅提示核查方向；需结合已完成需求的开发/交付周期、在途时长及积压样本，确认等待、依赖或计划变更等原因。
            </p>
            <div className="problemActionBox">
              <span className="actionBadge">改进建议与抓手</span>
              <p>逐项核实超期原单与继续开发价值，由负责人决定继续、调整计划或终止；不因均值超期批量结项。</p>
            </div>
          </div>
        </div>
      </div>

      {/* Bento Row 3: Top 3 Attack Focus Lines (最需关注治理业务线) */}
      <div className="focusSectionWrap">
        <div className="sectionHeader">
          <div className="sectionTitle">
            <Target size={18} className="textRed" />
            <span>最需关注治理业务线（Top 3 攻坚重点）</span>
          </div>
          <span className="sectionSubtitle">按重点治理产品敞口与过程能力短板综合排序</span>
        </div>

        <div className="focusBentoGrid">
          {focusLines.map((item) => {
            const priority = item.priority;
            return (
              <div
                key={item.name}
                className="focusBentoCard"
                onClick={() => onDrilldown(item.name)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onDrilldown(item.name);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <div>
                  <div className="cardTop">
                    <span className={`priorityBadge priority-${priority.toLowerCase()}`}>
                      {priority} 攻坚
                    </span>
                    <span className={`focusScore scoreTone-${item.avgScore >= 70 ? "green" : item.avgScore >= 60 ? "blue" : item.avgScore >= 45 ? "yellow" : "red"}`}>
                      均分 {item.avgScore.toFixed(1)} 分
                    </span>
                  </div>
                  <div className="focusCardTitle">{item.name}</div>
                  <div className="focusMetricChips">
                    <span>在研 <b>{item.productTotal}</b> 款</span>
                    <span>·</span>
                    <span className="textRed">重点治理 <b>{item.keyGovCount}</b> 款</span>
                    <span>·</span>
                    <span>未度量 <b>{item.unmeasuredCount}</b> 款</span>
                  </div>
                </div>

                <div className="focusBody">
                  <div className="focusDimRow">
                    <span className="dimLabel">最低过程分项：</span>
                    <span className="dimVal textRed">{item.lowest}</span>
                  </div>
                  <div className="focusActionText">
                    <strong>攻坚抓手：</strong>{item.focus}
                  </div>
                </div>

                <button
                  type="button"
                  className="focusActionBtn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDrilldown(item.name);
                  }}
                >
                  <span>穿透下钻 {item.productTotal} 款产品明细</span>
                  <ArrowRight size={13} />
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Bento Row 4: 9 Business Lines Ranking Matrix */}
      <div className="tableContainer">
        <div className="sectionHeader tableHeader">
          <div className="sectionTitle">
            <Award size={18} className="textAmber" />
            <span>一级业务线 RDHS 综合考核矩阵 (9 大业务线)</span>
          </div>
          <span className="sectionSubtitle">点击任意业务线即刻在工作台穿透下钻</span>
        </div>

        <div className="tableScrollWrap">
          <table className="bentoTable">
            <thead>
              <tr>
                <th style={{ width: 48 }}>排名</th>
                <th>一级业务线</th>
                <th>在管产品</th>
                <th>已度量 / 待关联</th>
                <th>考核均分</th>
                <th>环比变化</th>
                <th>及格率 (≥70)</th>
                <th>领跑标杆产品</th>
                <th>重点治理产品</th>
                <th>下钻</th>
              </tr>
            </thead>
            <tbody>
              {rankings.map((line) => {
                const rankNum = line.rank;
                const rankBadgeClass =
                  rankNum === 1
                    ? "rankGold"
                    : rankNum === 2
                      ? "rankSilver"
                      : rankNum === 3
                        ? "rankBronze"
                        : "rankDefault";
                const scoreValue = line.avgScore ?? 0;
                const scoreColorClass =
                  scoreValue >= 70
                    ? "var(--track)"
                    : scoreValue >= 60
                      ? "var(--optimize)"
                      : scoreValue >= 45
                        ? "var(--risk)"
                        : "var(--critical)";

                return (
                  <tr
                    key={line.businessLine}
                    className="bentoTableRow"
                    onClick={() => onDrilldown(line.businessLine)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onDrilldown(line.businessLine);
                      }
                    }}
                    tabIndex={0}
                  >
                    <td>
                      <span className={`bentoRankBadge ${rankBadgeClass}`} title={line.isTie ? "并列排名" : undefined}>
                        {rankNum}{line.isTie ? "*" : ""}
                      </span>
                    </td>
                    <td>
                      <span className="lineNameBold">{line.businessLine}</span>
                    </td>
                    <td>{line.total} 款</td>
                    <td>
                      {line.measuredCount} /{" "}
                      <span className={line.unmeasuredCount > 0 ? "textRed" : "textMuted"}>
                        {line.unmeasuredCount}
                      </span>
                    </td>
                    <td>
                      <span className="tableScoreNum" title={line.rawAvgScore !== null ? `未舍入分: ${line.rawAvgScore.toFixed(3)}` : undefined}>
                        {line.avgScore !== null ? `${line.avgScore.toFixed(1)} 分` : "—"}
                      </span>
                      <span className="tableProgressBar">
                        <i
                          className="tableProgressFill"
                          style={{
                            width: `${Math.min(100, Math.max(0, scoreValue))}%`,
                            background: scoreColorClass,
                          }}
                        />
                      </span>
                    </td>
                    <td>
                      {line.delta !== null ? (
                        <span className={`deltaBadge ${line.delta >= 0 ? "deltaUp" : "deltaDown"}`}>
                          {line.delta >= 0 ? `+${line.delta.toFixed(1)}` : line.delta.toFixed(1)}
                        </span>
                      ) : (
                        <span className="textMuted">-</span>
                      )}
                    </td>
                    <td>
                      <span style={{ fontWeight: line.passRate >= 50 ? 700 : 500, color: line.passRate >= 70 ? "var(--track)" : line.passRate > 0 ? "var(--ink)" : "var(--critical)" }}>
                        {line.passRate}%
                      </span>
                    </td>
                    <td className="textLead">{line.lead}</td>
                    <td className="textLag">{line.lag}</td>
                    <td>
                      <button
                        type="button"
                        className="drilldownActionBtn"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDrilldown(line.businessLine);
                        }}
                      >
                        下钻 <ArrowRight size={12} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
