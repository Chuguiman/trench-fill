#!/usr/bin/env python3
"""
Generate an exact SVG plan from a DXF file.
Focuses on the construction area by using survey points to define bounds.
Maintains exact 1:1 scale and alignment for mesh overlay.
"""
import argparse, math, re, xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import ezdxf

ap = argparse.ArgumentParser()
ap.add_argument('--dxf', required=True)
ap.add_argument('--out', required=True)
args = ap.parse_args()

# ── 1. Parse DXF ──────────────────────────────────────────────────────────────
print(f"Reading {args.dxf}…")
doc = ezdxf.readfile(args.dxf)
msp = doc.modelspace()

# Find project area using survey points (levels)
survey_pts = []
for e in msp:
    if e.dxftype() in ('TEXT', 'MTEXT'):
        try:
            raw = e.text if e.dxftype() == 'MTEXT' else e.dxf.text
            raw = re.sub(r'\\[^;]+;|[{}]', '', raw).strip()
            val = float(raw)
            if 100 < val < 200:
                survey_pts.append((e.dxf.insert.x, e.dxf.insert.y, val))
        except: pass
    elif e.dxftype() == 'POINT':
        if 100 < e.dxf.location.z < 200:
            survey_pts.append((e.dxf.location.x, e.dxf.location.y, e.dxf.location.z))

if not survey_pts:
    # Fallback to general geometry if no levels found
    xs = [e.dxf.start.x for e in msp if e.dxftype() == 'LINE']
    ys = [e.dxf.start.y for e in msp if e.dxftype() == 'LINE']
    WX0, WX1 = min(xs), max(xs)
    WY0, WY1 = min(ys), max(ys)
else:
    pxs = [p[0] for p in survey_pts]
    pys = [p[1] for p in survey_pts]
    WX0, WX1 = np.percentile(pxs, 0.5), np.percentile(pxs, 99.5)
    WY0, WY1 = np.percentile(pys, 0.5), np.percentile(pys, 99.5)

# Tight Construction Buffer (15m)
WX0 -= 15; WX1 += 15; WY0 -= 15; WY1 += 15
print(f"  Project Area: E=[{WX0:.1f},{WX1:.1f}] N=[{WY0:.1f},{WY1:.1f}]")

# Detect unit scaling (BNG is metres, so > 1M usually means mm)
COORD_SCALE = 0.001 if max(abs(WX0), abs(WX1)) > 1_000_000 else 1.0
if COORD_SCALE != 1.0:
    WX0, WX1, WY0, WY1 = WX0*0.001, WX1*0.001, WY0*0.001, WY1*0.001
    survey_pts = [(p[0]*0.001, p[1]*0.001, p[2]) for p in survey_pts]

# ── 2. Collect Geometry ───────────────────────────────────────────────────────
polylines = []
ARC_SEGS = 32

def in_bounds(pts):
    return any(WX0 <= p[0] <= WX1 and WY0 <= p[1] <= WY1 for p in pts)

def collect_entity(e):
    layer = getattr(e.dxf, 'layer', '0')
    if e.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
        try:
            pts = [(p[0] * COORD_SCALE, p[1] * COORD_SCALE) for p in e.get_points()]
            if len(pts) >= 2 and in_bounds(pts):
                closed = bool(getattr(e, 'closed', False) or getattr(e.dxf, 'flags', 0) & 1)
                polylines.append((layer, pts, closed))
        except: pass
    elif e.dxftype() == 'LINE':
        pts = [(e.dxf.start.x * COORD_SCALE, e.dxf.start.y * COORD_SCALE),
               (e.dxf.end.x * COORD_SCALE, e.dxf.end.y * COORD_SCALE)]
        if in_bounds(pts): polylines.append((layer, pts, False))

for e in msp:
    if e.dxftype() == 'INSERT':
        try:
            for ve in e.virtual_entities(): collect_entity(ve)
        except: pass
    else: collect_entity(e)

# ── 3. Transform ──────────────────────────────────────────────────────────────
PAD = 40
W_SVG = 2400
scale = (W_SVG - 2 * PAD) / (WX1 - WX0)
H_SVG = int((WY1 - WY0) * scale) + 2 * PAD

def sx(x): return PAD + (x - WX0) * scale
def sy(y): return H_SVG - PAD - (y - WY0) * scale

# ── 4. Build SVG ──────────────────────────────────────────────────────────────
svg = ET.Element('svg', {
    'xmlns': 'http://www.w3.org/2000/svg',
    'width': str(W_SVG), 'height': str(H_SVG),
    'viewBox': f'0 0 {W_SVG} {H_SVG}',
    'data-wx0': f'{WX0:.6f}', 'data-wy0': f'{WY0:.6f}',
    'data-scale': f'{scale:.8f}', 'data-hsvg': f'{H_SVG}', 'data-pad': f'{PAD}',
})

ET.SubElement(svg, 'rect', {'width': str(W_SVG), 'height': str(H_SVG), 'fill': '#212830'})

# Drawing paths
for layer, pts, closed in polylines:
    color = '#ffffff'
    opacity = '0.6'
    if 'RETAINING WALLS' in layer.upper():
        color = '#7E01FD'
        opacity = '1.0'
    
    d = ' '.join(f"{'M' if i==0 else 'L'}{sx(p[0]):.2f},{sy(p[1]):.2f}" for i, p in enumerate(pts))
    if closed: d += ' Z'
    ET.SubElement(svg, 'path', {
        'd': d, 
        'data-layer': layer, 
        'stroke': color, 
        'stroke-width': '0.3', 
        'fill': 'none', 
        'opacity': opacity
    })

# Survey markers
g_pts = ET.SubElement(svg, 'g', {'id': 'survey-points'})
for px, py, pz in survey_pts:
    if WX0 <= px <= WX1 and WY0 <= py <= WY1:
        cx, cy = sx(px), sy(py)
        ET.SubElement(g_pts, 'rect', {
            'x': f'{cx-0.8:.2f}', 'y': f'{cy-0.8:.2f}',
            'width': '1.6', 'height': '1.6', 'fill': '#4E9654', 'stroke': '#000', 'stroke-width': '0.2'
        })

# ── 5. Write ──────────────────────────────────────────────────────────────────
tree = ET.ElementTree(svg)
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
tree.write(str(out), xml_declaration=True, encoding='unicode')
print(f"  Done: {out} ({out.stat().st_size//1024} KB)")
