#!/usr/bin/env python3
"""
Regenerate DXF grid exports with explicit Z coordinates on every quadrant vertex.

Each 1m×1m cell LWPOLYLINE is converted to a POLYLINE3D so that every
vertex carries group codes 10/20/30 (X, Y, Z).

Fixes:
  1. Converts matched cells to POLYLINE3D with Z per vertex (group 30).
  2. Adds TEXT label inside every cell that lacks one.
  3. Updates $EXTMIN/$EXTMAX in the DXF header.
  4. Writes clean, ezdxf-validated output (no corruption).

Run from project root:
    python3 scripts/regen_dxf.py
"""

import math, re, json
from pathlib import Path
import ezdxf

# ── Coordinate origin ─────────────────────────────────────────────────────────
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


def _patch_extents(path: str, min_e: float, max_e: float, min_n: float, max_n: float) -> None:
    """
    ezdxf resets $EXTMIN/$EXTMAX to 1e+20 during saveas — patch raw text instead.
    CAD apps use these for initial zoom; wrong values = empty viewport on open.
    """
    raw = Path(path).read_text(encoding="utf-8")

    def _replace_point(text: str, var: str, x: float, y: float) -> str:
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
    cmap           : {(grid_x, grid_y): cell_dict}
    z_getter       : cell_dict → float
    text_formatter : cell_dict → str
    """
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # Cells that already have a TEXT entity — skip adding another.
    existing_txt: set[tuple[int, int]] = set()
    for ent in msp:
        if ent.dxftype() == "TEXT":
            cx, cy = _en_to_cell(ent.dxf.insert.x, ent.dxf.insert.y)
            existing_txt.add((cx, cy))

    to_delete: list = []
    new_polys: list[tuple] = []   # (pts_3d, attribs)
    new_texts: list[tuple] = []   # (layer, e, n, z, text)
    all_e: list[float] = []
    all_n: list[float] = []

    for ent in msp:
        if ent.dxftype() == "LWPOLYLINE":
            min_e, min_n = _poly_origin(ent)
            all_e.append(min_e)
            all_n.append(min_n)
            cx, cy = _en_to_cell(min_e, min_n)
            cell = cmap.get((cx, cy))
            if cell is None:
                continue  # barrier / building — leave as LWPOLYLINE

            z = z_getter(cell)

            # 3D corner points for this 1m×1m square
            pts_2d = [(p[0], p[1]) for p in ent.get_points()]
            pts_3d = [(p[0], p[1], z) for p in pts_2d]
            pts_3d.append(pts_3d[0])   # close

            attribs: dict = {"layer": ent.dxf.layer}
            for attr in ("color", "true_color", "lineweight"):
                if ent.dxf.hasattr(attr):
                    attribs[attr] = getattr(ent.dxf, attr)

            new_polys.append((pts_3d, attribs))
            to_delete.append(ent)

            if (cx, cy) not in existing_txt:
                new_texts.append((
                    text_layer,
                    min_e + 0.1, min_n + 0.2, z,
                    text_formatter(cell),
                ))
                existing_txt.add((cx, cy))

    # Apply changes
    for ent in to_delete:
        msp.delete_entity(ent)

    for pts_3d, attribs in new_polys:
        msp.add_polyline3d(pts_3d, dxfattribs=attribs)

    for layer, te, tn, tz, val in new_texts:
        msp.add_text(
            val,
            dxfattribs={"layer": layer, "insert": (te, tn, tz), "height": txt_height},
        )

    doc.saveas(dxf_path)

    # Patch EXTMIN/EXTMAX (ezdxf resets them on save)
    if all_e:
        _patch_extents(dxf_path, min(all_e), max(all_e) + 1, min(all_n), max(all_n) + 1)

    converted = len(to_delete)
    print(f"  {Path(dxf_path).name}: {converted} cells → POLYLINE3D, {len(new_texts)} new TEXT")


# ── Survey ────────────────────────────────────────────────────────────────────
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

# ── Civils ────────────────────────────────────────────────────────────────────
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

# ── Arch ──────────────────────────────────────────────────────────────────────
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

regen(
    "public/exports/XREF_Corr_SurveyCivils.dxf",
    cmap,
    text_layer="CORR-DIFF-TXT",
    z_getter=lambda c: c["sv"],
    text_formatter=lambda c: (
        f"SV:{c['sv']:.3f} CV:{c['cv']:.3f} D:{c['r']:+.3f}"
        if c.get("t") == "diff"
        else f"BLDG {c['sv']:.3f}"
    ),
    txt_height=0.2,
)

print("\nDone. All 4 DXF files regenerated.")
