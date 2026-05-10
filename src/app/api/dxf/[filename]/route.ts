import { readFile } from 'fs/promises';
import { join } from 'path';

export const dynamic = 'force-dynamic';

const ALLOWED = new Set([
  'XREF_Survey_Grid.dxf',
  'XREF_Civils_Grid.dxf',
  'XREF_Arch_Grid.dxf',
  'XREF_Corr_SurveyCivils.dxf',
]);

export async function GET(_req: Request, { params }: { params: Promise<{ filename: string }> }) {
  const { filename } = await params;

  if (!ALLOWED.has(filename)) {
    return new Response('Not found', { status: 404 });
  }

  const filePath = join(process.cwd(), 'public', 'exports', filename);
  const content = await readFile(filePath, 'latin1');

  return new Response(content, {
    headers: {
      'Content-Type': 'application/octet-stream',
      'Content-Disposition': `attachment; filename="${filename}"`,
      'Cache-Control': 'no-cache',
    },
  });
}
