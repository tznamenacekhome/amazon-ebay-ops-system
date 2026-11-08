import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../_server";
import { GET as getPreparation } from "../fba-shipments/route";
import { inventoryLabExportRows } from "../fba-shipments/inventoryLabExport";
import { BUSINESS_TIMEZONE, listingCsv, mfReference, selectedQuantities } from "../../fba/listingBatch";
export const dynamic = "force-dynamic";
const db = createServerSupabaseClient();
export async function GET(request: NextRequest) {
    try {
        const id = request.nextUrl.searchParams.get("id");
        if (id) {
            const { data, error } = await db.from("amazon_listing_batches").select("*,allocations:amazon_listing_allocations(*),lots:amazon_listing_completions(*,lots:amazon_merchant_inventory_lots(*))").eq("id", id).single();
            if (error)
                throw error;
            if (data.fulfillment_method === "MF" && data.allocations.length) {
                const asins = [...new Set(data.allocations.map((a: {
                        snapshot: {
                            asin: string;
                        };
                    }) => a.snapshot.asin))];
                const { data: skus, error: skuError } = await db.from("amazon_skus").select("asin,seller_sku,condition,fulfillment_channel").in("asin", asins);
                if (skuError)
                    throw skuError;
                const condition = (v: string | null) => (v || "").toLowerCase().replace(/^new_new$/, "new");
                for (const a of data.allocations) {
                    const matches = (skus || []).filter(s => s.asin === a.snapshot.asin && ["MFN", "MF", "MERCHANT", "MERCHANT_NA"].includes((s.fulfillment_channel || "").toUpperCase()) && condition(s.condition) && condition(s.condition) === condition(a.snapshot.condition));
                    const unique = [...new Set(matches.map(s => s.seller_sku))];
                    a.suggested_sku = unique.length === 1 ? unique[0] : null;
                }
            }
            return NextResponse.json(data);
        }
        const { data, error } = await db.from("amazon_listing_batches").select("id,fulfillment_method,external_reference,status,selection,created_at,exported_at,completed_at,fba_shipment_code,allocations:amazon_listing_allocations(quantity,listed_quantity)").order("created_at", { ascending: false }).limit(100);
        if (error)
            throw error;
        return NextResponse.json({ rows: data, time_zone: BUSINESS_TIMEZONE });
    }
    catch (e) {
        return fail(e);
    }
}
export async function POST(request: NextRequest) {
    const denied = requireAdminApiToken(request);
    if (denied)
        return denied;
    try {
        const body = await request.json();
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(body.id))
            throw new Error("Valid internal batch ID required.");
        mfReference(body.local); // Validate wall time without interpreting it as the browser timezone.
        if (body.action === "complete") {
            const { data, error } = await db.rpc("mbop_complete_mf_listing", { p_batch: body.id, p_request: body.request_id, p_items: body.items, p_local: body.local });
            if (error)
                throw error;
            return NextResponse.json(data);
        }
        if (!["FBA", "MF"].includes(body.method))
            throw new Error("Choose FBA or MF.");
        const reference = body.method === "MF" ? mfReference(body.local) : (body.reference || "FBA draft").trim();
        if (body.action === "reference") {
            const { data, error } = await db.from("amazon_listing_batches").update({ external_reference: reference, il_batch_local: body.local, updated_at: new Date().toISOString() }).eq("id", body.id).eq("fulfillment_method", body.method).in("status", ["exported", "partially_listed"]).select().single();
            if (error)
                throw error;
            return NextResponse.json(data);
        }
        if (!["draft", "export"].includes(body.action))
            throw new Error("Unknown batch action.");
        // Retry/re-export returns the original snapshot without querying mutable queue rows.
        const { data: existing, error: lookupError } = await db.from("amazon_listing_batches").select("*").eq("id", body.id).maybeSingle();
        if (lookupError)
            throw lookupError;
        if (existing?.export_csv && body.action === "export")
            return NextResponse.json(existing);
        const quantities = selectedQuantities(body.quantities);
        let allocations = null;
        let csv = null;
        if (body.action === "export") {
            if (!Object.keys(quantities).length)
                throw new Error("Select at least one allocation.");
            const response = await getPreparation(new NextRequest(new URL("/api/fba-shipments", request.url)));
            const preparation = await response.json();
            if (!response.ok)
                throw new Error(preparation.error);
            // All prices/costs and purchase identities come from the existing backend prep query.
            const groups = preparation.rows as Parameters<typeof inventoryLabExportRows>[0];
            if (body.method === "MF")
                for (const group of groups)
                    group.msku = null; // FBA SKUs are not MF mappings.
            const available = new Set(groups.flatMap(g => g.details.map(d => d.item_id)));
            if (Object.keys(quantities).some(id => !available.has(id)))
                throw new Error("Selected allocation is no longer eligible. Refresh and review.");
            allocations = groups.flatMap(g => g.details.filter(d => quantities[d.item_id]).map(d => ({ ...d, quantity: Number(quantities[d.item_id]), sell_price: g.sell_price })));
            if (body.method === "MF" && allocations.some(a => a.source_type !== "purchase_item"))
                throw new Error("Return recovery remains an FBA-only workflow in this phase.");
            csv = listingCsv(inventoryLabExportRows(groups, quantities));
        }
        const { data, error } = await db.rpc("mbop_save_listing_batch", { p_id: body.id, p_method: body.method, p_local: body.local, p_reference: reference, p_selection: body.quantities, p_csv: csv, p_allocations: allocations });
        if (error)
            throw error;
        return NextResponse.json(data);
    }
    catch (e) {
        return fail(e);
    }
}
function fail(e: unknown) {
    return NextResponse.json({ error: e instanceof Error ? e.message : (e as {
            message?: string;
        })?.message || "Listing batch request failed." }, { status: 400 });
}
