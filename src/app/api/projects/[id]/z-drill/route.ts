import { supabase } from '@/lib/supabase';
import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';

/**
 * Z-DRILL API
 * Returns elevation from all layers at a specific (E, N) coordinate.
 * Query params: ?e=287900.5&n=62980.2
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id: projectId } = await params;
  const { searchParams } = new URL(req.url);
  const e = parseFloat(searchParams.get('e') || '');
  const n = parseFloat(searchParams.get('n') || '');

  if (isNaN(e) || isNaN(n)) {
    return Response.json({ error: 'Valid e and n coordinates required' }, { status: 400 });
  }

  // 1. Get all interpolated layers for this project
  const { data: layers, error: lErr } = await supabase
    .from('layers')
    .select('id, name, category, layer_type, stack_order')
    .eq('project_id', projectId)
    .eq('status', 'interpolated')
    .order('stack_order', { ascending: true });

  if (lErr) return Response.json({ error: lErr.message }, { status: 500 });
  if (!layers || layers.length === 0) return Response.json({ results: [] });

  const layerIds = layers.map(l => l.id);
  const cx = Math.round(e);
  const cy = Math.round(n);

  // 2. Query the grid for these layers at the integer cell
  const { data: gridPoints, error: gErr } = await supabase
    .from('survey_grid')
    .select('layer_id, z, is_interp')
    .eq('x', cx)
    .eq('y', cy)
    .in('layer_id', layerIds);

  if (gErr) return Response.json({ error: gErr.message }, { status: 500 });

  // 3. Map results back to layer info
  const results = layers.map(l => {
    const pt = gridPoints?.find(p => p.layer_id === l.id);
    return {
      layer_id: l.id,
      name: l.name,
      category: l.category,
      layer_type: l.layer_type,
      z: pt ? pt.z : null,
      is_interp: pt ? pt.is_interp : null,
      found: !!pt
    };
  });

  return Response.json({
    project_id: projectId,
    coord: { e, n, cx, cy },
    results
  });
}
