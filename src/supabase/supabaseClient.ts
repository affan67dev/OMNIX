type Session = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  expires_at?: number;
  user: any;
};

type AuthListener = (event: string, session: Session | null) => void;

const SUPABASE_URL = String(import.meta.env.VITE_SUPABASE_URL || '').replace(/\/$/, '');
const SUPABASE_KEY = String(import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY || '');
const STORAGE_KEY = 'omnix.supabase.session';
const listeners = new Set<AuthListener>();
let currentSession: Session | null = null;
let initialized = false;

function requireConfig() {
  if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error('Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY (or VITE_SUPABASE_ANON_KEY).');
}

function save(session: Session | null) {
  currentSession = session;
  if (session) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  else window.localStorage.removeItem(STORAGE_KEY);
}

function emit(event: string, session: Session | null) {
  for (const listener of listeners) listener(event, session);
}

async function request(path: string, init: RequestInit = {}, token?: string) {
  requireConfig();
  const headers = new Headers(init.headers || {});
  headers.set('apikey', SUPABASE_KEY);
  headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${SUPABASE_URL}${path}`, { ...init, headers });
  let body: any = null;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) {
    const error: any = new Error(body?.msg || body?.message || body?.error_description || body?.error || `Supabase request failed (${response.status})`);
    error.status = response.status;
    error.code = body?.code;
    throw error;
  }
  return body;
}

async function userForToken(token: string) {
  return request('/auth/v1/user', {}, token);
}

async function initialize() {
  if (initialized) return;
  initialized = true;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    currentSession = stored ? JSON.parse(stored) : null;
  } catch { currentSession = null; }

  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const accessToken = hash.get('access_token');
  const refreshToken = hash.get('refresh_token');
  const expiresIn = Number(hash.get('expires_in') || 3600);
  const type = hash.get('type');
  if (accessToken && refreshToken) {
    try {
      const user = await userForToken(accessToken);
      const session: Session = { access_token: accessToken, refresh_token: refreshToken, expires_in: expiresIn, expires_at: Math.floor(Date.now() / 1000) + expiresIn, user };
      save(session);
      window.history.replaceState({}, document.title, window.location.pathname + window.location.search);
      emit(type === 'recovery' ? 'PASSWORD_RECOVERY' : 'SIGNED_IN', session);
    } catch {
      save(null);
    }
  } else if (currentSession) {
    emit('INITIAL_SESSION', currentSession);
  } else {
    emit('INITIAL_SESSION', null);
  }
}

void initialize();

const auth = {
  async getSession() {
    await initialize();
    if (!currentSession) return { data: { session: null }, error: null };
    const expiresAt = currentSession.expires_at || 0;
    if (expiresAt && expiresAt - Math.floor(Date.now() / 1000) < 60) {
      try {
        const refreshed = await request('/auth/v1/token?grant_type=refresh_token', { method: 'POST', body: JSON.stringify({ refresh_token: currentSession.refresh_token }) });
        currentSession = { ...currentSession, ...refreshed, expires_at: Math.floor(Date.now() / 1000) + Number(refreshed.expires_in || 3600) };
        if (!currentSession.user) currentSession.user = await userForToken(currentSession.access_token);
        save(currentSession);
        emit('TOKEN_REFRESHED', currentSession);
      } catch {
        save(null);
        emit('SIGNED_OUT', null);
        return { data: { session: null }, error: null };
      }
    }
    return { data: { session: currentSession }, error: null };
  },
  async signInWithPassword(credentials: { email?: string; phone?: string; password: string }) {
    try {
      const result = await request('/auth/v1/token?grant_type=password', { method: 'POST', body: JSON.stringify(credentials) });
      const session: Session = { ...result, expires_at: Math.floor(Date.now() / 1000) + Number(result.expires_in || 3600) };
      save(session); emit('SIGNED_IN', session);
      return { data: { session, user: result.user }, error: null };
    } catch (error: any) { return { data: { session: null, user: null }, error }; }
  },
  async signInWithOtp({ phone }: { phone: string; options?: any }) {
    try {
      await request('/auth/v1/otp', { method: 'POST', body: JSON.stringify({ phone, create_user: true }) });
      return { data: {}, error: null };
    } catch (error: any) { return { data: {}, error }; }
  },
  async verifyOtp({ phone, token, type }: { phone: string; token: string; type: string }) {
    try {
      const result = await request('/auth/v1/verify', { method: 'POST', body: JSON.stringify({ phone, token, type }) });
      const session: Session = { ...result, expires_at: Math.floor(Date.now() / 1000) + Number(result.expires_in || 3600) };
      save(session); emit('SIGNED_IN', session);
      return { data: { session, user: result.user }, error: null };
    } catch (error: any) { return { data: { session: null, user: null }, error }; }
  },
  async updateUser(attributes: { email?: string; password?: string; data?: Record<string, unknown> }) {
    const session = (await auth.getSession()).data.session;
    if (!session) return { data: { user: null }, error: new Error('No active authentication session.') };
    try {
      const user = await request('/auth/v1/user', { method: 'PUT', body: JSON.stringify(attributes) }, session.access_token);
      save({ ...session, user }); emit('USER_UPDATED', currentSession);
      return { data: { user }, error: null };
    } catch (error: any) { return { data: { user: null }, error }; }
  },
  async signInWithOAuth({ provider, options }: { provider: string; options?: { redirectTo?: string } }) {
    requireConfig();
    const redirectTo = options?.redirectTo || window.location.origin + '/';
    const url = `${SUPABASE_URL}/auth/v1/authorize?provider=${encodeURIComponent(provider)}&redirect_to=${encodeURIComponent(redirectTo)}`;
    window.location.assign(url);
    return { data: { url }, error: null };
  },
  async signOut() {
    try {
      const session = (await auth.getSession()).data.session;
      if (session) await request('/auth/v1/logout', { method: 'POST', body: JSON.stringify({}) }, session.access_token);
    } catch { /* local session is still cleared below */ }
    save(null); emit('SIGNED_OUT', null);
    return { error: null };
  },
  async resetPasswordForEmail(email: string, options: { redirectTo: string }) {
    try {
      await request('/auth/v1/recover', { method: 'POST', body: JSON.stringify({ email, redirect_to: options.redirectTo }) });
      return { data: {}, error: null };
    } catch (error: any) { return { data: {}, error }; }
  },
  onAuthStateChange(callback: AuthListener) {
    listeners.add(callback);
    void initialize().then(() => callback('INITIAL_SESSION', currentSession));
    return { data: { subscription: { unsubscribe: () => listeners.delete(callback) } } };
  },
};

function queryBuilder(table: string) {
  let columns = '*';
  let filters: Array<[string, string]> = [];
  let updatePayload: Record<string, unknown> | null = null;
  return {
    select(value = '*') { columns = value; return this; },
    eq(column: string, value: string) { filters.push([column, value]); return this; },
    update(value: Record<string, unknown>) { updatePayload = value; return this; },
    async maybeSingle() {
      requireConfig();
      const params = new URLSearchParams({ select: columns, limit: '1' });
      for (const [key, value] of filters) params.set(key, `eq.${value}`);
      const result = await request(`/rest/v1/${table}?${params.toString()}` , {}, currentSession?.access_token);
      return { data: Array.isArray(result) && result.length ? result[0] : null, error: null };
    },
    then(resolve: any, reject: any) {
      const run = async () => {
        requireConfig();
        const params = new URLSearchParams({ select: columns });
        for (const [key, value] of filters) params.set(key, `eq.${value}`);
        if (updatePayload) {
          const response = await request(`/rest/v1/${table}?${params.toString()}`, { method: 'PATCH', body: JSON.stringify(updatePayload) }, currentSession?.access_token);
          return { data: response, error: null };
        }
        const response = await request(`/rest/v1/${table}?${params.toString()}`, {}, currentSession?.access_token);
        return { data: response, error: null };
      };
      return run().then(resolve, reject);
    },
  };
}

export const supabase = {
  auth,
  from: queryBuilder,
};
