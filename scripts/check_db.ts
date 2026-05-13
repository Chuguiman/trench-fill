import { supabase } from './src/lib/supabase';

async function checkLayers() {
  const { data, error } = await supabase.from('layers').select('id, name, source_file, metadata');
  if (error) {
    console.error(error);
    return;
  }
  console.log(JSON.stringify(data, null, 2));
}

checkLayers();
