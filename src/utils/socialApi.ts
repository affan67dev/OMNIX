const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

type RequestOptions = RequestInit & {
  query?: Record<string, string | number | boolean | undefined>;
};

export async function apiJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
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
  } catch (error) {
    console.error('Unable to read access token', error);
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

export { API_BASE };