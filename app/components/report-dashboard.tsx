"use client";

import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Database,
  Layers,
  Search,
  Share2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  calculateBusinessLineRankings,
  calculateSublineDistribution,
  findPreviousSnapshot,
  getLineGovernanceCandidates,
  summarizeSnapshot,
} from "@/lib/rdhs/aggregate";
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
} from "@/lib/rdhs/types";
import { BgWarReport } from "./bg-war-report";

type ReportDashboardProps = {
  initialSnapshots: RdhsSnapshot[];
  dataMode: "live" | "preview";
  initialPeriodKey?: string;
  initialView?: "bg" | "workbench";
  initialLine?: string;
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

function syncUrl(
  params: {
    period?: string;
    view?: "bg" | "workbench";
    line?: string;
  },
  push = false,
) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (params.period) url.searchParams.set("period", params.period);
  if (params.view) url.searchParams.set("view", params.view);
  if (params.line !== undefined) {
    if (params.line === "全部业务线" || !params.line) {
      url.searchParams.delete("line");
    } else {
      url.searchParams.set("line", params.line);
    }
  }
  if (push) {
    window.history.pushState(null, "", url);
  } else {
    window.history.replaceState(null, "", url);
  }
}

function sortSnapshots(snapshots: RdhsSnapshot[]) {
  return snapshots
    .filter((snapshot) => snapshot.cadence === "monthly")
    .sort((left, right) => left.periodKey.localeCompare(right.periodKey));
}

function formatScore(value: number | null) {
  return value === null ? "未度量" : value.toFixed(1);
}

function formatComponentScore(value: number | null) {
  return value === null ? "—" : value.toFixed(1);
}

function bandClass(band: GovernanceBand) {
  if (band === "重点治理") return "critical";
  if (band === "风险改进") return "risk";
  if (band === "持续优化") return "optimize";
  return "track";
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

function DependencyCard({
  metric,
  prominent = false,
}: {
  metric: ProductDependencyMetric;
  prominent?: boolean;
}) {
  return (
    <div className={`dependencyCard ${prominent ? "prominent" : ""} ${metric.value === null ? "neutral" : metric.tone}`}>
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
          <div className="detailScoreLabel">{product.rdhs === null ? "RDHS 未度量 (考核计0)" : "RDHS 分数"}</div>
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
        <h3>快照问题提示（待核实）</h3>
        <p>{product.rdhs === null ? "本期无有效评分，需核实产品状态、图表范围与数据关联，不能直接认定过程未开展。" : product.problem}</p>
      </div>
      <div className="detailSection">
        <h3>快照治理建议（需业务确认）</h3>
        <div className="actionBox"><p>{product.rdhs === null ? "核实未度量原因并补齐真实记录；不得为提分虚假结项。" : product.action}</p></div>
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
  const snapshots = useMemo(() => sortSnapshots(initialSnapshots), [initialSnapshots]);
  const [viewMode, setViewMode] = useState<"bg" | "workbench">(initialView);
  const monthNow = currentMonthKey();
  const initialPeriod =
    snapshots.find((snapshot) => snapshot.periodKey === initialPeriodKey)?.periodKey ??
    snapshots.find((snapshot) => snapshot.periodKey === monthNow)?.periodKey ??
    snapshots.at(-1)?.periodKey ??
    "";
  const [periodKey, setPeriodKey] = useState(initialPeriod);
  const [selectedLine, setSelectedLine] = useState(initialLine ?? "全部业务线");
  const [selectedSubLine, setSelectedSubLine] = useState<string | null>(null);
  const [selectedBand, setSelectedBand] = useState<GovernanceBand | "全部分档">("全部分档");
  const [query, setQuery] = useState("");
  const [unmeasuredOnly, setUnmeasuredOnly] = useState(false);
  const [selectedProductKey, setSelectedProductKey] = useState<string | null>(null);
  const [productPage, setProductPage] = useState(1);
  const [runtimeDataMode] = useState(dataMode);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [missingPeriodNotice, setMissingPeriodNotice] = useState<string | null>(
    initialPeriodKey && !initialSnapshots.some((s) => s.periodKey === initialPeriodKey)
      ? initialPeriodKey
      : null,
  );

  const available = snapshots;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const applyUrlState = () => {
      const searchParams = new URLSearchParams(window.location.search);
      const urlView = searchParams.get("view");
      const urlPeriod = searchParams.get("period");
      const urlLine = searchParams.get("line")?.trim();
      const requestedSnapshot = available.find((s) => s.periodKey === urlPeriod);
      const fallbackPeriod = available.find((s) => s.periodKey === currentMonthKey())?.periodKey ?? available.at(-1)?.periodKey ?? "";
      setViewMode(urlView === "workbench" || (urlLine && urlView !== "bg") ? "workbench" : "bg");
      setPeriodKey(requestedSnapshot?.periodKey ?? fallbackPeriod);
      setMissingPeriodNotice(urlPeriod && !requestedSnapshot ? urlPeriod : null);
      setSelectedLine(urlLine || "全部业务线");
      setSelectedSubLine(null);
      setSelectedBand("全部分档");
      setQuery("");
      setUnmeasuredOnly(false);
      setSelectedProductKey(null);
      setProductPage(1);
    };

    applyUrlState();
    window.addEventListener("popstate", applyUrlState);
    return () => window.removeEventListener("popstate", applyUrlState);
  }, [available]);

  const snapshot =
    available.find((candidate) => candidate.periodKey === periodKey) ?? available.at(-1) ?? null;
  const summary = snapshot ? summarizeSnapshot(snapshot) : null;
  const previousSnapshot = snapshot
    ? findPreviousSnapshot(available, snapshot.periodKey)
    : null;
  const businessLines = snapshot ? sortBusinessLines(snapshot.businessLines) : [];
  const isLineValid =
    selectedLine === "全部业务线" ||
    (snapshot?.businessLines.some((b) => b.businessLine === selectedLine) ?? false);

  const baseFilteredProducts = snapshot
    ? sortProducts(
      filterProducts(snapshot.products, {
        businessLine: isLineValid ? selectedLine : "全部业务线",
        band: selectedBand,
        query,
        unmeasuredOnly,
      }),
      "rdhs-asc",
    )
    : [];

  const filteredProducts = selectedSubLine
    ? baseFilteredProducts.filter((p) => {
        const pSub = p.subLine && p.subLine.trim().length > 0 ? p.subLine.trim() : "未分二级业务线";
        return pSub === selectedSubLine;
      })
    : baseFilteredProducts;
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

  const lineRankings = snapshot
    ? calculateBusinessLineRankings(snapshot, previousSnapshot)
    : [];
  const currentLineRanking =
    lineRankings.find((r) => r.businessLine === selectedLine) ?? null;
  const prevLineProducts =
    previousSnapshot && selectedLine !== "全部业务线"
      ? previousSnapshot.products.filter((p) => p.businessLine === selectedLine)
      : [];
  const sublineDistribution =
    snapshot && selectedLine !== "全部业务线" && isLineValid
      ? calculateSublineDistribution(activeLineProducts)
      : [];
  const governanceCandidates =
    snapshot && selectedLine !== "全部业务线" && isLineValid
      ? getLineGovernanceCandidates(activeLineProducts, 3)
      : [];

  const isCurrentMonth = snapshot?.periodKey === monthNow;
  const snapshotStateText = isCurrentMonth
    ? runtimeDataMode === "preview"
      ? "当月预览数据"
      : "当月缓存已生成 · 可刷新"
    : runtimeDataMode === "preview"
      ? "历史快照已生成 · 内置预览"
      : "历史快照已生成 · 已固化";

  function resetDrilldown() {
    setSelectedLine("全部业务线");
    setSelectedSubLine(null);
    setSelectedBand("全部分档");
    setQuery("");
    setUnmeasuredOnly(false);
    setSelectedProductKey(null);
    setProductPage(1);
    syncUrl({ period: periodKey, view: viewMode, line: "全部业务线" }, false);
  }

  function changeViewMode(nextView: "bg" | "workbench") {
    setViewMode(nextView);
    syncUrl({ period: periodKey, view: nextView, line: selectedLine }, true);
    if (nextView === "bg") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  function returnToBg() {
    setViewMode("bg");
    syncUrl({ period: periodKey, view: "bg", line: selectedLine }, true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function handleDrilldown(line?: string) {
    const targetLine = line && line !== "全部业务线" ? line : "全部业务线";
    setSelectedLine(targetLine);
    setSelectedSubLine(null);
    setSelectedBand("全部分档");
    setQuery("");
    setUnmeasuredOnly(false);
    setSelectedProductKey(null);
    setProductPage(1);

    setViewMode("workbench");
    syncUrl({ period: periodKey, view: "workbench", line: targetLine }, true);

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
    setMissingPeriodNotice(null);
    setSelectedBand("全部分档");
    setQuery("");
    setUnmeasuredOnly(false);
    setSelectedSubLine(null);
    setSelectedProductKey(null);
    setProductPage(1);

    const nextSnapshot = available.find((s) => s.periodKey === nextPeriod);
    const lineStillExists = nextSnapshot?.businessLines.some((b) => b.businessLine === selectedLine);
    const nextLine = lineStillExists ? selectedLine : "全部业务线";
    if (!lineStillExists && selectedLine !== "全部业务线") {
      setSelectedLine("全部业务线");
    }
    syncUrl({ period: nextPeriod, view: viewMode, line: nextLine }, true);
  }

  function chooseBusinessLine(line: string) {
    setSelectedLine(line);
    setSelectedBand("全部分档");
    setQuery("");
    setUnmeasuredOnly(false);
    setSelectedSubLine(null);
    setSelectedProductKey(null);
    setProductPage(1);
    syncUrl({ period: periodKey, view: viewMode, line }, true);
    document.getElementById("product-workbench")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleShareUrl() {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    url.searchParams.set("period", periodKey);
    url.searchParams.set("view", "workbench");
    if (selectedLine !== "全部业务线") {
      url.searchParams.set("line", selectedLine);
    } else {
      url.searchParams.delete("line");
    }
    navigator.clipboard.writeText(url.toString()).then(() => {
      setCopiedUrl(true);
      setTimeout(() => setCopiedUrl(false), 2000);
    }).catch(() => {});
  }

  function locateProduct(prod: ProductMetric) {
    // Reset list filters so pagination and the target product use the same scope.
    setSelectedSubLine(null);
    setQuery("");
    setSelectedBand("全部分档");
    setUnmeasuredOnly(false);

    const key = productKey(prod);
    setSelectedProductKey(key);

    if (snapshot) {
      const targetList = sortProducts(
        filterProducts(snapshot.products, {
          businessLine: selectedLine,
          band: "全部分档",
          query: "",
          unmeasuredOnly: false,
        }),
        "rdhs-asc",
      );
      const targetIdx = targetList.findIndex((p) => productKey(p) === key);
      if (targetIdx >= 0) {
        setProductPage(Math.floor(targetIdx / PRODUCT_PAGE_SIZE) + 1);
      }
    }

    setTimeout(() => {
      document.getElementById("product-workbench")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
  }

  function changeProductPage(nextPage: number) {
    setProductPage(Math.min(Math.max(nextPage, 1), pageCount));
    setSelectedProductKey(null);
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
                {selectedLine === "全部业务线" ? (
                  <div className="lineMetricsSummary">
                    <span>覆盖全 BG 共 <b>{snapshot.products.length} 款在研产品</b></span>
                  </div>
                ) : null}
              </div>

              <div className="navRight">
                <button
                  type="button"
                  className={`shareUrlBtn ${copiedUrl ? "shareUrlSuccess" : ""}`}
                  onClick={handleShareUrl}
                  title="复制当前业务线工作台链接"
                >
                  {copiedUrl ? <CheckCircle2 size={13} /> : <Share2 size={13} />}
                  <span>{copiedUrl ? "链接已复制" : "分享工作台"}</span>
                </button>
                {selectedLine !== "全部业务线" ? (
                  <button
                    type="button"
                    className="clearLineBtn"
                    onClick={resetDrilldown}
                  >
                    <X size={13} />
                    <span>重置业务线筛选</span>
                  </button>
                ) : null}
              </div>
            </div>

            {missingPeriodNotice ? (
              <div className="bannerNotice warning" role="alert">
                <span>指定月份「{missingPeriodNotice}」暂无有效快照，已为您呈现 {snapshot.periodKey} 月报数据。</span>
              </div>
            ) : null}

            {!isLineValid && selectedLine !== "全部业务线" ? (
              <div className="bannerNotice warning" role="alert">
                <span>未在 {snapshot.periodKey} 快照中找到业务线「{selectedLine}」，该业务线不存在或当月无纳管产品。已为您切换为全业务线视图。</span>
                <button
                  type="button"
                  className="clearLineBtn"
                  onClick={resetDrilldown}
                >
                  <X size={12} />
                  <span>重置为全部业务线</span>
                </button>
              </div>
            ) : null}

            {selectedLine !== "全部业务线" && isLineValid && activeLineSummary ? (
              <section className="lineCtoDashboard" aria-label="业务线 CTO 概览面板">
                <div className="lineCtoOverview">
                  <div className="lineCtoHeroCard">
                    <div className="lineCtoHeroTop">
                      <span className="lineCtoHeroTitle">{selectedLine} · 均分考核</span>
                      {currentLineRanking ? (
                        <span className="bentoRankBadge rankBronze" title={currentLineRanking.isTie ? "并列排名" : undefined}>
                          BG 排名 #{currentLineRanking.rank}{currentLineRanking.isTie ? "*" : ""}
                        </span>
                      ) : null}
                    </div>

                    <div className="lineCtoHeroScore">
                      <span className="lineCtoHeroScoreNum">
                        {activeLineSummary.averageRdhs !== null ? activeLineSummary.averageRdhs.toFixed(1) : "—"}
                      </span>
                      <span className="lineCtoHeroScoreUnit">分</span>
                      {currentLineRanking?.delta !== null && currentLineRanking?.delta !== undefined ? (
                        <span className={`deltaBadge ${currentLineRanking.delta >= 0 ? "deltaUp" : "deltaDown"}`}>
                          {currentLineRanking.delta >= 0 ? `+${currentLineRanking.delta.toFixed(1)}` : currentLineRanking.delta.toFixed(1)}
                        </span>
                      ) : (
                        <span className="textMuted" style={{ fontSize: 11 }}>上月暂无对比</span>
                      )}
                    </div>

                    <div className="lineCtoHeroNote">
                      <div>未度量考核计0；在研 {activeLineSummary.productTotal} 款（上月 {previousSnapshot ? `${prevLineProducts.length} 款` : "未获取"}）</div>
                      <div>上月均分：{currentLineRanking?.prevAvgScore == null ? "未获取" : `${currentLineRanking.prevAvgScore.toFixed(1)} 分`} · 比较相邻自然月快照</div>
                      {currentLineRanking?.compositionChange?.hasChanged ? (
                        <div className="compNotice">
                          口径变化: 新增 {currentLineRanking.compositionChange.addedCount} 款，移出 {currentLineRanking.compositionChange.removedCount} 款
                        </div>
                      ) : null}
                      {isCurrentMonth ? (
                        <div className="mtdNotice">
                          当月进行中 (MTD)，与上月全月对比不构成直接归因
                        </div>
                      ) : null}
                    </div>
                  </div>

                  <div className="lineCtoGrid">
                    <div className="lineCtoCard">
                      <span className="lineCtoCardLabel">达标及格率 (≥70)</span>
                      <div className="lineCtoCardNum">
                        {currentLineRanking ? `${currentLineRanking.passRate}%` : `${(activeLineSummary.complianceRate * 100).toFixed(1)}%`}
                      </div>
                      <span className="lineCtoCardDesc">
                        及格 {activeLineSummary.complianceCount} / {activeLineSummary.productTotal} 款
                      </span>
                    </div>

                    <div className="lineCtoCard">
                      <span className="lineCtoCardLabel">度量覆盖率</span>
                      <div className="lineCtoCardNum">
                        {(activeLineSummary.measurementCoverage * 100).toFixed(1)}%
                      </div>
                      <span className="lineCtoCardDesc">
                        已度量 {activeLineSummary.measuredProductCount} 款 · 未度量 {activeLineSummary.unmeasuredProductCount} 款
                      </span>
                    </div>

                    <div className="lineCtoCard">
                      <span className="lineCtoCardLabel">重点治理敞口 (P0/&lt;45)</span>
                      <div className="lineCtoCardNum textRed">
                        {activeLineSummary.bandCounts.keyGovernance} <small>款</small>
                      </div>
                      <span className="lineCtoCardDesc">
                        含未度量计0；待治理(&lt;70)共 {activeLineSummary.pendingGovernanceCount} 款
                      </span>
                    </div>

                    <div className="lineCtoCard">
                      <span className="lineCtoCardLabel">最低过程短板</span>
                      <div className="lineCtoCardNum" style={{ fontSize: 14 }}>
                        {activeLineLowestComponent ? activeLineLowestComponent.label : "暂无"}
                      </div>
                      <span className="lineCtoCardDesc">
                        {activeLineLowestComponent ? `${formatComponentScore(activeLineLowestComponent.value)} / ${activeLineLowestComponent.maximum}` : "—"}
                      </span>
                    </div>
                  </div>
                </div>

                {sublineDistribution.length > 0 ? (
                  <div className="sublinesSection">
                    <div className="sublinesSectionHeader">
                      <div className="sublinesTitle">
                        <Layers size={14} />
                        <span>二级业务线分布 ({sublineDistribution.length} 条)</span>
                        {selectedSubLine ? (
                          <button
                            type="button"
                            className="clearLineBtn"
                            style={{ fontSize: 11, padding: "1px 6px" }}
                            onClick={() => {
                              setSelectedSubLine(null);
                              setSelectedProductKey(null);
                              setProductPage(1);
                            }}
                          >
                            已下钻: {selectedSubLine} (点击重置)
                          </button>
                        ) : null}
                      </div>
                      <span className="sublinesHint">点击卡片可下钻过滤下方产品列表</span>
                    </div>

                    <div className="sublinesGrid">
                      {sublineDistribution.map((sub) => {
                        const isActive = selectedSubLine === sub.name;
                        return (
                          <button
                            type="button"
                            key={sub.name}
                            className={`sublineCard ${isActive ? "active" : ""}`}
                            onClick={() => {
                              setSelectedSubLine(isActive ? null : sub.name);
                              setSelectedProductKey(null);
                              setProductPage(1);
                            }}
                          >
                            <div className="sublineCardHead">
                              <span className="sublineName" title={sub.name}>{sub.name}</span>
                              <span className="sublineCount">{sub.count} 款</span>
                            </div>
                            <div className="sublineScoreRow">
                              <span className="sublineScore">
                                {sub.averageRdhs !== null ? `${sub.averageRdhs.toFixed(1)}分` : "—"}
                              </span>
                              {sub.unmeasuredCount > 0 ? (
                                <span className="sublineUnmeasuredTag">未度量 {sub.unmeasuredCount}</span>
                              ) : null}
                            </div>
                            <div className="sublineMetaRow">
                              <span>及格率 {sub.passRate}%</span>
                              <span>P0治理 {sub.keyGovCount}款</span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ) : null}

                {governanceCandidates.length > 0 ? (
                  <div className="govRecommendationsSection">
                    <div className="govRecHeader">
                      <div className="govRecTitle">
                        <AlertTriangle size={14} />
                        <span>重点治理推荐 (Top {governanceCandidates.length})</span>
                      </div>
                      <span className="sublinesHint">按未度量与低分优先核查；建议不代表已确认业务根因</span>
                    </div>

                    <div className="govRecGrid">
                      {governanceCandidates.map((prod) => {
                        const priority =
                          prod.rdhs === null || prod.rdhs < 45
                            ? "p0"
                            : prod.rdhs < 60
                              ? "p1"
                              : "p2";
                        const priorityLabel = priority.toUpperCase();
                        const scoreText = prod.rdhs === null ? "未度量，考核计0" : `${prod.rdhs.toFixed(1)} 分`;
                        return (
                          <div key={productKey(prod)} className={`govRecCard ${priority}`}>
                            <div className="govRecCardTop">
                              <div>
                                <div className="govRecProductTitle">{prod.product}</div>
                                <div className="govRecSubline">{prod.subLine || "未分二级业务线"}</div>
                              </div>
                              <span className={`govRecScoreBadge badge ${bandClass(prod.governanceBand)}`}>
                                {priorityLabel} · {scoreText}
                              </span>
                            </div>
                            <div className="govRecBody">
                              <div><b>指标事实:</b> {prod.rdhs === null ? "本期无有效评分，考核计0；原因待核实。" : `RDHS ${prod.rdhs.toFixed(1)} 分，最低过程项：${prod.lowestComponent || "未获取"}。`}</div>
                              <div><b>核查动作:</b> {prod.rdhs === null ? "核实产品状态、图表范围与数据关联，不直接认定未开展研发。" : "结合原单和分项指标核实实际阶段；仅对真实完成且满足验收条件的需求补齐记录，不为提分结项。"}</div>
                              <div><b>责任角色:</b> 本期快照未提供，待业务线确认。</div>
                            </div>
                            <button
                              type="button"
                              className="govRecBtn"
                              onClick={() => locateProduct(prod)}
                            >
                              <span>定位至产品明细</span>
                              <ArrowRight size={12} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </section>
            ) : null}
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
                    chooseBusinessLine(event.target.value);
                  }}
                >
                  <option value="全部业务线">全部业务线</option>
                  {businessLines.map((line) => (
                    <option key={line.businessLine} value={line.businessLine}>
                      {line.businessLine} ({line.productTotal}款)
                    </option>
                  ))}
                </select>
                {selectedLine !== "全部业务线" && isLineValid && sublineDistribution.length > 0 ? (
                  <select
                    className="filterSelect"
                    aria-label="按二级业务线筛选"
                    value={selectedSubLine ?? "全部二级线"}
                    onChange={(event) => {
                      const val = event.target.value;
                      setSelectedSubLine(val === "全部二级线" ? null : val);
                      setSelectedProductKey(null);
                      setProductPage(1);
                    }}
                  >
                    <option value="全部二级线">全部二级业务线</option>
                    {sublineDistribution.map((sub) => (
                      <option key={sub.name} value={sub.name}>
                        {sub.name} ({sub.count}款)
                      </option>
                    ))}
                  </select>
                ) : null}
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
