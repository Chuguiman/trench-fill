# GIS Sandwich — CAD Layer Stacking & Analysis Platform

> **Standalone project** — no relation to any other system. A web/desktop GIS-style application for stacking, interpolating, and analyzing CAD survey/civil/architectural layers as a "layer sandwich" with vertical drill-down and ideal-vs-real plan comparison.

---

## 🎯 Initial Context Prompt (paste this first to Claude Code)

```
I'm building a standalone GIS-style web application called "GIS Sandwich" — a tool 
for stacking and analyzing CAD survey layers (DXF/DWG) as if they were ingredients 
in a sandwich.

CORE CONCEPT
The user creates a project, uploads multiple DXF files (one per discipline), and 
arranges them as stacked layers from bottom to top:
  • Bottom: topographic survey (the bread)
  • Middle: vegetation, hydrology, geotechnical, civil/architecture (fillings)
  • Top: services, finishings (the bread again)

The user can then:
  1. Reorder layers via drag-and-drop
  2. Toggle individual layer visibility
  3. "Drill" vertically at any (X, Y) coordinate to see a Z-section showing 
     all layers at that point — like piercing the sandwich with a corkscrew
  4. Overlay an "ideal plan" (proposed design) vs "real plan" (existing 
     conditions) and compute the delta

DATA FLOW
DXF upload → Python parses with ezdxf → extract layers, points, polylines → 
interpolate missing elevations with scipy → store in Supabase PostGIS → 
Next.js renders interactive canvas

STACK (NON-NEGOTIABLE)
  • Frontend: Next.js 14 App Router + TypeScript + Tailwind + shadcn/ui
  • Canvas/Map: deck.gl for layer rendering
  • State: Zustand
  • Backend: FastAPI (Python 3.11+) using ezdxf, scipy, numpy
  • Database: Supabase (PostgreSQL + PostGIS extension)
  • Storage: Supabase Storage for raw DXF files
  • Desktop (Phase 5): Tauri shell wrapping the Next.js app

NO Laravel. NO Django. NO Express backend.
The Next.js API routes handle thin CRUD; FastAPI handles all DXF/geometry work.

CRITICAL TECHNICAL CONSTRAINTS
  • DWG R2018+ binary files CANNOT be parsed directly — users must convert to DXF 
    first (via ODA File Converter or AutoCAD's SAVEAS). Document this in the UI.
  • Coordinates are in BNG EPSG:27700 (British National Grid) for the test data, 
    but the system must support arbitrary CRS via the `crs` field on each layer.
  • Survey points are typically sparse (~3-8m spacing); interpolation to a 1m 
    grid uses scipy.interpolate.griddata with method='linear' (Delaunay-based) 
    plus 'nearest' fallback for edge cells.
  • Real vs interpolated points must be visually distinguished (e.g., real = 
    full opacity bold, interpolated = 55% opacity italic).
  • Full-resolution 1m grids over large areas (~600x500m = 300k+ cells) cannot 
    be rendered as HTML tables. Use canvas/WebGL with viewport-based queries 
    (PostGIS bbox filter).

TEST DATA AVAILABLE
A real AutoCAD Civil 3D R2024 survey file (XREF_Survey_Topo.dxf) has been 
processed and validated:
  • 1,793 survey points on layer CLS_LEVELS
  • 422 contour polylines on layer CLS_CONTOURS at 2m intervals  
  • 22 layers total with naming convention CLS_*
  • Z range: 64.74m → 138.45m AOD
  • Coordinate origin (BNG): E=287676.925, N=62656.831
  • Site extent: 610m (E) × 532m (N)
  • Densest section for testing: E287857→287977, N62957→63017 (120×60m, 221 pts)

WORK PHASE BY PHASE
Do NOT try to build everything at once. Each phase has explicit deliverables 
and acceptance criteria. Wait for sign-off before advancing to the next phase.

When I say "start Phase 1", begin with the Supabase schema. When I say 
"start Phase 2", build the FastAPI service. And so on.

Read the full plan in PROJECT_PLAN.md before responding.
```

---

## 📐 Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Browser (Next.js)                    │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Project Dashboard │ Layer Stack │ Z-Drill │ Plan  │ │
│  │  (deck.gl canvas, Zustand state, shadcn UI)        │ │
│  └────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS
        ┌────────────┴────────────┐
        ▼                         ▼
┌──────────────────┐    ┌──────────────────────────────┐
│  Next.js API     │    │      FastAPI (Python)        │
│  ─────────────   │    │  ──────────────────────────  │
│  /api/projects   │    │  /parse        DXF → JSON    │
│  /api/layers     │◄──►│  /interpolate  scipy griddata│
│  /api/auth       │    │  /export       JSON → DXF    │
│  (Supabase SDK)  │    │  /section      Z-drill query │
└────────┬─────────┘    └────────────┬─────────────────┘
         │                           │
         └─────────────┬─────────────┘
                       ▼
        ┌──────────────────────────────┐
        │       Supabase               │
        │  ──────────────────────────  │
        │  PostgreSQL + PostGIS        │
        │  Storage (raw DXF files)     │
        │  Auth (email + OAuth)        │
        └──────────────────────────────┘
```

---

## 🗂 Repository Layout

```
gis-sandwich/
├── apps/
│   ├── web/                      # Next.js 14 App Router
│   │   ├── app/
│   │   │   ├── (auth)/login/
│   │   │   ├── (dashboard)/
│   │   │   │   ├── projects/
│   │   │   │   └── projects/[id]/
│   │   │   └── api/
│   │   │       ├── projects/
│   │   │       └── layers/
│   │   ├── components/
│   │   │   ├── ui/               # shadcn
│   │   │   ├── canvas/           # deck.gl wrappers
│   │   │   ├── layer-stack/      # drag-drop list
│   │   │   └── z-drill/          # vertical section
│   │   ├── lib/
│   │   │   ├── supabase.ts
│   │   │   ├── fastapi-client.ts
│   │   │   └── stores/
│   │   └── package.json
│   │
│   └── api-python/               # FastAPI service
│       ├── app/
│       │   ├── main.py
│       │   ├── routers/
│       │   │   ├── parse.py
│       │   │   ├── interpolate.py
│       │   │   └── export.py
│       │   ├── services/
│       │   │   ├── dxf_parser.py
│       │   │   ├── interpolator.py
│       │   │   └── dxf_writer.py
│       │   └── models/
│       └── requirements.txt
│
├── packages/
│   └── shared-types/             # TS types mirror Python Pydantic
│
├── infra/
│   ├── supabase/
│   │   └── migrations/
│   │       ├── 001_projects.sql
│   │       ├── 002_layers.sql
│   │       └── 003_geometry.sql
│   └── docker-compose.yml        # local FastAPI + Postgres
│
├── PROJECT_PLAN.md               # this file
└── README.md
```

---

## 📦 Phase 1 — Foundation (Database + Project CRUD)

**Goal:** User can sign in, create a project, see an empty project dashboard.

### 1.1 Supabase Schema

```sql
-- migrations/001_projects.sql
CREATE TABLE projects (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  description  TEXT,
  crs          TEXT DEFAULT 'EPSG:27700',
  origin_e     DOUBLE PRECISION,
  origin_n     DOUBLE PRECISION,
  bbox         GEOMETRY(Polygon, 27700),
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users see own projects" ON projects 
  FOR ALL USING (user_id = auth.uid());
```

```sql
-- migrations/002_layers.sql
CREATE TABLE layers (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  category      TEXT,                            -- topo, vegetation, hydro, civil...
  stack_order   INTEGER NOT NULL DEFAULT 0,      -- bottom = 0
  visible       BOOLEAN DEFAULT TRUE,
  color_hex     TEXT,
  source_file   TEXT,                            -- original DXF filename
  storage_path  TEXT,                            -- path in Supabase Storage
  layer_type    TEXT NOT NULL,                   -- 'survey' | 'design_ideal' | 'design_real'
  z_min         DOUBLE PRECISION,
  z_max         DOUBLE PRECISION,
  point_count   INTEGER DEFAULT 0,
  metadata      JSONB DEFAULT '{}',
  status        TEXT DEFAULT 'pending',          -- pending | parsed | interpolated | error
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX layers_project_idx ON layers(project_id, stack_order);
ALTER TABLE layers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users see own layers" ON layers 
  FOR ALL USING (
    project_id IN (SELECT id FROM projects WHERE user_id = auth.uid())
  );
```

```sql
-- migrations/003_geometry.sql
CREATE EXTENSION IF NOT EXISTS postgis;

-- Real survey points (from DXF parse)
CREATE TABLE survey_points (
  id            BIGSERIAL PRIMARY KEY,
  layer_id      UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
  x             DOUBLE PRECISION NOT NULL,
  y             DOUBLE PRECISION NOT NULL,
  z             DOUBLE PRECISION NOT NULL,
  geom          GEOMETRY(PointZ, 27700) GENERATED ALWAYS AS 
                  (ST_SetSRID(ST_MakePoint(x, y, z), 27700)) STORED,
  is_real       BOOLEAN DEFAULT TRUE,            -- false = interpolated
  source_entity TEXT                             -- POINT, INSERT, TEXT, etc.
);

CREATE INDEX survey_points_geom_idx ON survey_points USING GIST(geom);
CREATE INDEX survey_points_layer_idx ON survey_points(layer_id);

-- Interpolated 1m grid (one row per cell, queryable by bbox)
CREATE TABLE survey_grid (
  layer_id      UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
  x             INTEGER NOT NULL,                -- local metres from origin
  y             INTEGER NOT NULL,
  z             DOUBLE PRECISION NOT NULL,
  is_interp     BOOLEAN DEFAULT TRUE,
  PRIMARY KEY (layer_id, x, y)
);

CREATE INDEX survey_grid_xy_idx ON survey_grid(layer_id, x, y);

-- Polylines (contours, road centrelines, building outlines, etc.)
CREATE TABLE layer_polylines (
  id            BIGSERIAL PRIMARY KEY,
  layer_id      UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
  dxf_layer     TEXT,                            -- original DXF layer name
  elevation     DOUBLE PRECISION,
  geom          GEOMETRY(LineStringZ, 27700)
);
CREATE INDEX layer_polylines_geom_idx ON layer_polylines USING GIST(geom);
```

### 1.2 Next.js Bootstrap

- `npx create-next-app@latest apps/web --ts --tailwind --app`
- Install: `@supabase/ssr`, `@supabase/supabase-js`, `zustand`, `lucide-react`, shadcn-ui init
- Auth: email magic link via Supabase
- Pages: `/login`, `/projects` (list), `/projects/new`, `/projects/[id]` (empty for now)

### 1.3 Acceptance Criteria

- [ ] User can sign up and log in
- [ ] User can create a project with name + description
- [ ] User sees their projects in a list
- [ ] User can open a project and see the dashboard shell (no layers yet)
- [ ] RLS verified: User A cannot see User B's projects

**Estimated effort:** 1-2 days

---

## 🐍 Phase 2 — FastAPI Service (DXF Parsing)

**Goal:** Upload a DXF, get back parsed points and layer metadata.

### 2.1 FastAPI Setup

```python
# apps/api-python/requirements.txt
fastapi[standard]==0.110.0
ezdxf==1.2.0
scipy==1.13.0
numpy==1.26.0
shapely==2.0.3
pydantic==2.6.0
supabase==2.4.0
python-multipart==0.0.9
matplotlib==3.8.0  # for contour generation
```

### 2.2 Endpoints

```python
# apps/api-python/app/routers/parse.py

@router.post("/parse")
async def parse_dxf(
    file: UploadFile,
    layer_id: str = Form(...),
    project_id: str = Form(...),
):
    """
    1. Save uploaded DXF temporarily
    2. ezdxf.readfile() → modelspace
    3. Extract:
       - All layers (name, color, entity counts)
       - All POINTs with XYZ
       - All INSERTs paired with adjacent TEXT (Civil 3D COGO points pattern)
       - All LWPOLYLINEs and POLYLINEs
       - Layer category guessed from name (CLS_LEVELS → topo, etc.)
    4. Compute bbox, z_min, z_max
    5. Bulk insert into survey_points + layer_polylines
    6. Update layer status to 'parsed'
    7. Return { point_count, layer_count, bbox, z_range }
    """
```

```python
@router.post("/interpolate")
async def interpolate_layer(layer_id: str, resolution_m: int = 1):
    """
    1. Load all real points for layer_id
    2. scipy.interpolate.griddata with method='linear' over 1m grid
    3. Fill NaN edges with method='nearest'
    4. Bulk insert into survey_grid (is_interp=True for filled cells)
    5. Mark cells where (round(x), round(y)) matches a real point with is_interp=False
    6. Update layer status to 'interpolated'
    """
```

```python
@router.get("/section")
async def vertical_section(project_id: str, x: float, y: float, radius_m: float = 5):
    """
    The Z-DRILL: at point (x, y), return the elevation from EVERY layer in the 
    project, ordered by stack_order. This is the core 'pierce the sandwich' query.
    
    Returns:
    [
      { layer_id, name, stack_order, z_value, source: 'real' | 'interpolated' | 'none' },
      ...
    ]
    """
```

```python
@router.post("/export")
async def export_dxf(layer_id: str, include_interp: bool = True):
    """
    Generate a DXF with:
    - Real points on REAL_POINTS layer
    - Interpolated points on INTERP_POINTS layer
    - 3DFACE mesh on TIN layer
    - Major contours (1m) and minor (0.5m) on separate layers
    Returns DXF as file download.
    """
```

### 2.3 Acceptance Criteria

- [ ] `POST /parse` accepts the test file `XREF_Survey_Topo.dxf` and returns 
      exactly 1,793 points with z range 64.74-138.45
- [ ] `POST /interpolate` produces a complete 1m grid for the densest section 
      with no NaN values
- [ ] `GET /section?x=287900&y=62980` returns at least one entry per loaded layer
- [ ] `POST /export` produces a valid DXF that opens in AutoCAD
- [ ] Service runs in Docker locally and on Railway

**Estimated effort:** 2-3 days

---

## 🥪 Phase 3 — Layer Stack UI (The Sandwich)

**Goal:** User sees their loaded layers as a draggable vertical stack with toggle.

### 3.1 Components

```
components/layer-stack/
├── LayerStackPanel.tsx        # main container, right side of project view
├── LayerCard.tsx              # individual layer with color, name, count
├── LayerDragHandle.tsx        # using @dnd-kit/sortable
├── UploadDropzone.tsx         # accepts .dxf files
└── LayerActions.tsx           # menu: rename, recompute, delete, export
```

### 3.2 Behavior

- Drag-drop reorders `stack_order` in DB (optimistic update)
- Each card shows: thumbnail color swatch, name, category pill, point count, 
  visibility toggle, status badge (pending → parsed → interpolated)
- Upload zone accepts multiple DXFs at once → calls FastAPI `/parse` for each
- Polling every 2s for layers in 'pending' status until they reach 'interpolated'

### 3.3 Acceptance Criteria

- [ ] User uploads `XREF_Survey_Topo.dxf` and sees a card appear with status 'pending'
- [ ] Card transitions to 'parsed' then 'interpolated' without page refresh
- [ ] User can drag the layer up or down in the stack and the order persists
- [ ] User can toggle visibility (no canvas yet — this prepares state for Phase 4)
- [ ] Multiple uploads work in parallel

**Estimated effort:** 2 days

---

## 🎨 Phase 4 — Canvas Viewer (deck.gl)

**Goal:** Render the loaded layers as a stacked, zoomable, pannable map.

### 4.1 deck.gl Layer Mapping

| GIS Sandwich Layer Type | deck.gl Layer | Notes |
|-------------------------|---------------|-------|
| Survey grid (interpolated) | `BitmapLayer` from canvas-rendered heatmap | most performant |
| Real survey points | `ScatterplotLayer` | with elevation color ramp |
| Contour polylines | `PathLayer` | with elevation labels via `TextLayer` |
| Civil/architecture polygons | `SolidPolygonLayer` | with extrude option for 3D |

### 4.2 Viewport-Based Loading

- On pan/zoom, query: `GET /api/grid?layer_id=...&bbox=x0,y0,x1,y1`
- Backend returns only the cells in the viewport (PostGIS bbox filter)
- Cache by tile in Zustand to avoid refetching

### 4.3 Color & Visualization

- Each layer has a base color from its category
- Survey z-values use a fixed elevation ramp (blue → green → yellow → orange → red)
- Real vs interpolated distinguished by opacity (1.0 vs 0.55)
- Stack order controls deck.gl layer z-index

### 4.4 Acceptance Criteria

- [ ] Project dashboard shows a full-screen canvas with the loaded survey
- [ ] Pan and zoom are smooth at 60fps even with 300k+ grid cells
- [ ] Toggling visibility on a layer card hides/shows it in canvas
- [ ] Reordering the stack changes which layer is on top
- [ ] Coordinate readout (E/N/Z) updates as cursor moves over the map

**Estimated effort:** 3-4 days

---

## 🪛 Phase 5 — Z-Drill (Vertical Section)

**Goal:** Click anywhere on the map to "pierce the sandwich" and see all layer 
elevations at that point.

### 5.1 Interaction

- User clicks (or long-presses) a point on the canvas
- Side panel opens showing a vertical bar chart:
  - Y-axis = elevation in metres AOD
  - X-axis = each layer (ordered by stack_order)
  - Each bar starts at the lowest elevation, ends at the layer's elevation 
    at that point
  - Color-coded by layer category

### 5.2 Backend

- Calls `GET /section?project_id=...&x=...&y=...&radius=5`
- For each layer, query nearest cell or interpolate from grid
- Returns ordered array

### 5.3 UI

```
┌────────────────────────────────┐
│  Z-Drill at E287900, N62980    │
├────────────────────────────────┤
│  Services      ▓▓▓ 134.2m      │
│  Civil         ▓▓▓▓▓ 132.5m    │
│  Geotech       ▓▓▓▓▓▓ 130.1m   │
│  Hydrology     ▓▓▓▓▓▓▓ 128.8m  │
│  Vegetation    ▓▓▓▓▓▓▓▓ 127.0m │
│  Topo (real)   ▓▓▓▓▓▓▓▓▓ 125.5m│
└────────────────────────────────┘
```

### 5.4 Acceptance Criteria

- [ ] Click on map opens panel within 200ms
- [ ] Each loaded layer shows its z-value at that point (or "no data")
- [ ] User can pin multiple drill-points for comparison
- [ ] Drill point persists in URL for sharing

**Estimated effort:** 2 days

---

## 📋 Phase 6 — Ideal vs Real Plan Overlay

**Goal:** Compare a proposed design (ideal) against existing/built conditions (real).

### 6.1 Layer Type Distinction

- When uploading, user marks layer as `survey`, `design_ideal`, or `design_real`
- The same DXF can be used for both — the user duplicates and edits one

### 6.2 Diff Computation

- For each pair of (ideal, real) layers, compute on FastAPI:
  - `elevation_delta(x, y) = z_real(x, y) - z_ideal(x, y)`
  - Volume of cut/fill
  - Conflict zones (overlapping building footprints, etc.)

### 6.3 Visualization

- Toggle "Show Diff" mode
- Canvas shows a delta heatmap: red = excess, blue = deficit, transparent = match
- Stats panel: total cut/fill volume, max/min delta, % within tolerance

### 6.4 Acceptance Criteria

- [ ] User uploads two DXFs and tags them ideal/real
- [ ] Diff heatmap renders correctly with sensible color scale
- [ ] Volume calculation matches manual calculation on a simple test case
- [ ] User can export the diff as GeoTIFF or DXF

**Estimated effort:** 3 days

---

## 🖥 Phase 7 — Tauri Desktop Wrapper (Optional)

**Goal:** Same app, packaged as a native desktop app with local processing.

### 7.1 Architecture Change

```
Tauri Shell (Rust)
├── Frontend: same Next.js build (static export)
├── Backend: FastAPI bundled as sidecar binary (PyInstaller)
└── DB: SQLite + SpatiaLite (or local Postgres)
```

### 7.2 Mode Switching

```typescript
// apps/web/lib/api.ts
export const API_BASE = 
  typeof window !== 'undefined' && (window as any).__TAURI__
    ? 'http://localhost:8765'           // local FastAPI sidecar
    : process.env.NEXT_PUBLIC_API_URL;   // cloud
```

### 7.3 Why This Matters

- DXF files can be 50-500MB; uploading is slow and expensive
- Some users have proprietary site data they cannot put in cloud
- Offline use on construction sites with no connectivity

### 7.4 Acceptance Criteria

- [ ] App installs as .dmg/.exe
- [ ] User can open a project file from disk without internet
- [ ] Same UI as web, no functional regressions
- [ ] Optional cloud sync button to push project to Supabase

**Estimated effort:** 4-5 days

---

## 📊 Success Metrics for MVP (Phases 1-4)

When Phases 1-4 are complete, the MVP demo should be:

1. Sign up → create "Demo Site" project
2. Upload `XREF_Survey_Topo.dxf` → wait ~5 seconds → see green "interpolated" badge
3. Upload a vegetation DXF → drag above topo
4. Upload a civil DXF → drag above vegetation  
5. Toggle layers off/on, see canvas update instantly
6. Reorder the stack, see top-down rendering change
7. Pan and zoom around the site smoothly

**That's the validation milestone.** Phases 5-7 add the truly differentiated 
features (Z-drill and ideal-vs-real) that turn this from "another DXF viewer" 
into a real GIS platform.

---

## 🚀 Deployment Targets

| Service | Where | Notes |
|---------|-------|-------|
| Next.js | Vercel | Free tier ok for MVP |
| FastAPI | Railway or Render | Need ~1GB RAM for scipy on large files |
| Supabase | Supabase Cloud | Free tier: 500MB DB, 1GB Storage |
| Tauri builds | GitHub Actions | Cross-compile for macOS/Windows/Linux |

---

## 📚 Reference Implementation Notes

**Real DXF parsing pattern that works (from validated test):**

```python
# Civil 3D COGO points are stored as INSERT (block reference) for the symbol 
# + an adjacent TEXT containing the elevation as a string.
# They are NOT stored as POINT entities with z values.

inserts = [(e.dxf.insert.x, e.dxf.insert.y) 
           for e in msp.query("INSERT") if e.dxf.layer == "CLS_LEVELS"]

texts = []
for e in msp.query("TEXT"):
    if e.dxf.layer == "CLS_LEVELS":
        try:
            texts.append((e.dxf.insert.x, e.dxf.insert.y, float(e.dxf.text)))
        except ValueError:
            pass

# Match each insert to its nearest text within 5m
import math
points = []
for ix, iy in inserts:
    nearest = min(texts, key=lambda t: (ix-t[0])**2 + (iy-t[1])**2)
    if math.sqrt((ix-nearest[0])**2 + (iy-nearest[1])**2) < 5.0:
        points.append((ix, iy, nearest[2]))
```

**Interpolation that works:**

```python
import numpy as np
from scipy.interpolate import griddata

pts = np.array([[p[0], p[1]] for p in real_points])
vals = np.array([p[2] for p in real_points])

xs = np.arange(x_min, x_max + 1)
ys = np.arange(y_min, y_max + 1)
gx, gy = np.meshgrid(xs, ys)
grid_pts = np.column_stack([gx.ravel(), gy.ravel()])

z_linear = griddata(pts, vals, grid_pts, method='linear')
z_nearest = griddata(pts, vals, grid_pts, method='nearest')
z_final = np.where(np.isnan(z_linear), z_nearest, z_linear)
```

**DXF export pattern that works:**

```python
import ezdxf
doc = ezdxf.new("R2018")
doc.units = 6  # metres
msp = doc.modelspace()

doc.layers.add("REAL_POINTS",   color=3)   # green
doc.layers.add("INTERP_POINTS", color=8)   # grey
doc.layers.add("TIN_MESH",      color=7)
doc.layers.add("CONTOURS_1M",   color=1)   # red, major
doc.layers.add("CONTOURS_05M",  color=4)   # cyan, minor

# Points
for x, y, z, is_real in cells:
    layer = "REAL_POINTS" if is_real else "INTERP_POINTS"
    msp.add_point((x, y, z), dxfattribs={"layer": layer})

# 3DFACE mesh (one quad split into 2 triangles per grid cell)
for x in range(x0, x1):
    for y in range(y0, y1):
        z00, z10, z01, z11 = lookup(x,y), lookup(x+1,y), lookup(x,y+1), lookup(x+1,y+1)
        if None in (z00, z10, z01, z11): continue
        msp.add_3dface([(x,y,z00),(x+1,y,z10),(x+1,y+1,z11)], dxfattribs={"layer":"TIN_MESH"})
        msp.add_3dface([(x,y,z00),(x+1,y+1,z11),(x,y+1,z01)], dxfattribs={"layer":"TIN_MESH"})

doc.saveas("output.dxf")
```

---

## 🔒 Security Notes for Claude Code

- Always enable RLS on every table touching user data
- Validate DXF file size (reject > 100MB on cloud, no limit on Tauri local)
- Sanitize DXF layer names before using in SQL queries
- FastAPI must verify the Supabase JWT on every request (use `python-jose`)
- Never expose service role key to the frontend; only use anon key

---

## 🛣 What NOT to Build in MVP

Explicitly out of scope until Phase 6+:
- 3D perspective view (deck.gl supports it but stick to 2D top-down for MVP)
- DWG direct parsing (always require DXF conversion)
- Multi-user collaboration on the same project (single-user only)
- Version history of layers (just delete + re-upload)
- Custom CRS transformations (assume input DXF is already in target CRS)
- Mobile-responsive layout (desktop-only for MVP)

These can come later. Focus on the layer sandwich, interpolation, and Z-drill.

---

## ✅ Ready to Build

The first command for Claude Code after pasting the context prompt should be:

> **"Start Phase 1. Set up the Next.js project, create the Supabase migrations, 
> and build the project CRUD pages. Stop when the acceptance criteria for 
> Phase 1 are met and ask me to verify before moving to Phase 2."**
