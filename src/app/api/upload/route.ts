import { supabase } from '@/lib/supabase';
import { NextRequest } from 'next/server';
import { spawn } from 'child_process';
import { writeFile, unlink } from 'fs/promises';
import { join } from 'path';
import { tmpdir } from 'os';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

function runScript(cmd: string, args: string[]): Promise<{ code: number; out: string; err: string }> {
  return new Promise(resolve => {
    const proc = spawn(cmd, args);
    let out = '', err = '';
    proc.stdout.on('data', d => { out += d; });
    proc.stderr.on('data', d => { err += d; });
    proc.on('close', code => resolve({ code: code ?? 1, out, err }));
  });
}

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const file       = form.get('file') as File;
  const project_id = form.get('project_id') as string;
  const category   = (form.get('category') as string) || 'survey';
  const layer_type = (form.get('layer_type') as string) || 'survey';

  if (!file || !project_id)
    return Response.json({ error: 'file and project_id required' }, { status: 400 });

  // 1. Store DXF in Supabase Storage
  const storagePath = `${project_id}/${Date.now()}_${file.name}`;
  const bytes = await file.arrayBuffer();
  const { error: upErr } = await supabase.storage
    .from('dxf-files')
    .upload(storagePath, bytes, { contentType: 'application/octet-stream', upsert: true });
  if (upErr) return Response.json({ error: upErr.message }, { status: 500 });

  // 2. Create layer record
  const { data: layer, error: lErr } = await supabase
    .from('layers')
    .insert({
      project_id,
      name: file.name.replace(/\.dxf$/i, ''),
      category,
      layer_type,
      source_file: file.name,
      storage_path: storagePath,
      status: 'pending',
    })
    .select()
    .single();
  if (lErr) return Response.json({ error: lErr.message }, { status: 500 });

  // 3. Write DXF to temp file
  const tmpPath = join(tmpdir(), `${layer.id}.dxf`);
  await writeFile(tmpPath, Buffer.from(bytes));

  // 4. Run ingestor (IDW grid → Supabase)
  const ingest = await runScript('python3', [
    join(process.cwd(), 'scripts', 'ingest_dxf.py'),
    '--layer-id', layer.id,
    '--dxf', tmpPath,
    '--db', 'postgresql://postgres:8VoExsb8ehhNpfxy@db.uunjotqkfxcbalwcsoot.supabase.co:5432/postgres',
  ]);

  if (ingest.code !== 0) {
    await unlink(tmpPath).catch(() => {});
    await supabase.from('layers').update({ status: 'error', metadata: { error: ingest.err } }).eq('id', layer.id);
    return Response.json({ error: ingest.err }, { status: 500 });
  }

  // 5. Generate SVG plan + JSON export in parallel
  const svgOut  = join(process.cwd(), 'public', 'exports', `${layer.id}.svg`);
  const jsonOut = join(process.cwd(), 'public', 'exports', `${layer.id}.json`);

  const [svg, jsonExport] = await Promise.all([
    runScript('python3', [
      join(process.cwd(), 'scripts', 'gen_svg.py'),
      '--dxf', tmpPath, '--out', svgOut,
    ]),
    runScript('python3', [
      join(process.cwd(), 'scripts', 'export_dxf.py'),
      '--dxf', tmpPath, '--out', jsonOut,
    ]),
  ]);

  await unlink(tmpPath).catch(() => {});

  const svgPath  = svg.code === 0        ? `/exports/${layer.id}.svg`  : null;
  const jsonPath = jsonExport.code === 0 ? `/exports/${layer.id}.json` : null;

  if (svgPath || jsonPath) {
    await supabase.from('layers')
      .update({ metadata: { svg_path: svgPath, json_path: jsonPath } })
      .eq('id', layer.id);
  }

  const { data: updated } = await supabase.from('layers').select('*').eq('id', layer.id).single();
  return Response.json({
    layer: updated,
    svg_path: svgPath,
    json_path: jsonPath,
    log: ingest.out
      + (svg.code !== 0        ? `\nSVG warning: ${svg.err}`  : '')
      + (jsonExport.code !== 0 ? `\nJSON warning: ${jsonExport.err}` : ''),
  }, { status: 201 });
}
