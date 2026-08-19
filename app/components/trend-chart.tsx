"use client";

import { useState } from "react";

type TrendPoint = {
  periodKey: string;
  averageRdhs: number | null;
  measurementCoverage: number;
  complianceRate: number;
  productTotal: number;
  measuredProductCount: number;
};

type TrendChartProps = {
  points: TrendPoint[];
  ariaLabel: string;
};

const WIDTH = 690;
const HEIGHT = 178;
const LEFT = 48;
const RIGHT = 42;
const TOP = 18;
const BOTTOM = 28;
function formatScore(value: number | null) {
  return value === null ? "未度量" : value.toFixed(1);
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function pointX(index: number, count: number) {
  if (count <= 1) return (WIDTH + LEFT - RIGHT) / 2;
  return LEFT + (index * (WIDTH - LEFT - RIGHT)) / (count - 1);
}

function pointY(value: number) {
  return TOP + ((100 - value) / 100) * (HEIGHT - TOP - BOTTOM);
}

function linePath(values: Array<number | null>) {
  let started = false;
  return values
    .map((value, index) => {
      if (value === null) {
        started = false;
        return "";
      }
      const command = started ? "L" : "M";
      started = true;
      return `${command}${pointX(index, values.length)} ${pointY(value)}`;
    })
    .filter(Boolean)
    .join(" ");
}

export function TrendChart({ points, ariaLabel }: TrendChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  if (points.length === 0) {
    return <div className="emptyState compact">暂无月度趋势数据</div>;
  }

  const primaryValues = points.map((point) => point.averageRdhs);
  const complianceValues = points.map((point) => point.complianceRate * 100);
  const primaryPath = linePath(primaryValues);
  const compliancePath = linePath(complianceValues);
  const latest = [...points].reverse().find((point) => point.averageRdhs !== null);
  const latestCompliance = points.at(-1);
  const activePoint = activeIndex === null ? null : points[activeIndex];
  const activeX = activeIndex === null ? 0 : pointX(activeIndex, points.length);
  const activeY = activePoint?.averageRdhs === null || !activePoint
    ? TOP + 48
    : pointY(activePoint.averageRdhs);
  const tooltipLeft = (activeX / WIDTH) * 100;
  const tooltipTop = (Math.max(TOP + 6, activeY - 10) / HEIGHT) * 100;
  const tooltipEdgeClass = activeX < 170 ? "left" : activeX > WIDTH - 170 ? "right" : "";

  return (
    <div className="chartWrap">
      <div className="trendLegend" aria-hidden="true">
        <span><i className="rdhs" />平均 RDHS</span>
        <span><i className="compliance" />规范占比</span>
      </div>
      <svg
        className="trendChart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={ariaLabel}
      >
        {[100, 70, 60, 45, 0].map((tick) => (
          <g key={tick}>
            <line
              className={tick === 70 || tick === 60 || tick === 45 ? "trendRule threshold" : "trendRule"}
              x1={LEFT}
              x2={WIDTH - RIGHT}
              y1={pointY(tick)}
              y2={pointY(tick)}
            />
            <text className="axisLabel" x={LEFT - 11} y={pointY(tick) + 4} textAnchor="end">
              {tick}
            </text>
          </g>
        ))}

        {primaryPath ? (
          <path
            className="trendArea"
            d={`${primaryPath} L${pointX(points.length - 1, points.length)} ${pointY(0)} L${pointX(0, points.length)} ${pointY(0)} Z`}
          />
        ) : null}
        {primaryPath ? <path className="trendLine" d={primaryPath} /> : null}
        {compliancePath ? <path className="trendComplianceLine" d={compliancePath} /> : null}

        {points.map((point, index) => {
          const x = pointX(index, points.length);
          return (
            <g key={point.periodKey}>
              {point.averageRdhs !== null ? (
                <circle className="trendPoint" cx={x} cy={pointY(point.averageRdhs)} r={4.5} />
              ) : null}
              <circle
                className="trendCompliancePoint"
                cx={x}
                cy={pointY(point.complianceRate * 100)}
                r={3.8}
              />
              <text className="trendLabel" x={x} y={HEIGHT - 12} textAnchor="middle">
                {point.periodKey.slice(5)}
              </text>
            </g>
          );
        })}

        {latest?.averageRdhs !== null && latest ? (
          <text className="trendCurrentValue" x={WIDTH - RIGHT + 6} y={pointY(latest.averageRdhs) - 8}>
            {latest.averageRdhs.toFixed(1)}
          </text>
        ) : null}
        {latestCompliance ? (
          <text
            className="trendComplianceValue"
            x={WIDTH - RIGHT + 6}
            y={pointY(latestCompliance.complianceRate * 100) + 14}
          >
            {formatPercent(latestCompliance.complianceRate)}
          </text>
        ) : null}

        {points.map((point, index) => {
          const x = pointX(index, points.length);
          const previousX = index === 0 ? LEFT : pointX(index - 1, points.length);
          const nextX = index === points.length - 1 ? WIDTH - RIGHT : pointX(index + 1, points.length);
          const columnLeft = index === 0 ? LEFT : (previousX + x) / 2;
          const columnRight = index === points.length - 1 ? WIDTH - RIGHT : (nextX + x) / 2;
          const label = `${point.periodKey} 平均 RDHS ${formatScore(point.averageRdhs)}，规范占比 ${formatPercent(point.complianceRate)}，度量覆盖率 ${formatPercent(point.measurementCoverage)}`;
          return (
            <rect
              key={`hover-${point.periodKey}`}
              className="trendHoverZone"
              x={columnLeft}
              y={TOP}
              width={columnRight - columnLeft}
              height={HEIGHT - TOP - BOTTOM}
              tabIndex={0}
              role="img"
              aria-label={label}
              onMouseEnter={() => setActiveIndex(index)}
              onFocus={() => setActiveIndex(index)}
              onMouseLeave={() => setActiveIndex(null)}
              onBlur={() => setActiveIndex(null)}
            />
          );
        })}
      </svg>
      {activePoint ? (
        <div
          className={`trendTooltip ${tooltipEdgeClass}`}
          style={{ left: `${tooltipLeft}%`, top: `${tooltipTop}%` }}
          role="status"
        >
          <div className="trendTooltipTitle">{activePoint.periodKey}</div>
          <div className="trendTooltipRow">
            <span>平均 RDHS</span>
            <b>{formatScore(activePoint.averageRdhs)}</b>
          </div>
          <div className="trendTooltipRow">
            <span>度量覆盖率</span>
            <b>{formatPercent(activePoint.measurementCoverage)}</b>
          </div>
          <div className="trendTooltipRow">
            <span>规范占比</span>
            <b>{formatPercent(activePoint.complianceRate)}</b>
          </div>
          <div className="trendTooltipRow">
            <span>已度量产品</span>
            <b>{activePoint.measuredProductCount}/{activePoint.productTotal}</b>
          </div>
        </div>
      ) : null}
    </div>
  );
}
