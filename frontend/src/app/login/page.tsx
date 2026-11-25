"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Lock, ShieldCheck } from "lucide-react";
import { VortexenLogo } from "@/components/brand/VortexenLogo";
import { useProjectContext } from "@/hooks/useProjectContext";
import { getDefaultRoute } from "@/lib/rbac";
import { loginSchema } from "@/schemas/auth";
import { apiRequest } from "@/services/api-client/client";
import type { UserProfile } from "@/types/api";

export default function LoginPage() {
  const router = useRouter();
  const { refreshContext } = useProjectContext();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const parsed = loginSchema.safeParse({ email: email.trim(), password });
    if (!parsed.success) {
      setError(parsed.error.errors[0]?.message || "Invalid sign-in credentials.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await apiRequest<{ authenticated: boolean; user?: UserProfile }>("/auth/login/", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password }),
      });
      await refreshContext();
      router.replace(getDefaultRoute(res.user ?? null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid email or password.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col lg:flex-row bg-[#f8fafc]">
      {/* Official Vortexen Brand Showcase Panel */}
      <div className="flex flex-col justify-between bg-[#0b111e] px-8 py-10 text-white lg:w-5/12 lg:px-12 lg:py-14">
        <div>
          <VortexenLogo variant="dark" subtitle="DYNAMICS INDUSTRIAL SOLUTIONS" />
          <div className="mt-10 inline-flex items-center gap-2 rounded-full border border-[#29a9ea]/30 bg-[#0052cc]/20 px-3 py-1 text-[11px] font-semibold tracking-wider text-[#29a9ea] uppercase">
            <ShieldCheck className="h-3.5 w-3.5" />
            Organization-Controlled Access
          </div>
          <h2 className="mt-5 text-3xl font-extrabold tracking-tight text-white lg:text-4xl">
            Engineering Extraction &amp; Estimation Platform
          </h2>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-300">
            Deterministic extraction and quantity verification across PlanSwift packages, DXF drawings, and IFC BIM models — governed by strict tenant isolation and audit logging.
          </p>
        </div>

        <div className="mt-10 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-[#0f172a] p-4">
            <div className="font-mono text-xs font-semibold text-[#29a9ea]">NATIVE ENGINE</div>
            <div className="mt-1 text-xs text-slate-300">
              Standalone XML, ezdxf CAD &amp; IfcOpenShell BIM extraction with zero external CAD licenses.
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-[#0f172a] p-4">
            <div className="font-mono text-xs font-semibold text-[#2684ff]">3-ROLE RBAC</div>
            <div className="mt-1 text-xs text-slate-300">
              Admin, Estimator, and Read-Only User permissions enforced via HttpOnly JWT &amp; CSRF.
            </div>
          </div>
        </div>
      </div>

      {/* Sign-In Panel (Public Registration Strictly Disabled) */}
      <div className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-md rounded-2xl border border-[#e2e8f0] bg-white p-8 shadow-sm">
          <div className="border-b border-[#f1f5f9] pb-5">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[11px] font-semibold uppercase tracking-widest text-[#0052cc]">
                Vortexen Access
              </span>
              <span className="inline-flex items-center gap-1 rounded bg-[#eff6ff] px-2 py-0.5 font-mono text-[10px] font-semibold text-[#0052cc]">
                <Lock className="h-3 w-3" /> HttpOnly + CSRF
              </span>
            </div>
            <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-[#0f172a]">
              Sign in to Estimator
            </h1>
            <p className="mt-1 text-xs text-[#64748b]">
              Use the organization credentials provisioned by your Vortexen Administrator.
            </p>
          </div>

          <form noValidate onSubmit={handleSubmit} className="mt-6 space-y-5">
            {error && (
              <div
                role="alert"
                className="rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs font-medium text-rose-700"
              >
                {error}
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-xs font-semibold text-[#334155]">
                Work Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                className="mt-1.5 w-full rounded-lg border border-[#cbd5e1] bg-white px-3.5 py-2.5 text-sm text-[#0f172a] placeholder:text-slate-400 focus:border-[#0052cc] focus:outline-none focus:ring-2 focus:ring-[#0052cc]/15"
              />
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label htmlFor="password" className="block text-xs font-semibold text-[#334155]">
                  Password
                </label>
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#0052cc] hover:text-[#003d99]"
                >
                  {showPassword ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="mt-1.5 w-full rounded-lg border border-[#cbd5e1] bg-white px-3.5 py-2.5 text-sm text-[#0f172a] placeholder:text-slate-400 focus:border-[#0052cc] focus:outline-none focus:ring-2 focus:ring-[#0052cc]/15"
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-[#0052cc] px-4 py-2.5 text-sm font-bold text-white shadow-sm transition hover:bg-[#003d99] disabled:opacity-50"
            >
              {submitting ? "Authenticating..." : "Sign In"}
            </button>
          </form>

          <p className="mt-6 border-t border-[#f1f5f9] pt-4 text-center text-[11px] text-[#64748b]">
            Self-registration is disabled. Contact your organization Administrator for account provisioning or password resets.
          </p>
        </div>
      </div>
    </div>
  );
}
