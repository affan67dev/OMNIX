const rawApiBase = String(import.meta.env.VITE_API_BASE_URL || '').trim();

// Production must be explicitly configured. Never silently fall back to localhost,
// because a Vercel browser cannot reach a developer's local FastAPI process.
export const API_BASE = rawApiBase.replace(/\/$/, '');
export const apiConfigurationError = !API_BASE
  ? 'Backend API is not configured for this deployment. Set VITE_API_BASE_URL in the Vercel environment.'
  : null;

// Compatibility namespace only; this is never sent to the server and is not a user identity.
export const CURRENT_USER_ID = 'authenticated-session';

type RequestOptions = RequestInit & {
  query?: Record<string, string | number | boolean | undefined>;
};

function requireApiConfiguration(): void {
  if (!API_BASE) {
    throw new Error(apiConfigurationError || 'Backend API is not configured.');
  }
}

export async function apiJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  requireApiConfiguration();
  const url = new URL(`${API_BASE}${path}`);

  Object.entries(options.query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      url.searchParams.set(key, String(value));
    }
  });

  const headers = new Headers(options.headers ?? {});
  let accessToken: string | null = null;
  try {
    accessToken = window.localStorage.getItem('access_token');
  } catch {
    console.error('Unable to read access token');
  }
  if (accessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url.toString(), {
    ...options,
    headers,
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload ? String(payload.detail) : `Request failed with status ${response.status}`;
    throw new Error(detail);
  }

  return payload as T;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  requireApiConfiguration();
  const url = new URL(`${API_BASE}${path}`);
  const form = new FormData();
  form.append('file', file);
  const headers = new Headers();
  try {
    const accessToken = window.localStorage.getItem('access_token');
    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  } catch {
    console.error('Unable to read access token');
  }
  const response = await fetch(url.toString(), { method: 'POST', headers, body: form });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload ? String(payload.detail) : `Upload failed with status ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}
