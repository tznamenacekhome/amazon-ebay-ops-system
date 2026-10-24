import { useEffect, useState } from "react";

type Images = { ebay: string | null; amazon: string | null };

export function ReceivingCoverImages({ itemId, ebayUrl, amazonUrl }: {
  itemId?: string;
  ebayUrl?: string | null;
  amazonUrl?: string | null;
}) {
  const [images, setImages] = useState<Images | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!itemId) return;
    const controller = new AbortController();
    fetch(`/api/receiving/images?item_id=${encodeURIComponent(itemId)}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Images unavailable");
        return await response.json() as Images;
      })
      .then(setImages)
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [itemId]);

  return (
    <div className="mt-5 grid flex-1 grid-cols-2 gap-4" aria-label="Listing cover comparison">
      <Cover label="eBay listing" src={images?.ebay} href={ebayUrl} loading={Boolean(itemId) && !images && !error} />
      <Cover label="Amazon listing" src={images?.amazon} href={amazonUrl} loading={Boolean(itemId) && !images && !error} />
    </div>
  );
}

function Cover({ label, src, href, loading }: { label: string; src?: string | null; href?: string | null; loading: boolean }) {
  const [failed, setFailed] = useState(false);
  const content = src && !failed ? (
    // Preserve original listing image proportions so region and edition markings remain visible.
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={`${label} cover`} className="h-full min-h-0 w-full object-contain" onError={() => setFailed(true)} />
  ) : <span className="px-4 text-center text-sm text-slate-500">{loading ? "Loading image…" : "Image unavailable"}</span>;

  return (
    <figure className="flex min-w-0 flex-col">
      <figcaption className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">{label}</figcaption>
      {href ? (
        <a href={href} target="_blank" rel="noreferrer" aria-label={`Open ${label}`} className="flex min-h-[300px] flex-1 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50 p-2 h-[clamp(300px,40vh,560px)]">
          {content}
        </a>
      ) : (
        <div className="flex min-h-[300px] flex-1 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50 p-2 h-[clamp(300px,40vh,560px)]">{content}</div>
      )}
    </figure>
  );
}
