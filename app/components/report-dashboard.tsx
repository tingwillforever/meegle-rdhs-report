"use client";

import {
  ArrowLeft,
  BarChart3,
  BookOpenCheck,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Database,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

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
import { BgWarReport } from "./bg-war-report";

type ReportDashboardProps = {
  initialSnapshots: RdhsSnapshot[];
  dataMode: "live" | "preview";
  initialPeriodKey?: string;
  initialView?: "bg" | "workbench";
  initialLine?: string;
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

function replacePeriodInUrl(periodKey: string, viewMode?: "bg" | "workbench") {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  url.searchParams.set("period", periodKey);
  if (viewMode) url.searchParams.set("view", viewMode);
  window.history.replaceState(null, "", url);
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

function formatComponentScore(value: number | null) {
  return value === null ? "—" : value.toFixed(1);
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

function trendForLine(snapshots: RdhsSnapshot[], line: string, throughPeriod: string): TrendPoint[] {
  return buildMonthlyTrend(
    snapshots,
    line === "CBG整体"
      ? { throughPeriod }
      : { businessLine: line, throughPeriod },
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

function ExpandedSummary({
  snapshot,
  summary,
  mode,
  complianceDelta,
  pendingDelta,
  refreshMessage,
  refreshState,
}: {
  snapshot: RdhsSnapshot;
  summary: SnapshotSummary;
  mode: GovernanceBand;
  complianceDelta: DeltaView;
  pendingDelta: DeltaView;
  refreshMessage: string;
  refreshState: "idle" | "loading" | "success" | "error";
}) {
  const focusLines = snapshot.businessLines
    .map((line) => {
      const lineSummary = summaryForProducts(
        snapshot,
        snapshot.products.filter((product) => product.businessLine === line.businessLine),
      );
      return { line, lineSummary };
    })
    .filter(({ line }) => line.keyGovernanceCount > 0)
    .sort((left, right) => {
      const keyGovernanceDifference = right.line.keyGovernanceCount - left.line.keyGovernanceCount;
      if (keyGovernanceDifference !== 0) return keyGovernanceDifference;

      const leftRate = left.line.keyGovernanceCount / left.line.productTotal;
      const rightRate = right.line.keyGovernanceCount / right.line.productTotal;
      if (leftRate !== rightRate) return rightRate - leftRate;

      const leftScore = left.lineSummary.averageRdhs ?? -1;
      const rightScore = right.lineSummary.averageRdhs ?? -1;
      return leftScore - rightScore;
    })
    .slice(0, 3);

  return (
    <section className="panel summaryPrototype" aria-label="本月总体判断和核心指标">
      <div className="summaryPrototypeOverview">
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
      </div>

      <div className="summaryPrototypeDetail">
        <div className="summaryFocus">
          <div className="summaryPrototypeHead">
            <div>
              <h2 className="panelTitle">重点关注业务线</h2>
              <div className="panelSubtitle">按重点治理产品数与风险占比排序</div>
            </div>
            <span className="panelMeta">按治理优先级排序</span>
          </div>
          <div className="summaryFocusList">
            {focusLines.map(({ line, lineSummary }, index) => {
              const priority = index < 2 ? "P0" : "P1";
              const lowestComponent = COMPONENT_LABELS
                .map(([key, label, maximum]) => ({ key, label, maximum, value: lineSummary.componentAverages[key] }))
                .filter((component) => component.value !== null)
                .sort((left, right) => (left.value! / left.maximum) - (right.value! / right.maximum))
                .at(0);

              return (
                <div className="summaryFocusRow" key={line.businessLine}>
                  <span className={`summaryFocusPriority ${priority.toLowerCase()}`}>{priority}</span>
                  <div className="summaryFocusName">
                    <b>{line.businessLine}</b>
                    <span>重点治理 {line.keyGovernanceCount} / {line.productTotal} · 未度量 {lineSummary.unmeasuredProductCount || "—"}</span>
                  </div>
                  <div className="summaryFocusScore">
                    <b>{formatScore(lineSummary.averageRdhs)} / 100</b>
                    <span>{lowestComponent ? `${lowestComponent.label} ${formatComponentScore(lowestComponent.value)} / ${lowestComponent.maximum}` : "暂无可用分项"}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="summaryComponentScores">
          <div className="summaryPrototypeHead">
            <div>
              <h2 className="panelTitle">RDHS 分项得分</h2>
              <div className="panelSubtitle">CBG 已度量产品平均得分</div>
            </div>
            <span className="panelMeta">当前分 / 满分</span>
          </div>
          <div className="summaryComponentList">
            {COMPONENT_LABELS.map(([key, label, maximum]) => {
              const value = summary.componentAverages[key];
              return (
                <div className="summaryComponentRow" key={key}>
                  <span>{label}</span>
                  <div className="summaryComponentTrack" aria-hidden="true">
                    <i style={{ width: `${value === null ? 0 : Math.min(100, (value / maximum) * 100)}%` }} />
                  </div>
                  <strong>
                    {value === null ? "—" : <><b>{formatComponentScore(value)}</b><small> / {maximum}</small></>}
                  </strong>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="summaryPrototypeActions" aria-label="下月治理重点">
        <strong>下月治理重点</strong>
        <span><b>纳入飞书项目管理</b>未度量产品使用飞书项目进行需求、任务、缺陷和发布等产研过程管理。</span>
        <span><b>建立产品级过程关联</b>关注正确维护产品主数据，确保产研过程围绕产品进行。</span>
        <span><b>验证 P0 治理改善</b>聚焦短板问题，推动内部改进。</span>
      </div>
    </section>
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
      <div className="detailSection componentBreakdown">
        <div className="componentHeading">
          <h3>分项得分</h3>
          <span>当前分 / 满分</span>
        </div>
        <div className="componentList">
          {COMPONENT_LABELS.map(([key, label, maximum]) => {
            const value = product.components[key];
            return (
              <div className="componentRow" key={key}>
                <span className="componentLabel">{label}</span>
                <strong>
                  {value === null ? "—" : <><b>{formatComponentScore(value)}</b><small> / {maximum}</small></>}
                </strong>
                <span className="componentTrack" aria-hidden="true">
                  <i style={{ width: `${value === null ? 0 : Math.min(100, (value / maximum) * 100)}%` }} />
                </span>
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

export function ReportDashboard({
  initialSnapshots,
  dataMode,
  initialPeriodKey,
  initialView = "bg",
  initialLine,
}: ReportDashboardProps) {
  const [snapshots, setSnapshots] = useState(sortSnapshots(initialSnapshots));
  const [viewMode, setViewMode] = useState<"bg" | "workbench">(initialView);
  const monthNow = currentMonthKey();
  const initialPeriod =
    snapshots.find((snapshot) => snapshot.periodKey === initialPeriodKey)?.periodKey ??
    snapshots.find((snapshot) => snapshot.periodKey === monthNow)?.periodKey ??
    snapshots.at(-1)?.periodKey ??
    "";
  const [periodKey, setPeriodKey] = useState(initialPeriod);
  const [selectedLine, setSelectedLine] = useState(initialLine ?? "全部业务线");
  const [selectedTrendLine, setSelectedTrendLine] = useState(initialLine ?? "CBG整体");
  const [selectedBand, setSelectedBand] = useState<GovernanceBand | "全部分档">("全部分档");
  const [query, setQuery] = useState("");
  const [unmeasuredOnly, setUnmeasuredOnly] = useState(false);
  const [selectedProductKey, setSelectedProductKey] = useState<string | null>(null);
  const [productPage, setProductPage] = useState(1);
  const [refreshState, setRefreshState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [refreshMessage, setRefreshMessage] = useState("");
  const [runtimeDataMode, setRuntimeDataMode] = useState(dataMode);

  const available = sortSnapshots(snapshots);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const searchParams = new URLSearchParams(window.location.search);
    const urlView = searchParams.get("view");
    if (urlView === "workbench" || urlView === "bg") {
      setViewMode(urlView);
    }
    const urlPeriod = searchParams.get("period");
    if (urlPeriod && available.some((s) => s.periodKey === urlPeriod)) {
      setPeriodKey(urlPeriod);
    }
    const urlLine = searchParams.get("line");
    if (urlLine) {
      setSelectedLine(urlLine);
      setSelectedTrendLine(urlLine);
    }
  }, []);
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
  const trendPoints = snapshot
    ? trendForLine(available, selectedTrendLine, snapshot.periodKey)
    : [];

  const activeLineProducts = snapshot
    ? snapshot.products.filter((p) => selectedLine === "全部业务线" || p.businessLine === selectedLine)
    : [];
  const activeLineSummary =
    snapshot && selectedLine !== "全部业务线"
      ? summaryForProducts(snapshot, activeLineProducts)
      : null;
  const activeLineLowestComponent = activeLineSummary
    ? COMPONENT_LABELS
      .map(([key, label, maximum]) => ({
        key,
        label,
        maximum,
        value: activeLineSummary.componentAverages[key],
      }))
      .filter((component) => component.value !== null)
      .sort((left, right) => (left.value! / left.maximum) - (right.value! / right.maximum))
      .at(0)
    : null;

  const mode = summary ? modeForSummary(summary) : "重点治理";
  const isCurrentMonth = snapshot?.periodKey === monthNow;
  const snapshotStateText = isCurrentMonth
    ? runtimeDataMode === "preview"
      ? "当月预览数据"
      : "当月缓存已生成 · 可刷新"
    : runtimeDataMode === "preview"
      ? "历史快照已生成 · 内置预览"
      : "历史快照已生成 · 已固化";
  const refreshTitle = isCurrentMonth
    ? `刷新 ${monthNow} 当月缓存`
    : `刷新 ${monthNow} 当月缓存并切换至当月`;

  function resetDrilldown() {
    setSelectedLine("全部业务线");
    setSelectedTrendLine("CBG整体");
    setSelectedBand("全部分档");
    setQuery("");
    setUnmeasuredOnly(false);
    setSelectedProductKey(null);
    setProductPage(1);
  }

  function changeViewMode(nextView: "bg" | "workbench") {
    setViewMode(nextView);
    replacePeriodInUrl(periodKey, nextView);
    if (nextView === "bg") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  function returnToBg() {
    setViewMode("bg");
    replacePeriodInUrl(periodKey, "bg");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function handleDrilldown(line?: string) {
    if (line && line !== "全部业务线") {
      setSelectedLine(line);
      setSelectedTrendLine(line);
    } else {
      setSelectedLine("全部业务线");
      setSelectedTrendLine("CBG整体");
    }
    setSelectedBand("全部分档");
    setQuery("");
    setUnmeasuredOnly(false);
    setSelectedProductKey(null);
    setProductPage(1);

    setViewMode("workbench");
    replacePeriodInUrl(periodKey, "workbench");

    setTimeout(() => {
      const el = document.getElementById("product-workbench");
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    }, 60);
  }

  function changePeriod(nextPeriod: string) {
    setPeriodKey(nextPeriod);
    replacePeriodInUrl(nextPeriod, viewMode);
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
    const refreshPeriodKey = monthNow;

    setRefreshState("loading");
    setRefreshMessage("");
    try {
      // Resolve through the current app path so the dashboard also works
      // behind the production Ingress prefix (/meegle-rdhs-report/).
      const response = await fetch(appApiUrl("api/report/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json; charset=utf-8" },
        body: JSON.stringify({ periodKey: refreshPeriodKey }),
      });
      const payload = await response.json().catch(() => ({})) as { error?: string; message?: string };
      if (!response.ok) throw new Error(payload.error ?? "当月数据刷新失败");

      const reportResponse = await fetch(appApiUrl(`api/report?period=${refreshPeriodKey}`), { cache: "no-store" });
      if (!reportResponse.ok) throw new Error("当月缓存已更新，但无法读取最新快照");
      const report = await reportResponse.json() as { record: { snapshot: RdhsSnapshot } };
      setSnapshots((current) => sortSnapshots([
        ...current.filter((item) => item.periodKey !== report.record.snapshot.periodKey),
        report.record.snapshot,
      ]));
      setPeriodKey(refreshPeriodKey);
      replacePeriodInUrl(refreshPeriodKey);
      resetDrilldown();
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
        <div className="topbarInner">
          <div className="brand">
            <span className="brandSymbol" aria-hidden="true"><i /><i /><i /><i /></span>
            <span>CBG RDHS运营报告</span>
          </div>
          <div className="viewSwitcher" role="tablist" aria-label="视图模式切换">
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === "bg"}
              className={`viewTabBtn ${viewMode === "bg" ? "active" : ""}`}
              onClick={() => changeViewMode("bg")}
            >
              <BarChart3 size={14} />
              <span>BG 全局大盘</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === "workbench"}
              className={`viewTabBtn ${viewMode === "workbench" ? "active" : ""}`}
              onClick={() => changeViewMode("workbench")}
            >
              <Search size={14} />
              <span>业务明细工作台</span>
            </button>
          </div>
          <span className="contextLabel">研发过程效能 · 月报工作台{viewMode === "bg" ? " (大盘战报)" : " (明细工作区)"}</span>
          <span className="statusState srOnly">{snapshotStateText}</span>
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
          </div>
        </div>
      </header>

      <main className="pageInner">
        <div className="viewPaneBg" style={{ display: viewMode === "bg" ? "block" : "none" }}>
          <BgWarReport
            snapshot={snapshot}
            previousSnapshot={previousSnapshot}
            onDrilldown={handleDrilldown}
          />
        </div>

        <div className="viewPaneWorkbench" style={{ display: viewMode === "workbench" ? "block" : "none" }}>
          <section className="workstation" id="product-workbench" aria-label="产品治理工作台">
            {/* 1. Unified Sleek Context Header (一体化顶栏) */}
            <div className="workstationNavHeader">
              <div className="navLeft">
                <button type="button" className="backBtnPill" onClick={returnToBg}>
                  <ArrowLeft size={13} />
                  <span>返回 BG 全局大盘</span>
                </button>
                <span className="navDivider" />
                <span className="currentLineTitle">
                  {selectedLine === "全部业务线" ? "全在研产品治理工作台" : selectedLine}
                </span>
                {selectedLine !== "全部业务线" && activeLineSummary ? (
                  <>
                    <span className={`lineStatusChip ${bandClass(modeForSummary(activeLineSummary))}`}>
                      {modeForSummary(activeLineSummary)}
                    </span>
                    <div className="lineMetricsSummary">
                      <span>均分 <b>{activeLineSummary.averageRdhs !== null ? activeLineSummary.averageRdhs.toFixed(1) : "—"} 分</b></span>
                      <span>·</span>
                      <span>在研 <b>{filteredProducts.length} 款</b></span>
                      <span>·</span>
                      <span>重点治理 <b className="textRed">{activeLineSummary.pendingGovernanceCount} 款</b></span>
                      {activeLineLowestComponent ? (
                        <>
                          <span>·</span>
                          <span>短板: <b className="textRed">{activeLineLowestComponent.label} ({activeLineLowestComponent.value !== null ? formatComponentScore(activeLineLowestComponent.value) : "—"}/{activeLineLowestComponent.maximum})</b></span>
                        </>
                      ) : null}
                    </div>
                  </>
                ) : (
                  <div className="lineMetricsSummary">
                    <span>覆盖全 BG 共 <b>{snapshot.products.length} 款在研产品</b></span>
                  </div>
                )}
              </div>

              <div className="navRight">
                {selectedLine !== "全部业务线" ? (
                  <button
                    type="button"
                    className="clearLineBtn"
                    onClick={() => {
                      setSelectedLine("全部业务线");
                      setSelectedTrendLine("CBG整体");
                      setSelectedProductKey(null);
                      setProductPage(1);
                    }}
                  >
                    <X size={13} />
                    <span>重置业务线筛选</span>
                  </button>
                ) : null}
              </div>
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
                  className="filterSelect lineFilterSelect"
                  aria-label="按业务线筛选"
                  value={selectedLine}
                  onChange={(event) => {
                    const line = event.target.value;
                    setSelectedLine(line);
                    setSelectedTrendLine(line === "全部业务线" ? "CBG整体" : line);
                    setSelectedProductKey(null);
                    setProductPage(1);
                  }}
                >
                  <option value="全部业务线">全部业务线</option>
                  {businessLines.map((line) => (
                    <option key={line.businessLine} value={line.businessLine}>
                      {line.businessLine} ({line.productTotal}款)
                    </option>
                  ))}
                </select>
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

        <section className="auditBand" aria-label="数据质量审计" style={{ marginTop: 24 }}>
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
        </div>
      </main>
    </div>
  );
}
