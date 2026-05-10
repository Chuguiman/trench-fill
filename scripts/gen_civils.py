#!/usr/bin/env python3
"""
Generate CivilsViewer CELLS from XREF_Civils_External levels.dxf.

Rules enforced:
  1. Z value taken from POINT entity position (EXP-EW-LEVELS-POINTS)
     matched to nearest TEXT label (EXP-EW-LEVELS-TEXT, max 2 m).
     Grid cell = round(point_E - E_OFF), round(point_N - N_OFF).
  2. Barriers = ONLY polylines on 'EXP - RETAINING WALLS - 0.6m' or
     'EXP - RETAINING WALLS GRAVEL BOARD'. Nothing else.
  3. After IDW interpolation, any cell with z == 0 (no real points reachable
     in its zone) gets the minimum non-zero value of its 8-neighbours.
     Multiple passes until no zeros remain.

Output: writes updated CELLS + BARRIERS into src/components/CivilsViewer.tsx.

Run from project root:
    python3 scripts/gen_civils.py
"""

import math, json, re
from collections import deque
from pathlib import Path
import ezdxf
from shapely.geometry import LineString

# ── Config ────────────────────────────────────────────────────────────────────
DXF_PATH   = "public/XREF_Civils_External levels.dxf"
TSX_PATH   = "src/components/CivilsViewer.tsx"
E_OFF, N_OFF = 287676.925, 62656.831
X0, X1 = 180, 300
Y0, Y1 = 300, 360
MAX_TEXT_DIST = 2.0   # max metres to match a POINT to a TEXT label

RETAINING_WALL_LAYERS = {
    "EXP - RETAINING WALLS - 0.6m",
    "EXP - RETAINING WALLS GRAVEL BOARD",
}

# ── 1. Parse DXF ──────────────────────────────────────────────────────────────
print("Reading DXF…")
doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Collect TEXT labels (both TEXT and MTEXT)
texts = []   # (E, N, z_float)
for e in msp:
    raw = None
    if e.dxftype() == "TEXT" and e.dxf.layer == "EXP-EW-LEVELS-TEXT":
        raw = e.dxf.text
        te, tn = e.dxf.insert.x, e.dxf.insert.y
    elif e.dxftype() == "MTEXT" and e.dxf.layer == "EXP-EW-LEVELS-TEXT":
        raw = e.text   # strips ezdxf formatting codes
        te, tn = e.dxf.insert.x, e.dxf.insert.y
    if raw is None:
        continue
    raw = re.sub(r'\\[^;]+;|[{}]', '', raw).strip()   # strip MTEXT codes
    try:
        z = float(raw)
        if 100 < z < 200:
            texts.append((te, tn, z))
    except ValueError:
        pass

print(f"  Text labels: {len(texts)}")

# Collect POINT positions and match to nearest label
raw_points = []   # (grid_x, grid_y, z)
for e in msp:
    if e.dxftype() != "POINT" or e.dxf.layer != "EXP-EW-LEVELS-POINTS":
        continue
    pe, pn = e.dxf.location.x, e.dxf.location.y
    gx = pe - E_OFF
    gy = pn - N_OFF
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

# Average duplicate cells
real_accum: dict[tuple, list] = {}
for cx, cy, z in raw_points:
    real_accum.setdefault((cx, cy), []).append(z)
real_map: dict[tuple, float] = {k: sum(v) / len(v) for k, v in real_accum.items()}

# ── 2. Rasterise retaining walls → barrier cells ──────────────────────────────
print("Rasterising retaining walls…")
wall_segs: list[LineString] = []
for e in msp:
    if e.dxftype() == "LWPOLYLINE" and e.dxf.layer in RETAINING_WALL_LAYERS:
        pts2d = [(p[0], p[1]) for p in e.get_points()]
        if len(pts2d) >= 2:
            wall_segs.append(LineString(pts2d))

wall_cells: set[tuple] = set()
for seg in wall_segs:
    steps = max(2, int(seg.length / 0.25))
    for i in range(steps + 1):
        pt = seg.interpolate(i / steps, normalized=True)
        cx = round(pt.x - E_OFF)
        cy = round(pt.y - N_OFF)
        if X0 <= cx <= X1 and Y0 <= cy <= Y1:
            wall_cells.add((cx, cy))

print(f"  Wall cells: {len(wall_cells)}")

# ── 3. Zone flood-fill (4-directional, walls block) ───────────────────────────
def cardinal(cx, cy):
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nx, ny = cx + dx, cy + dy
        if X0 <= nx <= X1 and Y0 <= ny <= Y1:
            yield nx, ny

def eight(cx, cy):
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == dy == 0:
                continue
            nx, ny = cx + dx, cy + dy
            if X0 <= nx <= X1 and Y0 <= ny <= Y1:
                yield nx, ny

unvisited = {
    (cx, cy)
    for cx in range(X0, X1 + 1)
    for cy in range(Y0, Y1 + 1)
    if (cx, cy) not in wall_cells
}

cell_zone: dict[tuple, int] = {}
zone_id = 0
while unvisited:
    start = next(iter(unvisited))
    queue = deque([start])
    visited = {start}
    while queue:
        cell = queue.popleft()
        cell_zone[cell] = zone_id
        unvisited.discard(cell)
        for n in cardinal(*cell):
            if n in unvisited and n not in visited:
                visited.add(n)
                queue.append(n)
    zone_id += 1

# Collect real points per zone
zone_reals: dict[int, list] = {}
for (cx, cy), z in real_map.items():
    zid = cell_zone.get((cx, cy))
    if zid is not None:
        zone_reals.setdefault(zid, []).append((cx, cy, z))

# ── 4. IDW interpolation ──────────────────────────────────────────────────────
print("Interpolating…")
cells = []
for cx in range(X0, X1 + 1):
    for cy in range(Y0, Y1 + 1):
        key = (cx, cy)
        if key in real_map:
            cells.append({"x": cx, "y": cy, "z": round(real_map[key], 3), "i": 0, "b": 0})
        elif key in wall_cells:
            cells.append({"x": cx, "y": cy, "z": 0.0, "i": 2, "b": 1})
        else:
            zid  = cell_zone.get(key)
            reals = zone_reals.get(zid, []) if zid is not None else []
            if not reals:
                cells.append({"x": cx, "y": cy, "z": 0.0, "i": 1, "b": 0})
            else:
                tw = 0.0
                twz = 0.0
                for rcx, rcy, rz in reals:
                    d = math.hypot(cx - rcx, cy - rcy)
                    w = 1.0 / max(d ** 2, 1e-6)
                    tw += w
                    twz += w * rz
                cells.append({"x": cx, "y": cy, "z": round(twz / tw, 3), "i": 1, "b": 0})

# ── 5. Fix zeros: replace with min non-zero 8-neighbour ──────────────────────
print("Fixing zero cells…")
cmap = {(c["x"], c["y"]): c for c in cells}

changed = True
passes = 0
while changed and passes < 20:
    changed = False
    passes += 1
    for c in cells:
        if c["z"] != 0.0:
            continue
        nb_z = [
            cmap[n]["z"]
            for n in eight(c["x"], c["y"])
            if n in cmap and cmap[n]["z"] > 0
        ]
        if nb_z:
            c["z"] = round(min(nb_z), 3)
            changed = True

zeros_left = sum(1 for c in cells if c["z"] == 0.0)
print(f"  Done in {passes} pass(es). Zeros remaining: {zeros_left}")

# ── 6. Write back into CivilsViewer.tsx ──────────────────────────────────────
print("Writing TSX…")
cells_json = json.dumps(cells, separators=(",", ":"))

tsx = Path(TSX_PATH).read_text()
tsx = re.sub(
    r"const CELLS\s*=\s*\[.*?\];",
    f"const CELLS   = {cells_json};",
    tsx,
    flags=re.DOTALL,
)
Path(TSX_PATH).write_text(tsx)

real_n    = sum(1 for c in cells if c["i"] == 0)
interp_n  = sum(1 for c in cells if c["i"] == 1)
barrier_n = sum(1 for c in cells if c["i"] == 2)
print(f"\nDone. Real={real_n}  Interp={interp_n}  Barrier={barrier_n}  Zeros={zeros_left}")
