const CACHE_NAME = "omnix-media-v1";
const MAX_PREFETCH = 5;
const MAX_CACHED_MEDIA_BYTES = 12 * 1024 * 1024;

export async function cacheMedia(url: string): Promise<void> {
  if (!url || typeof caches === "undefined") return;
  try {
    const cache = await caches.open(CACHE_NAME);
    const request = new Request(url, { mode: "cors", credentials: "omit" });
    if (await cache.match(request)) return;
    const response = await fetch(request);
    if (!response.ok) return;
    const contentLength = Number(response.headers.get("content-length") || 0);
    if (contentLength > MAX_CACHED_MEDIA_BYTES) return;
    await cache.put(request, response.clone());
  } catch {
    // Cache is opportunistic; playback/fetch remains authoritative.
  }
}

export async function prefetchMedia(urls: string[], limit = MAX_PREFETCH): Promise<void> {
  const unique = [...new Set(urls.filter(Boolean))].slice(0, Math.min(MAX_PREFETCH, Math.max(0, limit)));
  const queue = [...unique];
  const worker = async () => {
    while (queue.length) {
      const url = queue.shift();
      if (url) await cacheMedia(url);
    }
  };
  await Promise.all([worker(), worker()]);
}

export async function getCachedMedia(url: string): Promise<Response | undefined> {
  if (!url || typeof caches === "undefined") return undefined;
  try {
    const cache = await caches.open(CACHE_NAME);
    return await cache.match(new Request(url, { mode: "cors", credentials: "omit" }));
  } catch {
    return undefined;
  }
}