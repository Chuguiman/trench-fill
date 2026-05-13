'use client';

import { useEffect, useState, useRef, useCallback } from 'react';

type Pt = { x: number; y: number; z?: number };
type BBox = { minX: number; maxX: number; minY: number; maxY: number };
type VB   = { x: number; y: number; w: number; h: number };

const PALETTE = [
  '#e74c3c','#3498db','#2ecc71','#f39c12',
  '#9b59b6','#1abc9c','#e67e22','#e91e63',
  '#00bcd4','#ff5722','#8bc34a','#607d8b',
];

function calcBBox(entities: any[]): BBox {
  const bb = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity };
  const upd = (x: number, y: number) => {
    bb.minX = Math.min(bb.minX, x); bb.maxX = Math.max(bb.maxX, x);
    bb.minY = Math.min(bb.minY, y); bb.maxY = Math.max(bb.maxY, y);
  };
  entities.forEach((e: any) => {
    if (e.vertices) e.vertices.forEach((v: Pt) => upd(v.x, v.y));
    if (e.center) { const r = e.radius || 0; upd(e.center.x - r, e.center.y - r); upd(e.center.x + r, e.center.y + r); }
    if (e.startPoint) upd(e.startPoint.x, e.startPoint.y);
    if (e.position)   upd(e.position.x, e.position.y);
  });
  if (!isFinite(bb.minX)) return { minX: 0, maxX: 100, minY: 0, maxY: 100 };
  return bb;
}

function makeTransform(bb: BBox, svgW: number, svgH: number) {
  const dw = bb.maxX - bb.minX || 1;
  const dh = bb.maxY - bb.minY || 1;
  const scale = Math.min(svgW / dw, svgH / dh) * 0.95;
  const offX = (svgW - dw * scale) / 2;
  const offY = (svgH - dh * scale) / 2;
  return {
    scale,
    tx: (x: number) => (x - bb.minX) * scale + offX,
    ty: (y: number) => svgH - ((y - bb.minY) * scale + offY),
  };
}

function arcPathStr(e: any, tx: (x:number)=>number, ty: (y:number)=>number, scale: number): string {
  const { center: c, radius: r, startAngle: sa, endAngle: ea } = e;
  let span = ea - sa;
  while (span < 0) span += 2 * Math.PI;
  while (span > 2 * Math.PI) span -= 2 * Math.PI;
  if (span < 0.001) return '';
  const x1 = c.x + r * Math.cos(sa), y1 = c.y + r * Math.sin(sa);
  const x2 = c.x + r * Math.cos(ea), y2 = c.y + r * Math.sin(ea);
  const sr = r * scale;
  const large = span > Math.PI ? 1 : 0;
  return `M ${tx(x1)} ${ty(y1)} A ${sr} ${sr} 0 ${large} 0 ${tx(x2)} ${ty(y2)}`;
}

function renderEntity(e: any, color: string, tx: (x:number)=>number, ty: (y:number)=>number, scale: number, idx: number) {
  const stroke = color;
  const fill   = 'none';
  const sw     = Math.max(0.5, 1 / scale * 2);

  switch (e.type) {
    case 'LINE': {
      const [p0, p1] = e.vertices as Pt[];
      if (!p0 || !p1) return null;
      return <line key={idx} x1={tx(p0.x)} y1={ty(p0.y)} x2={tx(p1.x)} y2={ty(p1.y)} stroke={stroke} strokeWidth={sw} />;
    }
    case 'LWPOLYLINE':
    case 'POLYLINE': {
      const pts = (e.vertices as Pt[]).map(v => `${tx(v.x)},${ty(v.y)}`).join(' ');
      return e.shape
        ? <polygon key={idx} points={pts} stroke={stroke} strokeWidth={sw} fill={fill} />
        : <polyline key={idx} points={pts} stroke={stroke} strokeWidth={sw} fill={fill} />;
    }
    case 'CIRCLE':
      return <circle key={idx} cx={tx(e.center.x)} cy={ty(e.center.y)} r={e.radius * scale} stroke={stroke} strokeWidth={sw} fill={fill} />;
    case 'ARC': {
      const d = arcPathStr(e, tx, ty, scale);
      return d ? <path key={idx} d={d} stroke={stroke} strokeWidth={sw} fill={fill} /> : null;
    }
    case 'TEXT': {
      const pt = e.startPoint || e.position;
      if (!pt) return null;
      const fs = Math.max(1, (e.textHeight || 1) * scale);
      return (
        <text key={idx} x={tx(pt.x)} y={ty(pt.y)} fill={stroke} fontSize={fs} fontFamily="monospace">
          {e.text}
        </text>
      );
    }
    default:
      return null;
  }
}

export default function DXFSVGViewer({ filename, label, layerId }: { filename: string; label: string; layerId?: string }) {
  const [entities,     setEntities]     = useState<any[]>([]);
  const [layers,       setLayers]       = useState<string[]>([]);
  const [activeLayers, setActiveLayers] = useState<Set<string>>(new Set());
  const [layerColors,  setLayerColors]  = useState<Record<string, string>>({});
  const [bbox,         setBbox]         = useState<BBox>({ minX: 0, maxX: 100, minY: 0, maxY: 100 });
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState<string | null>(null);

  const [interpCells,  setInterpCells]  = useState<any[]>([]);
  const [showInterp,   setShowInterp]   = useState(false);

  const svgRef   = useRef<SVGSVGElement>(null);
  const [vb, setVb] = useState<VB>({ x: 0, y: 0, w: 800, h: 600 });
  const dragRef  = useRef<{ startX: number; startY: number; startVb: VB } | null>(null);

  useEffect(() => {
    setLoading(true); setEntities([]); setError(null);
    let cancelled = false;

    // Load DXF
    fetch(`/api/dxf/${filename}`)
      .then(async r => {
        if (!r.ok) {
          const err = await r.text();
          throw new Error(`API Error: ${r.status} ${err}`);
        }
        return r.text();
      })
      .then(async text => {
        if (!text || text.trim().length === 0) {
          throw new Error('El archivo DXF está vacío');
        }
        const { DxfParser } = await import('dxf-parser');
        const parser = new DxfParser();
        try {
          const parsed = parser.parseSync(text);
          if (cancelled) return;

          const ents: any[] = parsed?.entities || [];
          const bb = calcBBox(ents);
          setBbox(bb);

          const layerSet = new Set<string>(ents.map((e: any) => e.layer || '0'));
          const layerArr = Array.from(layerSet).sort();
          const colors: Record<string, string> = {};
          layerArr.forEach((l, i) => { 
            if (l === 'EXP-RETAINING WALLS') {
              colors[l] = '#7E01FD';
            } else {
              colors[l] = PALETTE[i % PALETTE.length]; 
            }
          });

          setEntities(ents);
          setLayers(layerArr);
          setActiveLayers(new Set(layerArr));
          setLayerColors(colors);

          const dw = bb.maxX - bb.minX;
          const dh = bb.maxY - bb.minY;
          setVb({ x: bb.minX - dw * 0.025, y: bb.minY - dh * 0.025, w: dw * 1.05, h: dh * 1.05 });
          setLoading(false);
        } catch (pe: any) {
          throw new Error(`Error al procesar DXF: ${pe.message}`);
        }
      })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false); } });

    // Load Interpolated JSON if exists
    const interpUrl = layerId 
      ? `/exports/${layerId}_interp.json`
      : `/exports/${filename.replace('.dxf', '')}_interp.json`;

    fetch(interpUrl)
      .then(r => r.json())
      .then(data => {
        if (!cancelled && data.cells) {
          setInterpCells(data.cells);
          setShowInterp(true);
        }
      })
      .catch(() => {
        // Fallback for known UUID filename or if derivation failed
        const fallbackId = 'a7bd1c9b-fe3f-403d-91cd-9e85d8bc80cd';
        if (filename.includes('Civils') || layerId === fallbackId || filename.includes('a7bd1c9b')) {
             fetch(`/exports/${fallbackId}_interp.json`)
             .then(r => r.json())
             .then(data => { if (!cancelled && data.cells) { setInterpCells(data.cells); setShowInterp(true); } })
             .catch(() => {});
        }
      });

    return () => { cancelled = true; };
  }, [filename]);

  const toggleLayer = useCallback((l: string) => {
    setActiveLayers(prev => {
      const next = new Set(prev);
      next.has(l) ? next.delete(l) : next.add(l);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    setActiveLayers(prev => prev.size === layers.length ? new Set() : new Set(layers));
  }, [layers]);

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    setVb(prev => {
      const factor = e.deltaY > 0 ? 1.15 : 0.87;
      const ratioX = mouseX / rect.width;
      const ratioY = mouseY / rect.height;
      const nw = prev.w * factor;
      const nh = prev.h * factor;
      return {
        x: prev.x + (prev.w - nw) * ratioX,
        y: prev.y + (prev.h - nh) * ratioY,
        w: nw, h: nh,
      };
    });
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    dragRef.current = { startX: e.clientX, startY: e.clientY, startVb: vb };
  }, [vb]);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragRef.current) return;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const { startX, startY, startVb } = dragRef.current;
    const dx = (e.clientX - startX) / rect.width  * startVb.w;
    const dy = (e.clientY - startY) / rect.height * startVb.h;
    setVb({ ...startVb, x: startVb.x - dx, y: startVb.y + dy });
  }, []);

  const onMouseUp = useCallback(() => { dragRef.current = null; }, []);

  const onReset = useCallback(() => {
    const dw = bbox.maxX - bbox.minX;
    const dh = bbox.maxY - bbox.minY;
    setVb({ x: bbox.minX - dw * 0.025, y: bbox.minY - dh * 0.025, w: dw * 1.05, h: dh * 1.05 });
  }, [bbox]);

  // Build SVG elements using a stable transform based on viewBox
  const svgW = 800, svgH = 600;
  const { scale, tx, ty } = makeTransform(
    { minX: vb.x, maxX: vb.x + vb.w, minY: vb.y, maxY: vb.y + vb.h },
    svgW, svgH
  );

  const visibleEntities = entities.filter(e => activeLayers.has(e.layer || '0'));

  return (
    <div style={{ display: 'flex', height: '100%', fontFamily: 'monospace', background: '#0a0a0a', color: '#ccc' }}>
      {/* Sidebar */}
      <div style={{ width: 200, flexShrink: 0, borderRight: '1px solid #333', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '8px 10px', borderBottom: '1px solid #333', fontSize: 11, color: '#888' }}>
          {label}
        </div>
        <div style={{ padding: '5px 8px', borderBottom: '1px solid #333' }}>
          <button
            onClick={toggleAll}
            style={{ width: '100%', padding: '3px 0', background: '#1a1a1a', border: '1px solid #444', color: '#aaa', cursor: 'pointer', fontSize: 10 }}
          >
            {activeLayers.size === layers.length ? 'Ocultar todo' : 'Mostrar todo'}
          </button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
          {interpCells.length > 0 && (
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 10px', cursor: 'pointer', background: '#1a1a1a', marginBottom: 4 }}>
              <input type="checkbox" checked={showInterp} onChange={() => setShowInterp(!showInterp)} />
              <span style={{ fontSize: 10, fontWeight: 'bold', color: '#f39c12' }}>Malla 1x1m (Interpolada)</span>
            </label>
          )}
          {layers.map(l => (
            <label key={l} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 10px', cursor: 'pointer', opacity: activeLayers.has(l) ? 1 : 0.4 }}>
              <input type="checkbox" checked={activeLayers.has(l)} onChange={() => toggleLayer(l)} style={{ accentColor: layerColors[l] }} />
              <span style={{ width: 10, height: 10, background: layerColors[l], flexShrink: 0, borderRadius: 1 }} />
              <span style={{ fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l}</span>
            </label>
          ))}
        </div>
        <div style={{ padding: '6px 8px', borderTop: '1px solid #333', fontSize: 9, color: '#555' }}>
          {visibleEntities.length} / {entities.length} entidades
        </div>
        <div style={{ padding: '4px 8px', borderTop: '1px solid #222' }}>
          <button onClick={onReset} style={{ width: '100%', padding: '3px 0', background: '#111', border: '1px solid #333', color: '#888', cursor: 'pointer', fontSize: 10 }}>
            Reset zoom
          </button>
        </div>
      </div>

      {/* SVG area */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#0a0a0a' }}>
        {loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#888', fontSize: 13 }}>
            Cargando {filename}…
          </div>
        )}
        {error && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#f66', fontSize: 12, padding: 20 }}>
            Error: {error}
          </div>
        )}
        {!loading && !error && (
          <svg
            ref={svgRef}
            width="100%" height="100%"
            viewBox={`0 0 ${svgW} ${svgH}`}
            style={{ cursor: dragRef.current ? 'grabbing' : 'grab', display: 'block' }}
            onWheel={onWheel}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
          >
            {/* Interpolated Grid */}
            {showInterp && interpCells.map((c, i) => {
              if (c.z === null) return null;
              const isReal = c.type === 'real';
              const dotSize = isReal ? 1.5 : 0.8;
              const dotColor = '#4E9654';
              const textColor = isReal ? '#f39c12' : '#555';
              const opacity = isReal ? 1 : 0.6;
              
              return (
                <g key={`cell-${i}`}>
                  <circle 
                    cx={tx(c.x)} 
                    cy={ty(c.y)} 
                    r={dotSize * scale * 0.1} 
                    fill={dotColor} 
                    fillOpacity={opacity}
                  />
                  {scale > 10 && (
                    <text 
                      x={tx(c.x)} 
                      y={ty(c.y) - 2} 
                      fontSize={Math.max(2, 0.4 * scale)} 
                      fill={textColor} 
                      fillOpacity={opacity} 
                      textAnchor="middle"
                      style={{ pointerEvents: 'none' }}
                    >
                      {c.z.toFixed(2)}
                    </text>
                  )}
                </g>
              );
            })}

            {layers.map(l => (
              activeLayers.has(l) && (
                <g key={l}>
                  {entities
                    .filter(e => (e.layer || '0') === l)
                    .map((e, i) => renderEntity(e, layerColors[l] || '#888', tx, ty, scale, i))}
                </g>
              )
            ))}
          </svg>
        )}
        <div style={{ position: 'absolute', bottom: 6, right: 8, fontSize: 9, color: '#444' }}>
          scroll: zoom · drag: pan
        </div>
      </div>
    </div>
  );
}
