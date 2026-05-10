import { readFileSync } from "fs";
import { join } from "path";

export const dynamic = "force-dynamic";

interface Contour {
  elevation: number;
  layer: string;
  pts: [number, number][];
}

interface SpotLevel {
  x: number;
  y: number;
  z: number;
}

function parseDxf(content: string): { contours: Contour[]; spots: SpotLevel[] } {
  const lines = content.split(/\r?\n/);
  const contours: Contour[] = [];
  const spots: SpotLevel[] = [];

  let i = 0;
  while (i < lines.length) {
    const code = lines[i]?.trim();
    const val = lines[i + 1]?.trim();

    if (code === "0" && val === "LWPOLYLINE") {
      let layer = "";
      let elevation = 0;
      const pts: [number, number][] = [];
      let x: number | null = null;
      i += 2;
      while (i < lines.length) {
        const c = lines[i]?.trim();
        const v = lines[i + 1]?.trim();
        if (c === "0") break;
        if (c === "8") layer = v;
        else if (c === "38") elevation = parseFloat(v);
        else if (c === "10") x = parseFloat(v);
        else if (c === "20" && x !== null) {
          pts.push([x, parseFloat(v)]);
          x = null;
        }
        i += 2;
      }
      if (pts.length >= 2) contours.push({ elevation, layer, pts });
      continue;
    }

    if (code === "0" && val === "TEXT") {
      let x = 0, y = 0, z = 0, txt = "";
      i += 2;
      while (i < lines.length) {
        const c = lines[i]?.trim();
        const v = lines[i + 1]?.trim();
        if (c === "0") break;
        if (c === "10") x = parseFloat(v);
        else if (c === "20") y = parseFloat(v);
        else if (c === "8" && v === "TOPO-POINTS") { /* skip */ }
        else if (c === "1") txt = v;
        i += 2;
      }
      const num = parseFloat(txt);
      if (!isNaN(num) && num > 100) spots.push({ x, y, z: num });
      continue;
    }

    i += 2;
  }

  return { contours, spots };
}

export async function GET() {
  const filePath = join(process.cwd(), "public", "XREF_Survey_Topo.dxf");
  const content = readFileSync(filePath, "latin1");
  const data = parseDxf(content);
  return Response.json(data);
}
