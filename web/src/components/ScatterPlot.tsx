import { useMemo, useState } from "react";
import type { ParetoPoint } from "../api";

type MetricKey = "amota" | "mota" | "ids";

const METRIC_LABELS: Record<MetricKey, string> = {
  amota: "AMOTA",
  mota: "MOTA",
  ids: "IDS",
};

const PADDING = { top: 32, right: 32, bottom: 48, left: 64 };
const DOT_R = 6;

function extent(values: number[]): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (lo === hi) return [lo - 1, hi + 1];
  const pad = (hi - lo) * 0.08;
  return [lo - pad, hi + pad];
}

function niceStep(range: number, targetTicks: number): number {
  const rough = range / targetTicks;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const frac = rough / mag;
  let nice: number;
  if (frac <= 1.5) nice = 1;
  else if (frac <= 3) nice = 2;
  else if (frac <= 7) nice = 5;
  else nice = 10;
  return nice * mag;
}

function tickValues(lo: number, hi: number, targetTicks = 6): number[] {
  const step = niceStep(hi - lo, targetTicks);
  const start = Math.ceil(lo / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= hi + step * 0.001; v += step) {
    ticks.push(Math.round(v * 1e10) / 1e10);
  }
  return ticks;
}

export function ScatterPlot({
  points,
  xKey = "p99_ms",
  yKey = "amota",
}: {
  points: ParetoPoint[];
  xKey?: "p99_ms";
  yKey?: MetricKey;
}) {
  const [hover, setHover] = useState<ParetoPoint | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);

  const { xTicks, yTicks, mapped } = useMemo(() => {
    const xVals = points
      .map((p) => p[xKey])
      .filter((v): v is number => v != null && Number.isFinite(v));
    const yVals = points
      .map((p) => p[yKey])
      .filter((v): v is number => v != null && Number.isFinite(v));

    const [xLo, xHi] = extent(xVals.length ? xVals : [0, 1]);
    const [yLo, yHi] = extent(yVals.length ? yVals : [0, 1]);

    const w = 640;
    const h = 400;
    const plotW = w - PADDING.left - PADDING.right;
    const plotH = h - PADDING.top - PADDING.bottom;

    const mapped = points.map((p) => {
      const xv = p[xKey];
      const yv = p[yKey];
      if (xv == null || yv == null || !Number.isFinite(xv) || !Number.isFinite(yv)) {
        return { ...p, sx: null, sy: null };
      }
      const sx = PADDING.left + ((xv - xLo) / (xHi - xLo)) * plotW;
      const sy = PADDING.top + (1 - (yv - yLo) / (yHi - yLo)) * plotH;
      return { ...p, sx, sy };
    });

    return {
      xTicks: tickValues(xLo, xHi),
      yTicks: tickValues(yLo, yHi),
      mapped,
    };
  }, [points, xKey, yKey]);

  const w = 640;
  const h = 400;
  const plotW = w - PADDING.left - PADDING.right;
  const plotH = h - PADDING.top - PADDING.bottom;

  const xLo = xTicks.length > 0 ? xTicks[0] : 0;
  const xHi = xTicks.length > 1 ? xTicks[xTicks.length - 1] : 1;
  const yLo = yTicks.length > 0 ? yTicks[0] : 0;
  const yHi = yTicks.length > 1 ? yTicks[yTicks.length - 1] : 1;

  const handleMouseMove = (
    e: React.MouseEvent,
    p: ParetoPoint,
  ) => {
    const svg = (e.target as HTMLElement).closest("svg");
    const rect = svg?.getBoundingClientRect();
    if (!rect) return;
    setTooltipPos({ x: e.clientX - rect.left + 12, y: e.clientY - rect.top - 8 });
    setHover(p);
  };

  return (
    <div className="scatter-wrap">
      <svg viewBox={`0 0 ${w} ${h}`} className="scatter-svg">
        {/* axes */}
        <line
          x1={PADDING.left}
          y1={PADDING.top}
          x2={PADDING.left}
          y2={PADDING.top + plotH}
          stroke="var(--border)"
        />
        <line
          x1={PADDING.left}
          y1={PADDING.top + plotH}
          x2={PADDING.left + plotW}
          y2={PADDING.top + plotH}
          stroke="var(--border)"
        />

        {/* x ticks */}
        {xTicks.map((v) => {
          const sx = PADDING.left + ((v - xLo) / (xHi - xLo)) * plotW;
          return (
            <g key={`x-${v}`}>
              <line x1={sx} y1={PADDING.top + plotH} x2={sx} y2={PADDING.top + plotH + 5} stroke="var(--border)" />
              <text x={sx} y={PADDING.top + plotH + 18} textAnchor="middle" className="tick-label">
                {Number.isInteger(v) ? v : v.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* y ticks */}
        {yTicks.map((v) => {
          const sy = PADDING.top + (1 - (v - yLo) / (yHi - yLo)) * plotH;
          return (
            <g key={`y-${v}`}>
              <line x1={PADDING.left - 5} y1={sy} x2={PADDING.left} y2={sy} stroke="var(--border)" />
              <text x={PADDING.left - 10} y={sy + 4} textAnchor="end" className="tick-label">
                {Number.isInteger(v) ? v : v.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* axis labels */}
        <text x={PADDING.left + plotW / 2} y={h - 4} textAnchor="middle" className="axis-label">
          p99 ms
        </text>
        <text
          x={12}
          y={PADDING.top + plotH / 2}
          textAnchor="middle"
          className="axis-label"
          transform={`rotate(-90, 12, ${PADDING.top + plotH / 2})`}
        >
          {METRIC_LABELS[yKey]}
        </text>

        {/* dots */}
        {mapped.map((p) =>
          p.sx != null && p.sy != null ? (
            <circle
              key={p.id}
              cx={p.sx}
              cy={p.sy}
              r={hover?.id === p.id ? DOT_R + 2 : DOT_R}
              className={`dot ${hover?.id === p.id ? "dot-hover" : ""}`}
              onMouseMove={(e) => handleMouseMove(e, p)}
              onMouseLeave={() => setHover(null)}
            />
          ) : null,
        )}
      </svg>

      {hover && tooltipPos && (
        <div
          className="scatter-tooltip"
          style={{ left: tooltipPos.x, top: tooltipPos.y }}
        >
          <div className="mono" style={{ fontSize: "0.75rem" }}>
            {hover.commitSha.slice(0, 8)}
          </div>
          <div>p99: {hover.p99_ms?.toFixed(3) ?? "—"} ms</div>
          <div>AMOTA: {hover.amota?.toFixed(4) ?? "—"}</div>
          <div>MOTA: {hover.mota?.toFixed(4) ?? "—"}</div>
          <div>IDS: {hover.ids ?? "—"}</div>
          {hover.notes && <div className="muted">{hover.notes}</div>}
        </div>
      )}
    </div>
  );
}
