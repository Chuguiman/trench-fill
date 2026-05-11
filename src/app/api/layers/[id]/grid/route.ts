import { supabase } from '@/lib/supabase';

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const [gridRes, polyRes] = await Promise.all([
    supabase.rpc('get_layer_grid',      { p_layer_id: id }),
    supabase.rpc('get_layer_polylines', { p_layer_id: id }),
  ]);

  if (gridRes.error) return Response.json({ error: gridRes.error.message }, { status: 500 });
  if (polyRes.error) return Response.json({ error: polyRes.error.message }, { status: 500 });

  return Response.json({ grid: gridRes.data, polylines: polyRes.data });
}
