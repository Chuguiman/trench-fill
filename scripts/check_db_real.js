const { createClient } = require('@supabase/supabase-js');

const URL  = 'https://uunjotqkfxcbalwcsoot.supabase.co';
const ANON = 'sb_publishable_W8oZE3TmVJNhogk4XGM_lA_KhLtaDEu';

const supabase = createClient(URL, ANON);

async function check() {
  const { data, error } = await supabase.from('layers').select('id, name, source_file');
  if (error) console.error(error);
  else console.log(JSON.stringify(data, null, 2));
}

check();
