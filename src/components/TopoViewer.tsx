"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface Contour {
  elevation: number;
  layer: string;
  pts: [number, number][];
}
interface SpotLevel {
  x: number;
  y: number;
  z: number;
}
interface TopoData {
  contours: Contour[];
  spots: SpotLevel[];
}

const PRIMARY_COLOR = "#f5c518";
const SECONDARY_COLOR = "#888";
const SPOT_COLOR = "#4af";
const TEXT_COLOR = "#6f6";
const BG = "#1a1a2e";

export default function TopoViewer() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [data, setData] = useState<TopoData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showSpots, setShowSpots] = useState(true);
  const [showLabels, setShowLabels] = useState(true);

  // pan/zoom state
  const transform = useRef({ x: 0, y: 0, scale: 1 });
  const drag = useRef<{ active: boolean; sx: number; sy: number; tx: number; ty: number }>({
    active: false, sx: 0, sy: 0, tx: 0, ty: 0,
  });

  useEffect(() => {
    fetch("/api/topo")
      .then((r) => r.json())
      .then((d: TopoData) => { setData(d); setLoading(false); })
      .catch(() => { setError("Failed to load topo data"); setLoading(false); });
  }, []);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const d = data;
    if (!canvas || !d) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { x: tx, y: ty, scale } = transform.current;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Compute bounds on first draw
    if (!canvas.dataset.ready) {
      const allX = d.contours.flatMap((c) => c.pts.map((p) => p[0]));
      const allY = d.contours.flatMap((c) => c.pts.map((p) => p[1]));
      const minX = Math.min(...allX), maxX = Math.max(...allX);
      const minY = Math.min(...allY), maxY = Math.max(...allY);
      const dw = maxX - minX, dh = maxY - minY;
      const scaleX = (canvas.width * 0.9) / dw;
      const scaleY = (canvas.height * 0.9) / dh;
      const s = Math.min(scaleX, scaleY);
      transform.current = {
        scale: s,
        x: canvas.width / 2 - (minX + dw / 2) * s,
        y: canvas.height / 2 + (minY + dh / 2) * s, // flip Y
      };
      canvas.dataset.ready = "1";
      canvas.dataset.minX = String(minX);
      canvas.dataset.minY = String(minY);
      draw();
      return;
    }

    const toScreen = (wx: number, wy: number): [number, number] => [
      wx * transform.current.scale + transform.current.x,
      -wy * transform.current.scale + transform.current.y,
    ];

    // Draw contours
    for (const c of d.contours) {
      const isPrimary = c.layer === "TOPO-CONT-PRIMARY";
      ctx.beginPath();
      ctx.strokeStyle = isPrimary ? PRIMARY_COLOR : SECONDARY_COLOR;
      ctx.lineWidth = isPrimary ? 1.5 : 0.7;
      const [sx, sy] = toScreen(c.pts[0][0], c.pts[0][1]);
      ctx.moveTo(sx, sy);
      for (let i = 1; i < c.pts.length; i++) {
        const [ex, ey] = toScreen(c.pts[i][0], c.pts[i][1]);
        ctx.lineTo(ex, ey);
      }
      ctx.stroke();

      // Label on primary
      if (isPrimary && showLabels && transform.current.scale > 0.05) {
        const mid = c.pts[Math.floor(c.pts.length / 2)];
        const [lx, ly] = toScreen(mid[0], mid[1]);
        ctx.fillStyle = TEXT_COLOR;
        ctx.font = `${Math.max(9, 11 * transform.current.scale * 20)}px monospace`;
        ctx.fillText(c.elevation.toFixed(1), lx, ly);
      }
    }

    // Draw spot levels
    if (showSpots) {
      for (const s of d.spots) {
        const [sx, sy] = toScreen(s.x, s.y);
        ctx.beginPath();
        ctx.arc(sx, sy, 2, 0, Math.PI * 2);
        ctx.fillStyle = SPOT_COLOR;
        ctx.fill();
        if (showLabels && transform.current.scale > 0.08) {
          ctx.fillStyle = SPOT_COLOR;
          ctx.font = `${Math.max(7, 9 * transform.current.scale * 20)}px monospace`;
          ctx.fillText(s.z.toFixed(3), sx + 3, sy - 3);
        }
      }
    }
  }, [data, showSpots, showLabels]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    canvas.dataset.ready = "";
    draw();
  }, [data, draw]);

  // Resize observer
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ro = new ResizeObserver(() => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
      canvas.dataset.ready = "";
      draw();
    });
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [draw]);

  // Mouse events
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onDown = (e: MouseEvent) => {
      drag.current = { active: true, sx: e.clientX, sy: e.clientY, tx: transform.current.x, ty: transform.current.y };
    };
    const onMove = (e: MouseEvent) => {
      if (!drag.current.active) return;
      transform.current.x = drag.current.tx + (e.clientX - drag.current.sx);
      transform.current.y = drag.current.ty + (e.clientY - drag.current.sy);
      draw();
    };
    const onUp = () => { drag.current.active = false; };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      transform.current.x = mx + (transform.current.x - mx) * factor;
      transform.current.y = my + (transform.current.y - my) * factor;
      transform.current.scale *= factor;
      draw();
    };

    canvas.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      canvas.removeEventListener("mousedown", onDown);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      canvas.removeEventListener("wheel", onWheel);
    };
  }, [draw]);

  const resetView = () => {
    if (canvasRef.current) {
      canvasRef.current.dataset.ready = "";
      draw();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: BG, color: "#eee", fontFamily: "monospace" }}>
      <div style={{ padding: "8px 12px", background: "#111", display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ color: PRIMARY_COLOR, fontWeight: "bold" }}>XREF_Survey_Topo.dxf</span>
        {data && (
          <span style={{ color: "#aaa", fontSize: 12 }}>
            {data.contours.length} contours · {data.spots.length} spot levels
          </span>
        )}
        <label style={{ fontSize: 12, cursor: "pointer" }}>
          <input type="checkbox" checked={showSpots} onChange={(e) => setShowSpots(e.target.checked)} /> spots
        </label>
        <label style={{ fontSize: 12, cursor: "pointer" }}>
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /> labels
        </label>
        <button onClick={resetView} style={{ fontSize: 11, padding: "2px 8px", background: "#333", color: "#eee", border: "1px solid #555", cursor: "pointer" }}>
          reset view
        </button>
        <span style={{ fontSize: 11, color: "#666" }}>scroll=zoom · drag=pan</span>
        <div style={{ display: "flex", gap: 12, marginLeft: "auto", fontSize: 11 }}>
          <span><span style={{ color: PRIMARY_COLOR }}>━</span> 1m primary</span>
          <span><span style={{ color: SECONDARY_COLOR }}>━</span> 0.5m secondary</span>
          <span><span style={{ color: SPOT_COLOR }}>●</span> spot level</span>
        </div>
      </div>
      <div style={{ flex: 1, position: "relative" }}>
        {loading && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#aaa" }}>
            Loading topo data…
          </div>
        )}
        {error && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#f66" }}>
            {error}
          </div>
        )}
        <canvas
          ref={canvasRef}
          style={{ width: "100%", height: "100%", cursor: "grab", display: "block" }}
        />
      </div>
    </div>
  );
}
