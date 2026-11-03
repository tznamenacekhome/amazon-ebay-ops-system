/** CSV dates must never contain UI placeholders or shift date-only values. */
export function inventoryLabPurchaseDate(value?: string | null): string {
  if (!value || !/^\d{4}-\d{2}-\d{2}(?:$|T)/.test(value)) return "";
  const dateOnly = value.slice(0, 10);
  const date = new Date(`${dateOnly}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== dateOnly) return "";
  const [year, month, day] = dateOnly.split("-");
  return `${month}/${day}/${year}`;
}
