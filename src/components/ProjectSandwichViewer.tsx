"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { Layer } from "@/lib/supabase";

type ZDrillResult = {
  layer_id: string;
  name: string;
  category: string | null;
  layer_type: string;
  z: number | null;
  is_interp: boolean | null;
  found: boolean;
};

export default function ProjectSandwichViewer({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [layers, setLayers] = useState<Layer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drill, setDrill] = useState<{ e: number; n: number; results: ZDrillResult[] } | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);

  // Transform state
  const tx = useRef(0);
  const ty = useRef(0);
  const scale = useRef(8);
  const drag = useRef({ down: false, lx: 0, ly: 0 });

  useEffect(() => {
    setLoading(true);
    fetch(`/api/projects/${projectId}/layers`)
      .then(r => r.json())
      .then(d => {
        if (Array.isArray(d)) setLayers(d.filter(l => l.status === "interpolated"));
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [projectId]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#0A0E17";
    ctx.fillRect(0, 0, W, H);

    const sc = scale.current, ox = tx.current, oy = ty.current;
    
    // Legend / Title
    ctx.fillStyle = "#f5c518";
    ctx.font = "bold 12px monospace";
    ctx.fillText("PROJECT SANDWICH VIEWER", 20, 30);
    ctx.font = "10px monospace";
    ctx.fillStyle = "#555";
    ctx.fillText(`${layers.length} active layers · Click point for Z-Drill`, 20, 45);

    // Coordinate helper
    ctx.strokeStyle = "#1a1a1a";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = Math.floor(-ox/sc); x < (W-ox)/sc; x += 100) {
      const sx = x * sc + ox;
      ctx.moveTo(sx, 0); ctx.lineTo(sx, H);
    }
    for (let y = Math.floor((oy-H)/sc); y < oy/sc; y += 100) {
      const sy = -y * sc + oy;
      ctx.moveTo(0, sy); ctx.lineTo(W, sy);
    }
    ctx.stroke();

    if (drill) {
      const sx = drill.e * sc + ox;
      const sy = -drill.n * sc + oy;
      ctx.strokeStyle = "#f5c518";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(sx - 10, sy); ctx.lineTo(sx + 10, sy);
      ctx.moveTo(sx, sy - 10); ctx.lineTo(sx, sy + 10);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(sx, sy, 5, 0, Math.PI * 2);
      ctx.stroke();
    }

  }, [layers, drill]);

  const redraw = useCallback(() => draw(), [draw]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ro = new ResizeObserver(() => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
      redraw();
    });
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [redraw]);

  async function performDrill(mx: number, my: number) {
    const e = (mx - tx.current) / scale.current;
    const n = (ty.current - my) / scale.current;
    
    setDrillLoading(true);
    try {
      const r = await fetch(`/api/projects/${projectId}/z-drill?e=${e}&n=${n}`);
      const data = await r.json();
      if (data.results) {
        setDrill({ e, n, results: data.results });
      }
    } catch (err) {
      console.error(err);
    } finally {
      setDrillLoading(false);
    }
    redraw();
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "#000", display: "flex", zIndex: 2000 }}>
      {/* Sidebar: Layer List & Z-Drill Results */}
      <div style={{ width: 320, background: "#111", borderRight: "1px solid #222", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #222" }}>
          <div style={{ fontSize: 13, fontWeight: "bold", color: "#f5c518", marginBottom: 4 }}>PROJECT LAYERS</div>
          <div style={{ fontSize: 10, color: "#555" }}>{layers.length} layers in sandwich</div>
        </div>

        <div style={{ flex: 1, overflowY: "auto" }}>
          {layers.map(l => (
            <div key={l.id} style={{ padding: "10px 20px", borderBottom: "1px solid #1a1a1a", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#4E9654" }} />
              <div>
                <div style={{ fontSize: 11, color: "#eee" }}>{l.name}</div>
                <div style={{ fontSize: 9, color: "#444" }}>{l.category || "General"}</div>
              </div>
            </div>
          ))}
        </div>

        {drill && (
          <div style={{ height: "50%", borderTop: "2px solid #222", background: "#0a0a0a", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "12px 20px", background: "#111", borderBottom: "1px solid #222", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: 10, color: "#f5c518", fontWeight: "bold" }}>Z-DRILL RESULT</div>
                <div style={{ fontSize: 9, color: "#444" }}>E {drill.e.toFixed(2)} · N {drill.n.toFixed(2)}</div>
              </div>
              <button style={{ background: "none", border: "none", color: "#444", cursor: "pointer", fontSize: 14 }} onClick={() => setDrill(null)}>×</button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "10px 0" }}>
              {drill.results.map(r => (
                <div key={r.layer_id} style={{ padding: "8px 20px", borderBottom: "1px solid #111", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 10, color: "#aaa" }}>{r.name}</div>
                    <div style={{ fontSize: 8, color: "#444" }}>{r.category || "—"}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 14, color: r.found ? "#4ADE80" : "#333", fontWeight: "bold" }}>
                      {r.z !== null ? r.z.toFixed(3) : "—"}
                    </div>
                    {r.is_interp && <div style={{ fontSize: 8, color: "#444" }}>interpolated</div>}
                  </div>
                </div>
              ))}
            </div>
            {/* Visual Section */}
            <div style={{ height: 120, background: "#050505", borderTop: "1px solid #222", padding: "10px 20px", display: "flex", alignItems: "flex-end", gap: 4 }}>
                {drill.results.filter(r => r.found && r.z !== null).map((r, i) => {
                    const minZ = Math.min(...drill.results.map(x => x.z || 9999));
                    const maxZ = Math.max(...drill.results.map(x => x.z || -9999));
                    const h = maxZ === minZ ? 50 : ((r.z! - minZ) / (maxZ - minZ)) * 80 + 10;
                    return (
                        <div key={r.layer_id} style={{ flex: 1, background: "#333", height: `${h}%`, position: "relative" }} title={r.name}>
                            <div style={{ position: "absolute", top: -14, width: "100%", textAlign: "center", fontSize: 8, color: "#666" }}>{r.z?.toFixed(1)}</div>
                        </div>
                    );
                })}
            </div>
          </div>
        )}
      </div>

      {/* Main Viewport */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
        <canvas
          ref={canvasRef}
          style={{ width: "100%", height: "100%", display: "block", cursor: "crosshair" }}
          onClick={e => performDrill(e.clientX - 320, e.clientY)}
          onMouseDown={e => { drag.current = { down: true, lx: e.clientX, ly: e.clientY }; }}
          onMouseMove={e => {
            if (!drag.current.down) return;
            tx.current += e.clientX - drag.current.lx;
            ty.current += e.clientY - drag.current.ly;
            drag.current.lx = e.clientX; drag.current.ly = e.clientY;
            redraw();
          }}
          onMouseUp={() => { drag.current.down = false; }}
        />
        <button
          style={{ position: "absolute", top: 20, right: 20, padding: "8px 20px", background: "#1a0000", color: "#f87171", border: "1px solid #450a0a", borderRadius: 4, cursor: "pointer", fontFamily: "monospace", fontSize: 12 }}
          onClick={onClose}
        >✕ Close Sandwich</button>
        {drillLoading && (
          <div style={{ position: "absolute", bottom: 20, right: 20, background: "#f5c518", color: "#000", padding: "4px 10px", fontSize: 10, fontWeight: "bold", borderRadius: 3 }}>
            DRILLING…
          </div>
        )}
      </div>
    </div>
  );
}
