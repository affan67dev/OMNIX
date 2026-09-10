export interface FeedCacheItem<T = unknown> {
  key: string;
  value: T;
  cachedAt: number;
}

const DEFAULT_TTL_MS = 60_000;
const DEFAULT_MAX_ITEMS = 6;

export class FeedPrefetchCache<T> {
  private readonly cache = new Map<string, FeedCacheItem<T>>();
  constructor(private readonly ttlMs = DEFAULT_TTL_MS, private readonly maxItems = DEFAULT_MAX_ITEMS) {}

  get(key: string): T | undefined {
    const item = this.cache.get(key);
    if (!item) return undefined;
    if (Date.now() - item.cachedAt > this.ttlMs) {
      this.cache.delete(key);
      return undefined;
    }
    this.cache.delete(key);
    this.cache.set(key, item);
    return item.value;
  }

  set(key: string, value: T): void {
    this.cache.delete(key);
    this.cache.set(key, { key, value, cachedAt: Date.now() });
    while (this.cache.size > this.maxItems) {
      const oldest = this.cache.keys().next().value;
      if (oldest === undefined) break;
      this.cache.delete(oldest);
    }
  }

  has(key: string): boolean {
    return this.get(key) !== undefined;
  }

  clear(): void {
    this.cache.clear();
  }
}

export function prefetchNext<T>(
  cache: FeedPrefetchCache<T>,
  keys: string[],
  loader: (key: string) => Promise<T>,
  concurrency = 2,
): void {
  const pending = keys.filter((key) => !cache.has(key)).slice(0, 3);
  let cursor = 0;

  const worker = async () => {
    while (cursor < pending.length) {
      const key = pending[cursor++];
      try {
        cache.set(key, await loader(key));
      } catch {
        // Prefetch is opportunistic; the foreground request remains authoritative.
      }
    }
  };

  void Promise.all(Array.from({ length: Math.min(concurrency, pending.length) }, worker));
}
