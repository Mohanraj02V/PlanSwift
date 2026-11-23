"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  Bot,
  Box,
  Calculator,
  CheckCircle2,
  Database,
  FileCode2,
  FolderTree,
  Layers,
  LayoutDashboard,
  LogOut,
  Menu,
  Ruler,
  Settings,
  ShieldAlert,
  Waypoints,
} from "lucide-react";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import { clearAuthTokens, getRefreshToken } from "@/services/authentication/auth";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/organizations", label: "Organizations", icon: Layers },
  { href: "/projects", label: "Projects", icon: Database },
  { href: "/extraction", label: "Source & Extraction", icon: Activity },
  { href: "/project-explorer", label: "Project Explorer", icon: FolderTree },
  { href: "/objects", label: "Objects", icon: Box },
  { href: "/measurements", label: "Measurements", icon: Ruler },
  { href: "/geometry", label: "Geometry Data", icon: Waypoints },
  { href: "/formulas", label: "Formulas", icon: FileCode2 },
  { href: "/assemblies", label: "Assemblies", icon: Layers },
  { href: "/classifications", label: "Classifications", icon: Layers },
  { href: "/validation", label: "Validation", icon: CheckCircle2 },
  { href: "/estimation", label: "Estimation", icon: Calculator },
  { href: "/ai-assistant", label: "AI Assistant", icon: Bot },
  { href: "/audit", label: "Audit Trail", icon: ShieldAlert },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, projects, selectedProjectId, setSelectedProjectId, refreshContext } = useProjectContext();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = async () => {
    const refresh = getRefreshToken();
    if (refresh) {
      try {
        await apiRequest("/auth/logout/", { method: "POST", body: JSON.stringify({ refresh }) });
      } catch {
        // Ignore network errors on logout
      }
    }
    clearAuthTokens();
    await refreshContext();
    router.push("/login");
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside
        className={`${
          sidebarOpen ? "fixed inset-y-0 left-0 z-40 block" : "hidden"
        } w-64 shrink-0 border-r border-slate-200 bg-slate-900 text-slate-100 lg:block`}
      >
        <div className="flex h-14 items-center justify-between border-b border-slate-800 px-4">
          <Link href="/dashboard" className="font-semibold tracking-tight text-white">
            Vortexen Estimator
          </Link>
          <span className="rounded bg-blue-600/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-blue-300">
            Native XML
          </span>
        </div>
        <nav className="space-y-0.5 p-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition ${
                  active ? "bg-blue-600 text-white" : "text-slate-300 hover:bg-slate-800 hover:text-white"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 lg:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              aria-label="Toggle navigation"
              onClick={() => setSidebarOpen((v) => !v)}
              className="rounded border border-slate-200 p-1.5 text-slate-600 lg:hidden"
            >
              <Menu className="h-4 w-4" />
            </button>
            <h1 className="text-base font-semibold text-slate-900">{title}</h1>
          </div>

          <div className="flex items-center gap-3">
            {projects.length > 0 && (
              <select
                aria-label="Active Project"
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                className="max-w-xs rounded-md border border-slate-300 bg-white px-2.5 py-1 text-sm text-slate-800"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.object_count} objs)
                  </option>
                ))}
              </select>
            )}
            {user ? (
              <div className="flex items-center gap-2">
                <span className="hidden text-xs text-slate-600 sm:inline">{user.email}</span>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                >
                  <LogOut className="h-3.5 w-3.5" /> Logout
                </button>
              </div>
            ) : (
              <Link
                href="/login"
                className="rounded-md bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700"
              >
                Sign in
              </Link>
            )}
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}
