"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AlertTriangle,
  BarChart3,
  LogOut,
  PackageCheck,
  ReceiptText,
  Send,
  Search,
  ShoppingCart,
  TrendingDown,
} from "lucide-react";

const navItems = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: BarChart3,
  },
  {
    href: "/sourcing",
    label: "Sourcing",
    icon: Search,
  },
  {
    href: "/",
    label: "Purchases",
    icon: ShoppingCart,
  },
  {
    href: "/receiving",
    label: "Receiving",
    icon: PackageCheck,
  },
  {
    href: "/fba",
    label: "Send to Amazon",
    icon: Send,
  },
  {
    href: "/sales-orders",
    label: "Sales Orders",
    icon: ReceiptText,
  },
  {
    href: "/repricing",
    label: "Repricing",
    icon: TrendingDown,
  },
  {
    href: "/inventory-reconciliation",
    label: "Reconciliation",
    icon: AlertTriangle,
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-900">
      <aside className="sticky top-0 flex h-screen w-16 shrink-0 flex-col items-center border-r border-slate-200 bg-white py-3 shadow-sm">
        <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-xs font-semibold text-white">
          MB
        </div>

        <nav className="flex w-full flex-1 flex-col items-center gap-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex h-11 w-11 items-center justify-center rounded-lg transition ${
                  active
                    ? "bg-slate-900 text-white"
                    : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                }`}
                aria-label={item.label}
                title={item.label}
              >
                <Icon className="h-5 w-5" />
              </Link>
            );
          })}
        </nav>
      </aside>

      <a
        href="/api/logout"
        className="fixed right-3 top-3 z-50 inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
        title="Log out"
      >
        <LogOut className="h-4 w-4" />
        Log out
      </a>

      <div className="min-w-0 flex-1 pr-24">{children}</div>
    </div>
  );
}
