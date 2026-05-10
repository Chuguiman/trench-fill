#!/usr/bin/env python3
"""
Regenerate DXF grid exports with correct Z elevations on every quadrant.

Fixes:
  1. Adds 'elevation' (group 38) to every LWPOLYLINE cell.
  2. Adds TEXT label inside every cell that lacks one.
  3. Updates $EXTMIN/$EXTMAX in the DXF header.
  4. Writes clean, ezdxf-validated output (no corruption).

Run from project root:
    python3 scripts/regen_dxf.py
"""

import math, re, json
from pathlib import Path
import ezdxf

# ── Coordinate origin ────────────────────────────────────────────────────────
# Grid cell (x, y) bottom-left corner = BNG E=(x + E_OFF), N=(y + N_OFF)
E_OFF = 287676.925
N_OFF = 62656.831


def _load_cells(tsx_path: str, array_name: str = "CELLS") -> list:
    content = Path(tsx_path).read_text()
    m = re.search(rf"const {array_name}\s*=\s*(\[.*?\]);", content, re.DOTALL)
    if not m:
        raise ValueError(f"{array_name} not found in {tsx_path}")
    return json.loads(m.group(1))


def _poly_origin(entity) -> tuple[float, float]:
    """Bottom-left corner (min E, min N) of a closed LWPOLYLINE."""
    pts = list(entity.get_points())
    return min(p[0] for p in pts), min(p[1] for p in pts)


def _en_to_cell(e: float, n: float) -> tuple[int, int]:
    return math.floor(e - E_OFF), math.floor(n - N_OFF)


def _patch_extents(path: str, doc) -> None:
    """
    ezdxf resets $EXTMIN/$EXTMAX to 1e+20 during saveas — patch raw text instead.
    CAD apps use these for initial zoom, so wrong values = empty viewport on open.
    """
    msp = doc.modelspace()
    all_e, all_n = [], []
    for ent in msp:
        if ent.dxftype() == "LWPOLYLINE":
            for pt in ent.get_points():
                all_e.append(pt[0])
                all_n.append(pt[1])
    if not all_e:
        return

    min_e, max_e = min(all_e), max(all_e)
    min_n, max_n = min(all_n), max(all_n)

    raw = Path(path).read_text(encoding="utf-8")

    def _replace_point(text: str, var: str, x: float, y: float) -> str:
        # Pattern: 9\n$VARNAME\n 10\n<x>\n 20\n<y>\n 30\n<z>
        pat = (
            rf"(  9\r?\n\{var}\r?\n"
            rf"\s*10\r?\n)[^\n]+(\r?\n"
            rf"\s*20\r?\n)[^\n]+(\r?\n"
            rf"\s*30\r?\n)[^\n]+"
        )
        repl = rf"\g<1>{x:.6f}\g<2>{y:.6f}\g<3>0.0"
        return re.sub(pat, repl, text, count=1)

    raw = _replace_point(raw, "$EXTMIN", min_e, min_n)
    raw = _replace_point(raw, "$EXTMAX", max_e, max_n)
    Path(path).write_text(raw, encoding="utf-8")


def regen(
    dxf_path: str,
    cmap: dict,
    text_layer: str,
    z_getter,
    text_formatter,
    txt_height: float = 0.25,
) -> None:
    """
    cmap        : {(grid_x, grid_y): cell_dict}
    z_getter    : cell_dict → float  (elevation to set on LWPOLYLINE)
    text_formatter : cell_dict → str (label to write)
    """
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # Collect cells that already have a TEXT entity so we don't duplicate.
    existing_txt: set[tuple[int, int]] = set()
    for ent in msp:
        if ent.dxftype() == "TEXT":
            cx, cy = _en_to_cell(ent.dxf.insert.x, ent.dxf.insert.y)
            existing_txt.add((cx, cy))

    new_texts: list[tuple] = []  # (layer, e, n, z, text)

    for ent in msp:
        if ent.dxftype() != "LWPOLYLINE":
            continue
        min_e, min_n = _poly_origin(ent)
        cx, cy = _en_to_cell(min_e, min_n)
        cell = cmap.get((cx, cy))
        if cell is None:
            continue

        z = z_getter(cell)
        ent.dxf.elevation = z

        if (cx, cy) not in existing_txt:
            center_e = min_e + 0.1
            center_n = min_n + 0.2
            new_texts.append((text_layer, center_e, center_n, z, text_formatter(cell)))
            existing_txt.add((cx, cy))

    for layer, te, tn, tz, val in new_texts:
        msp.add_text(
            val,
            dxfattribs={
                "layer": layer,
                "insert": (te, tn, tz),
                "height": txt_height,
            },
        )

    doc.saveas(dxf_path)
    _patch_extents(dxf_path, doc)
    print(f"  {Path(dxf_path).name}: {len(new_texts)} new TEXT entities added")


# ── Survey ───────────────────────────────────────────────────────────────────
print("Survey…")
cells = _load_cells("src/components/SurveyViewer.tsx")
cmap  = {(c["x"], c["y"]): c for c in cells}
regen(
    "public/exports/XREF_Survey_Grid.dxf",
    cmap,
    text_layer="SURVEY-LEVEL-TXT",
    z_getter=lambda c: c["z"],
    text_formatter=lambda c: f"{c['z']:.3f}",
)

# ── Civils ───────────────────────────────────────────────────────────────────
print("Civils…")
cells = _load_cells("src/components/CivilsViewer.tsx")
cmap  = {(c["x"], c["y"]): c for c in cells}
regen(
    "public/exports/XREF_Civils_Grid.dxf",
    cmap,
    text_layer="CIVILS-LEVEL-TXT",
    z_getter=lambda c: c["z"],
    text_formatter=lambda c: f"{c['z']:.3f}",
)

# ── Arch ─────────────────────────────────────────────────────────────────────
print("Arch…")
cells = _load_cells("src/components/ArchViewer.tsx")
cmap  = {(c["x"], c["y"]): c for c in cells}
regen(
    "public/exports/XREF_Arch_Grid.dxf",
    cmap,
    text_layer="ARCH-LEVEL-TXT",
    z_getter=lambda c: c["z"],
    text_formatter=lambda c: f"{c['z']:.3f}",
)

# ── Correlation ───────────────────────────────────────────────────────────────
print("Correlation…")
cells = _load_cells("src/components/CorrViewer.tsx")
cmap  = {(c["x"], c["y"]): c for c in cells}

def corr_z(c):
    # Use survey elevation as the actual ground Z
    return c["sv"]

def corr_text(c):
    if c.get("t") == "diff":
        return f"SV:{c['sv']:.3f} CV:{c['cv']:.3f} D:{c['r']:+.3f}"
    return f"BLDG {c['sv']:.3f}"

regen(
    "public/exports/XREF_Corr_SurveyCivils.dxf",
    cmap,
    text_layer="CORR-DIFF-TXT",
    z_getter=corr_z,
    text_formatter=corr_text,
    txt_height=0.2,
)

print("\nDone. All 4 DXF files regenerated.")
