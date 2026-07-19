"use client";

import Link from "next/link";
import type { ReactNode } from "react";

export type DashboardView =
  | "overview"
  | "operations"
  | "inventory"
  | "amazon"
  | "sourcing"
  | "loss-prevention"
  | "provider-costs"
  | "system-health";

const dashboardTabs: Array<{ view: DashboardView; label: string }> = [
  { view: "overview", label: "Overview" },
  { view: "operations", label: "Operations" },
  { view: "inventory", label: "Inventory" },
  { view: "amazon", label: "Amazon" },
  { view: "sourcing", label: "Sourcing" },
  { view: "loss-prevention", label: "Loss Prevention" },
  { view: "provider-costs", label: "Provider Costs" },
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
    timeZone: "America/Los_Angeles",
  }).format(date);
}
