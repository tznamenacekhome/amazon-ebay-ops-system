import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

type DashboardPurchaseRow = {
  order_date: string | null;
  quantity: number | null;
  unit_cost: number | null;
  current_status: string | null;
};

type MonthAggregate = {
  year: number;
  month: number;
  monthLabel: string;
  units: number;
  cost: number;
};

export async function GET() {
  const rows = await fetchPurchaseRows();
  const monthly = aggregateByMonth(rows);
  const years = aggregateByYear(monthly);
  const totals = monthly.reduce(
    (accumulator, month) => ({
      units: accumulator.units + month.units,
      cost: accumulator.cost + month.cost,
    }),
    { units: 0, cost: 0 }
  );

  return NextResponse.json({
    totals,
    years,
    months: monthly,
  });
}

async function fetchPurchaseRows() {
  const rows: DashboardPurchaseRow[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from("vw_purchases_dashboard")
      .select("order_date,quantity,unit_cost,current_status")
      .range(offset, offset + pageSize - 1);

    if (error) {
      throw new Error(error.message);
    }

    rows.push(...((data ?? []) as DashboardPurchaseRow[]));

    if ((data ?? []).length < pageSize) {
      return rows;
    }

    offset += pageSize;
  }
}

function aggregateByMonth(rows: DashboardPurchaseRow[]) {
  const aggregates = new Map<string, MonthAggregate>();

  for (const row of rows) {
    if (normalizeStatus(row.current_status) === "return_opened") continue;
    if (!row.order_date) continue;

    const dateMatch = row.order_date.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!dateMatch) continue;

    const year = Number(dateMatch[1]);
    const month = Number(dateMatch[2]);
    const key = `${year}-${String(month).padStart(2, "0")}`;
    const quantity = Number(row.quantity ?? 0);
    const unitCost = Number(row.unit_cost ?? 0);
    const existing = aggregates.get(key) ?? {
      year,
      month,
      monthLabel: monthName(month),
      units: 0,
      cost: 0,
    };

    existing.units += Number.isFinite(quantity) ? quantity : 0;
    existing.cost += Number.isFinite(unitCost) ? unitCost * quantity : 0;

    aggregates.set(key, existing);
  }

  return [...aggregates.values()].sort((left, right) => {
    if (left.year !== right.year) return left.year - right.year;
    return left.month - right.month;
  });
}

function aggregateByYear(months: MonthAggregate[]) {
  const years = new Map<
    number,
    { year: number; units: number; cost: number; months: MonthAggregate[] }
  >();

  for (const month of months) {
    const existing = years.get(month.year) ?? {
      year: month.year,
      units: 0,
      cost: 0,
      months: [],
    };

    existing.units += month.units;
    existing.cost += month.cost;
    existing.months.push(month);

    years.set(month.year, existing);
  }

  return [...years.values()].sort((left, right) => left.year - right.year);
}

function normalizeStatus(value?: string | null) {
  return (value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function monthName(month: number) {
  return new Date(Date.UTC(2026, month - 1, 1)).toLocaleString("en-US", {
    month: "short",
    timeZone: "UTC",
  });
}
