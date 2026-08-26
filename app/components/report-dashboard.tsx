"use client";

import {
  BookOpenCheck,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Database,
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
} from "@/lib/rdhs/filter";
import type {
  ComponentScores,
  GovernanceBand,
  ProductDependencyMetric,
  ProductMetric,
  RdhsSnapshot,
  SnapshotSummary,
  TrendPoint,
} from "@/lib/rdhs/types";
import { ScoreRail } from "./score-rail";
import { TrendChart } from "./trend-chart";

type ReportDashboardProps = {
  initialSnapshots: RdhsSnapshot[];
  dataMode: "live" | "preview";
};

type DeltaView = {
  text: string;
  tone: "good" | "bad" | "neutral";
};

const BANDS: GovernanceBand[] = ["重点治理", "风险改进", "持续优化", "常规跟踪"];
const PRODUCT_PAGE_SIZE = 10;
const FEATURED_DEPENDENCY_METRICS = new Set(["需求发布闭环率", "需求积压占比"]);
const COMPONENT_LABELS: Array<[keyof ComponentScores, string, number]> = [
  ["linkClosure", "价值链路闭环", 25],
  ["deliveryClosure", "交付闭环", 15],
  ["timeliness", "时效节奏", 20],
  ["granularity", "颗粒度对齐", 20],
  ["quality", "质量表现", 20],
];

function currentMonthKey() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  return `${year}-${month}`;
}

function appApiUrl(path: string) {
  if (typeof window === "undefined") return path;
  const basePath = window.location.pathname.endsWith("/")
    ? window.location.pathname
    : `${window.location.pathname}/`;
  return `${basePath}${path}`;
}

function sortSnapshots(snapshots: RdhsSnapshot[]) {
  return snapshots
    .filter((snapshot) => snapshot.cadence === "monthly")
    .sort((left, right) => left.periodKey.localeCompare(right.periodKey));
}

function formatFetchedAt(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
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

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatDelta(label: string, current: number, previous: number | null, favorableDirection: "up" | "down"): DeltaView {
  if (previous === null) return { text: `${label}暂无上月对比`, tone: "neutral" };
  const delta = (current - previous) * 100;
  if (Math.abs(delta) < 0.05) return { text: `${label}环比持平`, tone: "neutral" };
  const isGood = favorableDirection === "up" ? delta > 0 : delta < 0;
  const sign = delta > 0 ? "+" : "-";
  return {
    text: `${label}环比 ${sign}${Math.abs(delta).toFixed(1)}pp`,
    tone: isGood ? "good" : "bad",
  };
}

function bandClass(band: GovernanceBand) {
  if (band === "重点治理") return "critical";
  if (band === "风险改进") return "risk";
  if (band === "持续优化") return "optimize";
  return "track";
}

function modeForSummary(summary: SnapshotSummary): GovernanceBand {
  if (summary.bandCounts.keyGovernance > 0) return "重点治理";
  if (summary.bandCounts.riskImprovement > 0) return "风险改进";
  if (summary.bandCounts.continuousOptimization > 0) return "持续优化";
  return "常规跟踪";
}

function scopeExclusionNote(snapshot: RdhsSnapshot) {
  const parts = [
    snapshot.audit.excludedTestBusinessLineCount > 0
      ? `测试业务线 ${snapshot.audit.excludedTestBusinessLineCount} 个`
      : "",
    snapshot.audit.excludedProductAttributeCount > 0
      ? `交付定制 ${snapshot.audit.excludedProductAttributeCount} 个`
      : "",
  ].filter(Boolean);
  return parts.length > 0 ? `已排除${parts.join("、")}` : "未排除额外主数据";
}

function productKey(product: Pick<ProductMetric, "businessLine" | "product">) {
  return `${product.businessLine}\u0000${product.product}`;
}

function linePath(product: Pick<ProductMetric, "businessLine"> & Partial<Pick<ProductMetric, "subLine">>) {
  return product.subLine ? `${product.businessLine} / ${product.subLine}` : product.businessLine;
}

function formatDependencyValue(metric: ProductDependencyMetric) {
  if (metric.value === null) return "—";
  if (metric.unit === "%") return (metric.value * 100).toFixed(1);
  if (metric.unit === "人" && Number.isInteger(metric.value)) return String(metric.value);
  return metric.value.toFixed(1);
}

function participantMetric(product: ProductMetric) {
  return product.dependencyMetrics.find((metric) => metric.label === "有效参与人数") ?? null;
}

function paginationItems(currentPage: number, pageCount: number): Array<number | "gap"> {
  if (pageCount <= 7) {
    return Array.from({ length: pageCount }, (_, index) => index + 1);
  }

  const pages = new Set([1, pageCount, currentPage - 1, currentPage, currentPage + 1]);
  const sorted = [...pages]
    .filter((page) => page >= 1 && page <= pageCount)
    .sort((left, right) => left - right);

  const items: Array<number | "gap"> = [];
  for (const page of sorted) {
    const previous = items.at(-1);
    if (typeof previous === "number" && page - previous === 2) {
      items.push(previous + 1);
    } else if (typeof previous === "number" && page - previous > 2) {
      items.push("gap");
    }
    items.push(page);
  }
  return items;
}

function summaryForProducts(snapshot: RdhsSnapshot, products: ProductMetric[]) {
  return summarizeSnapshot({ ...snapshot, products });
}

function trendForLine(snapshots: RdhsSnapshot[], line: string): TrendPoint[] {
  return buildMonthlyTrend(
    snapshots,
    line === "CBG整体" ? {} : { businessLine: line },
  );
}

function DependencyCard({
  metric,
  prominent = false,
}: {
  metric: ProductDependencyMetric;
  prominent?: boolean;
}) {
  return (
    <div className={`dependencyCard ${prominent ? "prominent" : ""} ${metric.tone}`}>
      <dt>{metric.label}</dt>
      <dd>
        {formatDependencyValue(metric)}
        {metric.value !== null && metric.unit ? <small>{metric.unit}</small> : null}
      </dd>
    </div>
  );
}

function DependencyMetrics({ metrics }: { metrics: ProductDependencyMetric[] }) {
  if (metrics.length === 0) {
    return <p className="dependencyEmpty">暂无可展示的过程依赖指标，待下次快照补齐。</p>;
  }
  const regularMetrics = metrics.filter(
    (metric) => metric.label !== "有效参与人数" && !FEATURED_DEPENDENCY_METRICS.has(metric.label),
  );
  const featuredMetrics = metrics.filter((metric) => FEATURED_DEPENDENCY_METRICS.has(metric.label));
  return (
    <>
      <dl className="dependentMetrics">
        {regularMetrics.map((metric) => <DependencyCard metric={metric} key={metric.label} />)}
      </dl>
      {featuredMetrics.length > 0 ? (
        <dl className="dependencyFocus">
          {featuredMetrics.map((metric) => <DependencyCard metric={metric} prominent key={metric.label} />)}
        </dl>
      ) : null}
      <p className="dependencyRule"><b>判色规则</b> 红色=重点治理阈值或无有效数据；黄色=风险观察；绿色=常规跟踪达标；灰色=中性参考。</p>
    </>
  );
}

function MetricCard({
  label,
  value,
  suffix,
  note,
  delta,
}: {
  label: string;
  value: string;
  suffix?: string;
  note: string;
  delta?: DeltaView;
}) {
  return (
    <div className="metric">
      <span className="metricLabel">{label}</span>
      <strong className="metricValue">
        {value}
        {suffix ? <small>{suffix}</small> : null}
      </strong>
      <span className="metricNote">{note}</span>
      {delta ? <span className={`metricDelta ${delta.tone}`}>{delta.text}</span> : null}
    </div>
  );
}

function Distribution({ summary }: { summary: SnapshotSummary }) {
  const rows: Array<[GovernanceBand, string, number]> = [
    ["重点治理", "<45 / 未度量", summary.bandCounts.keyGovernance],
    ["风险改进", "45-<60", summary.bandCounts.riskImprovement],
    ["持续优化", "60-<70", summary.bandCounts.continuousOptimization],
    ["常规跟踪", ">=70", summary.bandCounts.regularTracking],
  ];
  return (
    <section className="panel distributionPanel" aria-label="治理分档分布">
      <div className="panelHead">
        <div>
          <h2 className="panelTitle">治理分档分布</h2>
          <div className="panelSubtitle">未度量 / 待关联产品纳入重点治理</div>
        </div>
        <span className="mono panelMeta">{summary.productTotal} 个产品</span>
      </div>
      <div className="distributionBody">
        {rows.map(([band, range, count]) => (
          <div className="distributionRow" key={band}>
            <span>{band} <small>{range}</small></span>
            <div className="bar" aria-hidden="true">
              <i
                className={bandClass(band)}
                style={{ width: `${summary.productTotal === 0 ? 0 : (count / summary.productTotal) * 100}%` }}
              />
            </div>
            <b>{count}</b>
          </div>
        ))}
      </div>
    </section>
  );
}

function ProductDetail({
  product,
  periodKey,
  onClose,
  mobile = false,
}: {
  product: ProductMetric;
  periodKey: string;
  onClose?: () => void;
  mobile?: boolean;
}) {
  return (
    <div className={mobile ? "detailContent mobile" : "detailContent"}>
      <div className="detailTop">
        <div>
          <div className="detailKicker">{linePath(product)}</div>
          <h3 className="detailTitle">{product.product}</h3>
          <div className="detailMeta">{periodKey} 月报 · {product.rdhs === null ? "等待数据关联" : "已完成度量"}</div>
        </div>
        {onClose ? (
          <button className="iconButton quiet" type="button" title="关闭产品详情" aria-label="关闭产品详情" onClick={onClose}>
            <X size={15} strokeWidth={1.8} />
          </button>
        ) : null}
      </div>
      <div className="detailScore">
        <div>
          <div className="detailScoreNum">{product.rdhs === null ? "—" : product.rdhs.toFixed(1)}</div>
          <div className="detailScoreLabel">{product.rdhs === null ? "RDHS 未度量" : "RDHS 分数"}</div>
        </div>
        <span className={`badge ${bandClass(product.governanceBand)}`}>{product.governanceBand}</span>
        {product.priority ? <span className="priority">{product.priority}</span> : null}
      </div>
      <div className="detailSection">
        <h3>过程依赖指标</h3>
        <DependencyMetrics metrics={product.dependencyMetrics} />
      </div>
      <div className="detailSection">
        <h3>最低过程项</h3>
        <p>{product.lowestComponent}</p>
      </div>
      <div className="detailSection">
        <h3>分项得分</h3>
        <div className="componentList">
          {COMPONENT_LABELS.map(([key, label, maximum]) => {
            const value = product.components[key];
            return (
              <div className="componentRow" key={key}>
                <span>{label}</span>
                <span className="componentTrack"><i style={{ width: `${value === null ? 0 : Math.min(100, (value / maximum) * 100)}%` }} /></span>
                <strong>{value === null ? "—" : value.toFixed(1)}</strong>
              </div>
            );
          })}
        </div>
      </div>
      <div className="detailSection">
        <h3>主要问题</h3>
        <p>{product.problem}</p>
      </div>
      <div className="detailSection">
        <h3>建议治理动作</h3>
        <div className="actionBox"><p>{product.action}</p></div>
      </div>
    </div>
  );
}

export function ReportDashboard({ initialSnapshots, dataMode }: ReportDashboardProps) {
  const [snapshots, setSnapshots] = useState(sortSnapshots(initialSnapshots));
  const monthNow = currentMonthKey();
  const initialPeriod =
    snapshots.find((snapshot) => snapshot.periodKey === monthNow)?.periodKey ??
    snapshots.at(-1)?.periodKey ??
    "";
  const [periodKey, setPeriodKey] = useState(initialPeriod);
  const [selectedLine, setSelectedLine] = useState("全部业务线");
  const [selectedTrendLine, setSelectedTrendLine] = useState("CBG整体");
  const [selectedBand, setSelectedBand] = useState<GovernanceBand | "全部分档">("全部分档");
  const [query, setQuery] = useState("");
  const [unmeasuredOnly, setUnmeasuredOnly] = useState(false);
  const [selectedProductKey, setSelectedProductKey] = useState<string | null>(null);
  const [productPage, setProductPage] = useState(1);
  const [refreshState, setRefreshState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [refreshMessage, setRefreshMessage] = useState("");
  const [runtimeDataMode, setRuntimeDataMode] = useState(dataMode);

  const available = sortSnapshots(snapshots);
  const snapshot =
    available.find((candidate) => candidate.periodKey === periodKey) ?? available.at(-1) ?? null;
  const summary = snapshot ? summarizeSnapshot(snapshot) : null;
  const previousSnapshot = snapshot
    ? [...available].reverse().find((candidate) => candidate.periodKey < snapshot.periodKey) ?? null
    : null;
  const previousSummary = previousSnapshot ? summarizeSnapshot(previousSnapshot) : null;
  const businessLines = snapshot ? sortBusinessLines(snapshot.businessLines) : [];
  const filteredProducts = snapshot
    ? sortProducts(
      filterProducts(snapshot.products, {
        businessLine: selectedLine,
        band: selectedBand,
        query,
        unmeasuredOnly,
      }),
      "rdhs-asc",
    )
    : [];
  const selectedProduct = snapshot?.products.find(
    (product) => productKey(product) === selectedProductKey,
  ) ?? null;
  const selectedProductIsVisible = selectedProduct
    ? filteredProducts.some((product) => productKey(product) === selectedProductKey)
    : false;
  const activeDetail = selectedProductIsVisible ? selectedProduct : null;
  const pageCount = Math.max(1, Math.ceil(filteredProducts.length / PRODUCT_PAGE_SIZE));
  const currentProductPage = Math.min(productPage, pageCount);
  const pageStartIndex = (currentProductPage - 1) * PRODUCT_PAGE_SIZE;
  const paginatedProducts = filteredProducts.slice(pageStartIndex, pageStartIndex + PRODUCT_PAGE_SIZE);
  const visibleStart = filteredProducts.length === 0 ? 0 : pageStartIndex + 1;
  const visibleEnd = Math.min(pageStartIndex + PRODUCT_PAGE_SIZE, filteredProducts.length);
  const pageItems = paginationItems(currentProductPage, pageCount);
  const trendPoints = snapshot ? trendForLine(available, selectedTrendLine) : [];
  const mode = summary ? modeForSummary(summary) : "重点治理";
  const isCurrentMonth = snapshot?.periodKey === monthNow;
  const dataStateText =
    runtimeDataMode === "preview"
      ? "内置预览快照"
      : isCurrentMonth
        ? "当月缓存"
        : "历史快照";

  function resetDrilldown() {
    setSelectedLine("全部业务线");
    setSelectedTrendLine("CBG整体");
    setSelectedBand("全部分档");
    setQuery("");
    setUnmeasuredOnly(false);
    setSelectedProductKey(null);
    setProductPage(1);
  }

  function changePeriod(nextPeriod: string) {
    setPeriodKey(nextPeriod);
    setRefreshState("idle");
    setRefreshMessage("");
    resetDrilldown();
  }

  function chooseBusinessLine(line: string) {
    setSelectedLine(line);
    setSelectedTrendLine(line);
    setSelectedProductKey(null);
    setProductPage(1);
    document.getElementById("product-workbench")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function clearFilters() {
    resetDrilldown();
  }

  function changeProductPage(nextPage: number) {
    setProductPage(Math.min(Math.max(nextPage, 1), pageCount));
    setSelectedProductKey(null);
  }

  async function refreshCurrentMonth() {
    if (!snapshot) return;
    if (!isCurrentMonth) {
      setRefreshState("error");
      setRefreshMessage("历史月份使用快照，不支持实时刷新");
      return;
    }

    setRefreshState("loading");
    setRefreshMessage("");
    try {
      // Resolve through the current app path so the dashboard also works
      // behind the production Ingress prefix (/meegle-rdhs-report/).
      const response = await fetch(appApiUrl("api/report/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json; charset=utf-8" },
        body: JSON.stringify({ periodKey: snapshot.periodKey }),
      });
      const payload = await response.json().catch(() => ({})) as { error?: string; message?: string };
      if (!response.ok) throw new Error(payload.error ?? "当月数据刷新失败");

      const reportResponse = await fetch(appApiUrl(`api/report?period=${snapshot.periodKey}`), { cache: "no-store" });
      if (reportResponse.ok) {
        const report = await reportResponse.json() as { record: { snapshot: RdhsSnapshot } };
        setSnapshots((current) => sortSnapshots([
          ...current.filter((item) => item.periodKey !== report.record.snapshot.periodKey),
          report.record.snapshot,
        ]));
      }
      setRuntimeDataMode("live");
      setRefreshState("success");
      setRefreshMessage(payload.message ?? "已更新当月缓存");
    } catch (error) {
      setRefreshState("error");
      setRefreshMessage(error instanceof Error ? error.message : "当月数据刷新失败");
    }
  }

  if (!snapshot || !summary) {
    return (
      <div className="dashboardShell">
        <main className="pageInner">
          <section className="panel emptyState">该月份暂无有效报告</section>
        </main>
      </div>
    );
  }

  const complianceDelta = formatDelta(
    "规范",
    summary.complianceRate,
    previousSummary?.complianceRate ?? null,
    "up",
  );
  const pendingDelta = formatDelta(
    "待治理",
    summary.pendingGovernanceRate,
    previousSummary?.pendingGovernanceRate ?? null,
    "down",
  );
  const trendLabel = selectedTrendLine === "CBG整体" ? "CBG" : selectedTrendLine;

  return (
    <div className="dashboardShell">
      <header className="topbar">
        <div className="brand">
          <span className="brandSymbol" aria-hidden="true"><i /><i /><i /><i /></span>
          <span>CBG RDHS运营报告</span>
        </div>
        <span className="contextLabel">研发过程效能 · 月报工作台</span>
        <div className="barControls">
          <label className="selectWrap">
            <span className="srOnly">选择月报月份</span>
            <select
              aria-label="选择月报月份"
              value={snapshot.periodKey}
              onChange={(event) => changePeriod(event.target.value)}
              disabled={available.length === 0}
            >
              {available.length === 0 ? <option value="">暂无数据</option> : null}
              {[...available].reverse().map((item) => (
                <option key={item.periodKey} value={item.periodKey}>{item.periodKey}</option>
              ))}
            </select>
          </label>
          <button
            className="iconButton"
            type="button"
            title="更新数据"
            aria-label="更新数据"
            onClick={refreshCurrentMonth}
            disabled={refreshState === "loading"}
          >
            <RefreshCw className={refreshState === "loading" ? "spin" : ""} size={17} strokeWidth={1.8} />
          </button>
        </div>
      </header>

      <main className="pageInner">
        <section className="reportHead">
          <div>
            <div className="eyebrow">{snapshot.periodKey} / CBG</div>
            <h1>CBG RDHS运营报告</h1>
          </div>
          <div className="status">
            <b aria-hidden="true" />
            数据校验通过 · <span className="mono">{formatFetchedAt(snapshot.fetchedAt)}</span> 同步 · {dataStateText}
          </div>
        </section>

        <section className="panel summary" aria-label="本月总体判断和核心指标">
          <div className="judgement">
            <div className="judgementTop">
              <span className="label">总体判断</span>
              <span className={`badge ${bandClass(mode)}`}>{mode}阶段</span>
            </div>
            <p>
              本期 CBG 共覆盖 <b className="mono">{summary.productTotal}</b> 个研发中产品，整体仍处于{mode}阶段。
              {snapshot.overview.focus}
            </p>
            {refreshMessage ? <span className={`refreshMessage ${refreshState}`}>{refreshMessage}</span> : null}
          </div>
          <MetricCard label="研发中产品" value={String(summary.productTotal)} suffix=" 个" note={scopeExclusionNote(snapshot)} />
          <MetricCard label="平均 RDHS" value={summary.averageRdhs?.toFixed(1) ?? "—"} suffix=" 分" note={`仅统计 ${summary.measuredProductCount} 个已度量产品`} />
          <MetricCard label="度量覆盖率" value={(summary.measurementCoverage * 100).toFixed(1)} suffix="%" note={`未度量 / 待关联 ${summary.unmeasuredProductCount} 个`} />
          <MetricCard label="产品规范率" value={(summary.complianceRate * 100).toFixed(1)} suffix="%" note={`${summary.complianceCount} 个产品符合规范`} delta={complianceDelta} />
          <MetricCard label="待治理占比" value={(summary.pendingGovernanceRate * 100).toFixed(1)} suffix="%" note={`${summary.pendingGovernanceCount} 个产品需治理`} delta={pendingDelta} />
        </section>

        <div className="insights">
          <ScoreRail value={summary.averageRdhs} />
          <Distribution summary={summary} />
        </div>

        <section className="panel trendPanel" aria-label="月度 RDHS 趋势">
          <div className="panelHead">
            <div>
              <h2 className="panelTitle">{trendLabel} 平均 RDHS 与规范占比趋势</h2>
              <div className="panelSubtitle">
                {selectedTrendLine === "CBG整体"
                  ? "默认展示 CBG 平均 RDHS 和 CBG 产品规范占比"
                  : "仅展示业务线平均 RDHS 和业务线规范占比"}
              </div>
            </div>
            <label className="selectWrap">
              <span className="srOnly">选择趋势业务线</span>
              <select
                className="trendSelect"
                aria-label="选择趋势业务线"
                value={selectedTrendLine}
                onChange={(event) => {
                  const nextLine = event.target.value;
                  setSelectedTrendLine(nextLine);
                }}
              >
                <option value="CBG整体">CBG整体</option>
                {businessLines.map((line) => (
                  <option key={line.businessLine} value={line.businessLine}>{line.businessLine}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="trendBody">
            <div className="trendMeta">
              <span>平均 RDHS、规范占比与 45 / 60 / 70 治理阈值</span>
              <b>
                {snapshot.periodKey} · RDHS {trendPoints.at(-1)?.averageRdhs?.toFixed(1) ?? "—"} · 规范 {formatPercent(trendPoints.at(-1)?.complianceRate ?? 0)}
              </b>
            </div>
            <TrendChart
              points={trendPoints}
              ariaLabel={`${trendLabel}平均RDHS与规范占比趋势`}
            />
            <div className="sourceNote">平均 RDHS 仅统计已度量产品；规范占比按常规跟踪产品 / 研发中产品计算；悬停趋势点查看每月指标值；历史月份读取月初固化快照，当月读取缓存。</div>
          </div>
        </section>

        <section className="panel overview" aria-label="业务线总览">
          <div className="panelHead">
            <div>
              <h2 className="panelTitle">业务线总览</h2>
              <div className="panelSubtitle">按一级业务线汇总 · 点击行联动趋势与产品治理工作区</div>
            </div>
            <span className="mono panelMeta">{businessLines.length} 条业务线</span>
          </div>
          <div className="tableWrap">
            <table className="overviewTable">
              <thead>
                <tr>
                  <th>一级业务线</th>
                  <th>产品</th>
                  <th>重点治理</th>
                  <th>风险改进</th>
                  <th>持续优化</th>
                  <th>常规跟踪</th>
                  <th>未度量 / 待关联</th>
                  <th>规范占比</th>
                </tr>
              </thead>
              <tbody>
                {businessLines.map((line) => {
                  const lineProducts = snapshot.products.filter((product) => product.businessLine === line.businessLine);
                  const lineSummary = summaryForProducts(snapshot, lineProducts);
                  return (
                    <tr
                      className={selectedLine === line.businessLine ? "selected" : ""}
                      key={line.businessLine}
                      tabIndex={0}
                      onClick={() => chooseBusinessLine(line.businessLine)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") chooseBusinessLine(line.businessLine);
                      }}
                    >
                      <td>{line.businessLine}</td>
                      <td className="nMuted">{line.productTotal}</td>
                      <td className="nCritical">{line.keyGovernanceCount}</td>
                      <td className="nRisk">{line.riskImprovementCount}</td>
                      <td className="nOptimize">{line.continuousOptimizationCount}</td>
                      <td className="nTrack">{line.regularTrackingCount}</td>
                      <td className={lineSummary.unmeasuredProductCount > 0 ? "nCritical" : "nMuted"}>{lineSummary.unmeasuredProductCount || "—"}</td>
                      <td className="normRate">{formatPercent(lineSummary.complianceRate)}</td>
                    </tr>
                  );
                })}
                <tr className="totalRow">
                  <td>CBG（合计）</td>
                  <td>{summary.productTotal}</td>
                  <td>{summary.bandCounts.keyGovernance}</td>
                  <td>{summary.bandCounts.riskImprovement}</td>
                  <td>{summary.bandCounts.continuousOptimization}</td>
                  <td>{summary.bandCounts.regularTracking}</td>
                  <td>{summary.unmeasuredProductCount || "—"}</td>
                  <td>{formatPercent(summary.complianceRate)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel workbench" id="product-workbench" aria-label="产品治理工作区">
          <div className="panelHead workbenchHead">
            <div className="workbenchCopy">
              <div>
                <h2 className="panelTitle">
                  {selectedLine === "全部业务线" ? "产品治理工作区" : `${selectedLine} · 产品治理工作区`}
                </h2>
                <div className="panelSubtitle">
                  {selectedLine === "全部业务线" ? "产品列表与治理详情保持同屏核查" : "已按业务线筛选，趋势与产品列表保持一致"}
                </div>
              </div>
              <span className="workbenchCount">
                第 {currentProductPage}/{pageCount} 页 · {filteredProducts.length} / {snapshot.products.length} 个产品
              </span>
            </div>
            <button className="iconButton quiet" type="button" title="清除筛选" aria-label="清除筛选" onClick={clearFilters}>
              <X size={16} strokeWidth={1.8} />
            </button>
          </div>

          <div className="workspace">
            <div className="productBrowser">
              <div className="filters">
                <label className="search">
                  <Search size={16} strokeWidth={1.8} aria-hidden="true" />
                  <span className="srOnly">搜索产品、一级业务线或二级业务线</span>
                  <input
                    type="search"
                    value={query}
                    onChange={(event) => {
                      setQuery(event.target.value);
                      setSelectedProductKey(null);
                      setProductPage(1);
                    }}
                    placeholder="搜索产品 / 一级 / 二级业务线"
                  />
                </label>
                <select
                  className="filterSelect"
                  aria-label="按治理分档筛选"
                  value={selectedBand}
                  onChange={(event) => {
                    setSelectedBand(event.target.value as GovernanceBand | "全部分档");
                    setSelectedProductKey(null);
                    setProductPage(1);
                  }}
                >
                  <option value="全部分档">全部治理分档</option>
                  {BANDS.map((band) => <option key={band} value={band}>{band}</option>)}
                </select>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={unmeasuredOnly}
                    onChange={(event) => {
                      setUnmeasuredOnly(event.target.checked);
                      setSelectedProductKey(null);
                      setProductPage(1);
                    }}
                  />
                  <span>仅未度量</span>
                </label>
              </div>

              <div className="listStatus" aria-live="polite">
                <span>当前展示 <b className="mono">{visibleStart}-{visibleEnd}</b> / {filteredProducts.length} 个</span>
                <span>每页 {PRODUCT_PAGE_SIZE} 个</span>
              </div>

              <div className="productList">
                {paginatedProducts.map((product) => {
                  const key = productKey(product);
                  const isSelected = key === selectedProductKey;
                  const participants = participantMetric(product);
                  return (
                    <div key={key}>
                      <button
                        type="button"
                        className={`productRow ${isSelected ? "selected" : ""}`}
                        onClick={() => setSelectedProductKey(key)}
                      >
                        <span>
                          <span className="productName">{product.product}</span>
                          <span className="productLine">{linePath(product)}</span>
                        </span>
                        <span className="productStats">
                          <span className={`score ${product.rdhs === null ? "unmeasured" : bandClass(product.governanceBand)}`}>
                            {formatScore(product.rdhs)}
                          </span>
                          <span className={`participantCount ${participants?.tone ?? "neutral"}`}>
                            有效参与人数 {participants ? formatDependencyValue(participants) : "—"}
                            {participants?.value !== null && participants?.unit ? <small>{participants.unit}</small> : null}
                          </span>
                        </span>
                        <span className="productBottom">
                          <span className="process">{product.lowestComponent}</span>
                          <span className={`badge ${bandClass(product.governanceBand)}`}>{product.governanceBand}</span>
                        </span>
                      </button>
                      {isSelected ? <ProductDetail product={product} periodKey={snapshot.periodKey} mobile /> : null}
                    </div>
                  );
                })}
                {filteredProducts.length === 0 ? <div className="emptyList">没有匹配的产品</div> : null}
              </div>

              {filteredProducts.length > PRODUCT_PAGE_SIZE ? (
                <nav className="pagination" aria-label="产品列表分页">
                  <button
                    className="pageNav"
                    type="button"
                    title="上一页"
                    aria-label="上一页"
                    onClick={() => changeProductPage(currentProductPage - 1)}
                    disabled={currentProductPage === 1}
                  >
                    <ChevronLeft size={15} strokeWidth={1.8} />
                  </button>
                  <div className="pageNumbers">
                    {pageItems.map((item, index) => (
                      item === "gap" ? (
                        <span className="pageGap" key={`gap-${index}`}>...</span>
                      ) : (
                        <button
                          className={`pageNumber ${item === currentProductPage ? "active" : ""}`}
                          type="button"
                          key={item}
                          aria-label={`第 ${item} 页`}
                          aria-current={item === currentProductPage ? "page" : undefined}
                          onClick={() => changeProductPage(item)}
                        >
                          {item}
                        </button>
                      )
                    ))}
                  </div>
                  <button
                    className="pageNav"
                    type="button"
                    title="下一页"
                    aria-label="下一页"
                    onClick={() => changeProductPage(currentProductPage + 1)}
                    disabled={currentProductPage === pageCount}
                  >
                    <ChevronRight size={15} strokeWidth={1.8} />
                  </button>
                </nav>
              ) : null}
            </div>

            <aside className="detail">
              {activeDetail ? (
                <ProductDetail
                  product={activeDetail}
                  periodKey={snapshot.periodKey}
                  onClose={() => setSelectedProductKey(null)}
                />
              ) : (
                <div className="detailEmpty">
                  <BookOpenCheck size={30} strokeWidth={1.6} />
                  <strong>选择产品，查看治理动作</strong>
                  <span>最低过程项、主要问题和建议动作会在这里展开。</span>
                </div>
              )}
            </aside>
          </div>
        </section>

        <section className="auditBand" aria-label="数据质量审计">
          <div className="auditTitle">
            <Database size={16} strokeWidth={1.8} />
            <span>数据质量审计</span>
            <strong><CheckCircle2 size={14} strokeWidth={1.8} />已通过发布校验</strong>
          </div>
          <dl className="auditMetrics">
            <div><dt>原始行</dt><dd>{snapshot.audit.rawRowCount}</dd></div>
            <div><dt>有效度量</dt><dd>{snapshot.audit.acceptedRowCount}</dd></div>
            <div><dt>研发中产品</dt><dd>{snapshot.audit.researchProductCount}</dd></div>
            <div><dt>未度量/待关联</dt><dd>{snapshot.audit.unmeasuredProductCount}</dd></div>
            <div><dt>排除测试业务线</dt><dd>{snapshot.audit.excludedTestBusinessLineCount}</dd></div>
            <div><dt>排除交付定制</dt><dd>{snapshot.audit.excludedProductAttributeCount}</dd></div>
            <div><dt>源哈希</dt><dd title={snapshot.source.sha256}>{snapshot.source.sha256.slice(0, 10)}</dd></div>
          </dl>
        </section>
      </main>
    </div>
  );
}
