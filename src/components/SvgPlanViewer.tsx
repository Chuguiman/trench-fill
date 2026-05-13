"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export default function SvgPlanViewer({ url, onClose, layerId }: { url: string; onClose: () => void; layerId?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);

  const [interpCells, setInterpCells] = useState<any[]>([]);
  const [showInterp, setShowInterp]   = useState(false);
  const [meta, setMeta] = useState<{ wx0: number; wy0: number; scale: number; hsvg: number; pad: number } | null>(null);
  const [hoveredCell, setHoveredCell] = useState<any | null>(null);

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
        // Extract metadata
        const mWx0 = text.match(/data-wx0=["']([^"']+)["']/);
        const mWy0 = text.match(/data-wy0=["']([^"']+)["']/);
        const mScale = text.match(/data-scale=["']([^"']+)["']/);
        const mHsvg = text.match(/data-hsvg=["']([^"']+)["']/);
        const mPad = text.match(/data-pad=["']([^"']+)["']/);

        if (mWx0 && mWy0 && mScale && mHsvg) {
          setMeta({
            wx0: parseFloat(mWx0[1]),
            wy0: parseFloat(mWy0[1]),
            scale: parseFloat(mScale[1]),
            hsvg: parseFloat(mHsvg[1]),
            pad: mPad ? parseFloat(mPad[1]) : 30,
          });
        }

        // Strip xml declaration and set responsive attributes
        const cleaned = text
          .replace(/<\?xml[^?]*\?>\s*/i, '')
          .replace(/width=["'][^"']*["']/, 'width="100%"')
          .replace(/height=["'][^"']*["']/, 'height="100%"');
        setSvgContent(cleaned);
        setLoading(false);
      })
      .catch(e => { setError(String(e)); setLoading(false); });

    if (layerId) {
      fetch(`/exports/${layerId}_interp.json`)
        .then(r => r.json())
        .then(data => {
          if (data.cells) setInterpCells(data.cells);
        })
        .catch(() => {});
    }
  }, [url, layerId]);

  // Apply CSS transform to inner wrapper
  const applyTransform = useCallback(() => {
    const el = containerRef.current?.querySelector<HTMLElement>('.svg-inner-wrapper');
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
    <div style={{ position:"fixed", inset:0, background:"#212830", zIndex:1000, display:"flex", flexDirection:"column" }}>
      <style>{`
        .svg-inner-wrapper svg rect[fill="#0a0a0a"], 
        .svg-inner-wrapper svg rect[fill="#0A0A0A"],
        .svg-inner-wrapper svg rect[fill="#000000"],
        .svg-inner-wrapper svg rect[fill="#000"] { 
          fill: #212830 !important; 
        }
        .svg-inner-wrapper svg path[data-layer*="RETAINING WALLS"] { 
          stroke: #7E01FD !important; 
          opacity: 1 !important; 
          stroke-width: 0.5 !important;
        }
        .svg-inner-wrapper svg g#survey-points rect,
        .svg-inner-wrapper svg g[id*="layer-"] rect { 
          fill: #4E9654 !important; 
        }
      `}</style>
      {/* Toolbar */}
      <div style={{ display:"flex", alignItems:"center", gap:10, padding:"8px 16px", background:"#111", borderBottom:"1px solid #222", flexShrink:0, fontFamily:"monospace" }}>
        <span style={{ fontSize:12, color:"#f5c518", fontWeight:"bold" }}>⬡ SVG Plan — exact DXF · BNG EPSG:27700</span>
        
        {interpCells.length > 0 && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 8px', background: '#1a1a1a', border: '1px solid #333', borderRadius: 4, cursor: 'pointer', marginLeft: 10 }}>
            <input type="checkbox" checked={showInterp} onChange={() => setShowInterp(!showInterp)} />
            <span style={{ fontSize: 10, color: '#f39c12', fontWeight: 'bold' }}>Mostrar Malla 1x1m</span>
          </label>
        )}

        <span style={{ flex:1 }} />
        <button style={{ padding:"4px 10px", background:"#1a1a1a", color:"#888", border:"1px solid #333", borderRadius:4, cursor:"pointer", fontSize:11 }}
          onClick={fitView}>⌂ Fit</button>
        <a href={url} download style={{ padding:"4px 10px", background:"#14532d", color:"#4ADE80", border:"1px solid #166534", borderRadius:4, fontSize:11, textDecoration:"none" }}>⬇ Download</a>
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
            className="svg-inner-wrapper"
            style={{ transformOrigin:"0 0", width:"100%", height:"100%", userSelect:"none", position: 'relative' }}
          >
            <div
              style={{ position: 'absolute', inset: 0 }}
              dangerouslySetInnerHTML={{ __html: svgContent }}
            />
            {showInterp && meta && (
              <svg 
                style={{ position: 'absolute', inset: 0 }} 
                width="100%"
                height="100%"
                viewBox={`0 0 2400 ${meta.hsvg}`}
              >
                {interpCells.map((c, i) => {
                  if (c.z === null) return null;
                  const isReal = c.type === 'real';
                  
                  const sx = meta.pad + (c.x - meta.wx0) * meta.scale;
                  const sy = meta.hsvg - meta.pad - (c.y - meta.wy0) * meta.scale;
                  
                  // Interaction area
                  const dotSize = isReal ? 1.0 : 0.6;
                  const hitSize = 2.0;

                  return (
                    <g 
                      key={`interp-${i}`}
                      onMouseEnter={() => setHoveredCell(c)}
                      onMouseLeave={() => setHoveredCell(null)}
                    >
                      <rect 
                        x={sx - hitSize/2} 
                        y={sy - hitSize/2} 
                        width={hitSize} 
                        height={hitSize} 
                        fill="transparent"
                        style={{ cursor: 'crosshair', pointerEvents: 'all' }}
                      />
                      <rect 
                        x={sx - dotSize/2} 
                        y={sy - dotSize/2} 
                        width={dotSize} 
                        height={dotSize} 
                        fill="#4E9654" 
                        fillOpacity={isReal ? 1 : 0.4} 
                        style={{ pointerEvents: 'none' }}
                      />
                    </g>
                  );
                })}
              </svg>
            )}

            {hoveredCell && (
               <div style={{
                 position: 'absolute',
                 left: 10,
                 top: 10,
                 background: 'rgba(0,0,0,0.85)',
                 color: '#fff',
                 padding: '8px 12px',
                 borderRadius: 4,
                 fontSize: 11,
                 fontFamily: 'monospace',
                 border: '1px solid #444',
                 zIndex: 10,
                 pointerEvents: 'none',
                 boxShadow: '0 4px 10px rgba(0,0,0,0.5)'
               }}>
                 <div style={{ color: '#f39c12', fontWeight: 'bold', marginBottom: 4 }}>
                   {hoveredCell.type === 'real' ? 'PUNTO REAL' : 'PUNTO INTERPOLADO'}
                 </div>
                 <div>E (X): {hoveredCell.x.toFixed(3)}</div>
                 <div>N (Y): {hoveredCell.y.toFixed(3)}</div>
                 <div style={{ fontSize: 16, marginTop: 4, color: '#4ADE80' }}>
                   Z: {hoveredCell.z.toFixed(3)}m
                 </div>
               </div>
            )}
          </div>
        )}
      </div>

      <div style={{ padding:"4px 16px", background:"#0d0d0d", borderTop:"1px solid #1a1a1a", fontFamily:"monospace", fontSize:10, color:"#333" }}>
        Scroll to zoom · Drag to pan · ⌂ Fit to reset
      </div>
    </div>
  );
}
