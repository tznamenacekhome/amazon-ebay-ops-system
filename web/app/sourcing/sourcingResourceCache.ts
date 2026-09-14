"use client";

type Stored = { text: string; status: number };
export const sourcingTabUrls = [
  "/api/sourcing/opportunities?status=all&type=all&limit=50&scope=closest_excluded&format=list",
  "/api/sourcing/opportunities?status=business_excluded&type=all&limit=150&scope=all_open&format=list",
  "/api/sourcing/coverage-cycle",
  "/api/sourcing/coverage-cycle/items?pageSize=50&search=",
  "/api/sourcing/daily-runs?limit=20",
  "/api/sourcing/opportunities?status=watching&type=all&limit=150&scope=all_open&format=list",
  "/api/sourcing/opportunities?status=purchased_pending_match&type=all&limit=150&scope=all_open&format=list",
  "/api/sourcing/history?limit=50",
  "/api/sourcing/matching-intelligence",
  "/api/sourcing/settings",
];
export class SourcingResourceCache {
  private entries = new Map<string, Stored>();
  private pending = new Map<string, Promise<Stored>>();
  private generation = 0;
  private version: string | null = null;
  private checking: Promise<void> | null = null;
  private running = false;
  private foreground = 0;
  private queue: string[] = [];
  private preloaded: string | null = null;
  private pumping = false;
  private active = false;
  private listeners = new Set<() => void>();
  constructor(private transport: typeof fetch = (...args) => fetch(...args)) {}
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  snapshot = () => this.generation;
  invalidate(notify = false) {
    this.generation++; this.entries.clear(); this.queue = []; this.preloaded = null;
    if (notify) this.listeners.forEach(listener => listener());
  }
  async checkVersion() {
    if (this.checking) return this.checking;
    this.checking = (async () => {
      const response = await this.transport("/api/sourcing/cache-version", { cache: "no-store" });
      const body = await response.json();
      if (!response.ok || typeof body.version !== "string") throw new Error(body.error ?? "Sourcing freshness unavailable.");
      const changed = this.version !== null && this.version !== body.version;
      this.version = body.version; this.running = body.running === true;
      if (changed) this.invalidate(true);
    })();
    try { await this.checking; } finally { this.checking = null; }
  }
  start() {
    this.active = true;
    const check = () => { void this.checkVersion().catch(() => { this.version = null; this.invalidate(true); }); };
    check();
    const timer = setInterval(() => { if (typeof document === "undefined" || document.visibilityState === "visible") check(); }, 30_000);
    if (typeof window !== "undefined") window.addEventListener("focus", check);
    return () => { this.active = false; this.queue = []; clearInterval(timer); if (typeof window !== "undefined") window.removeEventListener("focus", check); };
  }
  async get(url: string, options: { fresh?: boolean; background?: boolean } = {}): Promise<Response> {
    if (!options.background) this.foreground++;
    try {
      if (this.checking) await this.checking;
      if (this.version === null) await this.checkVersion();
      const parsed = new URL(url, "https://mbop.invalid");
      parsed.searchParams.delete("_"); parsed.searchParams.delete("fresh"); parsed.searchParams.sort();
      const key = parsed.pathname + (parsed.search ? parsed.search : "");
      const cached = !options.fresh && !this.running ? this.entries.get(key) : null;
      if (cached) return new Response(cached.text, { status: cached.status });
      const generation = this.generation;
      const requestKey = `${generation}:${key}${options.fresh ? ":fresh" : ""}`;
      let task = this.pending.get(requestKey);
      if (!task) {
        task = (async () => {
          const response = await this.transport(key + (options.fresh ? `${parsed.search ? "&" : "?"}fresh=1` : ""), { cache: "no-store" });
          const stored = { text: await response.text(), status: response.status };
          if (response.ok && generation === this.generation && !this.running) {
            const body = JSON.parse(stored.text);
            const stable = !("cacheVersion" in body) || body.cacheVersion === this.version;
            if (stable && stored.text.length < 4 * 1024 * 1024) {
              while (this.entries.size >= 24 || [...this.entries.values()].reduce((sum,item)=>sum+item.text.length,0) + stored.text.length > 16 * 1024 * 1024) this.entries.delete(this.entries.keys().next().value!);
              this.entries.set(key, stored);
            }
          }
          return stored;
        })();
        this.pending.set(requestKey, task);
        void task.finally(() => { if (this.pending.get(requestKey) === task) this.pending.delete(requestKey); }).catch(()=>{});
      }
      const result = await task;
      if (generation !== this.generation) throw new Error("Sourcing data changed while loading. Reloading the current view.");
      return new Response(result.text, { status: result.status });
    } finally { if (!options.background) this.foreground--; }
  }
  prefetchAfterBuyList() {
    if (!this.active || this.running || this.preloaded === this.version) return;
    this.preloaded = this.version; this.queue = [...sourcingTabUrls];
    // Yield to React/the browser so Buy List paints before any background request.
    setTimeout(() => void this.pump(), 100);
  }
  private async pump() {
    if (this.pumping || !this.active || !this.queue.length || this.running) return;
    if (this.foreground) { setTimeout(() => void this.pump(), 200); return; }
    this.pumping = true;
    const next = this.queue.shift()!;
    try { await this.get(next, { background: true }); } catch { /* The active tab will show its actual error and retry. */ }
    finally { this.pumping = false; if (this.queue.length) setTimeout(() => void this.pump(), 100); }
  }
}
export const sourcingResources = new SourcingResourceCache();
export const fetchSourcing = (url: string, fresh = false) => sourcingResources.get(url, { fresh });
