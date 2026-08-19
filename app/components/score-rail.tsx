type ScoreRailProps = {
  value: number | null;
};

export function ScoreRail({ value }: ScoreRailProps) {
  const marker = Math.min(100, Math.max(0, value ?? 0));
  return (
    <section className="panel thresholdPanel" aria-label="RDHS 阈值标尺">
      <div className="panelHead">
        <div>
          <h2 className="panelTitle">RDHS 阈值标尺</h2>
          <div className="panelSubtitle">统一评分口径 · 当前 CBG 平均分落点</div>
        </div>
        <span className="mono panelMeta">0-100</span>
      </div>
      <div className="thresholdBody">
        <div className="scoreRail" aria-hidden="true">
          <span className="railTick t0">0</span>
          <span className="railTick t45">45</span>
          <span className="railTick t60">60</span>
          <span className="railTick t70">70</span>
          <span className="railTick t100">100</span>
          <div className="railTrack">
            <span className="railSegment key" />
            <span className="railSegment risk" />
            <span className="railSegment optimize" />
            <span className="railSegment regular" />
          </div>
          {value !== null ? (
            <>
              <span className="railMarker" style={{ left: `${marker}%` }} />
              <span className="railMarkerLabel" style={{ left: `${marker}%` }}>{value.toFixed(1)} 平均</span>
            </>
          ) : null}
        </div>
        <div className="railLegend">
          <span><i className="dot key" />重点治理<br /><b>&lt;45 + 未度量</b></span>
          <span><i className="dot risk" />风险改进<br /><b>45-&lt;60</b></span>
          <span><i className="dot optimize" />持续优化<br /><b>60-&lt;70</b></span>
          <span><i className="dot regular" />常规跟踪<br /><b>&gt;=70</b></span>
        </div>
      </div>
    </section>
  );
}
