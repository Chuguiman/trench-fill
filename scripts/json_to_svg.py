#!/usr/bin/env python3
"""
Generate an SVG from a JSON-exported CAD file (from export_dxf.py).
Maintains exact coordinates, layer grouping, and Z-elevation color-coding.

Usage:
  python3 scripts/json_to_svg.py --json <file.json> --out <output.svg>
"""
import argparse, json, math, xml.etree.ElementTree as ET
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--json', required=True)
ap.add_argument('--out', required=True)
args = ap.parse_args()

# ── 1. Load JSON ──────────────────────────────────────────────────────────────
print(f"Loading {args.json}…")
with open(args.json, 'r') as f:
    data = json.load(f)

entities = data.get('entities', [])
header = data.get('header', {})

# Precise bounds scanning
print("Scanning entities for project bounds…")
xs, ys, zs = [], [], []
survey_xs, survey_ys = [], []

for e in entities:
    t = e['type']
    layer = e.get('layer', '')
    p = e.get('position', e.get('center', [0, 0, 0]))
    
    # Track everything for filtering
    if t in ('LWPOLYLINE', 'POLYLINE'):
        for v in e.get('vertices', []):
            xs.append(v[0]); ys.append(v[1])
            if len(v) > 2: zs.append(v[2])
    elif t == 'LINE':
        xs += [e['start'][0], e['end'][0]]
        ys += [e['start'][1], e['end'][1]]
        zs += [e['start'][2], e['end'][2]]
    else:
        xs.append(p[0]); ys.append(p[1])
        if len(p) > 2: zs.append(p[2])

    # Specifically track survey points to define the "Real" project area
    if 'LEVELS' in layer.upper() or t == 'POINT':
        survey_xs.append(p[0]); survey_ys.append(p[1])

if not xs:
    print("Error: No geometry found.")
    exit(1)

# Use survey points as the primary anchor for bounds if they exist
import numpy as np
if survey_xs:
    # Use 1st and 99th percentile of survey points to avoid rogue points
    WX0, WX1 = np.percentile(survey_xs, 0.5), np.percentile(survey_xs, 99.5)
    WY0, WY1 = np.percentile(survey_ys, 0.5), np.percentile(survey_ys, 99.5)
    print(f"  Bounds anchored by Survey Points: E=[{WX0:.1f},{WX1:.1f}] N=[{WY0:.1f},{WY1:.1f}]")
else:
    # Fallback to IQR filtering of all geometry
    q1x, q3x = np.percentile(xs, 25), np.percentile(xs, 75)
    iqrx = q3x - q1x
    WX0, WX1 = q1x - 2*iqrx, q3x + 2*iqrx
    
    q1y, q3y = np.percentile(ys, 25), np.percentile(ys, 75)
    iqry = q3y - q1y
    WY0, WY1 = q1y - 2*iqry, q3y + 2*iqry
    print(f"  Bounds estimated from all geometry: E=[{WX0:.1f},{WX1:.1f}] N=[{WY0:.1f},{WY1:.1f}]")

# Add 10m buffer
WX0 -= 10; WX1 += 10; WY0 -= 10; WY1 += 10

# ── 2. SVG coordinate transform ───────────────────────────────────────────────
PAD   = 40
W_SVG = 2400
span_x = WX1 - WX0
span_y = WY1 - WY0

# CRITICAL: Scale is pixels-per-meter based on drawing area (W_SVG minus padding)
scale = (W_SVG - 2 * PAD) / span_x
# Height must match EXACTLY to maintain 1:1 ratio
H_SVG = int(span_y * scale) + 2 * PAD

def sx(x): return PAD + (x - WX0) * scale
def sy(y): return H_SVG - PAD - (y - WY0) * scale   # Y-flip

print(f"  Final SVG: {W_SVG}x{H_SVG} | Scale: {scale:.4f} px/m")

# ── 3. Elevation colour ────────────────────────────────────────────────────────
# Core terrain range
z_min, z_max = 100.0, 130.0 # Default for this site
if zs:
    z_min, z_max = np.percentile(zs, 5), np.percentile(zs, 95)
    if z_min < 10: # Filter out 0/nulls
        pos_zs = [z for z in zs if z > 10]
        if pos_zs: z_min, z_max = np.percentile(pos_zs, 5), np.percentile(pos_zs, 95)

def elev_color(z, lighten=0):
    if z_max <= z_min: return "#ffffff"
    t = max(0.0, min(1.0, (z - z_min) / (z_max - z_min)))
    
    # Adjusted Ramp: Light Blue/White -> Cyan -> Green -> Yellow -> Red
    # Lightened the start of the ramp (Blue -> Light Steel Blue)
    stops = [(180,200,255),(0,160,220),(0,200,80),(240,220,0),(220,0,0)]
    seg = (len(stops) - 1) * t
    i = min(int(seg), len(stops) - 2)
    f = seg - i
    a, b = stops[i], stops[i+1]
    
    r = int(a[0]+(b[0]-a[0])*f)
    g = int(a[1]+(b[1]-a[1])*f)
    bl = int(a[2]+(b[2]-a[2])*f)
    
    # Apply extra lightening for visibility as requested
    base_lighten = 0.5 # Default significant lightening
    eff_lighten = max(base_lighten, lighten)
    
    r = min(255, int(r + (255-r)*eff_lighten))
    g = min(255, int(g + (255-g)*eff_lighten))
    bl = min(255, int(bl + (255-bl)*eff_lighten))
        
    return f"#{r:02x}{g:02x}{bl:02x}"

# ── 4. Build SVG ──────────────────────────────────────────────────────────────
print("Building SVG…")
svg = ET.Element('svg', {
    'xmlns':   'http://www.w3.org/2000/svg',
    'width':   str(W_SVG),
    'height':  str(H_SVG),
    'viewBox': f'0 0 {W_SVG} {H_SVG}',
    'data-wx0': f'{WX0:.6f}',
    'data-wy0': f'{WY0:.6f}',
    'data-scale': f'{scale:.8f}',
    'data-hsvg': f'{H_SVG}',
    'data-pad': f'{PAD}',
})

# Background
ET.SubElement(svg, 'rect', {'width': str(W_SVG), 'height': str(H_SVG), 'fill': '#212830'})

# Group by layers
layers_groups = {}
def get_layer_group(name):
    if name not in layers_groups:
        g = ET.SubElement(svg, 'g', {'id': f'layer-{name}', 'data-layer': name})
        layers_groups[name] = g
    return layers_groups[name]

# Tracker for placed labels to avoid overlaps
# Store as Rects (x0, y0, x1, y1)
placed_rects = []
# Minimum space for a label (approx 20px wide, 6px high for "123.456")
LABEL_W = 18.0
LABEL_H = 5.0

for e in entities:
    t = e['type']
    layer = e.get('layer', '0')
    parent = get_layer_group(layer)
    
    # Skip entities far outside our 2-98% bounds
    def is_visible(pts):
        return any(WX0-10 <= p[0] <= WX1+10 and WY0-10 <= p[1] <= WY1+10 for p in pts)

    if t in ('LWPOLYLINE', 'POLYLINE'):
        pts = e.get('vertices', [])
        if len(pts) < 2 or not is_visible(pts): continue
        d = ' '.join(f"{'M' if i == 0 else 'L'}{sx(p[0]):.2f},{sy(p[1]):.2f}" for i, p in enumerate(pts))
        if e.get('closed'): d += ' Z'
        
        z_vals = [p[2] for p in pts if len(p) > 2 and abs(p[2]) > 0.1]
        z_avg = sum(z_vals)/len(z_vals) if z_vals else z_min
        color = elev_color(z_avg) if z_vals else "#333333"
        
        ET.SubElement(parent, 'path', {
            'd': d, 'stroke': color, 'fill': 'none', 'stroke-width': '0.3', 'opacity': '0.3'
        })

    elif t == 'LINE':
        p0, p1 = e['start'], e['end']
        if not is_visible([p0, p1]): continue
        z_avg = (p0[2] + p1[2]) / 2
        color = elev_color(z_avg) if abs(z_avg) > 0.1 else "#222222"
        ET.SubElement(parent, 'line', {
            'x1': f"{sx(p0[0]):.2f}", 'y1': f"{sy(p0[1]):.2f}",
            'x2': f"{sx(p1[0]):.2f}", 'y2': f"{sy(p1[1]):.2f}",
            'stroke': color, 'stroke-width': '0.3', 'opacity': '0.3'
        })

    elif t == 'CIRCLE':
        c = e['center']
        r = e['radius']
        if not is_visible([c]): continue
        color = elev_color(c[2]) if abs(c[2]) > 0.1 else "#ffffff"
        ET.SubElement(parent, 'circle', {
            'cx': f"{sx(c[0]):.2f}", 'cy': f"{sy(c[1]):.2f}",
            'r': f"{r * scale:.2f}",
            'stroke': color, 'fill': 'none',
            'stroke-width': '0.2', 'opacity': '0.15'
        })

    elif t in ('TEXT', 'MTEXT'):
        pos = e['position']
        if not is_visible([pos]): continue
        txt = e['text']
        
        # Check if numeric (Z coordinate)
        try:
            val = float(txt.replace('m', ''))
            is_numeric = True
        except:
            val = pos[2]
            is_numeric = False
            
        color_base = elev_color(val)
        color_light = elev_color(val, lighten=0.4) # Make labels/points lighter
        
        cx, cy = sx(pos[0]), sy(pos[1])
            
        if is_numeric and 50 < val < 200: # Typical Z range for the project
            # Bounding box check for label avoidance
            # Label is placed at cx+1.2, cy-1.1 to cy+1.1
            r_new = (cx, cy - LABEL_H/2, cx + LABEL_W, cy + LABEL_H/2)
            
            too_close = False
            for r in placed_rects:
                if not (r_new[2] < r[0] or r_new[0] > r[2] or r_new[3] < r[1] or r_new[1] > r[3]):
                    too_close = True
                    break
            
            # Point marker (Always draw marker if not TOO close to another marker)
            # Use radius check for marker-only avoidance
            marker_too_close = False
            for r in placed_rects:
                if math.hypot(cx - r[0], cy - (r[1]+r[3])/2) < 2.0:
                    marker_too_close = True
                    break
            
            if not marker_too_close:
                ET.SubElement(parent, 'rect', {
                    'x': f'{cx-0.6:.2f}', 'y': f'{cy-0.6:.2f}',
                    'width': '1.2', 'height': '1.2', 'fill': color_light, 'opacity': '0.9'
                })
            
            if not too_close:
                placed_rects.append(r_new)
                # Label with shadow
                st = ET.SubElement(parent, 'text', {
                    'x': f'{cx+1.2:.2f}', 'y': f'{cy+0.6:.2f}',
                    'font-family': 'monospace', 'font-size': '1.8', 'fill': '#000', 'stroke': '#000', 'stroke-width': '0.1'
                })
                st.text = f"{val:.3f}"
                t_el = ET.SubElement(parent, 'text', {
                    'x': f'{cx+1.2:.2f}', 'y': f'{cy+0.6:.2f}',
                    'font-family': 'monospace', 'font-size': '1.8', 'fill': color_light
                })
                t_el.text = f"{val:.3f}"
        else:
            # Descriptive text
            ET.SubElement(parent, 'text', {
                'x': f'{cx:.2f}', 'y': f'{cy:.2f}',
                'font-family': 'sans-serif', 'font-size': '1.8', 'fill': '#ffffff', 'opacity': '0.2'
            }).text = txt

    elif t == 'POINT':
        pos = e['position']
        if not is_visible([pos]): continue
        color = elev_color(pos[2], lighten=0.4)
        cx, cy = sx(pos[0]), sy(pos[1])
        # Very tiny dots for points, but lighter
        ET.SubElement(parent, 'circle', {'cx': f'{cx:.2f}', 'cy': f'{cy:.2f}', 'r': '0.6', 'fill': color, 'opacity': '0.6'})

# Legend
LX, LY, LW, LH = W_SVG - 100, PAD, 20, 200
defs = ET.SubElement(svg, 'defs')
grad = ET.SubElement(defs, 'linearGradient', {'id':'leg','x1':'0','y1':'1','x2':'0','y2':'0'})
# Ramp: Blue -> Cyan -> Green -> Yellow -> Red
for off, col in [('0%','#0000b4'),('25%','#00a0dc'),('50%','#00c850'),('75%','#f0dc00'),('100%','#dc0000')]:
    ET.SubElement(grad, 'stop', {'offset': off, 'stop-color': col})
ET.SubElement(svg, 'rect', {'x':str(LX),'y':str(LY),'width':str(LW),'height':str(LH),
                             'fill':'url(#leg)','stroke':'#555','stroke-width':'1'})
for i, val in enumerate([z_min, (z_min+z_max)/2, z_max]):
    yt = LY + LH - (i * 0.5 * LH)
    ET.SubElement(svg, 'text', {'x':str(LX-8),'y':f'{yt+4:.0f}',
                                 'font-family':'monospace','font-size':'12',
                                 'fill':'#aaa','text-anchor':'end'}).text = f'{val:.2f}m'

# Metadata Title
ET.SubElement(svg, 'text', {
    'x': str(PAD), 'y': str(PAD - 10),
    'font-family':'monospace','font-size':'14','fill':'#888',
}).text = f"Source: {data.get('source', 'Unknown')} | Z Range: {z_min:.3f}m - {z_max:.3f}m | Scale: 1px = {1/scale:.4f}m"

# ── 5. Write SVG ──────────────────────────────────────────────────────────────
tree = ET.ElementTree(svg)
ET.indent(tree, space='  ')
out_path = Path(args.out)
out_path.parent.mkdir(parents=True, exist_ok=True)
tree.write(str(out_path), xml_declaration=True, encoding='unicode')

print(f"Done: {out_path} ({out_path.stat().st_size // 1024} KB)")
