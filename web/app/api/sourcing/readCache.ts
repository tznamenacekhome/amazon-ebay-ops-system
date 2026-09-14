import { createHash } from "node:crypto";
import { supabase } from "./_supabase";

export async function sourcingCacheVersion() {
  const { data, error } = await supabase.rpc("sourcing_cache_version");
  if (error) throw new Error(`Sourcing freshness: ${error.message}`);
  if (!data || typeof data.revision !== "number") throw new Error("Sourcing cache version is unavailable.");
  return {
    version: createHash("sha256").update(JSON.stringify([process.env.MBOP_BUILD_SHA ?? "local", new Date().toISOString().slice(0,10), data.revision])).digest("hex"),
    running: data.running === true,
  };
}

// Process-local accelerator only: every request verifies the database revision.
// Restarts/multiple ECS tasks affect hit rate, never cache correctness.
const entries = new Map<string, { body: unknown; bytes: number }>();
const pending = new Map<string, Promise<unknown>>();
let generation = "";
let bytes = 0;
export async function cachedSourcingList(key: string, fresh: boolean, build: () => Promise<unknown>) {
  const before = await sourcingCacheVersion();
  if (generation !== before.version) { entries.clear(); bytes = 0; generation = before.version; }
  const cacheKey = `${before.version}:${key}`;
  const hit = !fresh && !before.running ? entries.get(cacheKey) : null;
  if (hit) return { body: hit.body, hit: true };
  if (!fresh && !before.running && pending.has(cacheKey)) return { body: await pending.get(cacheKey), hit: true };
  const task = (async () => {
    const value = await build();
    const after = await sourcingCacheVersion();
    const stable = before.version === after.version && !before.running && !after.running;
    const body = { ...(value as object), cacheVersion: stable ? before.version : null };
    if (stable && generation === before.version) {
      const size = Buffer.byteLength(JSON.stringify(body));
      if (size <= 4 * 1024 * 1024) {
        if (entries.has(cacheKey)) { bytes -= entries.get(cacheKey)!.bytes; entries.delete(cacheKey); }
        while (entries.size >= 24 || bytes + size > 32 * 1024 * 1024) {
          const oldest = entries.keys().next().value!;
          bytes -= entries.get(oldest)!.bytes; entries.delete(oldest);
        }
        entries.set(cacheKey, { body, bytes: size }); bytes += size;
      }
    }
    return body;
  })();
  pending.set(cacheKey, task);
  try { return { body: await task, hit: false }; }
  finally { if (pending.get(cacheKey) === task) pending.delete(cacheKey); }
}
