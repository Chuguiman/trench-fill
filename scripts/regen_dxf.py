#!/usr/bin/env python3
"""
Regenerate DXF grid exports from CELLS data embedded in React components.

Each run does a full rebuild from scratch so the DXF always reflects the
current CELLS (no stale entities from previous runs).

Each 1m×1m quadrant is a closed POLYLINE3D with group-30 Z on every vertex.
TEXT labels sit inside each cell at the correct Z.

Run from project root:
    python3 scripts/regen_dxf.py
"""

import math, re, json, zipfile, os
from pathlib import Path
import ezdxf

# ── Coordinate origin ─────────────────────────────────────────────────────────
E_OFF = 287676.925
N_OFF = 62656.831

# Layer colours (true-colour RGB as 24-bit int)
def _rgb(r, g, b):
    return (r << 16) | (g << 8) | b

LAYER_COLORS = {
    # Survey
    "SURVEY-REAL":        _rgb(74, 222, 128),
    "SURVEY-INTERP":      _rgb(148, 163, 184),
    "SURVEY-LEVEL-TXT":   _rgb(74, 222, 128),
    # Civils
    "CIVILS-REAL":        _rgb(56, 189, 248),
    "CIVILS-INTERP":      _rgb(100, 116, 139),
    "CIVILS-BARRIER":     _rgb(248, 113, 113),
    "CIVILS-LEVEL-TXT":   _rgb(56, 189, 248),
    # Arch
    "ARCH-REAL":          _rgb(167, 139, 250),
    "ARCH-INTERP":        _rgb(100, 116, 139),
    "ARCH-BARRIER":       _rgb(248, 113, 113),
    "ARCH-BUILDING":      _rgb(96, 165, 250),
    "ARCH-LEVEL-TXT":     _rgb(167, 139, 250),
    # Corr
    "CORR-CUT":           _rgb(59, 130, 246),
    "CORR-FILL":          _rgb(239, 68, 68),
    "CORR-BUILDING":      _rgb(250, 204, 21),
    "CORR-DIFF-TXT":      _rgb(255, 255, 255),
    "CORR-BLDG-TXT":      _rgb(250, 204, 21),
}


def _load_cells(tsx_path: str, array_name: str = "CELLS") -> list:
    content = Path(tsx_path).read_text()
    m = re.search(rf"const {array_name}\s*=\s*(\[.*?\]);", content, re.DOTALL)
    if not m:
        raise ValueError(f"{array_name} not found in {tsx_path}")
    return json.loads(m.group(1))


def _patch_extents(path: str, min_e, max_e, min_n, max_n) -> None:
    """ezdxf resets $EXTMIN/$EXTMAX during saveas — patch raw text after."""
    raw = Path(path).read_text(encoding="utf-8")

    def _rep(text, var, x, y):
        pat = (
            rf"(  9\r?\n\{var}\r?\n"
            rf"\s*10\r?\n)[^\n]+(\r?\n"
            rf"\s*20\r?\n)[^\n]+(\r?\n"
            rf"\s*30\r?\n)[^\n]+"
        )
        return re.sub(pat, rf"\g<1>{x:.6f}\g<2>{y:.6f}\g<3>0.0", text, count=1)

    raw = _rep(raw, "$EXTMIN", min_e, min_n)
    raw = _rep(raw, "$EXTMAX", max_e, max_n)
    Path(path).write_text(raw, encoding="utf-8")


def _ensure_layer(doc, name: str) -> None:
    if name not in doc.layers:
        color = LAYER_COLORS.get(name)
        attribs = {}
        if color is not None:
            attribs["true_color"] = color
        doc.layers.add(name, dxfattribs=attribs)


def build_dxf(
    dxf_path: str,
    cells: list,
    cell_layer_fn,          # cell → layer name for the POLYLINE3D
    z_getter,               # cell → float
    text_layer_fn,          # cell → layer name for TEXT  (or None = no text)
    text_formatter,         # cell → str
    txt_height: float = 0.25,
) -> None:
    """Full rebuild: create a fresh DXF from CELLS data."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    all_e, all_n = [], []

    for cell in cells:
        cx, cy = cell["x"], cell["y"]
        z = z_getter(cell)
        min_e = cx + E_OFF
        min_n = cy + N_OFF

        poly_layer = cell_layer_fn(cell)
        _ensure_layer(doc, poly_layer)

        # Closed 3D square: 4 corners + back to first
        pts = [
            (min_e,       min_n,       z),
            (min_e + 1.0, min_n,       z),
            (min_e + 1.0, min_n + 1.0, z),
            (min_e,       min_n + 1.0, z),
            (min_e,       min_n,       z),
        ]
        msp.add_polyline3d(pts, dxfattribs={"layer": poly_layer})

        all_e += [min_e, min_e + 1.0]
        all_n += [min_n, min_n + 1.0]

        # TEXT label
        txt_layer = text_layer_fn(cell) if text_layer_fn else None
        if txt_layer:
            _ensure_layer(doc, txt_layer)
            msp.add_text(
                text_formatter(cell),
                dxfattribs={
                    "layer":  txt_layer,
                    "insert": (min_e + 0.1, min_n + 0.2, z),
                    "height": txt_height,
                },
            )

    doc.saveas(dxf_path)
    if all_e:
        _patch_extents(dxf_path, min(all_e), max(all_e), min(all_n), max(all_n))

    poly_n = sum(1 for e in msp if e.dxftype() == "POLYLINE")
    txt_n  = sum(1 for e in msp if e.dxftype() == "TEXT")
    print(f"  {Path(dxf_path).name}: {poly_n} POLYLINE3D  {txt_n} TEXT")


# ── Survey ────────────────────────────────────────────────────────────────────
print("Survey…")
cells = _load_cells("src/components/SurveyViewer.tsx")

def sv_poly_layer(c):
    return "SURVEY-REAL" if c["i"] == 0 else "SURVEY-INTERP"

build_dxf(
    "public/exports/XREF_Survey_Grid.dxf",
    cells,
    cell_layer_fn=sv_poly_layer,
    z_getter=lambda c: c["z"],
    text_layer_fn=lambda c: "SURVEY-LEVEL-TXT",
    text_formatter=lambda c: f"{c['z']:.3f}",
)

# ── Civils ────────────────────────────────────────────────────────────────────
print("Civils…")
cells = _load_cells("src/components/CivilsViewer.tsx")

def cv_poly_layer(c):
    if c["i"] == 2:  return "CIVILS-BARRIER"
    if c["i"] == 0:  return "CIVILS-REAL"
    return "CIVILS-INTERP"

build_dxf(
    "public/exports/XREF_Civils_Grid.dxf",
    cells,
    cell_layer_fn=cv_poly_layer,
    z_getter=lambda c: c["z"],
    text_layer_fn=lambda c: "CIVILS-LEVEL-TXT",
    text_formatter=lambda c: f"{c['z']:.3f}",
)

# ── Arch ──────────────────────────────────────────────────────────────────────
print("Arch…")
cells = _load_cells("src/components/ArchViewer.tsx")

def av_poly_layer(c):
    if c.get("i") == 2: return "ARCH-BARRIER"
    if c.get("b") == 1: return "ARCH-BUILDING"
    if c.get("i") == 0: return "ARCH-REAL"
    return "ARCH-INTERP"

build_dxf(
    "public/exports/XREF_Arch_Grid.dxf",
    cells,
    cell_layer_fn=av_poly_layer,
    z_getter=lambda c: c["z"],
    text_layer_fn=lambda c: "ARCH-LEVEL-TXT",
    text_formatter=lambda c: f"{c['z']:.3f}",
)

# ── Correlation ───────────────────────────────────────────────────────────────
print("Correlation…")
cells = _load_cells("src/components/CorrViewer.tsx")

def corr_poly_layer(c):
    t = c.get("t", "diff")
    if t == "building": return "CORR-BUILDING"
    return "CORR-CUT" if c["r"] <= 0 else "CORR-FILL"

def corr_txt_layer(c):
    return "CORR-BLDG-TXT" if c.get("t") == "building" else "CORR-DIFF-TXT"

def corr_text(c):
    if c.get("t") == "building":
        return f"BLDG {c['sv']:.3f}"
    return f"SV:{c['sv']:.3f} CV:{c['cv']:.3f} D:{c['r']:+.3f}"

build_dxf(
    "public/exports/XREF_Corr_SurveyCivils.dxf",
    cells,
    cell_layer_fn=corr_poly_layer,
    z_getter=lambda c: c["sv"],
    text_layer_fn=corr_txt_layer,
    text_formatter=corr_text,
    txt_height=0.2,
)

# ── Rebuild ZIP ───────────────────────────────────────────────────────────────
print("Rebuilding ZIP…")
dxf_files = [
    "public/exports/XREF_Survey_Grid.dxf",
    "public/exports/XREF_Civils_Grid.dxf",
    "public/exports/XREF_Arch_Grid.dxf",
    "public/exports/XREF_Corr_SurveyCivils.dxf",
]
zip_path = "public/exports/XREF_Grids_Export.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for f in dxf_files:
        z.write(f, os.path.basename(f))
print(f"  {zip_path}: {os.path.getsize(zip_path) // 1024} KB")

print("\nDone. All 4 DXF + ZIP regenerated.")
