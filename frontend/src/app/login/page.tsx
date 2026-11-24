"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { loginSchema, registerSchema } from "@/schemas/auth";
import { apiRequest } from "@/services/api-client/client";
import { setAuthTokens } from "@/services/authentication/auth";
import { useProjectContext } from "@/hooks/useProjectContext";
import type { UserProfile } from "@/types/api";

export default function LoginPage() {
  const router = useRouter();
  const { refreshContext } = useProjectContext();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fullName, setFullName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (mode === "register") {
        const parsed = registerSchema.safeParse({ email, password, full_name: fullName, job_title: jobTitle });
        if (!parsed.success) {
          setError(parsed.error.errors[0]?.message || "Invalid registration details.");
          return;
        }
        await apiRequest("/auth/register/", { method: "POST", body: JSON.stringify(parsed.data) });
      } else {
        const parsed = loginSchema.safeParse({ email, password });
        if (!parsed.success) {
          setError(parsed.error.errors[0]?.message || "Invalid credentials.");
          return;
        }
      }

      const tokens = await apiRequest<{ access: string; refresh: string; user?: UserProfile }>("/auth/login/", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password }),
      });
      setAuthTokens(tokens.access, tokens.refresh);
      await refreshContext();

      if (tokens.user?.primary_role === "estimation_only") {
        router.push("/estimation");
      } else {
        router.push("/dashboard");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-900 p-4">
      <div className="w-full max-w-md rounded-xl border border-slate-800 bg-white p-6 shadow-xl">
        <div className="mb-5 border-b border-slate-100 pb-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-widest text-blue-700">
              VORTEXEN DYNAMICS
            </span>
            <span className="rounded bg-blue-50 px-2 py-0.5 font-mono text-[10px] font-semibold text-blue-700">
              JWT + RBAC
            </span>
          </div>
          <h1 className="mt-1.5 text-xl font-bold text-slate-900">
            {mode === "login" ? "Sign in to Vortexen Estimator" : "Create Estimator Account"}
          </h1>
          <p className="mt-1 text-xs text-slate-500">
            PlanSwift, DXF &amp; IFC digital extraction, deterministic estimation, and audited commercial quotations.
          </p>
        </div>

        <form noValidate onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {error}
            </div>
          )}

          {mode === "register" && (
            <>
              <div>
                <label htmlFor="fullName" className="block text-xs font-medium text-slate-700">
                  Full Name
                </label>
                <input
                  id="fullName"
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                  placeholder="Jane Doe"
                />
              </div>
              <div>
                <label htmlFor="jobTitle" className="block text-xs font-medium text-slate-700">
                  Job Title (Optional)
                </label>
                <input
                  id="jobTitle"
                  type="text"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                  placeholder="Senior MEP Estimator"
                />
              </div>
            </>
          )}

          <div>
            <label htmlFor="email" className="block text-xs font-medium text-slate-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              placeholder="estimator@vortexen.local"
            />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label htmlFor="password" className="block text-xs font-medium text-slate-700">
                Password
              </label>
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="text-[11px] font-medium text-blue-600 hover:underline"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              placeholder="••••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {submitting ? "Authenticating..." : mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>

        <div className="mt-4 text-center text-xs text-slate-600">
          {mode === "login" ? (
            <button type="button" onClick={() => setMode("register")} className="text-blue-600 hover:underline">
              Need an account? Register
            </button>
          ) : (
            <button type="button" onClick={() => setMode("login")} className="text-blue-600 hover:underline">
              Already registered? Sign in
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
