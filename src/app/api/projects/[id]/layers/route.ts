import { supabase } from '@/lib/supabase';

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const { data: layers, error } = await supabase
    .from('layers')
    .select('*')
    .eq('project_id', id)
    .order('created_at', { ascending: false });
  if (error) return Response.json({ error: error.message }, { status: 500 });

  // Attach grid cell counts via a separate count query per layer
  const enriched = await Promise.all((layers ?? []).map(async (l) => {
    const { count } = await supabase
      .from('survey_grid')
      .select('*', { count: 'exact', head: true })
      .eq('layer_id', l.id);
    return { ...l, grid_count: count ?? 0 };
  }));

  return Response.json(enriched);
}
