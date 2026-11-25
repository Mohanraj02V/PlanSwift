"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  Bot,
  Box,
  Calculator,
  CheckCircle2,
  ClipboardCheck,
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
  Users,
  Waypoints,
  X,
} from "lucide-react";
import { VortexenLogo } from "@/components/brand/VortexenLogo";
import { useProjectContext } from "@/hooks/useProjectContext";
import { canAccessRoute, getDefaultRoute, getRoleLabel } from "@/lib/rbac";
import { apiRequest } from "@/services/api-client/client";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/estimator", label: "Estimator Workspace", icon: ClipboardCheck },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, adminOnly: true },
  { href: "/organizations", label: "Organizations", icon: Layers, adminOnly: true },
  { href: "/users", label: "Users (Admin)", icon: Users, adminOnly: true },
  { href: "/projects", label: "Projects", icon: Database, adminOnly: true },
  { href: "/extraction", label: "Source & Extraction", icon: Activity, adminOnly: true },
  { href: "/cad-bim", label: "CAD & BIM Explorer", icon: Layers, adminOnly: true },
  { href: "/project-explorer", label: "Project Explorer", icon: FolderTree, adminOnly: true },
  { href: "/objects", label: "Objects", icon: Box, adminOnly: true },
  { href: "/measurements", label: "Measurements", icon: Ruler, adminOnly: true },
  { href: "/geometry", label: "Geometry Data", icon: Waypoints, adminOnly: true },
  { href: "/formulas", label: "Formulas", icon: FileCode2, adminOnly: true },
  { href: "/assemblies", label: "Assemblies", icon: Layers, adminOnly: true },
  { href: "/classifications", label: "Classifications", icon: Layers, adminOnly: true },
  { href: "/validation", label: "Validation", icon: CheckCircle2, adminOnly: true },
  { href: "/estimation", label: "Estimation & Quote", icon: Calculator, adminOnly: true },
  { href: "/ai-assistant", label: "AI Assistant", icon: Bot, adminOnly: true },
  { href: "/audit", label: "Audit Trail", icon: ShieldAlert, adminOnly: true },
  { href: "/settings", label: "Settings", icon: Settings, adminOnly: true },
];

export function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const {
    user,
    role,
    capabilities,
    projects,
    selectedProjectId,
    setSelectedProjectId,
    loading,
    clearSession,
  } = useProjectContext();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const isAdmin = role === "admin";
  const allowedOnRoute = canAccessRoute(user, pathname);

  useEffect(() => {
    if (loading) return;
    if (!user && pathname !== "/login") {
      router.replace("/login");
      return;
    }
    if (user && !allowedOnRoute) {
      router.replace(getDefaultRoute(user));
    }
  }, [loading, user, allowedOnRoute, pathname, router]);

  const visibleNavItems = NAV_ITEMS.filter((item) => {
    if (!role) return false;
    if (role === "admin") return true;
    return item.href === "/estimator";
  });

  const handleLogout = async () => {
    try {
      await apiRequest("/auth/logout/", { method: "POST", body: JSON.stringify({}) });
    } catch {
      // Clear local React session even if network fails
    }
    clearSession();
    router.replace("/login");
  };

  const roleBadgeClass =
    role === "admin"
      ? "bg-[#0052cc]/10 text-[#0052cc] border-[#0052cc]/25"
      : role === "estimator"
      ? "bg-[#29a9ea]/10 text-[#0369a1] border-[#29a9ea]/30"
      : "bg-slate-100 text-[#475569] border-slate-300";

  return (
    <div className="flex min-h-screen bg-[#f8fafc] text-[#0f172a]">
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-[#0b111e]/60 backdrop-blur-xs lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`${
          sidebarOpen ? "fixed inset-y-0 left-0 z-40 flex" : "hidden"
        } w-64 shrink-0 flex-col border-r border-white/10 bg-[#0b111e] text-slate-100 lg:flex`}
      >
        <div className="flex h-16 items-center justify-between border-b border-white/10 px-4">
          <Link href={getDefaultRoute(user)} onClick={() => setSidebarOpen(false)}>
            <VortexenLogo variant="dark" compact subtitle="ESTIMATOR" />
          </Link>
          <div className="flex items-center gap-1.5">
            <span className="rounded bg-[#0052cc]/25 px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase text-[#29a9ea]">
              {role === "admin" ? "ADMIN" : role === "estimator" ? "ESTIMATOR" : "READ-ONLY"}
            </span>
            <button
              type="button"
              aria-label="Close navigation"
              onClick={() => setSidebarOpen(false)}
              className="rounded p-1 text-slate-400 hover:bg-white/10 hover:text-white lg:hidden"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <nav aria-label="Primary Navigation" className="flex-1 space-y-0.5 overflow-y-auto p-3">
          {visibleNavItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-[#0052cc] text-white shadow-sm"
                    : "text-slate-300 hover:bg-white/5 hover:text-white"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {user && (
          <div className="border-t border-white/10 p-3 text-[11px] text-slate-400">
            <div className="truncate font-semibold text-slate-200">{user.full_name || user.email}</div>
            <div className="truncate font-mono text-[10px] text-slate-400">{user.email}</div>
          </div>
        )}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-h-[3.75rem] flex-wrap items-center justify-between gap-3 border-b border-[#e2e8f0] bg-white px-4 py-2 lg:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              aria-label="Toggle navigation"
              onClick={() => setSidebarOpen((v) => !v)}
              className="rounded-md border border-[#e2e8f0] p-1.5 text-[#475569] hover:bg-[#f8fafc] lg:hidden"
            >
              <Menu className="h-4 w-4" />
            </button>
            <h1 className="truncate text-base font-bold tracking-tight text-[#0f172a]">{title}</h1>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {projects.length > 0 && (
              <select
                aria-label="Active Project"
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                className="max-w-[230px] rounded-md border border-[#cbd5e1] bg-white px-2.5 py-1.5 text-xs font-medium text-[#0f172a] focus:border-[#0052cc] focus:outline-none"
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
                {role && (
                  <span
                    data-testid="role-badge"
                    className={`rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-semibold uppercase ${roleBadgeClass}`}
                  >
                    {getRoleLabel(role)}
                  </span>
                )}
                <span className="hidden text-xs font-medium text-[#475569] md:inline">{user.email}</span>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="inline-flex items-center gap-1.5 rounded-md border border-[#e2e8f0] bg-white px-2.5 py-1.5 text-xs font-semibold text-[#334155] transition hover:border-[#cbd5e1] hover:bg-[#f1f5f9]"
                >
                  <LogOut className="h-3.5 w-3.5" /> Logout
                </button>
              </div>
            ) : (
              <Link
                href="/login"
                className="rounded-md bg-[#0052cc] px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-[#003d99]"
              >
                Sign In
              </Link>
            )}
          </div>
        </header>

        <main className="min-w-0 flex-1 p-4 lg:p-6">
          {loading ? (
            <div className="flex items-center justify-center rounded-xl border border-[#e2e8f0] bg-white p-10 text-xs font-medium text-[#64748b]">
              Verifying organization session...
            </div>
          ) : !user ? (
            <div className="rounded-xl border border-[#e2e8f0] bg-white p-6 text-sm text-[#475569]">
              Authentication required. Redirecting to Vortexen Sign In...
            </div>
          ) : !allowedOnRoute ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
              Your organization role (<b>{getRoleLabel(role)}</b>) is scoped exclusively to the Estimator Workspace. Redirecting...
            </div>
          ) : !isAdmin && !capabilities.can_view_estimator_workspace ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
              No active organization membership assigned. Contact your organization administrator.
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}
