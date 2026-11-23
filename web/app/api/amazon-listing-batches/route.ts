import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../_server";
import { GET as getPreparation } from "../fba-shipments/route";
import { inventoryLabExportRows } from "../fba-shipments/inventoryLabExport";
import { BUSINESS_TIMEZONE, listingCsv, mfReference, selectedQuantities } from "../../fba/listingBatch";
import { fetchListingSkuMappings, resolveListingSku, resolveMfExportSku } from "../amazonSkuIdentity";
export const dynamic = "force-dynamic";
const db = createServerSupabaseClient();
export async function GET(request: NextRequest) {
    try {
        const id = request.nextUrl.searchParams.get("id");
        if (id) {
            const { data, error } = await db.from("amazon_listing_batches").select("*,allocations:amazon_listing_allocations!amazon_listing_allocations_batch_id_fkey(*),lots:amazon_listing_completions(*,lots:amazon_merchant_inventory_lots(*))").eq("id", id).single();
            if (error)
                throw error;
            if (data.fulfillment_method === "MF" && data.allocations.length) {
                const asins = [...new Set(data.allocations.map((a: {
                        snapshot: {
                            asin: string;
                        };
                    }) => a.snapshot.asin))];
                const skus = await fetchListingSkuMappings(db, asins as string[], "MF");
                for (const a of data.allocations) {
                    a.suggested_sku = resolveListingSku(skus, a.snapshot.asin, "MF", a.snapshot.condition);
                }
            }
            const allocationIds = new Set(data.allocations.map((a: { id: string }) => a.id));
            for (const completion of data.lots) completion.lots = completion.lots.filter((lot: { allocation_id: string }) => allocationIds.has(lot.allocation_id));
            data.lots = data.lots.filter((completion: { lots: unknown[] }) => completion.lots.length);
            return NextResponse.json(data);
        }
        const { data, error } = await db.from("amazon_listing_batches").select("id,fulfillment_method,external_reference,status,selection,created_at,exported_at,completed_at,fba_shipment_code,allocations:amazon_listing_allocations!amazon_listing_allocations_batch_id_fkey(quantity,listed_quantity,transferred_quantity,snapshot)").order("created_at", { ascending: false }).limit(100);
        if (error)
            throw error;
        const rows = (data || []).map(batch => {
            let totalCents = 0;
            let completeCost = batch.fulfillment_method === "MF" && batch.allocations.length > 0;
            const allocations = batch.allocations.map(allocation => {
                const snapshot = allocation.snapshot as { unit_cost?: number | string | null } | null;
                const unitCost = snapshot?.unit_cost;
                if (unitCost === null || unitCost === undefined || unitCost === "" || !Number.isFinite(Number(unitCost))) {
                    completeCost = false;
                } else {
                    totalCents += Math.round(Number(unitCost) * (allocation.quantity - (allocation.transferred_quantity || 0)) * 100);
                }
                return { quantity: allocation.quantity, listed_quantity: allocation.listed_quantity, transferred_quantity: allocation.transferred_quantity || 0 };
            });
            return { ...batch, allocations, total_cost: completeCost ? totalCents / 100 : null };
        });
        return NextResponse.json({ rows, time_zone: BUSINESS_TIMEZONE });
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
        if (existing && existing.fulfillment_method !== body.method)
            throw new Error("This batch belongs to a different fulfillment method. Start a new selection for that method.");
        if (existing?.export_csv && body.action === "export")
            return NextResponse.json(existing);
        const quantities = selectedQuantities(body.quantities);
        let allocations = null;
        let csv = null;
        if (body.action === "export") {
            if (!Object.keys(quantities).length)
                throw new Error("Select at least one allocation.");
            const preparationUrl = new URL("/api/fba-shipments", request.url);
            preparationUrl.searchParams.set("method", body.method);
            const response = await getPreparation(new NextRequest(preparationUrl));
            const preparation = await response.json();
            if (!response.ok)
                throw new Error(preparation.error);
            // All prices/costs and purchase identities come from the existing backend prep query.
            const groups = preparation.rows as Parameters<typeof inventoryLabExportRows>[0];
            const available = new Set(groups.flatMap(g => g.details.map(d => d.item_id)));
            if (Object.keys(quantities).some(id => !available.has(id)))
                throw new Error("Selected allocation is no longer eligible. Refresh and review.");
            if (body.method === "MF") {
                const missing = groups.flatMap(g => g.details.filter(d => quantities[d.item_id] &&
                    !(d.fulfillment_method === "MF" && d.seller_sku) && !(g.fulfillment_method === "MF" && g.msku)));
                const asins = [...new Set(missing.map(d => d.asin))];
                if (asins.length) {
                    const mappings = (await Promise.all([
                        fetchListingSkuMappings(db, asins, "MF"),
                        fetchListingSkuMappings(db, asins, "FBA"),
                    ])).flat();
                    for (const detail of missing) {
                        detail.seller_sku = resolveMfExportSku(mappings, detail.asin, detail.condition);
                        detail.fulfillment_method = "MF";
                    }
                }
                for (const group of groups) for (const detail of group.details) {
                    if (quantities[detail.item_id] && !detail.seller_sku && group.fulfillment_method === "MF") {
                        detail.seller_sku = group.msku;
                        detail.fulfillment_method = "MF";
                    }
                }
            }
            allocations = groups.flatMap(g => g.details.filter(d => quantities[d.item_id]).map(d => ({ ...d, quantity: Number(quantities[d.item_id]), sell_price: g.sell_price })));
            if (body.method === "MF" && allocations.some(a => a.source_type !== "purchase_item"))
                throw new Error("Return recovery remains an FBA-only workflow in this phase.");
            csv = listingCsv(inventoryLabExportRows(groups, quantities, body.method));
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
