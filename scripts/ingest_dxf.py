#!/usr/bin/env python3
"""
DXF ingestor — parse any DXF and store in Supabase (survey_points, layer_polylines, survey_grid).

Interpolation: barrier-aware IDW per zone (walls block diffusion), then
Delaunay TIN of real points with wall-crossing filter. Matches gen_civils.py exactly.

Usage:
  python3 scripts/ingest_dxf.py \
    --layer-id <uuid> \
    --dxf <path/to/file.dxf> \
    --db  postgresql://...
"""
import argparse, math, re, json, sys
from collections import deque
from pathlib import Path

import ezdxf
import numpy as np
import psycopg2
import psycopg2.extras
from shapely.geometry import LineString, MultiLineString

# ── Args ──────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument('--layer-id', required=True)
ap.add_argument('--dxf',      required=True)
ap.add_argument('--db',       required=True)
args = ap.parse_args()

LAYER_ID = args.layer_id
DXF_PATH = args.dxf
DB_URL   = args.db

MAX_DIST = 1.0   # INSERT/TEXT label match radius — 1 m, never wider
WALL_RE = re.compile(r'WALL|RETAINING|BOUNDARY|BUILDING|STRUCTURE|UNDERBUILD|PLOT-WALLS', re.I)

# ── 1. Parse DXF ──────────────────────────────────────────────────────────────
print(f"Parsing {DXF_PATH}…")
doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Collect TEXT / MTEXT elevation labels (all layers — z-IQR filter applied below)
texts_raw = []
for e in msp:
    if e.dxftype() == 'TEXT':
        try:
            z = float(e.dxf.text.strip())
            if 0 < z < 10000:
                texts_raw.append((e.dxf.insert.x, e.dxf.insert.y, z))
        except (ValueError, AttributeError):
            pass
    if e.dxftype() == 'MTEXT':
        try:
            raw = re.sub(r'\\[^;]+;|[{}]', '', e.text).strip()
            z = float(raw)
            if 0 < z < 10000:
                texts_raw.append((e.dxf.insert.x, e.dxf.insert.y, z))
        except (ValueError, AttributeError):
            pass

# Filter text z-values by IQR ×1.5 — removes dimension annotations, room labels, etc.
# that accidentally parse as numbers but are far from the real elevation cluster
def iqr_bounds(arr, k=3.0):
    q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr

if len(texts_raw) >= 4:
    tz_arr = np.array([t[2] for t in texts_raw])
    tz_lo, tz_hi = iqr_bounds(tz_arr, k=1.5)
    texts = [(tx,ty,tz) for tx,ty,tz in texts_raw if tz_lo <= tz <= tz_hi]
    print(f"  Text labels: {len(texts_raw)} raw → {len(texts)} after Z-IQR filter (Z range [{tz_lo:.2f},{tz_hi:.2f}])")
else:
    texts = texts_raw
    print(f"  Text labels: {len(texts)}")

# Collect raw survey points — INSERT+TEXT pairs only.
# POINT entities (COGO markers) have z≈0 in the DXF geometry; elevation is in the TEXT label.
raw_points = []   # (x, y, z, source)

inserts = []
for e in msp:
    if e.dxftype() == 'INSERT':
        inserts.append((e.dxf.insert.x, e.dxf.insert.y))
    # POINT with a meaningful z (abs > 0.5 m — rules out floating-point noise from 3D markers)
    if e.dxftype() == 'POINT':
        loc = e.dxf.location
        if abs(loc.z) > 0.5:
            raw_points.append((loc.x, loc.y, loc.z, 'POINT'))

for ix, iy in inserts:
    best_d, best_z = MAX_DIST, None
    for tx, ty, tz in texts:
        d = math.hypot(ix - tx, iy - ty)
        if d < best_d:
            best_d, best_z = d, tz
    if best_z is not None:
        raw_points.append((ix, iy, best_z, 'INSERT'))

if not raw_points:
    print("ERROR: No survey points found in DXF.")
    sys.exit(1)

print(f"  Points (raw): {len(raw_points)}")

# ── 2. Outlier filter — IQR ×3 on X, Y and Z
xs_raw = np.array([p[0] for p in raw_points])
ys_raw = np.array([p[1] for p in raw_points])
zs_raw = np.array([p[2] for p in raw_points])

x_lo, x_hi = iqr_bounds(xs_raw)
y_lo, y_hi = iqr_bounds(ys_raw)
z_lo, z_hi = iqr_bounds(zs_raw, k=1.5)

raw_points = [
    p for p in raw_points
    if x_lo <= p[0] <= x_hi and y_lo <= p[1] <= y_hi and z_lo <= p[2] <= z_hi
]

if not raw_points:
    print("ERROR: All points removed by outlier filter.")
    sys.exit(1)

print(f"  Points (filtered): {len(raw_points)}  Z-range kept: [{z_lo:.3f}, {z_hi:.3f}]")

# Compute bbox
xs = [p[0] for p in raw_points]
ys = [p[1] for p in raw_points]
zs = [p[2] for p in raw_points]
x0, x1 = min(xs), max(xs)
y0, y1 = min(ys), max(ys)
z_min, z_max = min(zs), max(zs)
print(f"  Bbox E=[{x0:.1f},{x1:.1f}] N=[{y0:.1f},{y1:.1f}]  Z=[{z_min:.3f},{z_max:.3f}]")

# Safety cap: 10M cells max
X0, X1 = int(math.floor(x0)), int(math.ceil(x1))
Y0, Y1 = int(math.floor(y0)), int(math.ceil(y1))
grid_w = X1 - X0 + 1
grid_h = Y1 - Y0 + 1
if grid_w * grid_h > 10_000_000:
    print(f"ERROR: Grid too large ({grid_w}×{grid_h}). Check CRS / coordinates.")
    sys.exit(1)

# Average duplicate points landing on same integer cell -> use MIN for trench bottoms
real_accum: dict = {}
for px, py, pz, _ in raw_points:
    key = (int(round(px)), int(round(py)))
    real_accum.setdefault(key, []).append(pz)
real_map: dict = {k: min(v) for k, v in real_accum.items()}

# ── 3. Collect polylines (walls / barriers) ───────────────────────────────────
print("Processing polylines…")
polylines = []   # (dxf_layer, elevation, [(x,y,z),...])
wall_segs: list[LineString] = []

for e in msp:
    if e.dxftype() not in ('LWPOLYLINE', 'POLYLINE'):
        continue
    try:
        pts = list(e.get_points())
    except Exception:
        continue
    if len(pts) < 2:
        continue
    elev = getattr(e.dxf, 'elevation', 0) or 0
    layer_name = e.dxf.layer
    coords = [(p[0], p[1], elev) for p in pts]
    polylines.append((layer_name, elev if elev else None, coords))

    # Only wall-like layers act as barriers for zone flood-fill
    if WALL_RE.search(layer_name):
        seg_pts = [(p[0], p[1]) for p in pts]
        # Filter to site area only
        in_site = [p for p in seg_pts if x_lo <= p[0] <= x_hi and y_lo <= p[1] <= y_hi]
        if len(in_site) >= 2:
            wall_segs.append(LineString(in_site))

wall_multi = MultiLineString(wall_segs) if wall_segs else None
print(f"  Polylines: {len(polylines)}  Wall segments: {len(wall_segs)}")

# Rasterise walls → barrier cells (0.25 m step along each segment)
wall_cells: set = set()
for seg in wall_segs:
    steps = max(2, int(seg.length / 0.25))
    for i in range(steps + 1):
        pt = seg.interpolate(i / steps, normalized=True)
        cx, cy = int(round(pt.x)), int(round(pt.y))
        if X0 <= cx <= X1 and Y0 <= cy <= Y1:
            wall_cells.add((cx, cy))

print(f"  Wall cells: {len(wall_cells)}")

# ── 4. Zone flood-fill (4-direction, walls block) ─────────────────────────────
def cardinal(cx, cy):
    for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
        nx, ny = cx+dx, cy+dy
        if X0 <= nx <= X1 and Y0 <= ny <= Y1:
            yield nx, ny

def eight_nbrs(cx, cy):
    for dx in (-1,0,1):
        for dy in (-1,0,1):
            if dx==dy==0: continue
            nx, ny = cx+dx, cy+dy
            if X0 <= nx <= X1 and Y0 <= ny <= Y1:
                yield nx, ny

unvisited = {
    (cx,cy) for cx in range(X0, X1+1) for cy in range(Y0, Y1+1)
    if (cx,cy) not in wall_cells
}
cell_zone: dict = {}
zone_id = 0
while unvisited:
    start = next(iter(unvisited))
    q = deque([start]); visited = {start}
    while q:
        cell = q.popleft()
        cell_zone[cell] = zone_id
        unvisited.discard(cell)
        for n in cardinal(*cell):
            if n in unvisited and n not in visited:
                visited.add(n); q.append(n)
    zone_id += 1

print(f"  Zones: {zone_id}")

# Real points per zone
zone_reals: dict = {}
for (cx,cy), z in real_map.items():
    zid = cell_zone.get((cx,cy))
    if zid is not None:
        zone_reals.setdefault(zid, []).append((cx,cy,z))

# ── 5. Barrier-aware IDW interpolation per zone ───────────────────────────────
print("Interpolating (IDW, barrier-aware)…")
cells = []
for cx in range(X0, X1+1):
    for cy in range(Y0, Y1+1):
        key = (cx, cy)
        if key in real_map:
            cells.append({"x":cx,"y":cy,"z":round(real_map[key],3),"is_interp":False})
        elif key in wall_cells:
            # Wall cells are typically not interpolated if they are the barrier itself
            continue
        else:
            zid   = cell_zone.get(key)
            reals = zone_reals.get(zid,[]) if zid is not None else []
            if not reals:
                # No data for this zone (e.g. outside or empty building) -> keep void
                continue
            else:
                tw = twz = 0.0
                for rcx,rcy,rz in reals:
                    d = math.hypot(cx-rcx, cy-rcy)
                    w = 1.0 / max(d**2, 1e-6)
                    tw += w; twz += w*rz
                cells.append({"x":cx,"y":cy,"z":round(twz/tw,3),"is_interp":True})

# Recompute z range from final grid
all_z = [c["z"] for c in cells if c["z"] > 0]
z_min = min(all_z) if all_z else 0.0
z_max = max(all_z) if all_z else 0.0

real_count  = sum(1 for c in cells if not c["is_interp"])
interp_count= sum(1 for c in cells if c["is_interp"])
print(f"  Grid cells: {len(cells)}  (real={real_count}  interp={interp_count})")

# ── 6. Store in DB ────────────────────────────────────────────────────────────
print("Writing to database…")
conn = psycopg2.connect(DB_URL)
cur  = conn.cursor()

# survey_points — original raw survey points (exact positions)
point_rows = [(LAYER_ID, p[0], p[1], p[2], True, p[3]) for p in raw_points]
psycopg2.extras.execute_values(
    cur,
    "INSERT INTO survey_points (layer_id,x,y,z,is_real,source_entity) VALUES %s ON CONFLICT DO NOTHING",
    point_rows, page_size=500
)
print(f"  Inserted {len(point_rows)} survey_points")

# layer_polylines
poly_rows = []
for dxf_layer, elev, coords in polylines:
    if len(coords) < 2:
        continue
    wkt = 'LINESTRING Z(' + ','.join(f'{x} {y} {z}' for x,y,z in coords) + ')'
    poly_rows.append((LAYER_ID, dxf_layer, elev, wkt))

if poly_rows:
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO layer_polylines (layer_id,dxf_layer,elevation,geom) VALUES %s",
        [(r[0], r[1], r[2], r[3]) for r in poly_rows],
        template="(%s,%s,%s,ST_GeomFromText(%s,27700))",
        page_size=200
    )
print(f"  Inserted {len(poly_rows)} polylines")

# survey_grid — IDW-interpolated 1m grid
grid_rows = [(LAYER_ID, c["x"], c["y"], c["z"], c["is_interp"]) for c in cells]
psycopg2.extras.execute_values(
    cur,
    """INSERT INTO survey_grid(layer_id,x,y,z,is_interp) VALUES %s
       ON CONFLICT (layer_id,x,y) DO UPDATE SET z=EXCLUDED.z,is_interp=EXCLUDED.is_interp""",
    grid_rows, page_size=1000
)
print(f"  Inserted {len(grid_rows)} grid cells")

# Update layer metadata
cur.execute("""
    UPDATE layers SET
      status='interpolated',
      z_min=%s, z_max=%s,
      point_count=%s,
      poly_count=%s
    WHERE id=%s
""", (z_min, z_max, len(point_rows), len(poly_rows), LAYER_ID))

conn.commit()
cur.close()
conn.close()

print(f"\nDone. Layer {LAYER_ID} → status=interpolated")
print(json.dumps({
    "points": len(point_rows),
    "polylines": len(poly_rows),
    "grid_cells": len(grid_rows),
    "z_min": z_min, "z_max": z_max
}))
