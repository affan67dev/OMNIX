const required = ['VITE_SUPABASE_URL', 'VITE_SUPABASE_ANON_KEY', 'VITE_API_BASE_URL'];
const missing = required.filter((name) => !String(process.env[name] || '').trim());
const privileged = ['VITE_SUPABASE_SERVICE_ROLE_KEY', 'VITE_SUPABASE_SERVICE_KEY'].filter((name) => String(process.env[name] || '').trim());
const localhost = /^https?:\/\/(localhost|127\.0\.0\.1)(?::\d+)?(?:\/|$)/i;
const invalid = [];

if (process.env.VITE_SUPABASE_URL && !/^https:\/\//i.test(process.env.VITE_SUPABASE_URL)) {
  invalid.push('VITE_SUPABASE_URL must use HTTPS');
}
if (process.env.VITE_API_BASE_URL && localhost.test(process.env.VITE_API_BASE_URL)) {
  invalid.push('VITE_API_BASE_URL points to localhost/127.0.0.1');
}
if (privileged.length) {
  invalid.push(`privileged frontend credential: ${privileged.join(', ')}`);
}

if (missing.length || invalid.length) {
  if (missing.length) console.error(`Missing required web environment variables: ${missing.join(', ')}`);
  if (invalid.length) console.error(`Invalid web environment configuration: ${invalid.join('; ')}`);
  process.exit(1);
}

console.log('Web production environment contract passed.');
