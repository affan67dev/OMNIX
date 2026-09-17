export type ProductionConfigStatus = {
  supabase: 'PRESENT' | 'MISSING';
  api: 'PRESENT' | 'MISSING' | 'LOCALHOST';
};

export function getProductionConfigStatus(): ProductionConfigStatus {
  const supabaseUrl = String(import.meta.env.VITE_SUPABASE_URL || '').trim();
  const supabaseKey = String(import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY || '').trim();
  const apiBase = String(import.meta.env.VITE_API_BASE_URL || '').trim();
  const apiIsLocal = /^https?:\/\/(localhost|127\.0\.0\.1)(?::\d+)?(?:\/|$)/i.test(apiBase);

  return {
    supabase: supabaseUrl && supabaseKey ? 'PRESENT' : 'MISSING',
    api: !apiBase ? 'MISSING' : apiIsLocal ? 'LOCALHOST' : 'PRESENT',
  };
}
