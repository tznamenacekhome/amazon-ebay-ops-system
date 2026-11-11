import { createHash } from "node:crypto";

export const DRAFT_PHOTO_BUCKET = "mbop-ebay-draft-photos";
export const MAX_DRAFT_PHOTOS = 60;
export const MAX_DRAFT_PHOTO_BYTES = 20 * 1024 * 1024;
export const MAX_DRAFT_TOTAL_BYTES = 120 * 1024 * 1024;

export type IntakePhoto = {
  file: File;
  corrected: File;
  relativePath: string;
  groupKey: string;
  groupName: string;
  groupingConfidence: number;
  groupingReason: string;
  listingKind: "single" | "lot";
  order: number;
  role: "hero" | "alternate_angle" | "label" | "included_item" | "flaw" | "unknown";
  rotation: 0 | 90 | 180 | 270;
};

export function safeRelativePath(input: string) {
  const parts = input.replaceAll("\\", "/").split("/").filter((part) => part && part !== "." && part !== "..");
  return parts.slice(-5).map((part) => part.replace(/[\u0000-\u001f]/g, "").slice(0, 120)).join("/") || "photo";
}

export function detectedItemNumber(name: string) {
  const match = /(?:^|[^A-Za-z0-9])(\d{5,12})(?=[^A-Za-z0-9]|$)/.exec(name);
  return match?.[1] ?? null;
}

export function importIdempotencyKey(photos: Array<{ relativePath: string; sha256: string }>) {
  const normalized = [...photos]
    .map((photo) => `${safeRelativePath(photo.relativePath).toLocaleLowerCase()}\0${photo.sha256}`)
    .sort()
    .join("\n");
  return createHash("sha256").update(normalized).digest("hex");
}

export function ebaySoldSearchUrl(title: string) {
  const terms = title.trim().split(/\s+/).filter(Boolean).slice(0, 9).join(" ") || "item";
  return `https://www.ebay.com/sch/i.html?${new URLSearchParams({ _nkw: terms, LH_Sold: "1", LH_Complete: "1", rt: "nc" }).toString()}`;
}

export function validateReadyDraft(draft: Record<string, unknown>, photoCount: number) {
  const problems: string[] = [];
  if (!draft.grouping_confirmed) problems.push("Confirm the photo grouping.");
  if (draft.identification_status !== "confirmed") problems.push("Confirm the exact item and variant.");
  if (typeof draft.title !== "string" || !draft.title.trim()) problems.push("Enter a listing title.");
  if (typeof draft.title === "string" && draft.title.length > 80) problems.push("Keep the title to 80 characters or fewer.");
  if (!draft.category_id) problems.push("Enter an eBay leaf category ID.");
  if (!draft.condition_id) problems.push("Choose the item condition.");
  if (!draft.condition_notes || !String(draft.condition_notes).trim()) problems.push("Describe the item's condition.");
  if (draft.tested_status === "unknown") problems.push("Say whether the item was tested, or mark it not applicable.");
  if (!draft.description || !String(draft.description).trim()) problems.push("Enter a description.");
  if (draft.price === null || draft.price === undefined || !Number.isFinite(Number(draft.price)) || Number(draft.price) < 0) problems.push("Enter an asking price.");
  if (!draft.item_specifics || typeof draft.item_specifics !== "object" || Array.isArray(draft.item_specifics)) problems.push("Review item specifics.");
  if (photoCount < 1) problems.push("Add at least one photo.");
  return problems;
}
