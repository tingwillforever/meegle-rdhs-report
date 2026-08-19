type TrendPoint = {
  periodKey: string;
  averageRdhs: number | null;
  measurementCoverage: number;
};

type ProductTrendSeries = {
  name: string;
  points: Array<{
    periodKey: string;
    value: number | null;
  }>;
};

type TrendChartProps = {
  points: TrendPoint[];
  productSeries?: ProductTrendSeries[];
  ariaLabel: string;
};

const WIDTH = 690;
const HEIGHT = 178;
const LEFT = 48;
const RIGHT = 42;
const TOP = 18;
const BOTTOM = 28;
const PRODUCT_LINE_CLASSES = ["productLine risk", "productLine optimize", "productLine track", "productLine muted"];

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

export function TrendChart({ points, productSeries = [], ariaLabel }: TrendChartProps) {
  if (points.length === 0) {
    return <div className="emptyState compact">暂无月度趋势数据</div>;
  }

  const primaryValues = points.map((point) => point.averageRdhs);
  const primaryPath = linePath(primaryValues);
  const latest = [...points].reverse().find((point) => point.averageRdhs !== null);

  return (
    <div className="chartWrap">
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

        {productSeries.map((series, seriesIndex) => {
          const values = points.map((point) => {
            const matched = series.points.find((item) => item.periodKey === point.periodKey);
            return matched?.value ?? null;
          });
          const path = linePath(values);
          const latestIndex = values.findLastIndex((value) => value !== null);
          if (!path || latestIndex < 0) return null;
          return (
            <g key={series.name}>
              <path className={PRODUCT_LINE_CLASSES[seriesIndex % PRODUCT_LINE_CLASSES.length]} d={path} />
              <text
                className="productTrendLabel"
                x={WIDTH - RIGHT + 7}
                y={pointY(values[latestIndex] ?? 0) + 3}
              >
                {series.name}
              </text>
            </g>
          );
        })}

        {primaryPath ? (
          <path
            className="trendArea"
            d={`${primaryPath} L${pointX(points.length - 1, points.length)} ${pointY(0)} L${pointX(0, points.length)} ${pointY(0)} Z`}
          />
        ) : null}
        {primaryPath ? <path className="trendLine" d={primaryPath} /> : null}

        {points.map((point, index) => {
          const x = pointX(index, points.length);
          return (
            <g key={point.periodKey}>
              {point.averageRdhs !== null ? (
                <circle className="trendPoint" cx={x} cy={pointY(point.averageRdhs)} r={4.5} />
              ) : null}
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
      </svg>
    </div>
  );
}
