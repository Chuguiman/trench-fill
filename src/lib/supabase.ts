import { createClient } from '@supabase/supabase-js';

const URL  = 'https://uunjotqkfxcbalwcsoot.supabase.co';
const ANON = 'sb_publishable_W8oZE3TmVJNhogk4XGM_lA_KhLtaDEu';

export const supabase = createClient(URL, ANON);

export type Project = {
  id: string;
  name: string;
  description: string | null;
  crs: string;
  created_at: string;
};

export type Layer = {
  id: string;
  project_id: string;
  name: string;
  category: string | null;
  stack_order: number;
  visible: boolean;
  color_hex: string;
  source_file: string | null;
  layer_type: string;
  z_min: number | null;
  z_max: number | null;
  point_count: number;
  poly_count: number;
  grid_count: number;
  status: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};
