import { readFile } from 'fs/promises';
import { join } from 'path';

export const dynamic = 'force-dynamic';

const ALLOWED = new Set([
  'XREF_Survey_Grid.dxf',
  'XREF_Civils_Grid.dxf',
  'XREF_Arch_Grid.dxf',
  'XREF_Corr_SurveyCivils.dxf',
  'XREF_Civils_Interp_MinZ.dxf',
  'XREF_Civils_External levels.dxf',
  'XREF_Survey_Topo.dxf',
  'XREF_Arch_Site layout.dxf',
  'a7bd1c9b-fe3f-403d-91cd-9e85d8bc80cd.dxf',
]);

export async function GET(_req: Request, { params }: { params: Promise<{ filename: string }> }) {
  const { filename } = await params;

  if (!ALLOWED.has(filename)) {
    return new Response('Not found', { status: 404 });
  }

  // Try exports first, then public root
  let filePath = join(process.cwd(), 'public', 'exports', filename);
  try {
    await readFile(filePath);
  } catch (e) {
    filePath = join(process.cwd(), 'public', filename);
  }

  const content = await readFile(filePath, 'latin1');

  return new Response(content, {
    headers: {
      'Content-Type': 'application/octet-stream',
      'Content-Disposition': `attachment; filename="${filename}"`,
      'Cache-Control': 'no-cache',
    },
  });
}
