#!/usr/bin/env python3
"""
Generate an exact SVG plan from a DXF file.
World bounds from DXF $EXTMIN/$EXTMAX — every polyline included.
Survey points coloured by elevation. Exact BNG float coordinates.

Usage:
  python3 scripts/gen_svg.py --dxf <file.dxf> --out <output.svg>
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

# World bounds from DXF header — fall back to vertex scan if header invalid
extmin = doc.header.get('$EXTMIN', (0, 0, 0))
extmax = doc.header.get('$EXTMAX', (1, 1, 1))
WX0, WY0 = float(extmin[0]), float(extmin[1])
WX1, WY1 = float(extmax[0]), float(extmax[1])

_span_ok = WX1 > WX0 and WY1 > WY0 and (WX1 - WX0) < 50_000 and (WY1 - WY0) < 50_000
if not _span_ok:
    print("  Header extents invalid — scanning vertices for bounds…")
    _xs, _ys = [], []
    for _e in msp:
        if _e.dxftype() in ('LWPOLYLINE', 'POLYLINE', 'LINE'):
            try:
                if _e.dxftype() == 'LINE':
                    _xs += [_e.dxf.start.x, _e.dxf.end.x]
                    _ys += [_e.dxf.start.y, _e.dxf.end.y]
                else:
                    for _p in _e.get_points():
                        _xs.append(_p[0]); _ys.append(_p[1])
            except Exception:
                pass
    if _xs:
        WX0, WX1 = min(_xs), max(_xs)
        WY0, WY1 = min(_ys), max(_ys)
    else:
        WX0, WY0, WX1, WY1 = 0, 0, 1, 1

# Detect millimetre-unit DXF (coords >2M → BNG metres would be outside UK)
COORD_SCALE = 1.0
if max(abs(WX0), abs(WX1), abs(WY0), abs(WY1)) > 2_000_000:
    COORD_SCALE = 0.001
    WX0, WX1, WY0, WY1 = WX0 * 0.001, WX1 * 0.001, WY0 * 0.001, WY1 * 0.001
    print(f"  Unit scaling ×0.001 (DXF appears to be in millimetres)")

print(f"  DXF extents E=[{WX0:.1f},{WX1:.1f}] N=[{WY0:.1f},{WY1:.1f}]")

# ── 2. Survey points: INSERT matched to nearest TEXT within 1m ────────────────
texts = []
for e in msp:
    if e.dxftype() == 'TEXT':
        try:
            z = float(e.dxf.text.strip())
            if 100 < z < 200:
                texts.append((e.dxf.insert.x * COORD_SCALE, e.dxf.insert.y * COORD_SCALE, z))
        except (ValueError, AttributeError):
            pass
    if e.dxftype() == 'MTEXT':
        try:
            raw = re.sub(r'\\[^;]+;|[{}]', '', e.text).strip()
            z = float(raw)
            if 100 < z < 200:
                texts.append((e.dxf.insert.x * COORD_SCALE, e.dxf.insert.y * COORD_SCALE, z))
        except (ValueError, AttributeError):
            pass

survey = []
for e in msp:
    if e.dxftype() == 'INSERT':
        ix, iy = e.dxf.insert.x * COORD_SCALE, e.dxf.insert.y * COORD_SCALE
        best_d, best_z = 1.0, None
        for tx, ty, tz in texts:
            d = math.hypot(ix - tx, iy - ty)
            if d < best_d:
                best_d, best_z = d, tz
        if best_z is not None:
            survey.append((ix, iy, best_z))
    if e.dxftype() == 'POINT':
        loc = e.dxf.location
        if 100 < loc.z < 200:
            survey.append((loc.x * COORD_SCALE, loc.y * COORD_SCALE, loc.z))

# Filter to within DXF extents only
survey = [p for p in survey if WX0 <= p[0] <= WX1 and WY0 <= p[1] <= WY1]
print(f"  Survey points: {len(survey)}")

if survey:
    zs = [p[2] for p in survey]
    z0, z1 = min(zs), max(zs)
else:
    z0, z1 = 100.0, 130.0

# ── 3. All geometry within DXF extents ───────────────────────────────────────
polylines = []  # (layer, pts, is_closed)

ARC_SEGS = 32  # segments per arc/circle approximation

def in_bounds(pts):
    return any(WX0 <= p[0] <= WX1 and WY0 <= p[1] <= WY1 for p in pts)

def collect_entity(e):
    """Extract geometry from a single entity, append to polylines."""
    layer = getattr(e.dxf, 'layer', '0')

    if e.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
        try:
            pts = [(p[0] * COORD_SCALE, p[1] * COORD_SCALE) for p in e.get_points()]
        except Exception:
            return
        if len(pts) < 2 or not in_bounds(pts):
            return
        closed = bool(getattr(e, 'closed', False) or getattr(e.dxf, 'flags', 0) & 1)
        polylines.append((layer, pts, closed))

    elif e.dxftype() == 'LINE':
        try:
            pts = [(e.dxf.start.x * COORD_SCALE, e.dxf.start.y * COORD_SCALE),
                   (e.dxf.end.x   * COORD_SCALE, e.dxf.end.y   * COORD_SCALE)]
        except Exception:
            return
        if in_bounds(pts):
            polylines.append((layer, pts, False))

    elif e.dxftype() == 'ARC':
        try:
            cx = e.dxf.center.x * COORD_SCALE
            cy = e.dxf.center.y * COORD_SCALE
            r  = e.dxf.radius   * COORD_SCALE
            a0, a1 = math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle)
            if a1 <= a0:
                a1 += 2 * math.pi
            pts = [(cx + r * math.cos(a0 + (a1 - a0) * i / ARC_SEGS),
                    cy + r * math.sin(a0 + (a1 - a0) * i / ARC_SEGS))
                   for i in range(ARC_SEGS + 1)]
        except Exception:
            return
        if in_bounds(pts):
            polylines.append((layer, pts, False))

    elif e.dxftype() == 'CIRCLE':
        try:
            cx = e.dxf.center.x * COORD_SCALE
            cy = e.dxf.center.y * COORD_SCALE
            r  = e.dxf.radius   * COORD_SCALE
            pts = [(cx + r * math.cos(2 * math.pi * i / ARC_SEGS),
                    cy + r * math.sin(2 * math.pi * i / ARC_SEGS))
                   for i in range(ARC_SEGS)]
        except Exception:
            return
        if in_bounds(pts):
            polylines.append((layer, pts, True))

_SKIP_TYPES = {'ATTRIB', 'ATTDEF', 'MTEXT', 'TEXT', 'POINT', 'WIPEOUT', 'LEADER', 'DIMENSION'}

for e in msp:
    if e.dxftype() == 'INSERT':
        try:
            for ve in e.virtual_entities():
                if ve.dxftype() not in _SKIP_TYPES:
                    collect_entity(ve)
        except Exception:
            pass
    else:
        collect_entity(e)

print(f"  Geometry: {len(polylines)} paths")

# ── 4. SVG coordinate transform ───────────────────────────────────────────────
PAD   = 30
W_SVG = 2400
H_SVG = int(W_SVG * (WY1 - WY0) / (WX1 - WX0)) + 2 * PAD

scale = (W_SVG - 2 * PAD) / (WX1 - WX0)

def sx(x): return PAD + (x - WX0) * scale
def sy(y): return H_SVG - PAD - (y - WY0) * scale   # Y-flip

print(f"  SVG {W_SVG}×{H_SVG}px  scale={scale:.4f}px/m")

# ── 5. Elevation colour ────────────────────────────────────────────────────────
def elev_color(z):
    t = 0.5 if z1 == z0 else max(0.0, min(1.0, (z - z0) / (z1 - z0)))
    stops = [(0,0,180),(0,160,220),(0,200,80),(240,220,0),(220,0,0)]
    seg = (len(stops) - 1) * t
    i = min(int(seg), len(stops) - 2)
    f = seg - i
    a, b = stops[i], stops[i+1]
    return f"#{int(a[0]+(b[0]-a[0])*f):02x}{int(a[1]+(b[1]-a[1])*f):02x}{int(a[2]+(b[2]-a[2])*f):02x}"

# ── 6. Build SVG ──────────────────────────────────────────────────────────────
print("Building SVG…")
svg = ET.Element('svg', {
    'xmlns':   'http://www.w3.org/2000/svg',
    'width':   str(W_SVG),
    'height':  str(H_SVG),
    'viewBox': f'0 0 {W_SVG} {H_SVG}',
})

ET.SubElement(svg, 'rect', {'width': str(W_SVG), 'height': str(H_SVG), 'fill': '#0a0a0a'})

# Polylines
g_poly = ET.SubElement(svg, 'g', {
    'id': 'polylines', 'stroke': '#ffffff',
    'stroke-width': '0.8', 'fill': 'none', 'stroke-linejoin': 'round',
})
for layer, pts, closed in polylines:
    d = ' '.join(
        f"{'M' if i == 0 else 'L'}{sx(p[0]):.2f},{sy(p[1]):.2f}"
        for i, p in enumerate(pts)
    )
    if closed:
        d += ' Z'
    ET.SubElement(g_poly, 'path', {'d': d, 'data-layer': layer})

# Survey points + labels
# PT_R: fixed 4px symbol — small enough not to obscure geometry
# Label: 3px monospace, placed just above symbol — scales with zoom but stays compact
PT_R = 4.0
FS   = 3.0   # SVG font-size units — tiny at full view, readable when zoomed

g_pts = ET.SubElement(svg, 'g', {'id': 'survey-points'})
g_labels = ET.SubElement(svg, 'g', {
    'id': 'labels', 'font-family': 'monospace', 'font-size': str(FS),
    'fill': '#e5e5e5', 'text-anchor': 'middle',
})
for px, py, pz in survey:
    cx, cy = sx(px), sy(py)
    col = elev_color(pz)
    ET.SubElement(g_pts, 'rect', {
        'x': f'{cx-PT_R:.2f}', 'y': f'{cy-PT_R:.2f}',
        'width': f'{PT_R*2:.2f}', 'height': f'{PT_R*2:.2f}',
        'fill': col, 'stroke': '#000000', 'stroke-width': '0.5',
    })
    # Shadow for readability
    for dx, dy in ((-0.3,0),(0.3,0),(0,-0.3),(0,0.3)):
        sh = ET.SubElement(g_labels, 'text', {
            'x': f'{cx+dx:.2f}', 'y': f'{cy - PT_R - 0.8 + dy:.2f}',
            'fill': '#000000',
        })
        sh.text = f'{pz:.3f}'
    t = ET.SubElement(g_labels, 'text', {
        'x': f'{cx:.2f}', 'y': f'{cy - PT_R - 0.8:.2f}',
    })
    t.text = f'{pz:.3f}'

# Legend
LX, LY, LW, LH = W_SVG - 70, PAD, 16, 160
defs = ET.SubElement(svg, 'defs')
grad = ET.SubElement(defs, 'linearGradient', {'id':'leg','x1':'0','y1':'0','x2':'0','y2':'1'})
for off, col in [('0%','#dc0000'),('25%','#f0dc00'),('50%','#00c850'),('75%','#00a0dc'),('100%','#0000b4')]:
    ET.SubElement(grad, 'stop', {'offset': off, 'stop-color': col})
ET.SubElement(svg, 'rect', {'x':str(LX),'y':str(LY),'width':str(LW),'height':str(LH),
                             'fill':'url(#leg)','stroke':'#555','stroke-width':'0.5'})
for val, frac in [(z1, 0.0), ((z0+z1)/2, 0.5), (z0, 1.0)]:
    yt = LY + frac * LH
    ET.SubElement(svg, 'text', {'x':str(LX-4),'y':f'{yt+3:.0f}',
                                 'font-family':'monospace','font-size':'9',
                                 'fill':'#aaa','text-anchor':'end'}).text = f'{val:.3f}m'

# Title
ET.SubElement(svg, 'text', {
    'x': str(PAD), 'y': str(PAD - 8),
    'font-family':'monospace','font-size':'11','fill':'#555',
}).text = (f"{Path(args.dxf).name}  |  {len(survey)} survey pts  |  "
           f"Z [{z0:.3f}–{z1:.3f}m]  |  BNG EPSG:27700  |  1px={1/scale:.3f}m")

# ── 7. Write ──────────────────────────────────────────────────────────────────
tree = ET.ElementTree(svg)
ET.indent(tree, space='')
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
tree.write(str(out), xml_declaration=True, encoding='unicode')
sz = out.stat().st_size
print(f"  Done: {out}  ({sz//1024} KB)  {W_SVG}×{H_SVG}px")
