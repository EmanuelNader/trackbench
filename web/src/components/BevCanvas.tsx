import { useEffect, useRef } from "react";
import type { BevBox, FramePayload } from "../api";

type Props = {
  frame: FramePayload | null;
  metersSpan?: number;
  /** GT instance token to emphasize (from selected failure event). */
  highlightGtId?: string | number | null;
  /** Tracker id to emphasize (from selected failure event). */
  highlightTrackId?: string | number | null;
};

function idsEqual(
  a: unknown,
  b: string | number | null | undefined,
): boolean {
  if (b == null || b === "") return false;
  if (a == null) return false;
  return String(a) === String(b);
}

function shortId(id: unknown, max = 7): string {
  if (id == null) return "?";
  const s = String(id);
  return s.length <= max ? s : `${s.slice(0, max)}…`;
}

function drawBox(
  ctx: CanvasRenderingContext2D,
  box: BevBox,
  color: string,
  scale: number,
  cx: number,
  cy: number,
  label: string,
  opts?: { highlight?: boolean; lineWidth?: number },
) {
  const l = box.l ?? 4.5;
  const w = box.w ?? 1.8;
  const yaw = box.yaw ?? 0;
  const x = box.x;
  const y = box.y;
  const highlight = opts?.highlight ?? false;
  const lineWidth = opts?.lineWidth ?? (highlight ? 3 : 1.5);

  const sx = cx + x * scale;
  const sy = cy - y * scale;

  if (highlight) {
    ctx.save();
    ctx.strokeStyle = "rgba(255, 230, 120, 0.9)";
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.arc(sx, sy, Math.max(l, w) * scale * 0.75 + 10, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  }

  ctx.save();
  ctx.translate(sx, sy);
  ctx.rotate(-yaw);

  const pw = l * scale;
  const ph = w * scale;
  ctx.strokeStyle = color;
  ctx.fillStyle =
    color.startsWith("#") && color.length === 7 ? `${color}26` : "rgba(255,255,255,0.08)";
  if (highlight) {
    ctx.fillStyle =
      color.startsWith("#") && color.length === 7 ? `${color}55` : "rgba(255,230,120,0.25)";
  }
  ctx.lineWidth = lineWidth;
  ctx.beginPath();
  ctx.rect(-pw / 2, -ph / 2, pw, ph);
  ctx.fill();
  ctx.stroke();

  // Heading tick
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(pw / 2, 0);
  ctx.stroke();

  ctx.restore();

  // Label in screen space
  ctx.fillStyle = highlight ? "#ffe678" : color;
  ctx.font = highlight
    ? "bold 12px IBM Plex Mono, monospace"
    : "11px IBM Plex Mono, monospace";
  ctx.textAlign = "center";
  ctx.fillText(label, sx, sy - (w * scale) / 2 - (highlight ? 10 : 6));
}

export function BevCanvas({
  frame,
  metersSpan = 50,
  highlightGtId = null,
  highlightTrackId = null,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;

    const dpr = window.devicePixelRatio || 1;

    const paint = () => {
      const rect = wrap.getBoundingClientRect();
      const w = Math.max(1, Math.floor(rect.width));
      const h = Math.max(1, Math.floor(rect.height));
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Background
      const grad = ctx.createRadialGradient(
        w * 0.5,
        h * 0.55,
        20,
        w * 0.5,
        h * 0.5,
        Math.max(w, h) * 0.7,
      );
      grad.addColorStop(0, "#182230");
      grad.addColorStop(1, "#0c1016");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);

      const scale = Math.min(w, h) / metersSpan;
      const cx = w / 2;
      const cy = h / 2;

      // Grid
      ctx.strokeStyle = "rgba(120, 140, 160, 0.12)";
      ctx.lineWidth = 1;
      const half = metersSpan / 2;
      for (let m = -half; m <= half; m += 5) {
        const px = cx + m * scale;
        const py = cy - m * scale;
        ctx.beginPath();
        ctx.moveTo(px, 0);
        ctx.lineTo(px, h);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, py);
        ctx.lineTo(w, py);
        ctx.stroke();
      }

      // Axes
      ctx.strokeStyle = "rgba(180, 195, 210, 0.28)";
      ctx.beginPath();
      ctx.moveTo(0, cy);
      ctx.lineTo(w, cy);
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, h);
      ctx.stroke();

      // Range rings
      ctx.strokeStyle = "rgba(120, 140, 160, 0.18)";
      for (const r of [10, 20]) {
        ctx.beginPath();
        ctx.arc(cx, cy, r * scale, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Ego
      ctx.fillStyle = "#c5d0dc";
      ctx.beginPath();
      ctx.arc(cx, cy, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#c5d0dc";
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + 14, cy);
      ctx.stroke();
      ctx.fillStyle = "rgba(197, 208, 220, 0.75)";
      ctx.font = "10px IBM Plex Mono, monospace";
      ctx.textAlign = "left";
      ctx.fillText("ego", cx + 8, cy - 8);

      if (!frame) {
        ctx.fillStyle = "rgba(139, 155, 176, 0.8)";
        ctx.font = "13px IBM Plex Sans, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("No frame loaded", cx, cy + 40);
        return;
      }

      const hiGt: BevBox[] = [];
      const hiTrk: BevBox[] = [];

      for (const g of frame.gt) {
        if (idsEqual(g.id, highlightGtId)) {
          hiGt.push(g);
          continue;
        }
        drawBox(ctx, g, "#5eb1ff", scale, cx, cy, shortId(g.id));
      }
      for (const t of frame.tracks) {
        const isHi = idsEqual(t.id, highlightTrackId);
        if (isHi) {
          hiTrk.push(t);
          continue;
        }
        if (t.state && t.state !== "confirmed" && t.state !== "coasting") {
          drawBox(
            ctx,
            t,
            "#8a7355",
            scale,
            cx,
            cy,
            `${shortId(t.id, 4)}·${t.state?.[0] ?? "?"}`,
          );
          continue;
        }
        drawBox(ctx, t, "#f0a35e", scale, cx, cy, String(t.id ?? "?"));
      }

      // Selected boxes last so they sit on top
      for (const g of hiGt) {
        drawBox(ctx, g, "#7ec8ff", scale, cx, cy, `GT ${shortId(g.id)}`, {
          highlight: true,
        });
      }
      for (const t of hiTrk) {
        const label =
          t.state && t.state !== "confirmed" && t.state !== "coasting"
            ? `tr ${t.id}·${t.state?.[0] ?? "?"}`
            : `tr ${t.id ?? "?"}`;
        drawBox(ctx, t, "#ffb86b", scale, cx, cy, label, { highlight: true });
      }

      if (highlightGtId || highlightTrackId) {
        const bits: string[] = ["selected"];
        if (highlightTrackId) bits.push(`tr ${highlightTrackId}`);
        if (highlightGtId) bits.push(`gt ${shortId(highlightGtId)}`);
        const missing: string[] = [];
        if (highlightGtId && hiGt.length === 0) missing.push("GT not in frame");
        if (highlightTrackId && hiTrk.length === 0) missing.push("track not in frame");
        const boxH = missing.length ? 44 : 28;
        const boxY = h - boxH - 12;
        ctx.fillStyle = "rgba(12, 16, 22, 0.82)";
        ctx.fillRect(10, boxY, 300, boxH);
        ctx.fillStyle = "#ffe678";
        ctx.font = "12px IBM Plex Mono, monospace";
        ctx.textAlign = "left";
        ctx.fillText(bits.join(" · "), 18, boxY + 18);
        if (missing.length) {
          ctx.fillStyle = "#e06c75";
          ctx.fillText(missing.join(" · "), 18, boxY + 36);
        }
      }
    };

    paint();
    const ro = new ResizeObserver(() => paint());
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [frame, metersSpan, highlightGtId, highlightTrackId]);

  return (
    <div className="bev-stage" ref={wrapRef}>
      <canvas ref={canvasRef} />
      <div className="bev-legend">
        <span className="gt">
          <i />
          GT
        </span>
        <span className="trk">
          <i />
          track
        </span>
        <span className="ego">
          <i />
          ego
        </span>
        <span className="hi">
          <i />
          selected
        </span>
      </div>
    </div>
  );
}
