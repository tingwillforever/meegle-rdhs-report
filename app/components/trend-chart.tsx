import type { TrendPoint } from "@/lib/rdhs/types";

type TrendChartProps = {
  points: TrendPoint[];
};

const WIDTH = 680;
const HEIGHT = 250;
const LEFT = 42;
const RIGHT = 24;
const TOP = 22;
const BOTTOM = 38;

function pointX(index: number, count: number) {
  if (count <= 1) return (WIDTH + LEFT - RIGHT) / 2;
  return LEFT + (index * (WIDTH - LEFT - RIGHT)) / (count - 1);
}

function pointY(value: number) {
  return TOP + ((100 - value) / 100) * (HEIGHT - TOP - BOTTOM);
}

export function TrendChart({ points }: TrendChartProps) {
  if (points.length === 0) {
    return <div className="emptyState">暂无月度趋势数据</div>;
  }
  const path = points
    .map((point, index) => {
      const value = point.averageRdhs ?? 0;
      return `${index === 0 ? "M" : "L"} ${pointX(index, points.length)} ${pointY(value)}`;
    })
    .join(" ");

  return (
    <div className="chartScroll">
      <svg
        className="trendChart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="月度平均 RDHS 趋势"
      >
        {[0, 20, 40, 60, 80, 100].map((tick) => (
          <g key={tick}>
            <line
              className="trendGrid"
              x1={LEFT}
              x2={WIDTH - RIGHT}
              y1={pointY(tick)}
              y2={pointY(tick)}
            />
            <text className="axisLabel" x={LEFT - 9} y={pointY(tick) + 4} textAnchor="end">
              {tick}
            </text>
          </g>
        ))}
        <line
          className="trendBaseline"
          x1={LEFT}
          x2={WIDTH - RIGHT}
          y1={pointY(70)}
          y2={pointY(70)}
        />
        <path className="trendLine" d={path} />
        {points.map((point, index) => {
          const x = pointX(index, points.length);
          const y = pointY(point.averageRdhs ?? 0);
          return (
            <g key={point.periodKey}>
              <circle className="trendPoint" cx={x} cy={y} r={5} />
              <text className="trendValue" x={x} y={y - 12} textAnchor="middle">
                {point.averageRdhs?.toFixed(1) ?? "—"}
              </text>
              <text className="trendLabel" x={x} y={HEIGHT - 13} textAnchor="middle">
                {point.periodKey}
              </text>
              <text className="trendLabel" x={x} y={HEIGHT - 1} textAnchor="middle">
                覆盖 {(point.measurementCoverage * 100).toFixed(0)}%
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
