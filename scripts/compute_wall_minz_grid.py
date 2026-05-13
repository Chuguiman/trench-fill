import json
import math
import re
import numpy as np
from collections import deque
import ezdxf

# --- Configuration ---
INPUT_JSON = 'public/exports/5837b788-43f8-4d58-9266-a0514fca31d2.json'
OUTPUT_JSON = 'public/exports/5837b788-43f8-4d58-9266-a0514fca31d2_interp.json'
OUTPUT_DXF = 'public/exports/XREF_Civils_Interp_MinZ.dxf'

# Layers to treat as barriers
WALL_LAYERS = [
    r'WALL',
    r'STEPS',
    r'UNDERBUILD',
    r'PLOT-WALLS',
    r'TANKING',
    r'BOUNDARY'
]

# Layers for survey points
POINT_LAYERS = ['EXP-EW-LEVELS-TEXT', 'EXP - LEVELS TEXT']

def is_wall_layer(layer_name):
    for pattern in WALL_LAYERS:
        if re.search(pattern, layer_name, re.I):
            return True
    return False

# --- 1. Load Data ---
print(f"Loading {INPUT_JSON}...")
with open(INPUT_JSON, 'r') as f:
    data = json.load(f)

entities = data.get('entities', [])
print(f"Total entities: {len(entities)}")

# --- 2. Extract Points (Match TEXT to POINT for precision) ---
print("Extracting survey points...")
text_labels = []
actual_points = []

for e in entities:
    if e['type'] in ('TEXT', 'MTEXT') and e['layer'] in POINT_LAYERS:
        try:
            txt = re.sub(r'[^\d.]', '', e['text'])
            z = float(txt)
            if 100 < z < 150:
                text_labels.append({'pos': e['position'], 'z': z})
        except:
            continue
    elif e['type'] == 'POINT' and e['layer'] == 'EXP-EW-LEVELS-POINTS':
        actual_points.append(e['position'])

if not text_labels:
    print("No points found in specified layers. Checking all layers...")
    # ... (rest of fallback logic if needed, but let's prioritize precision first)

print(f"Found {len(text_labels)} text labels and {len(actual_points)} point entities.")

raw_points = []
if actual_points:
    for lbl in text_labels:
        # Find nearest point within 2m
        lx, ly = lbl['pos'][0], lbl['pos'][1]
        best_d = 2.0
        best_p = None
        for px, py, pz in actual_points:
            d = math.hypot(lx-px, ly-py)
            if d < best_d:
                best_d = d
                best_p = (px, py, lbl['z'])
        
        if best_p:
            raw_points.append(best_p)
        else:
            # Fallback to text position if no point nearby
            raw_points.append((lx, ly, lbl['z']))
else:
    raw_points = [(l['pos'][0], l['pos'][1], l['z']) for l in text_labels]

print(f"Final resolved survey points: {len(raw_points)}")

# Determine grid extents
xs = [p[0] for p in raw_points]
ys = [p[1] for p in raw_points]
X0, X1 = int(math.floor(min(xs))), int(math.ceil(max(xs)))
Y0, Y1 = int(math.floor(min(ys))), int(math.ceil(max(ys)))
print(f"Grid Extents: {X1-X0}m x {Y1-Y0}m")

# --- 3. Extract Walls ---
print("Extracting wall barriers...")
wall_segments = []
for e in entities:
    if is_wall_layer(e['layer']):
        if e['type'] in ('LWPOLYLINE', 'POLYLINE'):
            verts = e.get('vertices', [])
            for i in range(len(verts)-1):
                wall_segments.append((verts[i], verts[i+1]))
        elif e['type'] == 'LINE':
            wall_segments.append((e['start'], e['end']))

print(f"Extracted {len(wall_segments)} wall segments.")

# --- 4. Rasterize Barriers ---
print("Rasterizing barriers into 1m grid...")
blocked_cells = set()
for p1, p2 in wall_segments:
    # Simple line rasterization (Bresenham-ish or sampling)
    dist = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
    steps = max(2, int(dist * 4)) # 25cm sampling
    for s in range(steps + 1):
        tx = p1[0] + (p2[0]-p1[0]) * (s/steps)
        ty = p1[1] + (p2[1]-p1[1]) * (s/steps)
        cx, cy = int(round(tx)), int(round(ty))
        if X0 <= cx <= X1 and Y0 <= cy <= Y1:
            blocked_cells.add((cx, cy))

# --- 5. Map Points to Cells (Min-Z) ---
cell_reals = {} # (cx, cy) -> min_z
for px, py, pz in raw_points:
    cx, cy = int(round(px)), int(round(py))
    if X0 <= cx <= X1 and Y0 <= cy <= Y1:
        if (cx, cy) not in cell_reals or pz < cell_reals[(cx, cy)]:
            cell_reals[(cx, cy)] = pz

# --- 6. Zone Segmentation (Flood Fill) ---
print("Segmenting into zones...")
unvisited = {(cx, cy) for cx in range(X0, X1+1) for cy in range(Y0, Y1+1) if (cx, cy) not in blocked_cells}
cell_zone = {}
zone_reals = {} # zone_id -> list of (x, y, z)
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
        
        for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
            nb = (curr[0]+dx, curr[1]+dy)
            if nb in unvisited and nb not in visited:
                visited.add(nb)
                q.append(nb)
    zone_id += 1

print(f"Found {zone_id} isolated zones.")

# --- 7. Interpolation within Zones ---
print("Interpolating empty cells...")
grid_cells = []

for cx in range(X0, X1+1):
    for cy in range(Y0, Y1+1):
        key = (cx, cy)
        zid = cell_zone.get(key)
        
        if key in cell_reals:
            grid_cells.append({"x": cx, "y": cy, "z": round(cell_reals[key], 3), "type": "real"})
        elif key in blocked_cells:
            # Maybe show wall cells?
            grid_cells.append({"x": cx, "y": cy, "z": None, "type": "barrier"})
        elif zid is not None and zid in zone_reals:
            reals = zone_reals[zid]
            # IDW Interpolation
            tw = 0.0
            twz = 0.0
            for rx, ry, rz in reals:
                d2 = (cx-rx)**2 + (cy-ry)**2
                w = 1.0 / max(d2, 0.01)
                tw += w
                twz += w * rz
            
            z_interp = twz / tw
            grid_cells.append({"x": cx, "y": cy, "z": round(z_interp, 3), "type": "interp"})

# --- 8. Export JSON ---
output_data = {
    "source": INPUT_JSON,
    "extents": {"x0": X0, "x1": X1, "y0": Y0, "y1": Y1},
    "cells": grid_cells
}
with open(OUTPUT_JSON, 'w') as f:
    json.dump(output_data, f)
print(f"Saved JSON to {OUTPUT_JSON}")

# --- 9. Export DXF ---
print("Generating DXF...")
doc = ezdxf.new('R2018')
msp = doc.modelspace()

doc.layers.add("SURVEY_REAL", color=3) # Green
doc.layers.add("SURVEY_INTERP", color=8) # Grey
doc.layers.add("BARRIERS", color=1) # Red

for c in grid_cells:
    if c['type'] == 'real':
        msp.add_point((c['x'], c['y'], c['z']), dxfattribs={'layer': 'SURVEY_REAL'})
        msp.add_text(f"{c['z']:.3f}", dxfattribs={'layer': 'SURVEY_REAL', 'height': 0.1}).set_placement((c['x']+0.1, c['y']+0.1, c['z']))
    elif c['type'] == 'interp':
        msp.add_point((c['x'], c['y'], c['z']), dxfattribs={'layer': 'SURVEY_INTERP'})
        # msp.add_text(f"{c['z']:.3f}", dxfattribs={'layer': 'SURVEY_INTERP', 'height': 0.05}).set_placement((c['x'], c['y'], c['z']))
    elif c['type'] == 'barrier':
        # msp.add_point((c['x'], c['y'], 0), dxfattribs={'layer': 'BARRIERS'})
        pass

# Add original walls for context
for p1, p2 in wall_segments:
    msp.add_line(p1, p2, dxfattribs={'layer': 'BARRIERS'})

doc.saveas(OUTPUT_DXF)
print(f"Saved DXF to {OUTPUT_DXF}")
