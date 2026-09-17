const required = ['VITE_SUPABASE_URL', 'VITE_API_BASE_URL'];
const missing = required.filter((name) => !String(process.env[name] || '').trim());
const publicKey = String(process.env.VITE_SUPABASE_PUBLISHABLE_KEY || process.env.VITE_SUPABASE_ANON_KEY || '').trim();
if (!publicKey) missing.push('VITE_SUPABASE_PUBLISHABLE_KEY or VITE_SUPABASE_ANON_KEY');

if (missing.length) {
  console.error(`Missing production web configuration: ${missing.join(', ')}`);
  process.exit(1);
}

if (!/^https:\/\//i.test(process.env.VITE_SUPABASE_URL)) {
  console.error('VITE_SUPABASE_URL must use HTTPS in production.');
  process.exit(1);
}

if (/^https?:\/\/(localhost|127\.0\.0\.1)(?::\d+)?(?:\/|$)/i.test(process.env.VITE_API_BASE_URL)) {
  console.error('VITE_API_BASE_URL must not point to localhost or 127.0.0.1 in production.');
  process.exit(1);
}

if (process.env.VITE_SUPABASE_SERVICE_ROLE_KEY || process.env.VITE_SUPABASE_SERVICE_KEY) {
  console.error('Privileged Supabase keys must never be exposed to the Vite frontend.');
  process.exit(1);
}

console.log('Production web configuration contract passed.');