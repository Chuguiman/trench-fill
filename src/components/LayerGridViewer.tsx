"use client";

import { useEffect, useRef, useState, useCallback } from "react";

type Cell = { x: number; y: number; z: number; is_interp: boolean };
type Poly = { dxf_layer: string; elevation: number | null; coords: [number, number, number][] };
type Data = { grid: Cell[]; polylines: Poly[] };

function elevColor(z: number, zMin: number, zMax: number): [number, number, number] {
  const t = zMax === zMin ? 0.5 : Math.max(0, Math.min(1, (z - zMin) / (zMax - zMin)));
  // Blue → Cyan → Green → Yellow → Red
  const stops: [number, number, number][] = [
    [0, 0, 180],
    [0, 160, 220],
    [0, 200, 80],
    [240, 220, 0],
    [220, 0, 0],
  ];
  const seg = (stops.length - 1) * t;
  const i = Math.min(Math.floor(seg), stops.length - 2);
  const f = seg - i;
  const a = stops[i], b = stops[i + 1];
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

export default function LayerGridViewer({ layerId, onClose }: { layerId: string; onClose: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [data, setData]       = useState<Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [info, setInfo]       = useState<string>("");
  const [fitKey, setFitKey]   = useState(0);

  // transform state: world→canvas  canvasXY = worldXY * scale + (tx,ty)
  const tx    = useRef(0);
  const ty    = useRef(0);
  const scale = useRef(8);
  const drag  = useRef<{ down: boolean; lx: number; ly: number }>({ down: false, lx: 0, ly: 0 });

  // Load data
  useEffect(() => {
    setLoading(true);
    fetch(`/api/layers/${layerId}/grid`)
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); return; }
        setData(d);
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [layerId]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(0, 0, W, H);

    const sc = scale.current, ox = tx.current, oy = ty.current;

    // world→canvas
    const wx = (x: number) => x * sc + ox;
    const wy = (y: number) => -y * sc + oy;   // y-flip (world Y up, canvas Y down)

    const { grid, polylines } = data;
    if (!grid.length) return;

    const zs = grid.map(c => c.z);
    const zMin = Math.min(...zs), zMax = Math.max(...zs);

    // ── 1. Cells (exact 1m×1m squares) ───────────────────────────────────────
    for (const c of grid) {
      const cx = wx(c.x), cy = wy(c.y);
      const [r, g, b] = elevColor(c.z, zMin, zMax);
      // Interpolated cells slightly dimmer
      const alpha = c.is_interp ? 0.72 : 1.0;
      ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
      ctx.fillRect(cx, cy, sc, sc);
    }

    // ── 2. Grid lines (thin, only when cells are large enough) ───────────────
    if (sc >= 6) {
      ctx.strokeStyle = "rgba(0,0,0,0.3)";
      ctx.lineWidth = 0.5;
      for (const c of grid) {
        ctx.strokeRect(wx(c.x) + 0.25, wy(c.y) + 0.25, sc - 0.5, sc - 0.5);
      }
    }

    // ── 3. Elevation labels ───────────────────────────────────────────────────
    if (sc >= 12) {
      const fs = Math.min(sc * 0.38, 11);
      ctx.font = `${fs}px monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (const c of grid) {
        const cx = wx(c.x) + sc / 2;
        const cy = wy(c.y) + sc / 2;
        ctx.shadowColor = "rgba(0,0,0,0.9)";
        ctx.shadowBlur = 2;
        ctx.fillStyle = c.is_interp ? "#ffffff" : "#86efac";
        ctx.fillText(c.z.toFixed(2), cx, cy);
      }
      ctx.shadowBlur = 0;
      ctx.textAlign = "start";
      ctx.textBaseline = "alphabetic";
    }

    // ── 4. Polylines (walls / barriers) — drawn last, always on top ──────────
    for (const poly of polylines) {
      if (!poly.coords || poly.coords.length < 2) continue;
      ctx.beginPath();
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = Math.max(1, sc * 0.12);
      ctx.lineJoin = "round";
      poly.coords.forEach(([px, py], i) => {
        const cx = wx(px), cy = wy(py);
        i === 0 ? ctx.moveTo(cx, cy) : ctx.lineTo(cx, cy);
      });
      ctx.stroke();
    }

    // ── 5. Legend ─────────────────────────────────────────────────────────────
    const lw = 12, lh = 120, lx = W - 36, ly = 20;
    const grad = ctx.createLinearGradient(0, ly, 0, ly + lh);
    grad.addColorStop(0,   "rgb(220,0,0)");
    grad.addColorStop(0.25,"rgb(240,220,0)");
    grad.addColorStop(0.5, "rgb(0,200,80)");
    grad.addColorStop(0.75,"rgb(0,160,220)");
    grad.addColorStop(1,   "rgb(0,0,180)");
    ctx.fillStyle = grad;
    ctx.fillRect(lx, ly, lw, lh);
    ctx.strokeStyle = "#333"; ctx.lineWidth = 1;
    ctx.strokeRect(lx, ly, lw, lh);
    ctx.fillStyle = "#aaa"; ctx.font = "9px monospace"; ctx.textAlign = "right";
    ctx.fillText(zMax.toFixed(2) + "m", lx - 3, ly + 5);
    ctx.fillText(zMin.toFixed(2) + "m", lx - 3, ly + lh);
    ctx.textAlign = "start";

  }, [data]);

  // Fit-to-view when data loads or fit button pressed
  useEffect(() => {
    if (!data?.grid.length || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const xs = data.grid.map(c => c.x), ys = data.grid.map(c => c.y);
    const x0 = Math.min(...xs), x1 = Math.max(...xs) + 1;
    const y0 = Math.min(...ys), y1 = Math.max(...ys) + 1;
    const gw = x1 - x0, gh = y1 - y0;
    const pad = 32;
    const sc = Math.max(1, Math.min(60,
      Math.floor(Math.min((canvas.width - pad * 2) / gw, (canvas.height - pad * 2) / gh))
    ));
    scale.current = sc;
    tx.current = pad - x0 * sc;
    ty.current = pad + y1 * sc;
    draw();
  }, [data, draw, fitKey]);

  // Redraw on transform change
  const redraw = useCallback(() => draw(), [draw]);

  // Resize observer
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ro = new ResizeObserver(() => {
      canvas.width  = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
      redraw();
    });
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [redraw]);

  // Mouse: pan
  function onMouseDown(e: React.MouseEvent) {
    drag.current = { down: true, lx: e.clientX, ly: e.clientY };
  }
  function onMouseMove(e: React.MouseEvent) {
    if (!drag.current.down) {
      // hover: show cell info
      if (!data || !canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const sc = scale.current, ox = tx.current, oy = ty.current;
      const wx = Math.floor((mx - ox) / sc);
      const wy = Math.floor((oy - my) / sc);
      const cell = data.grid.find(c => c.x === wx && c.y === wy);
      setInfo(cell ? `E ${cell.x}  N ${cell.y}  Z ${cell.z.toFixed(3)}m  ${cell.is_interp ? "(interpolated)" : "(surveyed)"}` : "");
      return;
    }
    const dx = e.clientX - drag.current.lx, dy = e.clientY - drag.current.ly;
    tx.current += dx; ty.current += dy;
    drag.current.lx = e.clientX; drag.current.ly = e.clientY;
    redraw();
  }
  function onMouseUp() { drag.current.down = false; }

  // Wheel: zoom centred on cursor — must be a native listener with passive:false
  // React synthetic wheel events cannot call preventDefault() (passive by default in modern browsers)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2;
      const newSc = Math.max(1, Math.min(200, scale.current * factor));
      tx.current = mx - (mx - tx.current) * (newSc / scale.current);
      ty.current = my - (my - ty.current) * (newSc / scale.current);
      scale.current = newSc;
      draw();
    };
    canvas.addEventListener("wheel", handler, { passive: false });
    return () => canvas.removeEventListener("wheel", handler);
  }, [draw]);

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.92)",
      display: "flex", flexDirection: "column", zIndex: 1000,
    }}>
      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "8px 16px", background: "#111", borderBottom: "1px solid #222",
        flexShrink: 0,
      }}>
        <span style={{ fontFamily: "monospace", fontSize: 12, color: "#f5c518", fontWeight: "bold" }}>▦ Grid Viewer</span>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: "#555" }}>
          {data ? `${data.grid.length.toLocaleString()} cells · ${data.polylines.length} polylines` : ""}
        </span>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: "#4ade80", flex: 1 }}>{info}</span>
        <button
          style={{ padding: "4px 12px", background: "#1a1a1a", color: "#888", border: "1px solid #333", borderRadius: 4, cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}
          onClick={() => setFitKey(k => k + 1)}
          title="Fit to view"
        >⌂ Fit</button>
        <button
          style={{ padding: "4px 12px", background: "#1a0000", color: "#f87171", border: "1px solid #450a0a", borderRadius: 4, cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}
          onClick={onClose}
        >✕ Close</button>
      </div>

      {/* Canvas */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden", touchAction: "none" }}>
        {loading && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#555", fontFamily: "monospace", fontSize: 13 }}>
            Loading grid data…
          </div>
        )}
        {error && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#f87171", fontFamily: "monospace", fontSize: 12, padding: 40, textAlign: "center" }}>
            {error}
          </div>
        )}
        <canvas
          ref={canvasRef}
          style={{ width: "100%", height: "100%", display: "block", cursor: drag.current.down ? "grabbing" : "crosshair" }}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
        />
      </div>

      {/* Scale hint */}
      <div style={{ padding: "4px 16px", background: "#0d0d0d", borderTop: "1px solid #1a1a1a", fontFamily: "monospace", fontSize: 10, color: "#333" }}>
        Scroll to zoom · Drag to pan · Hover cell for coordinates · White lines = walls / polylines · Green labels = surveyed · White labels = interpolated
      </div>
    </div>
  );
}
