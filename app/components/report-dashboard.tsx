"use client";

import {
  Activity,
  CheckCircle2,
  CircleAlert,
  Database,
  Gauge,
  PackageCheck,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { useState } from "react";

import { buildMonthlyTrend, summarizeSnapshot } from "@/lib/rdhs/aggregate";
import {
  filterProducts,
  sortBusinessLines,
  sortProducts,
  type ProductSort,
} from "@/lib/rdhs/filter";
import type {
  Cadence,
  ComponentScores,
  GovernanceBand,
  RdhsSnapshot,
} from "@/lib/rdhs/types";
import { ScoreRail } from "./score-rail";
import { TrendChart } from "./trend-chart";

type ReportDashboardProps = {
  initialSnapshots: RdhsSnapshot[];
  dataMode: "live" | "preview";
};

const BANDS: GovernanceBand[] = ["重点治理", "风险改进", "持续优化", "常规跟踪"];
const COMPONENT_LABELS: Array<[keyof ComponentScores, string, number]> = [
  ["linkClosure", "价值链路闭环", 25],
  ["deliveryClosure", "交付闭环", 15],
  ["timeliness", "时效节奏", 20],
  ["granularity", "颗粒度对齐", 20],
  ["quality", "质量表现", 20],
];

function formatFetchedAt(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function formatScore(value: number | null) {
  return value === null ? "未度量" : value.toFixed(1);
}

function bandClass(band: GovernanceBand) {
  if (band === "重点治理") return "key";
  if (band === "风险改进") return "risk";
  if (band === "持续优化") return "optimize";
  return "regular";
}

function MetricItem({
  icon,
  label,
  value,
  suffix,
  meta,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  suffix?: string;
  meta: string;
}) {
  return (
    <div className="metricItem">
      <div className="metricLabel">{icon}<span>{label}</span></div>
      <div className="metricValue">
        {value}{suffix ? <span className="metricSuffix">{suffix}</span> : null}
      </div>
      <div className="metricMeta">{meta}</div>
    </div>
  );
}

function BandStack({ counts, total, label }: {
  counts: [number, number, number, number];
  total: number;
  label: string;
}) {
  return (
    <span className="bandStack" aria-label={`${label}：重点治理 ${counts[0]}，风险改进 ${counts[1]}，持续优化 ${counts[2]}，常规跟踪 ${counts[3]}`}>
      {counts.map((count, index) => (
        <span
          className={`bandStackItem ${["key", "risk", "optimize", "regular"][index]}`}
          key={index}
          style={{ width: `${total === 0 ? 0 : (count / total) * 100}%` }}
        />
      ))}
    </span>
  );
}

export function ReportDashboard({ initialSnapshots, dataMode }: ReportDashboardProps) {
  const [snapshots, setSnapshots] = useState(initialSnapshots);
  const monthlySnapshots = snapshots.filter((snapshot) => snapshot.cadence === "monthly");
  const [cadence, setCadence] = useState<Cadence>("monthly");
  const [periodKey, setPeriodKey] = useState(
    monthlySnapshots.at(-1)?.periodKey ?? snapshots.at(-1)?.periodKey ?? "",
  );
  const [selectedLine, setSelectedLine] = useState("全部业务线");
  const [selectedBand, setSelectedBand] = useState<GovernanceBand | "全部分档">("全部分档");
  const [query, setQuery] = useState("");
  const [unmeasuredOnly, setUnmeasuredOnly] = useState(false);
  const [productSort, setProductSort] = useState<ProductSort>("rdhs-asc");
  const [selectedProductName, setSelectedProductName] = useState<string | null>(null);
  const [refreshState, setRefreshState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [refreshMessage, setRefreshMessage] = useState("");
  const [currentDataMode, setCurrentDataMode] = useState(dataMode);

  const available = snapshots.filter((snapshot) => snapshot.cadence === cadence);
  const snapshot =
    available.find((candidate) => candidate.periodKey === periodKey) ?? available.at(-1) ?? null;
  const summary = snapshot ? summarizeSnapshot(snapshot) : null;
  const trend = buildMonthlyTrend(snapshots);
  const businessLines = snapshot ? sortBusinessLines(snapshot.businessLines) : [];
  const filteredProducts = snapshot
    ? sortProducts(
      filterProducts(snapshot.products, {
        businessLine: selectedLine,
        band: selectedBand,
        query,
        unmeasuredOnly,
      }),
      productSort,
    )
    : [];
  const selectedProduct = snapshot?.products.find(
    (product) => product.product === selectedProductName,
  ) ?? null;

  function resetDrilldown() {
    setSelectedLine("全部业务线");
    setSelectedBand("全部分档");
    setQuery("");
    setUnmeasuredOnly(false);
    setProductSort("rdhs-asc");
    setSelectedProductName(null);
  }

  function changeCadence(nextCadence: Cadence) {
    setCadence(nextCadence);
    const candidates = snapshots.filter((item) => item.cadence === nextCadence);
    setPeriodKey(candidates.at(-1)?.periodKey ?? "");
    resetDrilldown();
  }

  function changePeriod(nextPeriod: string) {
    setPeriodKey(nextPeriod);
    resetDrilldown();
  }

  function chooseBusinessLine(line: string) {
    setSelectedLine(line);
    setSelectedProductName(null);
    document.getElementById("product-drilldown")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function refreshReports() {
    setRefreshState("loading");
    setRefreshMessage("");
    try {
      const periodsResponse = await fetch(`/api/periods?cadence=${cadence}`, { cache: "no-store" });
      if (!periodsResponse.ok) throw new Error("实时数据暂不可用");
      const periodsPayload = await periodsResponse.json() as { periods: Array<{ periodKey: string }> };
      if (periodsPayload.periods.length === 0) {
        setRefreshState("success");
        setRefreshMessage("当前无新增有效快照");
        return;
      }
      const records = await Promise.all(periodsPayload.periods.map(async ({ periodKey: nextPeriod }) => {
        const response = await fetch(`/api/report?cadence=${cadence}&period=${nextPeriod}`, { cache: "no-store" });
        if (!response.ok) throw new Error("实时报告读取失败");
        return response.json() as Promise<{ record: { snapshot: RdhsSnapshot } }>;
      }));
      const otherCadence = snapshots.filter((item) => item.cadence !== cadence);
      const refreshed = records.map((record) => record.record.snapshot);
      setSnapshots([...otherCadence, ...refreshed]);
      changePeriod(refreshed.at(-1)?.periodKey ?? periodKey);
      setCurrentDataMode("live");
      setRefreshState("success");
      setRefreshMessage("已更新至最新有效快照");
    } catch (error) {
      setRefreshState("error");
      setRefreshMessage(error instanceof Error ? error.message : "实时数据暂不可用");
    }
  }

  function clearFilters() {
    resetDrilldown();
  }

  return (
    <div className="dashboardShell">
      <header className="topbar">
        <div className="topbarInner">
          <div className="brandLockup">
            <div className="brandMark" aria-hidden="true">RDHS</div>
            <div>
              <h1 className="brandTitle">产研过程效能运营报告</h1>
              <p className="brandSubtitle">消费者BG · 产品视角</p>
            </div>
          </div>
          <div className="topbarActions">
            <div className="segmented" aria-label="报告周期">
              <button className="segment" type="button" aria-pressed={cadence === "weekly"} onClick={() => changeCadence("weekly")}>周报</button>
              <button className="segment" type="button" aria-pressed={cadence === "monthly"} onClick={() => changeCadence("monthly")}>月报</button>
            </div>
            <select className="periodSelect" aria-label="选择报告周期" value={periodKey} onChange={(event) => changePeriod(event.target.value)} disabled={available.length === 0}>
              {available.length === 0 ? <option value="">暂无数据</option> : null}
              {[...available].reverse().map((item) => <option key={item.periodKey} value={item.periodKey}>{item.periodKey}</option>)}
            </select>
            <button className="iconButton" type="button" title="检查最新数据" aria-label="检查最新数据" onClick={refreshReports} disabled={refreshState === "loading"}>
              <RefreshCw className={refreshState === "loading" ? "spin" : ""} size={16} strokeWidth={1.8} />
            </button>
          </div>
        </div>
      </header>

      <main className="pageInner">
        {snapshot && summary ? (
          <>
            <section className="reportIntro">
              <div>
                <p className="eyebrow">{snapshot.periodKey} · {cadence === "monthly" ? "月度" : "周度"}判断</p>
                <h2>{snapshot.overview.conclusion}</h2>
                <p className="focusText">{snapshot.overview.focus}</p>
              </div>
              <div className="dataStamp">
                <span className="stampLabel">数据更新时间</span>
                <span className="stampValue">{formatFetchedAt(snapshot.fetchedAt)}</span>
                <span className={`dataState ${currentDataMode === "live" ? "live" : "preview"}`}>
                  {currentDataMode === "live" ? "实时数据已校验" : "已验证历史快照"}
                </span>
                {refreshMessage ? <span className={`refreshMessage ${refreshState}`}>{refreshMessage}</span> : null}
              </div>
            </section>

            <section className="metricStrip" aria-label="消费者BG核心指标">
              <MetricItem icon={<PackageCheck size={15} />} label="研发中产品" value={String(summary.productTotal)} suffix="个" meta={`${snapshot.businessLines.length} 条业务线`} />
              <MetricItem icon={<Gauge size={15} />} label="平均 RDHS" value={summary.averageRdhs?.toFixed(1) ?? "—"} suffix="分" meta={`${summary.measuredProductCount} 个已度量产品`} />
              <MetricItem icon={<Activity size={15} />} label="度量覆盖率" value={(summary.measurementCoverage * 100).toFixed(1)} suffix="%" meta={`${summary.unmeasuredProductCount} 个未度量/待关联`} />
              <MetricItem icon={<CircleAlert size={15} />} label="低于70分" value={String(summary.below70Count)} suffix="个" meta="包含未度量/待关联" />
            </section>

            <ScoreRail value={summary.averageRdhs} />

            <section className="contentGrid">
              <div className="panel">
                <div className="panelHeader">
                  <div><h3 className="panelTitle">月度 RDHS 趋势</h3><p className="panelSubtitle">已度量产品均值 · 覆盖率独立核验</p></div>
                  <div className="chartLegend" aria-hidden="true">
                    <span className="legendItem"><span className="legendSwatch" />平均 RDHS</span>
                    <span className="legendItem"><span className="legendSwatch baseline" />70分基线</span>
                  </div>
                </div>
                <TrendChart points={trend} />
              </div>

              <div className="panel">
                <div className="panelHeader"><div><h3 className="panelTitle">业务线分布</h3><p className="panelSubtitle">产品数与四档治理结构</p></div></div>
                <ul className="lineList">
                  {businessLines.map((line) => (
                    <li className="lineListItem" key={line.businessLine}>
                      <button className="lineSelect" type="button" onClick={() => chooseBusinessLine(line.businessLine)} aria-label={`筛选 ${line.businessLine}`}>
                        <span className="lineName">{line.businessLine}</span>
                        <span className="lineCount">{line.productTotal}</span>
                        <BandStack
                          counts={[line.keyGovernanceCount, line.riskImprovementCount, line.continuousOptimizationCount, line.regularTrackingCount]}
                          total={line.productTotal}
                          label={line.businessLine}
                        />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </section>

            <section className="panel operationPanel" aria-labelledby="business-table-title">
              <div className="panelHeader tablePanelHeader">
                <div><h3 className="panelTitle" id="business-table-title">RDHS 总览</h3><p className="panelSubtitle">未度量/待关联纳入重点治理</p></div>
                <div className="bandLegend">
                  {BANDS.map((band) => <span className="legendItem" key={band}><span className={`legendDot ${bandClass(band)}`} />{band}</span>)}
                </div>
              </div>
              <div className="tableScroll">
                <table className="dataTable lineTable">
                  <thead><tr><th>业务线</th><th>产品总数</th><th>重点治理</th><th>风险改进</th><th>持续优化</th><th>常规跟踪</th><th>度量覆盖率</th><th>平均 RDHS</th><th>本期关注重点</th></tr></thead>
                  <tbody>
                    {businessLines.map((line) => {
                      const lineProducts = snapshot.products.filter((product) => product.businessLine === line.businessLine);
                      const lineSummary = summarizeSnapshot({ ...snapshot, products: lineProducts });
                      return (
                        <tr key={line.businessLine}>
                          <th scope="row"><button className="tableLink" type="button" onClick={() => chooseBusinessLine(line.businessLine)}>{line.businessLine}</button></th>
                          <td>{line.productTotal}</td><td className="bandNumber key">{line.keyGovernanceCount}</td><td className="bandNumber risk">{line.riskImprovementCount}</td><td className="bandNumber optimize">{line.continuousOptimizationCount}</td><td className="bandNumber regular">{line.regularTrackingCount}</td>
                          <td>{(lineSummary.measurementCoverage * 100).toFixed(1)}%</td><td>{formatScore(lineSummary.averageRdhs)}</td><td className="focusCell">{line.focus}</td>
                        </tr>
                      );
                    })}
                    <tr className="totalRow"><th scope="row">消费者BG（合计）</th><td>{summary.productTotal}</td><td>{summary.bandCounts.keyGovernance}</td><td>{summary.bandCounts.riskImprovement}</td><td>{summary.bandCounts.continuousOptimization}</td><td>{summary.bandCounts.regularTracking}</td><td>{(summary.measurementCoverage * 100).toFixed(1)}%</td><td>{formatScore(summary.averageRdhs)}</td><td className="focusCell">{snapshot.overview.focus}</td></tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section className="drilldownSection" id="product-drilldown" aria-labelledby="product-table-title">
              <div className="sectionHeading">
                <div><h3 id="product-table-title">产品治理明细</h3><p>{filteredProducts.length} / {snapshot.products.length} 个研发中产品</p></div>
                {(selectedLine !== "全部业务线" || selectedBand !== "全部分档" || query || unmeasuredOnly) ? <button className="clearButton" type="button" onClick={clearFilters}><X size={14} />清除筛选</button> : null}
              </div>
              <div className="filterBar">
                <label className="searchField"><Search size={15} aria-hidden="true" /><span className="srOnly">搜索产品或业务线</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索产品或业务线" /></label>
                <select aria-label="筛选业务线" value={selectedLine} onChange={(event) => { setSelectedLine(event.target.value); setSelectedProductName(null); }}><option>全部业务线</option>{businessLines.map((line) => <option key={line.businessLine}>{line.businessLine}</option>)}</select>
                <select aria-label="筛选治理分档" value={selectedBand} onChange={(event) => setSelectedBand(event.target.value as GovernanceBand | "全部分档")}><option>全部分档</option>{BANDS.map((band) => <option key={band}>{band}</option>)}</select>
                <select aria-label="产品排序" value={productSort} onChange={(event) => setProductSort(event.target.value as ProductSort)}><option value="rdhs-asc">RDHS 从低到高</option><option value="rdhs-desc">RDHS 从高到低</option><option value="product-asc">产品名称</option></select>
                <label className="checkControl"><input type="checkbox" checked={unmeasuredOnly} onChange={(event) => setUnmeasuredOnly(event.target.checked)} /><span>仅未度量/待关联</span></label>
              </div>

              <div className={`productWorkspace ${selectedProduct ? "hasDetail" : ""}`}>
                <div className="panel productTablePanel">
                  <div className="tableScroll">
                    <table className="dataTable productTable">
                      <thead><tr><th>产品</th><th>业务线</th><th>RDHS</th><th>治理分档</th><th>优先级</th><th>最低过程项</th></tr></thead>
                      <tbody>
                        {filteredProducts.map((product) => (
                          <tr className={selectedProductName === product.product ? "selectedRow" : ""} key={`${product.businessLine}-${product.product}`}>
                            <th scope="row"><button className="tableLink productLink" type="button" onClick={() => setSelectedProductName(product.product)}>{product.product}</button><span className="productLineMobile">{product.businessLine}</span></th>
                            <td>{product.businessLine}</td><td className="scoreCell">{formatScore(product.rdhs)}</td><td><span className={`bandBadge ${bandClass(product.governanceBand)}`}>{product.governanceBand}</span></td><td>{product.priority ?? "—"}</td><td>{product.lowestComponent}</td>
                          </tr>
                        ))}
                        {filteredProducts.length === 0 ? <tr><td className="tableEmpty" colSpan={6}>无匹配产品</td></tr> : null}
                      </tbody>
                    </table>
                  </div>
                </div>

                {selectedProduct ? (
                  <aside className="panel productDetail" aria-label={`${selectedProduct.product}治理详情`}>
                    <div className="detailHeader"><div><span className="detailLine">{selectedProduct.businessLine}</span><h4>{selectedProduct.product}</h4></div><button className="iconButton quiet" type="button" aria-label="关闭产品详情" title="关闭产品详情" onClick={() => setSelectedProductName(null)}><X size={15} /></button></div>
                    <div className="detailScoreRow"><span className={`scorePlate ${selectedProduct.rdhs === null ? "unmeasured" : bandClass(selectedProduct.governanceBand)}`}>{formatScore(selectedProduct.rdhs)}</span><span className={`bandBadge ${bandClass(selectedProduct.governanceBand)}`}>{selectedProduct.governanceBand}</span>{selectedProduct.priority ? <span className="priorityTag">{selectedProduct.priority}</span> : null}</div>
                    <div className="componentList">
                      {COMPONENT_LABELS.map(([key, label, maximum]) => {
                        const value = selectedProduct.components[key];
                        return <div className="componentRow" key={key}><span>{label}</span><span className="componentTrack"><span style={{ width: `${value === null ? 0 : Math.min(100, (value / maximum) * 100)}%` }} /></span><strong>{value === null ? "—" : value.toFixed(1)}</strong></div>;
                      })}
                    </div>
                    <dl className="detailNotes"><div><dt>主要问题</dt><dd>{selectedProduct.problem}</dd></div><div><dt>治理动作</dt><dd>{selectedProduct.action}</dd></div></dl>
                  </aside>
                ) : null}
              </div>
            </section>

            <section className="auditBand" aria-label="数据质量审计">
              <div className="auditTitle"><Database size={16} /><span>数据质量审计</span><strong><CheckCircle2 size={14} />已通过发布校验</strong></div>
              <dl className="auditMetrics"><div><dt>原始行</dt><dd>{snapshot.audit.rawRowCount}</dd></div><div><dt>有效度量</dt><dd>{snapshot.audit.acceptedRowCount}</dd></div><div><dt>研发中产品</dt><dd>{snapshot.audit.researchProductCount}</dd></div><div><dt>未度量/待关联</dt><dd>{snapshot.audit.unmeasuredProductCount}</dd></div><div><dt>排除测试业务线</dt><dd>{snapshot.audit.excludedTestBusinessLineCount}</dd></div><div><dt>数据哈希</dt><dd title={snapshot.source.sha256}>{snapshot.source.sha256.slice(0, 10)}</dd></div></dl>
            </section>
          </>
        ) : <section className="panel emptyState">该周期暂无有效报告</section>}
      </main>
    </div>
  );
}
