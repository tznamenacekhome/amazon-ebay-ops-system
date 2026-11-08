import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../_server";
export const dynamic = "force-dynamic";
const db = createServerSupabaseClient();
async function scope() { const { data, error } = await db.from("amazon_mf_accounts").select("*").eq("configured", true).maybeSingle(); if (error)
    throw error; return data ? { ...data, stale: !data.last_success_at || Date.now() - Date.parse(data.last_success_at) > 7200000 } : null; }
export async function GET(request: NextRequest) {
    try {
        const account = await scope();
        const { data: runs, error: re } = await db.from("amazon_mf_sync_runs").select("*").order("started_at", { ascending: false }).limit(10);
        if (re)
            throw re;
        if (!account)
            return NextResponse.json({ account: null, runs, rows: [], total: 0, error: "MF account not initialized. Refresh from Amazon; missing scheduler configuration appears in synchronization failures." });
        const p = request.nextUrl.searchParams, view = p.get("view") || "inventory", sku = p.get("sku");
        if (view === "lots") {
            if (!sku)
                throw Error("MSKU required");
            const { data, error } = await db.from("vw_mf_lot_balances").select("*,listing_lot:amazon_merchant_inventory_lots(source_item_id,listed_item_id,purchase_id,allocation_id,allocation:amazon_listing_allocations(batch_id,snapshot)),opening:amazon_mf_openings(*)").eq("account_id", account.id).eq("seller_sku", sku).order("acquired_at").limit(500);
            if (error)
                throw error;
            return NextResponse.json({ account, runs, rows: data?.map(l => {
                    const { listing_lot, opening, ...lot } = l;
                    const allocation = listing_lot?.allocation;
                    return { ...lot, lineage: listing_lot ? { purchase_id: listing_lot.purchase_id, source_item_id: listing_lot.source_item_id, listed_item_id: listing_lot.listed_item_id, batch_id: allocation?.batch_id, supplier_order_id: allocation?.snapshot?.supplier_order_id, received_date: allocation?.snapshot?.received_date } : lot.return_inspection_id ? { return_inspection_id: lot.return_inspection_id, original_shipped_lot_id: lot.parent_lot_id, cost_lineage: lot.parent_lot_id ? "Inherited from original shipped lot" : "Unknown original purchase cost" } : { opening_id: opening?.id, notes: opening?.notes, confirmed_at: opening?.confirmed_at } };
                }) });
        }
        if (!["inventory", "orders"].includes(view))
            throw Error("Unknown MF view");
        const page = Math.max(0, Math.min(10000, Math.floor(Number(p.get("page")) || 0)));
        let query = db.from(view === "inventory" ? "vw_mf_inventory" : "vw_mf_orders").select("*", { count: "exact" }).eq("account_id", account.id);
        if (sku)
            query = query.ilike("seller_sku", `%${sku.replace(/[\\%_]/g, "\\$&")}%`);
        query = view === "inventory" ? query.order("seller_sku").order("condition") : query.order("purchased_at", { ascending: false }).order("id");
        const { data, error, count } = await query.range(page * 100, page * 100 + 99);
        if (error)
            throw error;
        return NextResponse.json({ account, runs, rows: data, total: count, page });
    }
    catch (e) {
        return failure(e);
    }
}
export async function POST(request: NextRequest) {
    const denied = requireAdminApiToken(request);
    if (denied)
        return denied;
    try {
        const account = await scope();
        if (!account)
            throw Error("Synchronize the Amazon MF account first.");
        const body = await request.json();
        if (typeof body.sku !== "string" || !body.sku.trim())
            throw Error("MSKU required");
        if (body.action === "keep-mf") {
            if (typeof body.keep_mf !== "boolean")
                throw Error("Keep MF must be true or false");
            const { error } = await db.from("amazon_mf_preferences").upsert({ account_id: account.id, seller_sku: body.sku, keep_mf: body.keep_mf, source: "operator", updated_at: new Date().toISOString() }, { onConflict: "account_id,seller_sku" });
            if (error)
                throw error;
            return NextResponse.json({ success: true });
        }
        if (body.action !== "opening")
            throw Error("Unknown MF action");
        if (!Number.isInteger(body.count) || body.count < 0 || typeof body.notes !== "string" || !body.notes.trim() || body.cost !== null && (!Number.isFinite(body.cost) || body.cost < 0))
            throw Error("Physical count and notes required; acquisition cost may be unknown.");
        const { data, error } = await db.rpc("mbop_mf_opening", { p_account: account.id, p_request: body.request_id, p_sku: body.sku, p_condition: body.condition, p_count: body.count, p_cost: body.cost, p_notes: body.notes, p_revision: body.revision });
        if (error)
            throw error;
        return NextResponse.json(data);
    }
    catch (e) {
        return failure(e);
    }
}
function failure(e: unknown) { return NextResponse.json({ error: e instanceof Error ? e.message : (e as {
        message?: string;
    })?.message || "MF request failed" }, { status: 400 }); }
