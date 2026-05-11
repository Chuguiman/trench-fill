#!/usr/bin/env python3
"""
Upgrade a Viewer TSX to include TIN and Boundary visualization.
Reads existing CELLS from TSX, computes TIN and Boundary, and updates TSX.
"""

import json, re, math
from pathlib import Path
import numpy as np
from scipy.spatial import Delaunay
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

def upgrade_viewer(tsx_path):
    print(f"Upgrading {tsx_path}…")
    content = Path(tsx_path).read_text()
    
    # 1. Extract CELLS
    m = re.search(r"const CELLS\s*=\s*(\[.*?\]);", content, re.DOTALL)
    if not m:
        print(f"  CELLS not found in {tsx_path}")
        return
    cells = json.loads(m.group(1))
    print(f"  Found {len(cells)} cells.")

    # 2. Compute TIN
    # For Correlation, we'll use survey points (sv) where si=0
    is_corr = "CorrViewer" in tsx_path
    
    if is_corr:
        real_cells = [c for c in cells if c.get("si") == 0]
        z_key = "sv"
    else:
        real_cells = [c for c in cells if c.get("i") == 0]
        z_key = "z"

    if not real_cells:
        print("  No real cells found. Using all cells for TIN.")
        real_cells = cells
    
    pts = np.array([[c["x"], c["y"]] for c in real_cells], dtype=float)
    z_arr = np.array([c[z_key] for c in real_cells])
    
    print(f"  Computing TIN from {len(real_cells)} points…")
    tri = Delaunay(pts)
    
    tris_data = []
    for simplex in tri.simplices:
        row = []
        for i in simplex:
            row.extend([float(pts[i][0]), float(pts[i][1]), float(z_arr[i])])
        row.append(0) # type 0
        tris_data.append(row)
    
    # 3. Compute Boundary
    print("  Computing Boundary…")
    site_union = unary_union([Point(c["x"], c["y"]).buffer(8) for c in real_cells]).buffer(-4)
    geoms = [site_union] if site_union.geom_type == "Polygon" else list(site_union.geoms)
    boundary_data = [[[round(x,1),round(y,1)] for x,y in g.exterior.coords] for g in geoms]

    # 4. Update TSX
    tris_json = json.dumps(tris_data, separators=(",",":"))
    boundary_json = json.dumps(boundary_data, separators=(",",":"))
    
    all_z = [c[z_key] for c in cells if c[z_key] > 0]
    z_min, z_max = round(min(all_z), 2), round(max(all_z), 2)
    z_range_json = f"[{z_min},{z_max}]"

    # Remove old TRIS/BOUNDARY
    content = re.sub(r"const BOUNDARY:number\[\]\[\]\[\]\s*=\s*\[.*?\];", "", content, flags=re.DOTALL)
    content = re.sub(r"const TRIS:number\[\]\[\]\s*=\s*\[.*?\];", "", content, flags=re.DOTALL)
    
    # Update Z_RANGE
    content = re.sub(r"const Z_RANGE\s*=\s*\[.*?\];", f"const Z_RANGE = {z_range_json};", content, flags=re.DOTALL)
    
    # Insert new ones
    if "const LAYERS" in content:
        content = content.replace("const LAYERS", f"const BOUNDARY:number[][][] = {boundary_json};\nconst TRIS:number[][] = {tris_json};\nconst LAYERS", 1)
    else:
        # CorrViewer might not have LAYERS
        content = content.replace("const ORIGIN", f"const BOUNDARY:number[][][] = {boundary_json};\nconst TRIS:number[][] = {tris_json};\nconst ORIGIN", 1)
    
    Path(tsx_path).write_text(content)
    print("  Done.")

if __name__ == "__main__":
    upgrade_viewer("src/components/SurveyViewer.tsx")
    upgrade_viewer("src/components/ArchViewer.tsx")
    upgrade_viewer("src/components/CorrViewer.tsx")
