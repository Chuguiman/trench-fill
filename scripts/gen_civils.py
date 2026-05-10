#!/usr/bin/env python3
"""
Generate CivilsViewer CELLS + TIN triangulation from XREF_Civils_External levels.dxf.

Rules:
  1. Z value from POINT entity position (EXP-EW-LEVELS-POINTS) matched to
     nearest TEXT label (EXP-EW-LEVELS-TEXT, max 2 m). Point pos → grid cell.
  2. Barriers = ONLY polylines on retaining-wall layers. Nothing else.
  3. After IDW interpolation, zero cells get min non-zero 8-neighbour value.
  4. Delaunay triangulation of real points. Triangles crossing retaining walls
     are excluded. TRIS + WALLS written to CivilsViewer for canvas rendering.

Run from project root:
    python3 scripts/gen_civils.py
"""

import math, json, re
from collections import deque
from pathlib import Path

import numpy as np
import ezdxf
from scipy.spatial import Delaunay
from shapely.geometry import LineString, MultiLineString

# ── Config ────────────────────────────────────────────────────────────────────
DXF_PATH = "public/XREF_Civils_External levels.dxf"
TSX_PATH = "src/components/CivilsViewer.tsx"
E_OFF, N_OFF = 287676.925, 62656.831
X0, X1 = 180, 300
Y0, Y1 = 300, 360
MAX_TEXT_DIST = 2.0

RETAINING_WALL_LAYERS = {
    "EXP - RETAINING WALLS - 0.6m",
    "EXP - RETAINING WALLS GRAVEL BOARD",
}

# ── 1. Parse DXF ──────────────────────────────────────────────────────────────
print("Reading DXF…")
doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

texts = []
for e in msp:
    raw, te, tn = None, 0, 0
    if e.dxftype() == "TEXT" and e.dxf.layer == "EXP-EW-LEVELS-TEXT":
        raw, te, tn = e.dxf.text, e.dxf.insert.x, e.dxf.insert.y
    elif e.dxftype() == "MTEXT" and e.dxf.layer == "EXP-EW-LEVELS-TEXT":
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

# ── 2. Match POINT → TEXT for real level data ─────────────────────────────────
raw_points = []
for e in msp:
    if e.dxftype() != "POINT" or e.dxf.layer != "EXP-EW-LEVELS-POINTS":
        continue
    pe, pn = e.dxf.location.x, e.dxf.location.y
    gx, gy = pe - E_OFF, pn - N_OFF
    if not (X0 <= gx <= X1 and Y0 <= gy <= Y1):
        continue
    best_d, best_z = MAX_TEXT_DIST, None
    for te, tn, tz in texts:
        d = math.hypot(pe - te, pn - tn)
        if d < best_d:
            best_d, best_z = d, tz
    if best_z is not None:
        raw_points.append((round(gx), round(gy), best_z))

print(f"  Level points in grid: {len(raw_points)}")

real_accum: dict = {}
for cx, cy, z in raw_points:
    real_accum.setdefault((cx, cy), []).append(z)
real_map: dict = {k: sum(v) / len(v) for k, v in real_accum.items()}

# ── 3. Retaining walls ────────────────────────────────────────────────────────
print("Processing retaining walls…")
wall_polylines_world: list[list] = []   # [[E,N],...] in BNG
for e in msp:
    if e.dxftype() == "LWPOLYLINE" and e.dxf.layer in RETAINING_WALL_LAYERS:
        pts = [[p[0], p[1]] for p in e.get_points()]
        if len(pts) >= 2:
            wall_polylines_world.append(pts)

# Wall segments as shapely for crossing test (in grid coords)
wall_segs_grid: list[LineString] = []
for poly in wall_polylines_world:
    grid_pts = [(p[0] - E_OFF, p[1] - N_OFF) for p in poly]
    if len(grid_pts) >= 2:
        wall_segs_grid.append(LineString(grid_pts))

wall_multi_grid = MultiLineString(wall_segs_grid) if wall_segs_grid else None

# Rasterise walls → barrier cells
wall_cells: set = set()
for seg in wall_segs_grid:
    steps = max(2, int(seg.length / 0.25))
    for i in range(steps + 1):
        pt = seg.interpolate(i / steps, normalized=True)
        cx, cy = round(pt.x), round(pt.y)
        if X0 <= cx <= X1 and Y0 <= cy <= Y1:
            wall_cells.add((cx, cy))

print(f"  Wall cells: {len(wall_cells)}")

# ── 4. Zone flood-fill (4-dir, walls block) ───────────────────────────────────
def cardinal(cx, cy):
    for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
        nx, ny = cx+dx, cy+dy
        if X0 <= nx <= X1 and Y0 <= ny <= Y1:
            yield nx, ny

def eight(cx, cy):
    for dx in (-1,0,1):
        for dy in (-1,0,1):
            if dx==dy==0: continue
            nx, ny = cx+dx, cy+dy
            if X0 <= nx <= X1 and Y0 <= ny <= Y1:
                yield nx, ny

unvisited = {
    (cx,cy) for cx in range(X0,X1+1) for cy in range(Y0,Y1+1)
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

zone_reals: dict = {}
for (cx,cy), z in real_map.items():
    zid = cell_zone.get((cx,cy))
    if zid is not None:
        zone_reals.setdefault(zid, []).append((cx,cy,z))

# ── 5. IDW interpolation ──────────────────────────────────────────────────────
print("Interpolating…")
cells = []
for cx in range(X0, X1+1):
    for cy in range(Y0, Y1+1):
        key = (cx, cy)
        if key in real_map:
            cells.append({"x":cx,"y":cy,"z":round(real_map[key],3),"i":0,"b":0})
        elif key in wall_cells:
            cells.append({"x":cx,"y":cy,"z":0.0,"i":2,"b":1})
        else:
            zid   = cell_zone.get(key)
            reals = zone_reals.get(zid,[]) if zid is not None else []
            if not reals:
                cells.append({"x":cx,"y":cy,"z":0.0,"i":1,"b":0})
            else:
                tw = twz = 0.0
                for rcx,rcy,rz in reals:
                    d = math.hypot(cx-rcx, cy-rcy)
                    w = 1.0 / max(d**2, 1e-6)
                    tw += w; twz += w*rz
                cells.append({"x":cx,"y":cy,"z":round(twz/tw,3),"i":1,"b":0})

# Fix zeros
cmap = {(c["x"],c["y"]): c for c in cells}
changed, passes = True, 0
while changed and passes < 20:
    changed = False; passes += 1
    for c in cells:
        if c["z"] != 0.0: continue
        nb = [cmap[n]["z"] for n in eight(c["x"],c["y"]) if n in cmap and cmap[n]["z"]>0]
        if nb:
            c["z"] = round(min(nb), 3); changed = True

print(f"  Zeros fixed in {passes} pass(es)")

# ── 6. Delaunay TIN of real points ────────────────────────────────────────────
print("Computing Delaunay triangulation…")
real_cells = [c for c in cells if c["i"] == 0]
pts   = np.array([[c["x"], c["y"]] for c in real_cells], dtype=float)
z_arr = np.array([c["z"] for c in real_cells])

tri = Delaunay(pts)

# Filter triangles that cross retaining walls
def edge_crosses_wall(p0, p1):
    if wall_multi_grid is None:
        return False
    edge = LineString([p0, p1])
    return edge.crosses(wall_multi_grid)

tris_data: list[list] = []
kept = skipped = 0
for simplex in tri.simplices:
    v = pts[simplex]
    if any(
        edge_crosses_wall(v[a], v[b])
        for a,b in ((0,1),(1,2),(0,2))
    ):
        skipped += 1
        continue
    row = []
    for i in simplex:
        row.extend([float(pts[i][0]), float(pts[i][1]), float(z_arr[i])])
    tris_data.append(row)
    kept += 1

print(f"  Triangles: {kept} kept, {skipped} removed (cross walls)")

# ── 7. Wall polylines in grid coords (for canvas drawing) ────────────────────
walls_data: list[list] = []
for poly in wall_polylines_world:
    grid_pts = [[round(p[0]-E_OFF,1), round(p[1]-N_OFF,1)] for p in poly]
    if grid_pts[0] != grid_pts[-1]:   # don't close open polylines
        pass
    walls_data.append(grid_pts)

print(f"  Wall polylines for canvas: {len(walls_data)}")

# ── 8. Write back to CivilsViewer.tsx ────────────────────────────────────────
print("Writing TSX…")
cells_json = json.dumps(cells, separators=(",",":"))
tris_json  = json.dumps(tris_data, separators=(",",":"))
walls_json = json.dumps(walls_data, separators=(",",":"))

tsx = Path(TSX_PATH).read_text()

# Replace CELLS
tsx = re.sub(
    r"const CELLS\s*=\s*\[.*?\];",
    f"const CELLS   = {cells_json};",
    tsx, flags=re.DOTALL
)

# Remove old TRIS / WALLS if present
tsx = re.sub(r"\nconst TRIS:[^=]+=.*?;\n", "\n", tsx, flags=re.DOTALL)
tsx = re.sub(r"\nconst WALLS:[^=]+=.*?;\n", "\n", tsx, flags=re.DOTALL)

# Insert TRIS + WALLS before LAYERS constant
tsx = tsx.replace(
    "const LAYERS",
    f"const TRIS:number[][]={tris_json};\nconst WALLS:number[][][]={walls_json};\nconst LAYERS",
    1
)

Path(TSX_PATH).write_text(tsx)

r = sum(1 for c in cells if c["i"]==0)
interp = sum(1 for c in cells if c["i"]==1)
bar = sum(1 for c in cells if c["i"]==2)
zeros = sum(1 for c in cells if c["z"]==0)
print(f"\nDone.  Real={r}  Interp={interp}  Barrier={bar}  Zeros={zeros}")
print(f"       Triangles={len(tris_data)}  Wall polylines={len(walls_data)}")
