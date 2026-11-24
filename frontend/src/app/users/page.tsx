"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { UserProfile } from "@/types/api";

const ROLE_OPTIONS = [
  { value: "estimation_only", label: "Estimation User (Estimation Page Only)" },
  { value: "estimator", label: "Estimator (Full Takeoff & CAD/BIM)" },
  { value: "reviewer", label: "Reviewer" },
  { value: "viewer", label: "Viewer (Read-Only)" },
  { value: "admin", label: "Admin (User & Org Management)" },
  { value: "owner", label: "Owner" },
];

export default function UsersAdminPage() {
  const { user, organizations } = useProjectContext();
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  // Form states
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("estimation_only");
  const [orgId, setOrgId] = useState("");

  const loadUsers = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiRequest<{ results: UserProfile[] }>("/auth/users/");
      setUsers(res.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user?.is_admin) {
      loadUsers();
    }
  }, [user?.is_admin]);

  useEffect(() => {
    if (!orgId && organizations.length > 0) {
      setOrgId(organizations[0].id);
    }
  }, [organizations, orgId]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      const created = await apiRequest<UserProfile>("/auth/users/", {
        method: "POST",
        body: JSON.stringify({
          email: email.trim(),
          password,
          full_name: fullName.trim(),
          job_title: jobTitle.trim(),
          role,
          ...(orgId ? { organization: orgId } : {}),
        }),
      });
      setMessage(`Created user '${created.email}' with role '${created.primary_role}'.`);
      setEmail("");
      setFullName("");
      setJobTitle("");
      setPassword("");
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user.");
    }
  };

  const handleRoleChange = async (targetUser: UserProfile, newRole: string) => {
    setError("");
    setMessage("");
    try {
      const targetOrgId = targetUser.memberships?.[0]?.organization_id || orgId;
      await apiRequest(`/auth/users/${targetUser.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ role: newRole, ...(targetOrgId ? { organization: targetOrgId } : {}) }),
      });
      setMessage(`Updated '${targetUser.email}' role to '${newRole}'.`);
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update user role.");
    }
  };

  const handleToggleActive = async (targetUser: UserProfile) => {
    setError("");
    setMessage("");
    try {
      await apiRequest(`/auth/users/${targetUser.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !targetUser.is_active }),
      });
      setMessage(`${targetUser.is_active ? "Disabled" : "Enabled"} '${targetUser.email}'.`);
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status.");
    }
  };

  if (user && !user.is_admin) {
    return (
      <AppShell title="User Management (Admin)">
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
          Admin or Owner privileges are required to manage user accounts.
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title="User Management & Role Access (Admin)">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <form onSubmit={handleCreateUser} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-900">Create New User</h2>
          <p className="text-xs text-slate-500">
            Assign <b>Estimation User</b> to restrict a user exclusively to the Estimation &amp; Quotation page.
          </p>
          {error && <div className="rounded bg-rose-50 p-2 text-xs text-rose-700">{error}</div>}
          {message && <div className="rounded bg-emerald-50 p-2 text-xs text-emerald-800">{message}</div>}

          <div>
            <label className="block text-xs font-medium text-slate-700">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="estimation.user@vortexen.local"
              className="mt-1 w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700">Full Name</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Sales Estimator"
              className="mt-1 w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700">Job Title</label>
            <input
              type="text"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="Estimation Engineer"
              className="mt-1 w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700">Initial Password (min 10 chars)</label>
            <input
              type="password"
              required
              minLength={10}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 10 characters"
              className="mt-1 w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>

          {organizations.length > 0 && (
            <div>
              <label className="block text-xs font-medium text-slate-700">Organization</label>
              <select
                value={orgId}
                onChange={(e) => setOrgId(e.target.value)}
                className="mt-1 w-full rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
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
            <label className="block text-xs font-medium text-slate-700">Access Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="mt-1 w-full rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          <button type="submit" className="w-full rounded bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700">
            Create User Account
          </button>
        </form>

        <div className="rounded-lg border border-slate-200 bg-white p-4 lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Organization Users ({users.length})</h2>
            {loading && <span className="text-xs text-slate-500">Refreshing...</span>}
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 font-semibold text-slate-600">
                <tr>
                  <th className="px-3 py-2">User</th>
                  <th className="px-3 py-2">Organization</th>
                  <th className="px-3 py-2">Role</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Last Login</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.map((u) => (
                  <tr key={u.id}>
                    <td className="px-3 py-2">
                      <div className="font-semibold text-slate-900">{u.full_name || u.email}</div>
                      <div className="font-mono text-[11px] text-slate-500">{u.email}</div>
                    </td>
                    <td className="px-3 py-2 text-slate-600">
                      {u.memberships?.[0]?.organization_name || "—"}
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={u.primary_role || "viewer"}
                        onChange={(e) => handleRoleChange(u, e.target.value)}
                        className="rounded border border-slate-300 bg-white px-2 py-1 text-xs font-medium"
                      >
                        {ROLE_OPTIONS.map((r) => (
                          <option key={r.value} value={r.value}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                          u.is_active ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
                        }`}
                      >
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-500">
                      {u.last_login ? new Date(u.last_login).toLocaleString() : "Never"}
                    </td>
                    <td className="px-3 py-2">
                      {u.id !== user?.id && (
                        <button
                          type="button"
                          onClick={() => handleToggleActive(u)}
                          className="rounded border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                        >
                          {u.is_active ? "Disable" : "Enable"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
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
