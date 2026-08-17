type ScoreRailProps = {
  value: number | null;
};

export function ScoreRail({ value }: ScoreRailProps) {
  const marker = Math.min(100, Math.max(0, value ?? 0));
  return (
    <section className="scoreRailWrap" aria-label="RDHS 分档标尺">
      <div className="scoreRailHeader">
        <h3 className="scoreRailTitle">RDHS 分档标尺</h3>
        <span className="scoreRailValue">当前均值 {value?.toFixed(1) ?? "—"}</span>
      </div>
      <div className="scoreRail" aria-hidden="true">
        <span className="railSegment" />
        <span className="railSegment" />
        <span className="railSegment" />
        <span className="railSegment" />
        {value !== null ? <span className="railMarker" style={{ left: `${marker}%` }} /> : null}
      </div>
      <div className="railLabels" aria-hidden="true">
        <span>0</span>
        <span style={{ left: "45%" }}>45</span>
        <span style={{ left: "60%" }}>60</span>
        <span style={{ left: "70%" }}>70</span>
        <span>100</span>
      </div>
    </section>
  );
}
