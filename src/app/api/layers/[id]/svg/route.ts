import { supabase } from '@/lib/supabase';
import { spawn } from 'child_process';
import { writeFile, readFile, unlink } from 'fs/promises';
import { join } from 'path';
import { tmpdir } from 'os';

export const dynamic = 'force-dynamic';
export const maxDuration = 120;

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  // Fetch layer record
  const { data: layer, error } = await supabase
    .from('layers').select('*').eq('id', id).single();
  if (error || !layer) return Response.json({ error: 'Layer not found' }, { status: 404 });
  if (layer.status !== 'interpolated')
    return Response.json({ error: 'Layer not yet processed' }, { status: 400 });

  // Download DXF from Supabase Storage
  const { data: blob, error: dlErr } = await supabase.storage
    .from('dxf-files').download(layer.storage_path);
  if (dlErr || !blob) return Response.json({ error: dlErr?.message ?? 'Download failed' }, { status: 500 });

  const dxfPath = join(tmpdir(), `${id}.dxf`);
  const svgPath = join(tmpdir(), `${id}.svg`);
  await writeFile(dxfPath, Buffer.from(await blob.arrayBuffer()));

  // Run gen_svg.py
  const py = spawn('python3', [
    join(process.cwd(), 'scripts', 'gen_svg.py'),
    '--dxf', dxfPath,
    '--out', svgPath,
  ]);
  let stderr = '';
  py.stderr.on('data', d => { stderr += d; });
  await new Promise(res => py.on('close', res));
  await unlink(dxfPath).catch(() => {});

  if (py.exitCode !== 0) {
    return Response.json({ error: stderr }, { status: 500 });
  }

  const svg = await readFile(svgPath, 'utf8');
  await unlink(svgPath).catch(() => {});

  return new Response(svg, {
    headers: {
      'Content-Type': 'image/svg+xml',
      'Content-Disposition': `inline; filename="${layer.name}.svg"`,
    },
  });
}
