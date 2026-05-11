"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export default function SvgPlanViewer({ url, onClose }: { url: string; onClose: () => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);

  // transform state
  const tx    = useRef(0);
  const ty    = useRef(0);
  const scale = useRef(1);
  const drag  = useRef({ down: false, lx: 0, ly: 0 });

  // Fetch SVG as text and embed inline
  useEffect(() => {
    setLoading(true);
    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text(); })
      .then(text => {
        // Strip xml declaration and set responsive attributes
        const cleaned = text
          .replace(/<\?xml[^?]*\?>\s*/i, '')
          .replace(/width=["'][^"']*["']/, 'width="100%"')
          .replace(/height=["'][^"']*["']/, 'height="100%"');
        setSvgContent(cleaned);
        setLoading(false);
      })
      .catch(e => { setError(String(e)); setLoading(false); });
  }, [url]);

  // Apply CSS transform to inner wrapper
  const applyTransform = useCallback(() => {
    const el = containerRef.current?.querySelector<HTMLElement>('.svg-inner');
    if (el) el.style.transform = `translate(${tx.current}px,${ty.current}px) scale(${scale.current})`;
  }, []);

  // Fit to view after SVG loads
  useEffect(() => {
    if (!svgContent) return;
    tx.current = 0; ty.current = 0; scale.current = 1;
    applyTransform();
  }, [svgContent, applyTransform]);

  // Non-passive wheel zoom
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2;
      const newSc = Math.max(0.05, Math.min(50, scale.current * factor));
      tx.current = mx - (mx - tx.current) * (newSc / scale.current);
      ty.current = my - (my - ty.current) * (newSc / scale.current);
      scale.current = newSc;
      applyTransform();
    };
    el.addEventListener('wheel', handler, { passive: false });
    return () => el.removeEventListener('wheel', handler);
  }, [applyTransform]);

  function onMouseDown(e: React.MouseEvent) {
    drag.current = { down: true, lx: e.clientX, ly: e.clientY };
  }
  function onMouseMove(e: React.MouseEvent) {
    if (!drag.current.down) return;
    tx.current += e.clientX - drag.current.lx;
    ty.current += e.clientY - drag.current.ly;
    drag.current.lx = e.clientX; drag.current.ly = e.clientY;
    applyTransform();
  }
  function onMouseUp() { drag.current.down = false; }

  function fitView() {
    tx.current = 0; ty.current = 0; scale.current = 1;
    applyTransform();
  }

  return (
    <div style={{ position:"fixed", inset:0, background:"#0a0a0a", zIndex:1000, display:"flex", flexDirection:"column" }}>
      {/* Toolbar */}
      <div style={{ display:"flex", alignItems:"center", gap:10, padding:"8px 16px", background:"#111", borderBottom:"1px solid #222", flexShrink:0, fontFamily:"monospace" }}>
        <span style={{ fontSize:12, color:"#f5c518", fontWeight:"bold" }}>⬡ SVG Plan — exact DXF · BNG EPSG:27700</span>
        <span style={{ flex:1 }} />
        <button style={{ padding:"4px 10px", background:"#1a1a1a", color:"#888", border:"1px solid #333", borderRadius:4, cursor:"pointer", fontSize:11 }}
          onClick={fitView}>⌂ Fit</button>
        <a href={url} download style={{ padding:"4px 10px", background:"#14532d", color:"#4ade80", border:"1px solid #166534", borderRadius:4, fontSize:11, textDecoration:"none" }}>⬇ Download</a>
        <button style={{ padding:"4px 10px", background:"#1a0000", color:"#f87171", border:"1px solid #450a0a", borderRadius:4, cursor:"pointer", fontSize:11 }}
          onClick={onClose}>✕ Close</button>
      </div>

      {/* SVG canvas */}
      <div
        ref={containerRef}
        style={{ flex:1, overflow:"hidden", cursor: drag.current.down ? "grabbing" : "grab", touchAction:"none", position:"relative" }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        {loading && (
          <div style={{ position:"absolute", inset:0, display:"flex", alignItems:"center", justifyContent:"center", color:"#555", fontFamily:"monospace", fontSize:13 }}>
            Loading plan…
          </div>
        )}
        {error && (
          <div style={{ position:"absolute", inset:0, display:"flex", alignItems:"center", justifyContent:"center", color:"#f87171", fontFamily:"monospace", fontSize:12 }}>
            {error}
          </div>
        )}
        {svgContent && (
          <div
            className="svg-inner"
            style={{ transformOrigin:"0 0", width:"100%", height:"100%", userSelect:"none" }}
            dangerouslySetInnerHTML={{ __html: svgContent }}
          />
        )}
      </div>

      <div style={{ padding:"4px 16px", background:"#0d0d0d", borderTop:"1px solid #1a1a1a", fontFamily:"monospace", fontSize:10, color:"#333" }}>
        Scroll to zoom · Drag to pan · ⌂ Fit to reset
      </div>
    </div>
  );
}
