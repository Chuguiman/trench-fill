#!/usr/bin/env python3
"""
Export all geometry from a DXF file to JSON with exact float64 coordinates.
No rounding, no interpolation — raw CAD data.

Usage:
  python3 scripts/export_dxf.py --dxf <file.dxf> --out <output.json>
"""
import argparse, json, math, re
from pathlib import Path
import ezdxf

ap = argparse.ArgumentParser()
ap.add_argument('--dxf', required=True)
ap.add_argument('--out', required=True)
args = ap.parse_args()

print(f"Reading {args.dxf}…")
doc = ezdxf.readfile(args.dxf)
msp = doc.modelspace()

# ── Coordinate scale (detect mm DXF) ─────────────────────────────────────────
extmin = doc.header.get('$EXTMIN', (0, 0, 0))
extmax = doc.header.get('$EXTMAX', (1, 1, 1))
_max_coord = max(abs(float(extmin[0])), abs(float(extmax[0])),
                 abs(float(extmin[1])), abs(float(extmax[1])))
COORD_SCALE = 0.001 if _max_coord > 2_000_000 else 1.0
if COORD_SCALE != 1.0:
    print(f"  Millimetre DXF detected — scaling ×0.001")

# ── DXF metadata ──────────────────────────────────────────────────────────────
def v3(pt):
    """Convert a DXF point to [x, y, z] with scale applied."""
    return [pt[0] * COORD_SCALE, pt[1] * COORD_SCALE,
            pt[2] * COORD_SCALE if len(pt) > 2 else 0.0]

def v2(pt):
    return [pt[0] * COORD_SCALE, pt[1] * COORD_SCALE]

def clean_mtext(raw):
    return re.sub(r'\\[^;]+;|[{}]', '', raw).strip()

ARC_SEGS = 64  # arc/circle approximation segments

# ── Entity extraction ─────────────────────────────────────────────────────────
entities = []

_SKIP = {'ATTRIB', 'ATTDEF', 'WIPEOUT', 'DIMENSION', 'VIEWPORT'}

def extract(e, from_block=None):
    t = e.dxftype()
    if t in _SKIP:
        return
    layer = getattr(e.dxf, 'layer', '0')
    base = {'type': t, 'layer': layer}
    if from_block:
        base['from_block'] = from_block

    if t == 'LWPOLYLINE':
        pts = [[p[0] * COORD_SCALE, p[1] * COORD_SCALE] for p in e.get_points()]
        if len(pts) < 2:
            return
        closed = bool(getattr(e, 'closed', False) or getattr(e.dxf, 'flags', 0) & 1)
        entities.append({**base, 'closed': closed, 'vertices': pts})

    elif t == 'POLYLINE':
        try:
            pts = [[p[0] * COORD_SCALE, p[1] * COORD_SCALE, p[2] * COORD_SCALE]
                   for p in e.points()]
        except Exception:
            return
        if len(pts) < 2:
            return
        closed = bool(getattr(e.dxf, 'flags', 0) & 1)
        entities.append({**base, 'closed': closed, 'vertices': pts})

    elif t == 'LINE':
        entities.append({**base,
            'start': v3(e.dxf.start),
            'end':   v3(e.dxf.end),
        })

    elif t == 'ARC':
        cx, cy = e.dxf.center.x * COORD_SCALE, e.dxf.center.y * COORD_SCALE
        cz = getattr(e.dxf.center, 'z', 0.0) * COORD_SCALE
        r  = e.dxf.radius * COORD_SCALE
        a0, a1 = e.dxf.start_angle, e.dxf.end_angle
        entities.append({**base,
            'center': [cx, cy, cz],
            'radius': r,
            'start_angle': a0,
            'end_angle':   a1,
        })

    elif t == 'CIRCLE':
        cx, cy = e.dxf.center.x * COORD_SCALE, e.dxf.center.y * COORD_SCALE
        cz = getattr(e.dxf.center, 'z', 0.0) * COORD_SCALE
        r  = e.dxf.radius * COORD_SCALE
        entities.append({**base,
            'center': [cx, cy, cz],
            'radius': r,
        })

    elif t == 'POINT':
        loc = e.dxf.location
        entities.append({**base,
            'position': [loc.x * COORD_SCALE, loc.y * COORD_SCALE,
                         getattr(loc, 'z', 0.0) * COORD_SCALE],
        })

    elif t == 'TEXT':
        try:
            text = e.dxf.text.strip()
            pos  = e.dxf.insert
            entities.append({**base,
                'text':     text,
                'position': [pos.x * COORD_SCALE, pos.y * COORD_SCALE,
                             getattr(pos, 'z', 0.0) * COORD_SCALE],
                'height':   getattr(e.dxf, 'height', 0.0) * COORD_SCALE,
            })
        except Exception:
            pass

    elif t == 'MTEXT':
        try:
            text = clean_mtext(e.text)
            pos  = e.dxf.insert
            entities.append({**base,
                'text':     text,
                'position': [pos.x * COORD_SCALE, pos.y * COORD_SCALE,
                             getattr(pos, 'z', 0.0) * COORD_SCALE],
                'height':   getattr(e.dxf, 'char_height', 0.0) * COORD_SCALE,
            })
        except Exception:
            pass

    elif t == 'INSERT':
        # Record the block reference itself
        pos = e.dxf.insert
        entities.append({**base,
            'block':    e.dxf.name,
            'position': [pos.x * COORD_SCALE, pos.y * COORD_SCALE,
                         getattr(pos, 'z', 0.0) * COORD_SCALE],
            'scale':    [getattr(e.dxf, 'xscale', 1.0),
                         getattr(e.dxf, 'yscale', 1.0),
                         getattr(e.dxf, 'zscale', 1.0)],
            'rotation': getattr(e.dxf, 'rotation', 0.0),
        })
        # Expand constituent geometry
        try:
            for ve in e.virtual_entities():
                extract(ve, from_block=e.dxf.name)
        except Exception:
            pass

    elif t == 'SPLINE':
        try:
            pts = [[p[0] * COORD_SCALE, p[1] * COORD_SCALE,
                    p[2] * COORD_SCALE if len(p) > 2 else 0.0]
                   for p in e.control_points]
            entities.append({**base, 'control_points': pts,
                              'degree': getattr(e.dxf, 'degree', 3)})
        except Exception:
            pass

    elif t == 'ELLIPSE':
        try:
            cx, cy = e.dxf.center.x * COORD_SCALE, e.dxf.center.y * COORD_SCALE
            entities.append({**base,
                'center':     [cx, cy],
                'major_axis': [e.dxf.major_axis.x * COORD_SCALE,
                               e.dxf.major_axis.y * COORD_SCALE],
                'ratio':      e.dxf.ratio,
                'start_param': e.dxf.start_param,
                'end_param':   e.dxf.end_param,
            })
        except Exception:
            pass

# ── Process modelspace ────────────────────────────────────────────────────────
for e in msp:
    extract(e)

# ── Block definitions (raw, before insertion) ─────────────────────────────────
blocks = {}
for block in doc.blocks:
    if block.name.startswith('*'):
        continue
    block_ents = []
    for e in block:
        t = e.dxftype()
        if t in _SKIP:
            continue
        if t == 'LWPOLYLINE':
            try:
                pts = [[p[0] * COORD_SCALE, p[1] * COORD_SCALE] for p in e.get_points()]
                closed = bool(getattr(e, 'closed', False) or getattr(e.dxf, 'flags', 0) & 1)
                block_ents.append({'type': t, 'layer': getattr(e.dxf,'layer','0'),
                                   'closed': closed, 'vertices': pts})
            except Exception:
                pass
        elif t == 'LINE':
            try:
                block_ents.append({'type': t, 'layer': getattr(e.dxf,'layer','0'),
                                   'start': v3(e.dxf.start), 'end': v3(e.dxf.end)})
            except Exception:
                pass
    if block_ents:
        blocks[block.name] = block_ents

# ── Header / metadata ─────────────────────────────────────────────────────────
def hdr(key, default=None):
    v = doc.header.get(key, default)
    if hasattr(v, '__iter__') and not isinstance(v, str):
        return list(v)
    return v

output = {
    'source': Path(args.dxf).name,
    'coord_scale': COORD_SCALE,
    'crs': 'EPSG:27700',
    'header': {
        'extmin':     hdr('$EXTMIN'),
        'extmax':     hdr('$EXTMAX'),
        'insunits':   hdr('$INSUNITS'),
        'measurement': hdr('$MEASUREMENT'),
    },
    'layers': sorted({e.get('layer', '0') for e in entities}),
    'entity_count': len(entities),
    'entities': entities,
    'block_definitions': blocks,
}

# ── Write ─────────────────────────────────────────────────────────────────────
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, 'w') as f:
    json.dump(output, f, separators=(',', ':'))

sz = out.stat().st_size
print(f"  Entities: {len(entities)}")
print(f"  Layers:   {len(output['layers'])}")
print(f"  Done: {out}  ({sz//1024} KB)")
