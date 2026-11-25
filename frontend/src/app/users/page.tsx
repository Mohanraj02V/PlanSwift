"use client";

import React, { useEffect, useState } from "react";
import { KeyRound, ShieldAlert, UserPlus } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { UserProfile, UserRole } from "@/types/api";

const ROLE_OPTIONS: Array<{ value: UserRole; label: string; hint: string }> = [
  { value: "user", label: "User (Read-Only)", hint: "Read-only access inside Estimator Workspace" },
  { value: "estimator", label: "Estimator", hint: "Upload & extract inside Estimator Workspace (no export/edit)" },
  { value: "admin", label: "Admin", hint: "Full platform access, user admin, estimation & exports" },
];

export default function UsersAdminPage() {
  const { user, organizations, role: currentRole } = useProjectContext();
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  // Create form states
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("user");
  const [orgId, setOrgId] = useState("");
  const [mustChangePw, setMustChangePw] = useState(false);

  // Password reset state
  const [resetTarget, setResetTarget] = useState<UserProfile | null>(null);
  const [resetPasswordVal, setResetPasswordVal] = useState("");

  const loadUsers = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiRequest<{ results: UserProfile[] }>("/auth/users/");
      setUsers(res.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load organization users.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (currentRole === "admin") {
      loadUsers();
    }
  }, [currentRole]);

  useEffect(() => {
    if (!orgId && organizations.length > 0) {
      setOrgId(organizations[0].id);
    }
  }, [organizations, orgId]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");
    if (
      role === "admin" &&
      typeof window !== "undefined" &&
      !window.confirm(`Assign full Organization Admin privileges to '${email.trim()}'?`)
    ) {
      return;
    }

    try {
      const created = await apiRequest<UserProfile>("/auth/users/", {
        method: "POST",
        body: JSON.stringify({
          email: email.trim(),
          password,
          full_name: fullName.trim(),
          job_title: jobTitle.trim(),
          role,
          must_change_password: mustChangePw,
          ...(orgId ? { organization: orgId } : {}),
        }),
      });
      setMessage(`Created user '${created.email}' as ${created.primary_role}.`);
      setEmail("");
      setFullName("");
      setJobTitle("");
      setPassword("");
      setMustChangePw(false);
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user.");
    }
  };

  const handleRoleChange = async (targetUser: UserProfile, newRole: UserRole) => {
    if (newRole === targetUser.primary_role) return;
    if (
      newRole === "admin" &&
      typeof window !== "undefined" &&
      !window.confirm(`Promote '${targetUser.email}' to full Organization Admin?`)
    ) {
      return;
    }
    setError("");
    setMessage("");
    try {
      const targetOrgId = targetUser.memberships?.[0]?.organization_id || orgId;
      await apiRequest(`/auth/users/${targetUser.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ role: newRole, ...(targetOrgId ? { organization: targetOrgId } : {}) }),
      });
      setMessage(`Updated '${targetUser.email}' role to '${newRole}' and revoked old sessions.`);
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update user role.");
    }
  };

  const handleToggleActive = async (targetUser: UserProfile) => {
    const nextState = !targetUser.is_active;
    if (
      !nextState &&
      typeof window !== "undefined" &&
      !window.confirm(`Deactivate '${targetUser.email}' and revoke all active sessions immediately?`)
    ) {
      return;
    }
    setError("");
    setMessage("");
    try {
      await apiRequest(`/auth/users/${targetUser.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: nextState }),
      });
      setMessage(`${nextState ? "Enabled" : "Disabled"} '${targetUser.email}'.`);
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update user status.");
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetTarget) return;
    setError("");
    setMessage("");
    try {
      await apiRequest(`/auth/users/${resetTarget.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ password: resetPasswordVal, must_change_password: true }),
      });
      setMessage(`Password reset for '${resetTarget.email}'. Active sessions revoked.`);
      setResetTarget(null);
      setResetPasswordVal("");
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset password.");
    }
  };

  return (
    <AppShell title="User Management & Three-Role RBAC (Admin)">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <form onSubmit={handleCreateUser} className="space-y-3.5 rounded-xl border border-[#e2e8f0] bg-white p-5">
          <div className="flex items-center gap-2">
            <UserPlus className="h-4 w-4 text-[#0052cc]" />
            <h2 className="text-sm font-bold text-[#0f172a]">Provision Organization User</h2>
          </div>
          <p className="text-xs text-[#64748b]">
            Public self-registration is disabled. Create users directly with <b>Admin</b>, <b>Estimator</b>, or <b>User</b> access.
          </p>

          {error && <div className="rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-700">{error}</div>}
          {message && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-2.5 text-xs text-emerald-800">{message}</div>}

          <div>
            <label className="block text-xs font-semibold text-[#334155]">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@company.com"
              className="mt-1 w-full rounded-lg border border-[#cbd5e1] px-3 py-2 text-sm focus:border-[#0052cc] focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#334155]">Full Name</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Amina Al Mansoori"
              className="mt-1 w-full rounded-lg border border-[#cbd5e1] px-3 py-2 text-sm focus:border-[#0052cc] focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#334155]">Job Title</label>
            <input
              type="text"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="MEP Estimator"
              className="mt-1 w-full rounded-lg border border-[#cbd5e1] px-3 py-2 text-sm focus:border-[#0052cc] focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#334155]">Initial Password (min 10 chars)</label>
            <input
              type="password"
              required
              minLength={10}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Minimum 10 characters"
              className="mt-1 w-full rounded-lg border border-[#cbd5e1] px-3 py-2 text-sm focus:border-[#0052cc] focus:outline-none"
            />
          </div>

          {organizations.length > 0 && (
            <div>
              <label className="block text-xs font-semibold text-[#334155]">Organization</label>
              <select
                value={orgId}
                onChange={(e) => setOrgId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[#cbd5e1] bg-white px-3 py-2 text-sm"
              >
                {organizations.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-[#334155]">Organization Role</label>
            <select
              aria-label="Organization Role"
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
              className="mt-1 w-full rounded-lg border border-[#cbd5e1] bg-white px-3 py-2 text-sm"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[11px] text-[#64748b]">
              {ROLE_OPTIONS.find((r) => r.value === role)?.hint}
            </p>
          </div>

          <label className="flex items-center gap-2 text-xs text-[#334155]">
            <input
              type="checkbox"
              checked={mustChangePw}
              onChange={(e) => setMustChangePw(e.target.checked)}
            />
            Require password change on first sign-in
          </label>

          <button
            type="submit"
            className="w-full rounded-lg bg-[#0052cc] px-4 py-2.5 text-sm font-bold text-white transition hover:bg-[#003d99]"
          >
            Create User Account
          </button>
        </form>

        <div className="space-y-4 rounded-xl border border-[#e2e8f0] bg-white p-5 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-bold text-[#0f172a]">Organization Directory ({users.length})</h2>
              <p className="text-xs text-[#64748b]">
                Changing a role or deactivating an account immediately revokes active JWT sessions.
              </p>
            </div>
            {loading && <span className="text-xs text-[#64748b]">Refreshing...</span>}
          </div>

          {resetTarget && (
            <form
              onSubmit={handleResetPassword}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-[#0052cc]/30 bg-[#eff6ff] p-3 text-xs"
            >
              <KeyRound className="h-4 w-4 text-[#0052cc]" />
              <span className="font-semibold text-[#0f172a]">Reset password for {resetTarget.email}:</span>
              <input
                type="password"
                minLength={10}
                required
                value={resetPasswordVal}
                onChange={(e) => setResetPasswordVal(e.target.value)}
                placeholder="New password (min 10 chars)"
                className="flex-1 rounded border border-[#cbd5e1] bg-white px-2.5 py-1 text-xs"
              />
              <button
                type="submit"
                className="rounded bg-[#0052cc] px-3 py-1 font-semibold text-white hover:bg-[#003d99]"
              >
                Save Reset
              </button>
              <button
                type="button"
                onClick={() => {
                  setResetTarget(null);
                  setResetPasswordVal("");
                }}
                className="rounded border border-[#cbd5e1] bg-white px-2.5 py-1 text-[#475569]"
              >
                Cancel
              </button>
            </form>
          )}

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-[#e2e8f0] text-left text-xs">
              <thead className="bg-[#f8fafc] font-semibold text-[#475569]">
                <tr>
                  <th className="px-3 py-2.5">User</th>
                  <th className="px-3 py-2.5">Organization</th>
                  <th className="px-3 py-2.5">Role</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-3 py-2.5">Last Login</th>
                  <th className="px-3 py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f1f5f9]">
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-[#fafbfd]">
                    <td className="px-3 py-2.5">
                      <div className="font-semibold text-[#0f172a]">{u.full_name || u.email}</div>
                      <div className="font-mono text-[11px] text-[#64748b]">{u.email}</div>
                    </td>
                    <td className="px-3 py-2.5 text-[#475569]">
                      {u.memberships?.[0]?.organization_name || "—"}
                    </td>
                    <td className="px-3 py-2.5">
                      <select
                        aria-label={`Role for ${u.email}`}
                        value={(u.primary_role as UserRole) || "user"}
                        onChange={(e) => handleRoleChange(u, e.target.value as UserRole)}
                        className="rounded-md border border-[#cbd5e1] bg-white px-2 py-1 text-xs font-medium"
                      >
                        {ROLE_OPTIONS.map((r) => (
                          <option key={r.value} value={r.value}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${
                          u.is_active ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
                        }`}
                      >
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 font-mono text-[11px] text-[#64748b]">
                      {u.last_login ? new Date(u.last_login).toLocaleString() : "Never"}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap gap-1.5">
                        <button
                          type="button"
                          onClick={() => {
                            setResetTarget(u);
                            setResetPasswordVal("");
                          }}
                          className="rounded border border-[#cbd5e1] px-2 py-1 text-[11px] font-medium text-[#334155] hover:bg-[#f1f5f9]"
                        >
                          Reset PW
                        </button>
                        {u.id !== user?.id && (
                          <button
                            type="button"
                            onClick={() => handleToggleActive(u)}
                            className="rounded border border-[#cbd5e1] px-2 py-1 text-[11px] font-medium text-[#334155] hover:bg-[#f1f5f9]"
                          >
                            {u.is_active ? "Disable" : "Enable"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center text-[#64748b]">
                      <ShieldAlert className="mx-auto mb-1 h-4 w-4 text-slate-400" />
                      No users found in your organization.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
