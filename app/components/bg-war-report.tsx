"use client";

import {
  AlertTriangle,
  ArrowRight,
  Award,
  CheckCircle2,
  FileText,
  ShieldAlert,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { RdhsSnapshot, SnapshotSummary } from "@/lib/rdhs/types";
import { summarizeSnapshot } from "@/lib/rdhs/aggregate";

type BgWarReportProps = {
  snapshot: RdhsSnapshot;
  previousSnapshot: RdhsSnapshot | null;
  onDrilldown: (businessLine?: string) => void;
};

type LineStat = {
  name: string;
  total: number;
  measuredCount: number;
  unmeasuredCount: number;
  avgScore: number;
  prevAvgScore: number | null;
  delta: number | null;
  passRate: number;
  passCount: number;
  lead: string;
  lag: string;
  focus: string;
};

type FocusLineItem = {
  name: string;
  unmeasuredCount: number;
  keyGovCount: number;
  productTotal: number;
  avgScore: number;
  lowest: string;
  focus: string;
};

const COMPONENT_LABELS: Array<[string, string, number]> = [
  ["linkClosure", "价值链路闭环", 25],
  ["deliveryClosure", "交付闭环", 15],
  ["timeliness", "时效节奏", 20],
  ["granularity", "颗粒度对齐", 20],
  ["quality", "质量表现", 20],
];

function calcBusinessLineRanking(
  snapshot: RdhsSnapshot,
  previousSnapshot: RdhsSnapshot | null,
): LineStat[] {
  const prevMap = new Map<string, number>();
  if (previousSnapshot) {
    for (const b of previousSnapshot.businessLines) {
      const prods = previousSnapshot.products.filter(
        (p) => p.businessLine === b.businessLine && p.rdhs !== null && p.rdhs !== undefined,
      );
      if (prods.length > 0) {
        const sum = prods.reduce((acc, p) => acc + (p.rdhs ?? 0), 0);
        prevMap.set(b.businessLine, Math.round((sum / prods.length) * 10) / 10);
      }
    }
  }

  const results: LineStat[] = [];
  for (const b of snapshot.businessLines) {
    const prods = snapshot.products.filter((p) => p.businessLine === b.businessLine);
    const measured = prods.filter((p) => p.rdhs !== null && p.rdhs !== undefined);
    const unmeasured = prods.filter((p) => p.rdhs === null || p.rdhs === undefined);
    const avg =
      measured.length > 0
        ? Math.round((measured.reduce((acc, p) => acc + (p.rdhs ?? 0), 0) / measured.length) * 10) / 10
        : 0;
    const prevAvg = prevMap.get(b.businessLine) ?? null;
    const delta = prevAvg !== null ? Math.round((avg - prevAvg) * 10) / 10 : null;
    const passCount = measured.filter((p) => (p.rdhs ?? 0) >= 70).length;
    const passRate = prods.length > 0 ? Math.round((passCount / prods.length) * 1000) / 10 : 0;

    const sorted = [...measured].sort((a, b) => (b.rdhs ?? 0) - (a.rdhs ?? 0));
    const lead = sorted[0] ? `${sorted[0].product} (${sorted[0].rdhs}分)` : "-";
    const lag =
      unmeasured.length > 0
        ? `${unmeasured[0].product} (未度量)`
        : sorted.length > 0
          ? `${sorted[sorted.length - 1].product} (${sorted[sorted.length - 1].rdhs}分)`
          : "-";

    results.push({
      name: b.businessLine,
      total: b.productTotal,
      measuredCount: measured.length,
      unmeasuredCount: unmeasured.length,
      avgScore: avg,
      prevAvgScore: prevAvg,
      delta,
      passRate,
      passCount,
      lead,
      lag,
      focus: b.focus,
    });
  }

  return results.sort((a, b) => b.avgScore - a.avgScore);
}

function getTopFocusLines(snapshot: RdhsSnapshot): FocusLineItem[] {
  return snapshot.businessLines
    .map((line) => {
      const lineProducts = snapshot.products.filter((p) => p.businessLine === line.businessLine);
      const lineSummary = summarizeSnapshot({ ...snapshot, products: lineProducts });

      const componentAverages = COMPONENT_LABELS
        .map(([key, label, max]) => ({
          key,
          label,
          max,
          val: lineSummary.componentAverages[key as keyof typeof lineSummary.componentAverages],
        }))
        .filter((c) => c.val !== null);

      const lowest = [...componentAverages].sort(
        (a, b) => ((a.val ?? 0) / a.max) - ((b.val ?? 0) / b.max)
      )[0] ?? null;

      return {
        name: line.businessLine,
        unmeasuredCount: lineSummary.unmeasuredProductCount,
        keyGovCount: line.keyGovernanceCount,
        productTotal: line.productTotal,
        avgScore: lineSummary.averageRdhs !== null ? Math.round(lineSummary.averageRdhs * 10) / 10 : 0,
        lowest: lowest ? `${lowest.label} (${lowest.val?.toFixed(1)} / ${lowest.max})` : "暂无",
        focus: line.focus,
      };
    })
    .filter((entry) => entry.keyGovCount > 0 || entry.avgScore < 60)
    .sort((a, b) => {
      const diff = b.keyGovCount - a.keyGovCount;
      if (diff !== 0) return diff;
      return a.avgScore - b.avgScore;
    })
    .slice(0, 3);
}

export function BgWarReport({
  snapshot,
  previousSnapshot,
  onDrilldown,
}: BgWarReportProps) {
  const summary: SnapshotSummary = summarizeSnapshot(snapshot);
  const prevSummary: SnapshotSummary | null = previousSnapshot ? summarizeSnapshot(previousSnapshot) : null;
  const rankings = calcBusinessLineRanking(snapshot, previousSnapshot);
  const focusLines = getTopFocusLines(snapshot);

  // Overall Pass rate (>=70 is passing)
  const measuredTotal = snapshot.products.filter((p) => p.rdhs !== null && p.rdhs !== undefined);
  const passTotal = measuredTotal.filter((p) => (p.rdhs ?? 0) >= 70).length;
  const overallPassRate =
    snapshot.products.length > 0
      ? Math.round((passTotal / snapshot.products.length) * 1000) / 10
      : 0;

  const scoreDelta =
    prevSummary && summary.averageRdhs !== null && prevSummary.averageRdhs !== null
      ? Math.round((summary.averageRdhs - prevSummary.averageRdhs) * 10) / 10
      : null;

  const scoreVal = summary.averageRdhs ?? 0;
  // Standardized thresholds: <45 重点治理, 45~<60 风险改进, 60~<70 持续改进区间, >=70 及格达标
  const stageName =
    scoreVal < 45
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
            <div className="capsuleLabel">重点治理敞口 (&lt;45)</div>
            <div className="capsuleNum textRed">
              {summary.pendingGovernanceCount}<span className="capsuleUnit"> 款</span>
            </div>
            <div className="capsuleDesc">
              占比 {Math.round(summary.pendingGovernanceRate * 1000) / 10}% (含未度量)
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
              <span className="problemBadge badgeRed">共性病因 01</span>
              <span className="problemImpactTag">拖累全BG均分约 3~4分</span>
            </div>
            <strong className="problemCardTitle">产品主数据“黑户”（未关联直接计 0 分）</strong>
            <p className="problemDesc">
              部分实际研发中产品未挂接飞书项目度量图表，系统按 0 分纳统（如《智能评标》《Spark Insight》等），严重拉低所属业务线考核均分。
            </p>
            <div className="problemActionBox">
              <span className="actionBadge">改进建议与抓手</span>
              <p>各业务线 PMO 联合负责人立即在飞书项目中补齐产品主数据关联与工作流绑定，消除未度量 0 分敞口。</p>
            </div>
          </div>

          <div className="problemCard cardBorderAmber">
            <div className="problemCardHead">
              <span className="problemBadge badgeAmber">共性病因 02</span>
              <span className="problemImpactTag">未闭环差额明显</span>
            </div>
            <strong className="problemCardTitle">发布登记断链（漏登发版单与未绑定卡片）</strong>
            <p className="problemDesc">
              实际发版正常开展，但发版登记闭环率跌破警戒水位，存在已上线卡片未挂接发布单的现象，导致“交付闭环”分项得分失真。
            </p>
            <div className="problemActionBox">
              <span className="actionBadge">改进建议与抓手</span>
              <p>每周建立上线卡片核销机制，项目管理代表必须将已上线的发版单与卡片完成闭环绑定，消灭挂账。</p>
            </div>
          </div>

          <div className="problemCard cardBorderBlue">
            <div className="problemCardHead">
              <span className="problemBadge badgeBlue">共性病因 03</span>
              <span className="problemImpactTag">滞留超 90~130天</span>
            </div>
            <strong className="problemCardTitle">长在途卡片积压（时效节奏维度得分趋零）</strong>
            <p className="problemDesc">
              部分重点产品在途卡片超 90~130 天长期滞留未验收流转，积压率偏高，直接拖垮“时效节奏”维度得分（多业务线时效甚至低于 6 分）。
            </p>
            <div className="problemActionBox">
              <span className="actionBadge">改进建议与抓手</span>
              <p>启动“僵尸卡片清退专项”，对在途超 90 天的需求评估：有业务价值则分期拆小流转，无价值立即终止归档。</p>
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
          {focusLines.map((item, index) => {
            const priority = index < 2 ? "P0" : "P1";
            return (
              <div
                key={item.name}
                className="focusBentoCard"
                onClick={() => onDrilldown(item.name)}
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
              {rankings.map((line, index) => {
                const rankNum = index + 1;
                const rankBadgeClass =
                  rankNum === 1
                    ? "rankGold"
                    : rankNum === 2
                      ? "rankSilver"
                      : rankNum === 3
                        ? "rankBronze"
                        : "rankDefault";
                const scoreColorClass =
                  line.avgScore >= 70
                    ? "var(--track)"
                    : line.avgScore >= 60
                      ? "var(--optimize)"
                      : line.avgScore >= 45
                        ? "var(--risk)"
                        : "var(--critical)";

                return (
                  <tr
                    key={line.name}
                    className="bentoTableRow"
                    onClick={() => onDrilldown(line.name)}
                  >
                    <td>
                      <span className={`bentoRankBadge ${rankBadgeClass}`}>
                        {rankNum}
                      </span>
                    </td>
                    <td>
                      <span className="lineNameBold">{line.name}</span>
                    </td>
                    <td>{line.total} 款</td>
                    <td>
                      {line.measuredCount} /{" "}
                      <span className={line.unmeasuredCount > 0 ? "textRed" : "textMuted"}>
                        {line.unmeasuredCount}
                      </span>
                    </td>
                    <td>
                      <span className="tableScoreNum">{line.avgScore.toFixed(1)} 分</span>
                      <span className="tableProgressBar">
                        <i
                          className="tableProgressFill"
                          style={{
                            width: `${Math.min(100, Math.max(0, line.avgScore))}%`,
                            background: scoreColorClass,
                          }}
                        />
                      </span>
                    </td>
                    <td>
                      {line.delta !== null ? (
                        <span className={`deltaBadge ${line.delta >= 0 ? "deltaUp" : "deltaDown"}`}>
                          {line.delta >= 0 ? `+${line.delta}` : line.delta}
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
                          onDrilldown(line.name);
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

      {/* Bento Row 5: Archive Links */}
      <div className="bentoArchiveCard">
        <div className="archiveTitle">
          <FileText size={15} />
          <span>历史单期例会战报归档（独立 HTML）</span>
        </div>
        <div className="archiveLinkGroup">
          <a href="./reports/2026-10.html" target="_blank" rel="noopener noreferrer" className="archivePill">
            📄 消费者 BG 10 月产研过程治理情况 (例会汇报版) ↗
          </a>
          <a href="./reports/2026-09.html" target="_blank" rel="noopener noreferrer" className="archivePill">
            📄 消费者 BG 9 月产研过程治理战报 (例会汇报版) ↗
          </a>
        </div>
      </div>
    </div>
  );
}
