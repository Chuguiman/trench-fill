#!/usr/bin/env python3
"""
Compute a high-precision 1m x 1m grid from CAD JSON data.
Implements:
1. Barrier-aware interpolation (murs/walls block data flow).
2. Min-Z logic (use lowest elevation in each 1x1m cell).
3. Zone flood-fill to isolate areas.
"""
import argparse, json, math, re
import numpy as np
from pathlib import Path
from collections import deque

ap = argparse.ArgumentParser()
ap.add_argument('--json', required=True, help="Input CAD JSON (from export_dxf.py)")
ap.add_argument('--out', required=True, help="Output JSON grid")
args = ap.parse_args()

# ── 1. Load Data ──────────────────────────────────────────────────────────────
print(f"Loading {args.json}…")
with open(args.json, 'r') as f:
    data = json.load(f)

entities = data.get('entities', [])

# ── 2. Extract Points with Precision Z ────────────────────────────────────────
print("Extracting survey points…")
points = [] # (x, y, z)

for e in entities:
    t = e['type']
    if t in ('TEXT', 'MTEXT'):
        try:
            val = float(e['text'].replace('m', ''))
            if 50 < val < 250: # Valid survey range
                p = e.get('position', [0, 0, 0])
                points.append((p[0], p[1], val))
        except:
            pass
    elif t in ('POINT', 'INSERT'):
        p = e.get('position', [0, 0, 0])
        if abs(p[2]) > 0.1: # Only if it has a real physical Z
            points.append((p[0], p[1], p[2]))

if not points:
    print("Error: No survey points found.")
    exit(1)

# Bounding box for construction area (where points are)
xs = [p[0] for p in points]
ys = [p[1] for p in points]
X0, X1 = int(math.floor(min(xs))), int(math.ceil(max(xs)))
Y0, Y1 = int(math.floor(min(ys))), int(math.ceil(max(ys)))
grid_w = X1 - X0 + 1
grid_h = Y1 - Y0 + 1
print(f"  Grid Extents: {grid_w}x{grid_h}m (E:[{X0},{X1}], N:[{Y0},{Y1}])")

# ── 3. Extract Wall Barriers ──────────────────────────────────────────────────
print("Detecting wall barriers…")
walls = [] # List of list of (x, y)

# Layer names that suggest barriers
WALL_RE = re.compile(r'WALL|RETAINING|BOUNDARY|BUILDING|STRUCTURE', re.I)

for e in entities:
    layer = e.get('layer', '0')
    if WALL_RE.search(layer) and e['type'] in ('LWPOLYLINE', 'POLYLINE'):
        pts = e.get('vertices', [])
        if len(pts) >= 2:
            walls.append([(p[0], p[1]) for p in pts])

print(f"  Detected {len(walls)} barrier polylines.")

# ── 4. Rasterize Walls and Grid ───────────────────────────────────────────────
# We use a set of (cx, cy) for blocked cells
wall_cells = set()
for poly in walls:
    for i in range(len(poly)-1):
        p0, p1 = poly[i], poly[i+1]
        dist = math.hypot(p1[0]-p0[0], p1[1]-p0[1])
        steps = max(2, int(dist / 0.2)) # 20cm step for rasterization
        for s in range(steps + 1):
            tx = p0[0] + (p1[0]-p0[0]) * (s/steps)
            ty = p0[1] + (p1[1]-p0[1]) * (s/steps)
            cx, cy = int(round(tx)), int(round(ty))
            if X0 <= cx <= X1 and Y0 <= cy <= Y1:
                wall_cells.add((cx, cy))

print(f"  Rasterized {len(wall_cells)} barrier cells.")

# ── 5. Map Points to Cells (Min-Z logic) ──────────────────────────────────────
cell_reals = {} # (cx, cy) -> min_z
for px, py, pz in points:
    cx, cy = int(round(px)), int(round(py))
    if X0 <= cx <= X1 and Y0 <= cy <= Y1:
        if (cx, cy) not in cell_reals or pz < cell_reals[(cx, cy)]:
            cell_reals[(cx, cy)] = pz

# ── 6. Zone Flood-Fill ────────────────────────────────────────────────────────
print("Segmenting site into zones…")
unvisited = {(cx, cy) for cx in range(X0, X1+1) for cy in range(Y0, Y1+1) if (cx, cy) not in wall_cells}
cell_zone = {}
zone_reals = {} # zone_id -> list of (cx, cy, z)
zone_id = 0

while unvisited:
    start = next(iter(unvisited))
    q = deque([start])
    visited = {start}
    while q:
        curr = q.popleft()
        cell_zone[curr] = zone_id
        unvisited.discard(curr)
        if curr in cell_reals:
            zone_reals.setdefault(zone_id, []).append((curr[0], curr[1], cell_reals[curr]))
        
        # 4-connectivity
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nb = (curr[0]+dx, curr[1]+dy)
            if nb in unvisited and nb not in visited:
                visited.add(nb)
                q.append(nb)
    zone_id += 1

print(f"  Found {zone_id} separate zones.")

# ── 7. Barrier-Aware Interpolation ───────────────────────────────────────────
print("Interpolating grid cells…")
grid_data = []

for cx in range(X0, X1+1):
    for cy in range(Y0, Y1+1):
        key = (cx, cy)
        zid = cell_zone.get(key)
        
        if key in cell_reals:
            # Real point exists in this cell
            grid_data.append({"x":cx, "y":cy, "z":round(cell_reals[key], 3), "type":"real"})
        elif key in wall_cells:
            # It's a wall cell, maybe take min neighbor?
            grid_data.append({"x":cx, "y":cy, "z":None, "type":"barrier"})
        elif zid is not None and zid in zone_reals:
            # Interpolate from points in the SAME zone
            reals = zone_reals[zid]
            # Simple IDW (Inverse Distance Weighting)
            tw = 0.0
            twz = 0.0
            for rx, ry, rz in reals:
                d2 = (cx-rx)**2 + (cy-ry)**2
                if d2 == 0: # Should not happen due to cell_reals check above
                    w = 1.0; d2 = 1.0
                else:
                    w = 1.0 / d2
                tw += w
                twz += w * rz
            
            z_interp = twz / tw
            grid_data.append({"x":cx, "y":cy, "z":round(z_interp, 3), "type":"interp"})
        else:
            # No data for this zone or cell
            grid_data.append({"x":cx, "y":cy, "z":None, "type":"void"})

# ── 8. Write Output ───────────────────────────────────────────────────────────
output = {
    "extents": {"x0":X0, "x1":X1, "y0":Y0, "y1":Y1},
    "cell_size": 1.0,
    "points_count": len(points),
    "zones_count": zone_id,
    "cells": grid_data
}

with open(args.out, 'w') as f:
    json.dump(output, f, separators=(',', ':'))

print(f"Done: {args.out} ({len(grid_data)} cells)")
