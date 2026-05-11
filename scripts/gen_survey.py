#!/usr/bin/env python3
"""
Generate SurveyViewer CELLS + TIN triangulation from XREF_Survey_Topo.dxf.

Rules:
  1. Z value from INSERT position matched to nearest TEXT label (CLS_LEVELS).
  2. Barriers = CLS_BANKS, CLS_BUILDINGS, CLS_FENCE.
  3. Interpolation: linear TIN + nearest fallback.
  4. Delaunay triangulation of real points.
  5. Site boundary: alpha shape of real points.
"""

import math, json, re
from pathlib import Path

import numpy as np
import ezdxf
from scipy.spatial import Delaunay
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import unary_union

# ── Config ────────────────────────────────────────────────────────────────────
DXF_PATH = "public/XREF_Survey_Topo.dxf"
TSX_PATH = "src/components/SurveyViewer.tsx"
E_OFF, N_OFF = 287676.925, 62656.831
X0, X1 = 180, 300
Y0, Y1 = 300, 360
MAX_TEXT_DIST = 1.0

BARRIER_LAYERS = {
    "CLS_BANKS",
    "CLS_BUILDINGS",
    "CLS_FENCE",
}

# ── 1. Parse DXF ──────────────────────────────────────────────────────────────
print("Reading DXF…")
doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

texts = []
for e in msp:
    raw, te, tn = None, 0, 0
    if e.dxftype() == "TEXT" and e.dxf.layer == "CLS_LEVELS":
        raw, te, tn = e.dxf.text, e.dxf.insert.x, e.dxf.insert.y
    elif e.dxftype() == "MTEXT" and e.dxf.layer == "CLS_LEVELS":
        raw = re.sub(r'\\[^;]+;|[{}]', '', e.text).strip()
        te, tn = e.dxf.insert.x, e.dxf.insert.y
    if raw is None:
        continue
    try:
        z = float(raw.strip())
        if 100 < z < 200:
            texts.append((te, tn, z))
    except ValueError:
        pass

print(f"  Text labels: {len(texts)}")

# ── 2. Match INSERT → TEXT for real level data ────────────────────────────────
raw_points = []
for e in msp:
    if e.dxftype() != "INSERT" or e.dxf.layer != "CLS_LEVELS":
        continue
    pe, pn = e.dxf.insert.x, e.dxf.insert.y
    gx, gy = pe - E_OFF, pn - N_OFF
    if not (X0 <= gx <= X1 and Y0 <= gy <= Y1):
        continue
    best_d, best_z = MAX_TEXT_DIST, None
    for te, tn, tz in texts:
        d = math.hypot(pe - te, pn - tn)
        if d < best_d:
            best_d, best_z = d, tz
    if best_z is not None:
        raw_points.append((gx, gy, best_z))

print(f"  Level points in grid: {len(raw_points)}")

# Average points on same integer cell
real_accum: dict = {}
for gx, gy, z in raw_points:
    cx, cy = round(gx), round(gy)
    real_accum.setdefault((cx, cy), []).append(z)
real_map: dict = {k: sum(v) / len(v) for k, v in real_accum.items()}

# ── 3. Barriers ───────────────────────────────────────────────────────────────
print("Processing barriers…")
barrier_segs: list[LineString] = []
for e in msp:
    if e.dxftype() == "LWPOLYLINE" and e.dxf.layer in BARRIER_LAYERS:
        pts = [(p[0] - E_OFF, p[1] - N_OFF) for p in e.get_points()]
        if len(pts) >= 2:
            barrier_segs.append(LineString(pts))

barrier_multi = MultiLineString(barrier_segs) if barrier_segs else None

# Rasterise barriers
barrier_cells: set = set()
for seg in barrier_segs:
    steps = max(2, int(seg.length / 0.25))
    for i in range(steps + 1):
        pt = seg.interpolate(i / steps, normalized=True)
        cx, cy = round(pt.x), round(pt.y)
        if X0 <= cx <= X1 and Y0 <= cy <= Y1:
            barrier_cells.add((cx, cy))

print(f"  Barrier cells: {len(barrier_cells)}")

# ── 4. Interpolation (Basic IDW for simplicity, matching Survey style) ────────
print("Interpolating…")
cells = []
all_real_pts = np.array([[cx, cy] for (cx, cy) in real_map.keys()])
all_real_z   = np.array([z for z in real_map.values()])

for cx in range(X0, X1+1):
    for cy in range(Y0, Y1+1):
        key = (cx, cy)
        if key in real_map:
            cells.append({"x":cx,"y":cy,"z":round(real_map[key],3),"i":0})
        elif key in barrier_cells:
            cells.append({"x":cx,"y":cy,"z":0.0,"i":1}) # Treat as interp with 0 for now
        else:
            # Simple IDW
            dists = np.hypot(all_real_pts[:,0] - cx, all_real_pts[:,1] - cy)
            weights = 1.0 / np.maximum(dists**2, 1e-6)
            z_interp = np.sum(weights * all_real_z) / np.sum(weights)
            cells.append({"x":cx,"y":cy,"z":round(z_interp, 3),"i":1})

# ── 5. Delaunay TIN ───────────────────────────────────────────────────────────
print("Computing TIN…")
pts   = np.array([[p[0], p[1]] for p in raw_points], dtype=float)
z_arr = np.array([p[2] for p in raw_points])

tri = Delaunay(pts)

def edge_crosses_barrier(p0, p1):
    if barrier_multi is None: return False
    return LineString([p0, p1]).crosses(barrier_multi)

tris_data: list[list] = []
for simplex in tri.simplices:
    v = pts[simplex]
    if any(edge_crosses_barrier(v[a], v[b]) for a,b in ((0,1),(1,2),(0,2))):
        continue
    row = []
    for i in simplex:
        row.extend([float(pts[i][0]), float(pts[i][1]), float(z_arr[i])])
    row.append(0) # type 0
    tris_data.append(row)

# ── 6. Boundary ───────────────────────────────────────────────────────────────
print("Computing Boundary…")
site_union = unary_union([Point(p[0], p[1]).buffer(8) for p in raw_points]).buffer(-4)
geoms = [site_union] if site_union.geom_type == "Polygon" else list(site_union.geoms)
boundary_data = [[[round(x,1),round(y,1)] for x,y in g.exterior.coords] for g in geoms]

# ── 7. Write to TSX ───────────────────────────────────────────────────────────
print("Updating TSX…")
cells_json    = json.dumps(cells, separators=(",",":"))
tris_json     = json.dumps(tris_data, separators=(",",":"))
boundary_json = json.dumps(boundary_data, separators=(",",":"))

tsx = Path(TSX_PATH).read_text()

# Update CELLS
tsx = re.sub(r"const CELLS\s*=\s*\[.*?\];", f"const CELLS   = {cells_json};", tsx, flags=re.DOTALL)

# Insert BOUNDARY + TRIS before LAYERS
if "const BOUNDARY" in tsx:
    tsx = re.sub(r"const BOUNDARY:number[][][] = .*?;", f"const BOUNDARY:number[][][] = {boundary_json};", tsx, flags=re.DOTALL)
else:
    tsx = tsx.replace("const LAYERS", f"const BOUNDARY:number[][][] = {boundary_json};\nconst LAYERS", 1)

if "const TRIS" in tsx:
    tsx = re.sub(r"const TRIS:number[][] = .*?;", f"const TRIS:number[][] = {tris_json};", tsx, flags=re.DOTALL)
else:
    tsx = tsx.replace("const LAYERS", f"const TRIS:number[][] = {tris_json};\nconst LAYERS", 1)

Path(TSX_PATH).write_text(tsx)
print("Done.")
