"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AlertTriangle,
  BarChart3,
  Bell,
  Boxes,
  LogOut,
  PackageCheck,
  PackageOpen,
  ReceiptText,
  Send,
  Search,
  ShoppingCart,
  TrendingDown,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { mutationHeaders } from "./mutationHeaders";

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
    href: "/wholesale",
    label: "Wholesale",
    icon: Boxes,
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
    href: "/amazon-return-recovery",
    label: "Amazon Returns",
    icon: PackageOpen,
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
  const buildSha = process.env.NEXT_PUBLIC_MBOP_BUILD_SHA || "local";
  const [notifications, setNotifications] = useState<any[]>([]);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const loadNotifications = useCallback(async () => {
    const response = await fetch("/api/notifications", { cache: "no-store" });
    if (response.ok) setNotifications((await response.json()).rows ?? []);
  }, []);
  useEffect(() => { void loadNotifications(); const timer = window.setInterval(loadNotifications, 60000); return () => window.clearInterval(timer); }, [loadNotifications]);
  const unread = notifications.filter(row => !row.read_at).length;

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

        <div
          className="mt-3 max-w-12 truncate px-1 text-center text-[10px] font-medium text-slate-400"
          title={`Build ${buildSha}`}
        >
          {buildSha.slice(0, 7)}
        </div>
      </aside>

      <div className="absolute right-28 top-3 z-50">
        <button onClick={() => setNotificationOpen(value => !value)} className="relative inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-700 shadow-sm" aria-label="Notifications" title="Notifications">
          <Bell className="h-4 w-4"/>{unread ? <span className="absolute -right-1 -top-1 min-w-4 rounded-full bg-red-600 px-1 text-[10px] text-white">{Math.min(unread, 99)}</span> : null}
        </button>
        {notificationOpen ? <div className="absolute right-0 mt-2 w-96 rounded border bg-white shadow-xl">
          <div className="flex items-center justify-between border-b px-3 py-2 text-sm font-semibold"><span>Notifications</span>{unread ? <button className="text-xs text-blue-700" onClick={async () => { await fetch("/api/notifications", { method: "PATCH", headers: mutationHeaders() }); await loadNotifications(); }}>Mark all read</button> : null}</div>
          <div className="max-h-96 overflow-auto">{notifications.length ? notifications.map(row => <a key={row.notification_id} href={row.href || "#"} className={`block border-b px-3 py-3 text-sm hover:bg-slate-50 ${row.read_at ? "text-slate-500" : "bg-blue-50/50"}`}><div className="font-semibold">{row.title}</div><div className="mt-1 text-xs">{row.message}</div>{row.occurrence_count > 1 ? <div className="mt-1 text-xs">Occurred {row.occurrence_count} times</div> : null}</a>) : <div className="p-5 text-center text-sm text-slate-500">No notifications.</div>}</div>
        </div> : null}
      </div>

      <a
        href="/api/logout"
        className="absolute right-3 top-3 z-50 inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
        title="Log out"
      >
        <LogOut className="h-4 w-4" />
        Log out
      </a>

      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
