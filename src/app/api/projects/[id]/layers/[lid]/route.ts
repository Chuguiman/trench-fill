import { supabase } from '@/lib/supabase';

export async function DELETE(_: Request, { params }: { params: Promise<{ lid: string }> }) {
  const { lid } = await params;
  const { error } = await supabase.from('layers').delete().eq('id', lid);
  if (error) return Response.json({ error: error.message }, { status: 500 });
  return new Response(null, { status: 204 });
}
