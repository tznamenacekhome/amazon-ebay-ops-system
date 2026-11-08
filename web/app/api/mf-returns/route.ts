import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../_server";
import { normalizeTrackingScan } from "../../receiving/trackingScan";

export const dynamic = "force-dynamic";
const db = createServerSupabaseClient();
async function scope() {
  const { data, error } = await db.from("amazon_mf_accounts").select("id,seller_id,marketplace_id").eq("configured", true).single();
  if (error) throw error;
  return data;
}
function fail(e: unknown) { return NextResponse.json({ error: (e as { message?: string }).message || "Return operation failed" }, { status: 400 }); }
function checked<T>(result: { data: T; error: unknown }): NonNullable<T> { if (result.error) throw result.error; return result.data as NonNullable<T>; }
export async function GET(req: NextRequest) {
  try {
    const account = await scope(), p = req.nextUrl.searchParams, id = p.get("id"), scan = p.get("scan");
    if (scan) {
      const normalized = normalizeTrackingScan(scan);
      const packages = checked(await db.from("amazon_mf_return_packages").select("*").eq("account_id", account.id).in("tracking_number", normalized.candidates).limit(51));
      const lookup = /^[a-zA-Z0-9 _\-]+$/.test(scan) ? scan : normalized.normalizedInput;
      const returns = checked(await db.from("vw_mf_open_returns").select("*").eq("account_id", account.id).or(`amazon_order_id.eq.${safeLookup(lookup)},rma.eq.${safeLookup(lookup)},merchant_rma.eq.${safeLookup(lookup)}`).limit(51));
      const links = packages.length ? checked(await db.from("amazon_mf_return_package_items").select("return_id,package_id").in("package_id", packages.map(x => x.id))) : [];
      const linked = links.length ? checked(await db.from("vw_mf_open_returns").select("*").eq("account_id", account.id).in("id", links.map(x => x.return_id))) : [];
      return NextResponse.json({ normalized, packages, returns: [...new Map([...returns, ...linked].map(r => [r.id, r])).values()], links, truncated: packages.length > 50 || returns.length > 50 });
    }
    if (id) {
      const row = checked(await db.from("vw_mf_open_returns").select("*").eq("account_id", account.id).eq("id", id).single());
      const links = checked(await db.from("amazon_mf_return_package_items").select("package_id").eq("return_id", id));
      const packages = links.length ? checked(await db.from("amazon_mf_return_packages").select("*").eq("account_id", account.id).in("id", links.map(l => l.package_id))) : [];
      const [inspections, claims, evidence, dates, finances, order, financeNotes] = await Promise.all([
        db.from("amazon_mf_return_inspections").select("*").eq("account_id", account.id).eq("return_id", id).order("recorded_at"),
        db.from("amazon_mf_return_claims").select("*").eq("account_id", account.id).eq("return_id", id).order("updated_at", { ascending: false }),
        db.from("amazon_mf_return_evidence").select("*").eq("account_id", account.id).eq("return_id", id),
        db.from("amazon_mf_return_dates").select("*").eq("return_id", id).order("recorded_at"),
        db.from("vw_mf_return_finances").select("*").eq("account_id", account.id).eq("amazon_order_id", row.amazon_order_id).order("posted_at"),
        db.from("amazon_mf_order_items").select("*").eq("account_id", account.id).eq("amazon_order_id", row.amazon_order_id),
        db.from("amazon_mf_return_finance_notes").select("*").eq("account_id", account.id).eq("return_id", id),
      ]);
      return NextResponse.json({ row, packages, inspections: checked(inspections), claims: checked(claims), evidence: checked(evidence), dates: checked(dates), finances: checked(finances), order: checked(order), financeNotes: checked(financeNotes) });
    }
    if (p.get("view") === "unmatched") {
      const rows = checked(await db.from("amazon_mf_return_packages").select("*").eq("account_id", account.id).eq("unmatched", true).order("received_at", { ascending: false }).limit(100));
      return NextResponse.json({ rows });
    }
    const page = Math.max(0, Math.min(10000, Number(p.get("page")) || 0));
    let query = db.from("vw_mf_open_returns").select("*", { count: "exact" }).eq("account_id", account.id);
    const filter = p.get("filter") || "open";
    if (filter === "open") query = query.or("physical_status.neq.inspected,unresolved_claim.eq.true,contents_exception.eq.true,refunded_unreceived.eq.true");
    else if (["awaiting_return", "partially_received", "received_awaiting_inspection"].includes(filter)) query = query.eq("physical_status", filter);
    else if (["refunded_unreceived", "delivered_unreceived", "contents_exception", "unresolved_claim"].includes(filter)) query = query.eq(filter, true);
    else if (filter === "follow_up") query = query.or("refunded_unreceived.eq.true,contents_exception.eq.true,unresolved_claim.eq.true");
    const search = p.get("q")?.trim();
    if (search) query = query.or(`amazon_order_id.ilike.*${safeLookup(search)}*,seller_sku.ilike.*${safeLookup(search)}*,rma.ilike.*${safeLookup(search)}*`);
    const [rows, runs, success] = await Promise.all([
      query.order("requested_at", { ascending: false, nullsFirst: true }).order("id").range(page * 100, page * 100 + 99),
      db.from("amazon_mf_return_sync_runs").select("*").order("started_at", { ascending: false }).limit(5),
      db.from("amazon_mf_return_sync_runs").select("finished_at").eq("account_id", account.id).eq("status", "completed").order("finished_at", { ascending: false }).limit(1),
    ]);
    const lastSuccess = checked(success)[0]?.finished_at || null;
    return NextResponse.json({ account, rows: checked(rows), total: rows.count, runs: checked(runs), last_success_at: lastSuccess, stale: !lastSuccess || Date.now() - Date.parse(lastSuccess) > 7200000, page });
  } catch (e) { return fail(e); }
}
function safeLookup(value: string) {
  if (!/^[a-zA-Z0-9 _\-]+$/.test(value) || value.length > 150) throw Error("Use an order ID, RMA, tracking number or MSKU containing letters, numbers, spaces and hyphens.");
  return value;
}
export async function POST(req: NextRequest) {
  const denied = requireAdminApiToken(req); if (denied) return denied;
  try {
    const account = await scope(), b = await req.json();
    let result;
    if (b.action === "receive") {
      result = checked(await db.rpc("mbop_mf_return_receive", { p_account: account.id, p_request: b.request_id, p_package: b.package_id || null, p_tracking: b.tracking || null, p_raw: b.raw_scan, p_received: b.received_at, p_notes: b.notes || "", p_return: b.return_id || null }));
    } else if (b.action === "inspect") {
      result = checked(await db.rpc("mbop_mf_return_inspect", { p_account: account.id, p_request: b.request_id, p_data: b.data }));
    } else {
      const row = checked(await db.from("amazon_mf_returns").select("id").eq("account_id", account.id).eq("id", b.return_id).single());
      if (!row) throw Error("Return not found");
      if (b.action === "finance-note") {
        const f = checked(await db.from("amazon_mf_return_finances").select("amazon_order_id,currency").eq("account_id", account.id).eq("transaction_id", b.transaction_id).single());
        const r = checked(await db.from("amazon_mf_returns").select("amazon_order_id").eq("id", row.id).single());
        if (f.amazon_order_id !== r.amazon_order_id || !Number.isFinite(b.amount) || !b.notes?.trim() || !b.source_reference?.trim()) throw Error("Choose this order's actual transaction, signed component amount and supporting source");
        result = checked(await db.from("amazon_mf_return_finance_notes").upsert({ id: b.request_id, account_id: account.id, transaction_id: b.transaction_id, return_id: row.id, kind: b.kind, component_amount: b.amount, currency: f.currency, notes: b.notes, source_reference: b.source_reference }, { onConflict: "account_id,transaction_id,return_id,kind", ignoreDuplicates: true }));
      } else if (b.action === "match") {
        result = checked(await db.rpc("mbop_mf_return_match", { p_account: account.id, p_return: row.id, p_item: b.item_id, p_quantity: b.quantity, p_notes: b.notes }));
      } else if (b.action === "claim") {
        const c = b.data;
        if (!c.claim_type?.trim() || !c.notes?.trim() || !/^[A-Z]{3}$/.test(c.currency) || (c.deadline_at && !c.deadline_source?.trim())) throw Error("Claim type, currency, notes and any deadline source are required");
        const existing = checked(await db.from("amazon_mf_return_claims").select("id,account_id,return_id").eq("id", b.request_id).maybeSingle());
        if (existing && (existing.account_id !== account.id || existing.return_id !== row.id)) throw Error("Claim scope mismatch");
        const fields = { id: b.request_id, account_id: account.id, return_id: row.id, claim_type: c.claim_type, case_id: c.case_id || null, submitted_at: c.submitted_at || null, claimed_amount: c.claimed_amount ?? null, currency: c.currency, status: c.status, next_follow_up: c.next_follow_up || null, resolved_at: c.resolved_at || null, resolution: c.resolution || null, reimbursed_amount: c.reimbursed_amount ?? null, deadline_at: c.deadline_at || null, deadline_source: c.deadline_source || null, notes: c.notes, updated_at: new Date().toISOString() };
        result = checked(await db.from("amazon_mf_return_claims").upsert(fields).select("id").single());
      } else if (b.action === "evidence") {
        const url = new URL(b.url); if (url.protocol !== "https:" || !b.caption?.trim()) throw Error("HTTPS photo/document link and caption required");
        result = checked(await db.from("amazon_mf_return_evidence").upsert({ id: b.request_id, account_id: account.id, return_id: row.id, url: url.href, caption: b.caption }, { onConflict: "id", ignoreDuplicates: true }).select("id"));
      } else if (b.action === "date") {
        if (!b.notes?.trim()) throw Error("Source/evidence notes required for merchant-entered dates");
        result = checked(await db.from("amazon_mf_return_dates").upsert({ id: b.request_id, return_id: row.id, kind: b.kind, occurred_at: b.occurred_at, notes: b.notes }, { onConflict: "id", ignoreDuplicates: true }).select("id"));
      } else if (b.action === "returnless") {
        if (typeof b.returnless !== "boolean") throw Error("Explicit returnless choice required");
        result = checked(await db.from("amazon_mf_returns").update({ manual_returnless: b.returnless }).eq("account_id", account.id).eq("id", row.id));
      } else throw Error("Unknown return action");
    }
    return NextResponse.json({ success: true, result });
  } catch (e) { return fail(e); }
}
