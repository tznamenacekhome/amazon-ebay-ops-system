export function imageUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

export function ebayImageUrl(raw: unknown): string | null {
  if (!raw || typeof raw !== "object") return null;
  const record = raw as Record<string, unknown>;
  for (const key of ["PictureURL", "GalleryURL", "imageUrl", "ebay_image_url"]) {
    const values = Array.isArray(record[key]) ? record[key] : [record[key]];
    for (const value of values) {
      const url = imageUrl(value);
      if (url) return url;
    }
  }
  for (const child of Object.values(record)) {
    const url = ebayImageUrl(child);
    if (url) return url;
  }
  return null;
}

export function amazonListingImageUrl(raw: unknown): string | null {
  if (!raw || typeof raw !== "object") return null;
  const summaries = (raw as { summaries?: unknown }).summaries;
  if (!Array.isArray(summaries)) return null;
  for (const summary of summaries) {
    const url = imageUrl(summary?.mainImage?.link);
    if (url) return url;
  }
  return null;
}

export function ebayLegacyItemId(item: { supplier_listing_url?: string | null; supplier_sku?: string | null; raw_import_json?: unknown }): string | null {
  const urlId = item.supplier_listing_url?.match(/\/itm\/(?:[^/?]+\/)?(\d{9,15})(?:[/?]|$)/)?.[1];
  const skuId = item.supplier_sku?.match(/^(\d{9,15})(?:-|$)/)?.[1];
  if (urlId || skuId) return urlId || skuId || null;
  function find(value: unknown): string | null {
    if (!value || typeof value !== "object") return null;
    const record = value as Record<string, unknown>;
    if (typeof record.ItemID === "string" && /^\d{9,15}$/.test(record.ItemID)) return record.ItemID;
    for (const child of Object.values(record)) {
      const id = find(child);
      if (id) return id;
    }
    return null;
  }
  return find(item.raw_import_json);
}
