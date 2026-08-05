// Supabase client — reads connection details from environment variables.
// Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in your .env file.
// See .env.example for the full list of required variables.

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn(
    '[OMNIX] VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY is not set. ' +
    'Copy .env.example to .env and fill in your Supabase credentials.',
  );
}

function buildHeaders(key: string): Record<string, string> {
  return {
    apikey: key,
    Authorization: 'Bearer ' + key,
    'Content-Type': 'application/json',
  };
}

function createClient(url: string, key: string) {
  const headers = buildHeaders(key);

  return {
    auth: {
      signInWithPassword: async (credentials: { email: string; password: string }) => {
        try {
          const res = await fetch(url + '/auth/v1/token?grant_type=password', {
            method: 'POST',
            headers,
            body: JSON.stringify(credentials),
          });
          const data = await res.json();
          if (!res.ok) return { data: null, error: data };
          return { data, error: null };
        } catch (err) {
          return { data: null, error: err };
        }
      },
      signUp: async (credentials: { email: string; password: string }) => {
        try {
          const res = await fetch(url + '/auth/v1/signup', {
            method: 'POST',
            headers,
            body: JSON.stringify(credentials),
          });
          const data = await res.json();
          if (!res.ok) return { data: null, error: data };
          return { data, error: null };
        } catch (err) {
          return { data: null, error: err };
        }
      },
      signOut: async () => {
        try {
          const res = await fetch(url + '/auth/v1/logout', { method: 'POST', headers });
          if (!res.ok) return { error: await res.json() };
          return { error: null };
        } catch (err) {
          return { error: err };
        }
      },
    },
    from: (table: string) => ({
      select: async (columns = '*') => {
        try {
          const res = await fetch(url + '/rest/v1/' + table + '?select=' + encodeURIComponent(columns), { headers });
          const data = await res.json();
          if (!res.ok) return { data: null, error: data };
          return { data: data as unknown[], error: null };
        } catch (err) {
          return { data: null, error: err };
        }
      },
    }),
  };
}

export const supabase = createClient(
  supabaseUrl ?? '',
  supabaseAnonKey ?? '',
);
