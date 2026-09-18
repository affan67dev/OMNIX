import { supabase } from '../supabase/supabaseClient';

const configuredApiBase = String(import.meta.env.VITE_API_BASE_URL || '').trim();
const API_BASE = (configuredApiBase || (import.meta.env.DEV ? 'http://localhost:8000' : '')).replace(/\/$/, '');

export function getConfiguredApiBase(): string {
  if (!API_BASE) {
    throw new Error('OMNIX API is not configured. Set VITE_API_BASE_URL for this deployment.');
  }
  return API_BASE;
}

export function getApiBase(): string {
  return getConfiguredApiBase();
}

// Compatibility namespace only; this is never sent to the server and is not a user identity.
export const CURRENT_USER_ID = 'authenticated-session';

type RequestOptions = RequestInit & {
  query?: Record<string, string | number | boolean | undefined>;
};

export async function apiJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = new URL(`${getConfiguredApiBase()}${path}`);

  Object.entries(options.query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      url.searchParams.set(key, String(value));
    }
  });

  const headers = new Headers(options.headers ?? {});
  let accessToken: string | null = null;
  try {
    accessToken = (await supabase.auth.getSession()).data.session?.access_token ?? null;
  } catch (error) {
    console.error('Unable to resolve current Supabase session', error);
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
  const url = new URL(`${getConfiguredApiBase()}${path}`);
  const form = new FormData();
  form.append('file', file);
  const headers = new Headers();
  try {
    const accessToken = (await supabase.auth.getSession()).data.session?.access_token ?? null;
    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  } catch (error) {
    console.error('Unable to resolve current Supabase session', error);
  }
  const response = await fetch(url.toString(), { method: 'POST', headers, body: form });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload ? String(payload.detail) : `Upload failed with status ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

export { API_BASE };
