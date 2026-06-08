"use client";

import Link from "next/link";
import type { ReactNode } from "react";

export type DashboardView =
  | "overview"
  | "financial"
  | "operations"
  | "inventory"
  | "amazon"
  | "growth"
  | "sourcing"
  | "loss-prevention"
  | "system-health";

const dashboardTabs: Array<{ view: DashboardView; label: string }> = [
  { view: "overview", label: "Overview" },
  { view: "financial", label: "Financial" },
  { view: "operations", label: "Operations" },
  { view: "inventory", label: "Inventory" },
  { view: "amazon", label: "Amazon" },
  { view: "growth", label: "Growth" },
  { view: "sourcing", label: "Sourcing" },
  { view: "loss-prevention", label: "Loss Prevention" },
  { view: "system-health", label: "System Health" },
];

export function DashboardTabs({ activeView }: { activeView: DashboardView }) {
  return (
    <nav className="flex flex-wrap gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-sm" aria-label="Dashboard views">
      {dashboardTabs.map((tab) => (
        <Link
          key={tab.view}
          href={`/dashboard?view=${tab.view}`}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
            activeView === tab.view
              ? "bg-slate-900 text-white"
              : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}

export function DashboardSection({
  title,
  eyebrow,
  children,
  action,
}: {
  title: string;
  eyebrow?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-3 py-2">
        <div>
          {eyebrow ? <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{eyebrow}</div> : null}
          <h2 className="text-base font-semibold text-slate-950">{title}</h2>
        </div>
        {action}
      </div>
      <div className="p-3">{children}</div>
    </section>
  );
}

export function MetricGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">{children}</div>;
}

export function MetricCard({
  label,
  value,
  detail,
  href,
  external = false,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  detail?: string;
  href?: string;
  external?: boolean;
  tone?: "neutral" | "green" | "yellow" | "red" | "unknown";
}) {
  const content = (
    <div className={`h-full rounded-md border px-3 py-2 ${toneClass(tone)}`}>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-slate-950">{value}</div>
      {detail ? <div className="mt-1 text-xs leading-snug text-slate-500">{detail}</div> : null}
    </div>
  );

  if (!href) return content;
  if (external) {
    return (
      <a href={href} className="block h-full hover:opacity-90" target="_blank" rel="noreferrer">
        {content}
      </a>
    );
  }

  return (
    <Link href={href} className="block h-full hover:opacity-90">
      {content}
    </Link>
  );
}

export function CompactStatusTable({
  columns,
  rows,
  emptyText = "No rows.",
}: {
  columns: string[];
  rows: Array<{ id: string; cells: ReactNode[]; href?: string; external?: boolean }>;
  emptyText?: string;
}) {
  return (
    <div className="overflow-hidden rounded-md border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
          <tr>
            {columns.map((column) => (
              <th key={column} className="px-3 py-2 font-semibold">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row) => {
              const cells = row.cells.map((cell, index) => (
                <td key={index} className="border-t border-slate-100 px-3 py-2">
                  {cell}
                </td>
              ));
              if (!row.href) return <tr key={row.id}>{cells}</tr>;
              if (row.external) {
                return (
                  <tr key={row.id} className="hover:bg-slate-50">
                    {row.cells.map((cell, index) => (
                      <td key={index} className="border-t border-slate-100 p-0">
                        <a href={row.href} className="block px-3 py-2" target="_blank" rel="noreferrer">
                          {cell}
                        </a>
                      </td>
                    ))}
                  </tr>
                );
              }
              return (
                <tr key={row.id} className="hover:bg-slate-50">
                  {row.cells.map((cell, index) => (
                    <td key={index} className="border-t border-slate-100 p-0">
                      <Link href={row.href ?? "#"} className="block px-3 py-2">
                        {cell}
                      </Link>
                    </td>
                  ))}
                </tr>
              );
            })
          ) : (
            <tr>
              <td className="px-3 py-6 text-center text-slate-500" colSpan={columns.length}>
                {emptyText}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function TrendSparkline({ points }: { points: Array<{ date: string; value: number }> }) {
  if (points.length < 2) {
    return <div className="py-8 text-center text-sm text-slate-500">Not enough history yet.</div>;
  }

  const width = 760;
  const height = 220;
  const margin = { top: 18, right: 22, bottom: 34, left: 82 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const values = points.map((point) => Number(point.value ?? 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = Math.max((max - min) * 0.12, max * 0.01, 1);
  const yMin = Math.max(0, min - padding);
  const yMax = max + padding;
  const range = Math.max(yMax - yMin, 1);
  const step = chartWidth / Math.max(points.length - 1, 1);
  const coordinates = points.map((point, index) => {
    const value = Number(point.value ?? 0);
    return {
      ...point,
      value,
      x: margin.left + index * step,
      y: margin.top + chartHeight - ((value - yMin) / range) * chartHeight,
    };
  });
  const path = coordinates
    .map((point, index) => {
      return `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    })
    .join(" ");
  const yTicks = Array.from({ length: 5 }, (_, index) => {
    const value = yMin + (range * index) / 4;
    const y = margin.top + chartHeight - ((value - yMin) / range) * chartHeight;
    return { value, y };
  }).reverse();
  const xTickIndexes = Array.from(new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]));
  const first = coordinates[0];
  const last = coordinates[coordinates.length - 1];
  const change = last.value - first.value;
  const changePercent = first.value ? change / first.value : 0;

  return (
    <div className="space-y-2">
      <div className="grid gap-2 text-xs text-slate-600 sm:grid-cols-3">
        <div>
          <div className="font-semibold uppercase tracking-wide text-slate-500">Latest</div>
          <div className="text-sm font-semibold text-slate-950">{formatCompactMoney(last.value)}</div>
        </div>
        <div>
          <div className="font-semibold uppercase tracking-wide text-slate-500">Range</div>
          <div className="text-sm font-semibold text-slate-950">
            {formatCompactMoney(min)} - {formatCompactMoney(max)}
          </div>
        </div>
        <div>
          <div className="font-semibold uppercase tracking-wide text-slate-500">Change</div>
          <div className={`text-sm font-semibold ${change < 0 ? "text-rose-700" : "text-emerald-700"}`}>
            {formatSignedMoney(change)} ({formatSignedPercent(changePercent)})
          </div>
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-56 w-full" role="img" aria-label="Total business value trend">
        {yTicks.map((tick) => (
          <g key={tick.value}>
            <line x1={margin.left} x2={width - margin.right} y1={tick.y} y2={tick.y} stroke="#e2e8f0" />
            <text x={margin.left - 10} y={tick.y + 4} textAnchor="end" className="fill-slate-500 text-[11px]">
              {formatCompactMoney(tick.value)}
            </text>
          </g>
        ))}
        <line x1={margin.left} x2={margin.left} y1={margin.top} y2={height - margin.bottom} stroke="#cbd5e1" />
        <line x1={margin.left} x2={width - margin.right} y1={height - margin.bottom} y2={height - margin.bottom} stroke="#cbd5e1" />
        {xTickIndexes.map((index) => {
          const point = coordinates[index];
          return (
            <g key={point.date}>
              <line x1={point.x} x2={point.x} y1={height - margin.bottom} y2={height - margin.bottom + 5} stroke="#94a3b8" />
              <text x={point.x} y={height - 10} textAnchor="middle" className="fill-slate-500 text-[11px]">
                {formatChartDate(point.date)}
              </text>
            </g>
          );
        })}
        <path d={path} fill="none" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {coordinates.map((point) => (
          <circle key={`${point.date}-${point.value}`} cx={point.x} cy={point.y} r="4" fill="#ffffff" stroke="#0f172a" strokeWidth="2">
            <title>{`${formatChartDate(point.date)}: ${formatCompactMoney(point.value)}`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}

export function FreshnessBadge({ refreshedAt }: { refreshedAt: string | null | undefined }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600">
      Last updated: {formatDateTime(refreshedAt)}
    </div>
  );
}

export function DrilldownLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="text-sm font-medium text-blue-700 hover:text-blue-900">
      {children}
    </Link>
  );
}

function toneClass(tone: "neutral" | "green" | "yellow" | "red" | "unknown") {
  if (tone === "green") return "border-emerald-200 bg-emerald-50";
  if (tone === "yellow") return "border-amber-200 bg-amber-50";
  if (tone === "red") return "border-rose-200 bg-rose-50";
  if (tone === "unknown") return "border-slate-200 bg-slate-50";
  return "border-slate-200 bg-white";
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatChartDate(value: string | null | undefined) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(date);
}

function formatCompactMoney(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatSignedMoney(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatCompactMoney(value)}`;
}

function formatSignedPercent(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value)}`;
}
