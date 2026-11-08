export const BUSINESS_TIMEZONE = "America/Los_Angeles";
export function businessLocalNow(now = new Date()) {
    const parts = new Intl.DateTimeFormat("sv-SE", { timeZone: BUSINESS_TIMEZONE, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(now);
    return parts.replace(" ", "T");
}
export function mfReference(local: string) {
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local))
        throw new Error("Enter the InventoryLab batch date and time.");
    const d = new Date(`${local}:00Z`);
    if (!Number.isFinite(d.getTime()) || d.toISOString().slice(0, 16) !== local)
        throw new Error("Invalid InventoryLab date/time.");
    const hour = Number(local.slice(11, 13));
    return `MF ${local.slice(0, 10)} ${String(hour % 12 || 12).padStart(2, "0")}:${local.slice(14, 16)} ${hour >= 12 ? "PM" : "AM"}`;
}
export function selectedQuantities(quantities: Record<string, string>) {
    const result: Record<string, string> = {};
    if (!quantities || typeof quantities !== "object" || Array.isArray(quantities) || Object.keys(quantities).length > 500)
        throw new Error("Select at most 500 allocations.");
    for (const [id, value] of Object.entries(quantities)) {
        if (String(value).trim() === "" || Number(value) === 0)
            continue;
        if (!/^(?:amazon-return:)?[0-9a-f-]{36}$/i.test(id) || !Number.isInteger(Number(value)) || Number(value) < 1)
            throw new Error("Selected quantities must be positive whole numbers.");
        result[id] = String(value);
    }
    return result;
}
export const CSV_HEADER = ["ASIN", "MSKU", "Title", "System", "Cost per unit", "List Price", "Quantity", "Purchase date", "Supplier"];
export function listingCsv(rows: string[][]) {
    return [CSV_HEADER, ...rows].map(row => row.map(v => `"${String(v).replaceAll('"', '""')}"`).join(",")).join("\n");
}
